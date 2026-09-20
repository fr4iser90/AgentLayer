#!/usr/bin/env python3
"""Validate the friend/sharing fixture through the real code paths.

Runs the actual DB-layer and domain functions against the rows written by
scripts/seed_friend_sharing_fixture.sql, so the ADR 0014 findings are observed
rather than asserted from reading.

Run inside the app container (the repo is mounted read-only at /code):

    docker compose run --rm -e PYTHONPATH=/code agent-layer \
        python /code/scripts/validate_friend_sharing_fixture.py

Exit 0 = every check behaved as expected.
"""

from __future__ import annotations

import sys
import uuid

import psycopg.rows

from apps.backend.domain.collections.access import access_for_slug
from apps.backend.domain.shares.collection_grant import friend_collection_permission
from apps.backend.domain.shares.dashboard_grant import friend_dashboard_access_detail
from apps.backend.domain.shares.policy import grant_is_active
from apps.backend.infrastructure.db import db as appdb
from apps.backend.infrastructure.db import friends_db as fdb
from apps.backend.infrastructure.db.share_permissions_db import (
    share_permission_check_resolved,
    share_permission_get,
)

# The domain grant modules take their DB access by injected module-global. The
# infrastructure services register themselves at import; without these the
# adapters silently see no rows.
import apps.backend.infrastructure.collections.collection_share_service  # noqa: F401,E402
import apps.backend.infrastructure.collections.collections_db_service  # noqa: F401,E402
import apps.backend.infrastructure.dashboards.dashboard_grant_service  # noqa: F401,E402

appdb.init_pool()

ANNA = uuid.UUID("a1111111-1111-4111-8111-111111111111")
TIM = uuid.UUID("a2222222-2222-4222-8222-222222222222")
LENA = uuid.UUID("a3333333-3333-4333-8333-333333333333")
BOB = uuid.UUID("a4444444-4444-4444-8444-444444444444")

ANNA_DASHBOARD = uuid.UUID("b1111111-1111-4111-8111-111111111111")
TIM_DASHBOARD = uuid.UUID("b2222222-2222-4222-8222-222222222222")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def raw_grant(owner: uuid.UUID, grantee: uuid.UUID, rtype: str, ident: str) -> dict | None:
    """Bypass the getter's own filtering and read the stored row."""
    with appdb.pool().connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT is_allowed, revoked_at, policy FROM share_permissions "
                "WHERE owner_user_id=%s AND grantee_user_id=%s AND resource_type=%s "
                "AND resource_identifier=%s",
                (owner, grantee, rtype, ident),
            )
            return cur.fetchone()


# ── friendship ────────────────────────────────────────────────────────────────

# The precedence case fixed in 3c6687c. bob->anna is DECLINED while anna->bob is
# PENDING. Called with BOB first, the pre-fix SQL
#   (A) OR (B) AND status='pending'  ->  (A) OR (B AND status)
# let clause A match the declined row and return it as if it were pending.
between = fdb.friend_request_get_between(BOB, ANNA)
check(
    "get_between(BOB, ANNA) returns the PENDING row, not the declined one",
    between is not None and between["status"] == "pending" and between["from_user_id"] == ANNA,
    f"status={between['status']} from={between['from_user_id']}" if between else "None",
)

incoming = fdb.friend_requests_incoming(ANNA)
check("incoming(ANNA) lists tim's pending request",
      any(r["from_user_id"] == TIM for r in incoming), f"{len(incoming)} row(s)")
check("incoming(ANNA) does not list bob's declined request",
      not any(r["from_user_id"] == BOB for r in incoming), f"{len(incoming)} row(s)")

outgoing = fdb.friend_requests_outgoing(ANNA)
check("outgoing(ANNA) lists the pending request to bob",
      any(r["to_user_id"] == BOB for r in outgoing), f"{len(outgoing)} row(s)")

friends_of_anna = {r.get("friend_user_id") or r.get("id") for r in fdb.friends_list(ANNA)}
check("friends_list(ANNA) contains lena", LENA in friends_of_anna, str(friends_of_anna))
check("friends_list(ANNA) does not contain bob", BOB not in friends_of_anna, str(friends_of_anna))

# ── the two enforced types ────────────────────────────────────────────────────

dash = friend_dashboard_access_detail(LENA, ANNA_DASHBOARD)
check("dashboard grant resolves to editor",
      dash is not None and dash.role == "editor", f"{dash}")
check("dashboard grant carries the block_ids restriction",
      dash is not None and dash.allowed_block_ids == frozenset({"block-shifts", "block-coverage"}),
      f"{dash.allowed_block_ids if dash else None}")
check("dashboard grant is writable (policy permission=edit)",
      dash is not None and dash.granular_can_write is True, f"{dash}")

col = access_for_slug(LENA, "haustiere", owner_user_id=ANNA)
check("collection access_for_slug(LENA, 'haustiere', owner=ANNA) is granted",
      col is not None and col.role in ("viewer", "editor"), f"{col}")
check("collection grant is read-only (policy permission=view)",
      col is not None and col.can_write is False, f"{col}")

# The adapter with no production caller (ADR 0014 §1.3). It works — nothing uses
# it; access.py re-implements the same check inline.
dead = friend_collection_permission(LENA, ANNA, "haustiere")
check("collection_grant.friend_collection_permission works but has no caller",
      dead is not None, "adapter functional; the live path is access.py's inline copy")

# ── grant lifecycle ───────────────────────────────────────────────────────────

# share_permission_get filters revoked_at IS NULL AND is_allowed = TRUE itself and
# then applies grant_is_active, so a revoked row is invisible to callers rather
# than returned-and-flagged. Verified against the stored row to show the
# distinction.
revoked_row = raw_grant(TIM, ANNA, "google_calendar", "primary")
check("revoked row is stored with is_allowed=TRUE + revoked_at set",
      revoked_row is not None and revoked_row["is_allowed"] is True
      and revoked_row["revoked_at"] is not None,
      f"is_allowed={revoked_row['is_allowed'] if revoked_row else None}")
check("share_permission_get hides the revoked row (getter filters, not flags)",
      share_permission_get(owner_user_id=TIM, grantee_user_id=ANNA,
                          resource_type="google_calendar",
                          resource_identifier="primary") is None, "")
check("grant_is_active denies the revoked grant",
      revoked_row is not None and not grant_is_active(
          is_allowed=bool(revoked_row["is_allowed"]),
          revoked_at=revoked_row["revoked_at"],
          policy=revoked_row.get("policy") or {}), "")

expired_row = raw_grant(TIM, ANNA, "dashboard", str(TIM_DASHBOARD))
check("expired row is stored with a past expires_at",
      expired_row is not None and "expires_at" in (expired_row.get("policy") or {}),
      f"policy={expired_row.get('policy') if expired_row else None}")
check("grant_is_active denies the expired grant",
      expired_row is not None and not grant_is_active(
          is_allowed=bool(expired_row["is_allowed"]),
          revoked_at=expired_row["revoked_at"],
          policy=expired_row.get("policy") or {}), "")

# ── the findings ADR 0014 is about ────────────────────────────────────────────

# Inert types: the grant resolves as active. A reader that trusts a truthy grant
# would believe access exists. Nothing behind it enforces anything.
for inert in ("github_activity", "todoist", "notes", "roadmap"):
    g = share_permission_get(owner_user_id=ANNA, grantee_user_id=LENA,
                            resource_type=inert, resource_identifier="primary")
    check(f"INERT type '{inert}' resolves as a live grant (no reader behind it)",
          g is not None, "truthy grant — this is what makes it look like access")

# Legacy alias: stored as 'haustiere', queried as canonical 'collection'.
check("legacy alias row ('haustiere') resolves when queried as 'collection'",
      share_permission_check_resolved(owner_user_id=ANNA, grantee_user_id=LENA,
                                    resource_type="collection",
                                    resource_identifier="dienstreisen") is True, "")

# Policy imprecision (§1.9): block_ids accepted on a calendar grant.
imprecise = share_permission_get(owner_user_id=ANNA, grantee_user_id=TIM,
                                resource_type="google_calendar",
                                resource_identifier="primary")
check("block_ids was accepted onto a google_calendar grant (§1.9 consent bug)",
      imprecise is not None and "block_ids" in (imprecise.get("policy") or {}),
      f"policy={imprecise.get('policy') if imprecise else None}")

# Grant without friendship: anna granted to bob, who is not her friend.
check("grant exists and resolves for a NON-friend (grant layer ignores friendship)",
      share_permission_get(owner_user_id=ANNA, grantee_user_id=BOB,
                          resource_type="google_calendar",
                          resource_identifier="primary") is not None,
      "no friendship check in the grant layer")

# Unregistered type: nothing refuses it at write or read time.
check("unregistered type 'payroll_export' is grantable and readable",
      share_permission_get(owner_user_id=ANNA, grantee_user_id=LENA,
                          resource_type="payroll_export",
                          resource_identifier="primary") is not None,
      "a registry (ADR 0014 option A) must refuse this; today nothing does")

# ── the shared-calendar adapter (ADR 0014 Principle 1) ────────────────────────
# Everything below runs for real except the network: the secret is written with
# the real encrypting upsert, read back through the real decrypting getter,
# resolved by the adapter and guarded. Only httpx.Client is stood in for, so the
# check does not depend on outbound internet.

import json  # noqa: E402

import httpx  # noqa: E402

from plugins.tools.personal.calendar import ics  # noqa: E402

LENA_ICS = "https://calendar.example.org/ical/lena/basic.ics"


def _ics_doc(*summaries: str) -> bytes:
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc) + timedelta(hours=2)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//agentlayer//fixture//EN"]
    for i, s in enumerate(summaries):
        st = base + timedelta(days=i)
        lines += [
            "BEGIN:VEVENT",
            f"UID:fixture-{i}@agentlayer.test",
            f"SUMMARY:{s}",
            "DTSTART:" + st.strftime("%Y%m%dT%H%M%SZ"),
            "DTEND:" + (st + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ"),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode()


class _Resp:
    def __init__(self, status_code=200, location=None, content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR"):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", "replace")
        self.headers = {} if location is None else {"location": location}


class _NoNetClient:
    def __init__(self):
        self.requested: list[str] = []

    def get(self, url, headers=None):
        self.requested.append(url)
        return _Resp(200, content=_ics_doc("Schicht 12:00", "Zahnarzt"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _with_stubbed_network(fn):
    client = _NoNetClient()
    real = httpx.Client
    httpx.Client = lambda *a, **k: client  # type: ignore[assignment]
    try:
        out = fn()
    finally:
        httpx.Client = real  # type: ignore[misc]
    return out, client


# Write a real, encrypted calendar secret for Lena and read her calendar the way
# a grantee's tool call does.
appdb.user_secret_upsert(LENA, "google_calendar", json.dumps({"ics_url": LENA_ICS}))

seen_reads: list[tuple[str, str]] = []
_real_get = appdb.user_secret_get_plaintext


def _spy_get(uid, service_key):
    seen_reads.append((str(uid), service_key))
    return _real_get(uid, service_key)


appdb.user_secret_get_plaintext = _spy_get
try:
    res, client = _with_stubbed_network(
        lambda: ics.fetch_shared_calendar(LENA, days_ahead=7)
    )
finally:
    appdb.user_secret_get_plaintext = _real_get

check("shared calendar resolves the owner's ENCRYPTED secret and parses events",
      res.get("ok") is True and res.get("count") == 2,
      f"count={res.get('count')} events={[e['summary'] for e in res.get('events', [])]}")

def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


_CREDENTIAL_KEYS = {"ics_url", "url", "secret", "token", "ciphertext", "api_key"}

check("the bearer URL is nowhere in what the grantee receives",
      LENA_ICS not in json.dumps(res)
      and not [k for k in _all_keys(res) if k.lower() in _CREDENTIAL_KEYS],
      f"keys={sorted(set(_all_keys(res)))}")

check("the secret was read for the OWNER (Lena), never the caller",
      bool(seen_reads) and all(u == str(LENA) for u, _ in seen_reads),
      f"reads={seen_reads}")

appdb.user_secret_upsert(
    LENA, "google_calendar",
    json.dumps({"ics_url": "http://169.254.169.254/latest/meta-data/"}),
)
blocked, client2 = _with_stubbed_network(
    lambda: ics.fetch_shared_calendar(LENA, days_ahead=7)
)
check("the guard still runs on the shared path (internal owner URL refused)",
      blocked.get("ok") is False and "blocked_ssrf" in str(blocked.get("error")),
      f"error={blocked.get('error')} requested={client2.requested}")

check("an owner with no calendar secret is reported, not silently empty",
      ics.fetch_shared_calendar(BOB, days_ahead=7).get("error")
      == "owner_has_no_calendar_configured",
      "bob has no secret stored")

# The grant layer and the adapter are separate: Tim's grant on Anna's calendar
# must resolve the secret of ANNA, the owner.
tim_grant = share_permission_get(owner_user_id=ANNA, grantee_user_id=TIM,
                                resource_type="google_calendar",
                                resource_identifier="primary")
appdb.user_secret_upsert(ANNA, "google_calendar", json.dumps({"ics_url": LENA_ICS}))
seen_owner_reads: list[str] = []


def _spy_owner(uid, service_key):
    seen_owner_reads.append(str(uid))
    return _real_get(uid, service_key)


appdb.user_secret_get_plaintext = _spy_owner
try:
    _owner_res, _ = _with_stubbed_network(
        lambda: ics.fetch_shared_calendar(ANNA, days_ahead=7)
    )
finally:
    appdb.user_secret_get_plaintext = _real_get

check("reading via Tim's grant touches ANNA's secret (owner, not grantee)",
      tim_grant is not None and seen_owner_reads
      and all(u == str(ANNA) for u in seen_owner_reads),
      f"reads={seen_owner_reads}")

# Leave the fixture as the seed SQL wrote it.
with appdb.pool().connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_secrets WHERE user_id IN (%s, %s)", (LENA, ANNA)
        )
    conn.commit()
check("fixture secrets cleaned up",
      appdb.user_secret_get_plaintext(LENA, "google_calendar") is None
      and appdb.user_secret_get_plaintext(ANNA, "google_calendar") is None,
      "user_secrets rows for Lena/Anna removed")


# ── the adapter registry (ADR 0014 steps 1–2) ────────────────────────────────
# Step 2 says "wrap the two working adapters without changing their
# behaviour". The only proof of that is comparing the registry's answer to
# the direct call on the same rows.

from apps.backend.domain.shares import collection_grant as _cg  # noqa: E402
from apps.backend.domain.shares import dashboard_grant as _dg  # noqa: E402
from apps.backend.domain.shares import registry as reg  # noqa: E402
from apps.backend.domain.shares.adapter import find_credential_keys  # noqa: E402
from apps.backend.infrastructure.shares import share_registry_service  # noqa: F401,E402


def _conflict_refused() -> bool:
    """Binding 'dashboard' to a second adapter must raise, not override."""

    class _Usurper:
        resource_types = ("dashboard",)
        policy_fields = frozenset()

        def normalize_identifier(self, raw):
            return raw

        def resolve(self, **kw):
            return {"role": "editor"}

        def list_shared(self, g):
            return []

    try:
        reg.register_share_adapter(_Usurper())
    except reg.ShareRegistryError:
        return True
    return False

check("registry has the shipped types bound",
      reg.registered_resource_types()
      == ("calendar", "collection", "dashboard", "google_calendar"),
      f"registered={reg.registered_resource_types()}")

direct_dash = _dg.friend_dashboard_access_detail(LENA, ANNA_DASHBOARD)
via_reg = reg.resolve_projection(
    resource_type="dashboard",
    owner_user_id=ANNA,
    grantee_user_id=LENA,
    identifier=str(ANNA_DASHBOARD),
)
check("registry dashboard resolve == direct adapter call (behaviour preserved)",
      via_reg.served and via_reg.projection == direct_dash,
      f"direct={direct_dash} via_registry={via_reg.projection}")

direct_col = _cg.friend_collection_permission(LENA, ANNA, "haustiere")
via_reg_col = reg.resolve_projection(
    resource_type="collection",
    owner_user_id=ANNA,
    grantee_user_id=LENA,
    identifier="haustiere",
)
check("registry collection resolve == direct adapter call (behaviour preserved)",
      via_reg_col.served and via_reg_col.projection == direct_col,
      f"direct={direct_col} via_registry={via_reg_col.projection}")

# The inert types are grantable and readable-as-granted, but the registry
# refuses them: no adapter means no read. This is the pre-registry "a grant
# looked like access" failure mode, closed.
inert_refusals = {}
for t in ("github_activity", "todoist", "notes", "roadmap"):
    out = reg.resolve_projection(
        resource_type=t, owner_user_id=ANNA, grantee_user_id=LENA, identifier="primary"
    )
    inert_refusals[t] = (out.served, out.refusal)
check("all four inert types are refused by the registry (grantable, not readable)",
      all(served is False and r == "no_adapter_registered"
          for served, r in inert_refusals.values()),
      f"{inert_refusals}")

# Step 4 replaced the "two parallel truths" with one: google_calendar is now
# registry-backed, so the generic read path enforces the same grant the
# bespoke tool did. The secrets are cleared by the time we get here, so the
# adapter serves its not-configured result rather than the credential-less
# empty read it would return against a connected owner.
cal_out = reg.resolve_projection(
    resource_type="google_calendar",
    owner_user_id=ANNA,
    grantee_user_id=TIM,
    identifier="primary",
)
check("google_calendar IS registry-backed now (step 4) — no longer refused as unknown",
      cal_out.refusal != "no_adapter_registered",
      f"refusal={cal_out.refusal} adapter={type(cal_out.adapter).__name__ if cal_out.adapter else None}")
check("the legacy 'calendar' alias binds the same adapter instance as google_calendar",
      reg.get_share_adapter("calendar") is reg.get_share_adapter("google_calendar"),
      "a grant under either name must be enforced by one adapter, not two")
check("the calendar adapter declares only the fields its read acts on",
      reg.policy_fields_for("google_calendar") == frozenset({"days_ahead", "expires_at"}),
      f"fields={reg.policy_fields_for('google_calendar')}")

check("real fixture projections pass the Principle 1 gate",
      find_credential_keys(direct_dash) == [] and find_credential_keys(direct_col) == [],
      f"dash_leaks={find_credential_keys(direct_dash)} col_leaks={find_credential_keys(direct_col)}")

check("registry refuses a conflicting adapter rather than silently overriding",
      _conflict_refused(),
      "binding 'dashboard' to a second adapter raises")


# ── per-type policy field enforcement (ADR 0014 step 3, §1.9) ────────────────
from apps.backend.domain.shares.policy import normalize_policy  # noqa: E402

col_rej = normalize_policy("collection", {"block_ids": ["x"]})
check("step 3: block_ids now REJECTED on a collection grant",
      col_rej[0] == {} and col_rej[1] is not None,
      f"err={col_rej[1]}")

dash_ok = normalize_policy("dashboard", {"block_ids": ["block-shifts"]})
check("step 3: block_ids still ACCEPTED on a dashboard (it reads them)",
      dash_ok[1] is None and dash_ok[0].get("block_ids") == ["block-shifts"],
      f"clean={dash_ok[0]}")

dash_rej = normalize_policy("dashboard", {"list_keys": ["x"]})
check("step 3: list_keys REJECTED on a dashboard (nothing reads it)",
      dash_rej[1] is not None, f"err={dash_rej[1]}")

lk_rej = normalize_policy("collection", {"permission": "edit", "list_keys": ["pets"]})
check("step 3: list_keys REJECTED on a collection — the §1.9 case this found",
      lk_rej[0] == {} and lk_rej[1] is not None,
      f"err={lk_rej[1]}")

cal_gap = normalize_policy("google_calendar", {"block_ids": ["x"]})
check("step 4 CLOSED the §1.9 consent bug: block_ids now REJECTED on a calendar grant",
      cal_gap[1] is not None,
      f"err={cal_gap[1]}")

cal_alias_gap = normalize_policy("calendar", {"list_keys": ["x"]})
check("the legacy 'calendar' alias is held to the same set (no way around it)",
      cal_alias_gap[1] is not None,
      f"err={cal_alias_gap[1]}")

notes_open = normalize_policy("notes", {"block_ids": ["x"]})
check("unregistered type keeps the open write side (§1.4)",
      notes_open[1] is None and notes_open[0] == {"block_ids": ["x"]},
      f"clean={notes_open[0]}")

truly_bad = normalize_policy("notes", {"bogus_key": 1})
check("a field nobody knows is still refused on an unregistered type",
      truly_bad[1] is not None and "unknown policy field" in truly_bad[1],
      f"err={truly_bad[1]}")

check("app wiring is live in this container (registry populated)",
      reg.registered_resource_types()
      == ("calendar", "collection", "dashboard", "google_calendar")
      and reg.policy_fields_for("collection") is not None,
      f"fields(collection)={reg.policy_fields_for('collection')}")


# ── registry-driven catalog + agent help (ADR 0014 step 5) ────────────────────
from apps.backend.domain.shares.catalog import catalog_for_api  # noqa: E402

cat = catalog_for_api()
check("step 5: catalog_for_api() returns the registry, not the old [] stub",
      [c["id"] for c in cat] == ["collection", "dashboard", "google_calendar"],
      f"ids={[c['id'] for c in cat]}")
check("step 5: catalog carries the per-type policy fields the UI renders",
      {c["id"]: c["policy_fields"] for c in cat} == {
          "collection": ["expires_at", "permission"],
          "dashboard": ["block_ids", "expires_at", "permission"],
          "google_calendar": ["days_ahead", "expires_at"],
      },
      "policy_fields per type as declared by the adapters")
check("step 5: default_identifier comes from the adapter (calendar only)",
      {c["id"]: c["default_identifier"] for c in cat} == {
          "collection": None,
          "dashboard": None,
          "google_calendar": "primary",
      },
      f"defaults={ {c['id']: c['default_identifier'] for c in cat} }")
check("step 5: catalog lists canonical ids only, aliases are metadata",
      all(c["id"] != "calendar" for c in cat)
      and next(c for c in cat if c["id"] == "google_calendar")["aliases"] == ["calendar"],
      f"aliases(google_calendar)="
      f"{next(c for c in cat if c['id'] == 'google_calendar')['aliases']}")

# The agent-facing help must match what the grant path enforces, live.
from plugins.tools.integrations.friends.shares import TOOLS as SHARES_TOOLS  # noqa: E402

_help = SHARES_TOOLS[0]["function"]["TOOL_DESCRIPTION"]
check("step 5: the agent help no longer advertises the flat field list",
      "list_keys" not in _help,
      "list_keys is read by nothing and must not be offered")
check("step 5: the agent help names the readable types canonically",
      "Readable here: collection, dashboard, google_calendar." in _help,
      f"help excerpt={_help[_help.find('Readable here'):][:80]!r}")
_advert_ok = True
for _c in cat:
    _start = _help.find(f"{_c['id']} accepts {{")
    _advert_ok = _advert_ok and _start != -1
    if _start != -1:
        _inner = _help[_start + len(_c["id"]) + len(" accepts {"):_help.index("}", _start)]
        _advertised = sorted(x.strip() for x in _inner.split(",") if x.strip())
        _advert_ok = _advert_ok and _advertised == _c["policy_fields"]
check("step 5: every advertised per-type field set equals the enforced set",
      _advert_ok,
      "the text an agent reads must match normalize_policy")


# ── projections: publish, shape, cascade (ADR 0014 step 6) ───────────────────
from datetime import datetime, timedelta, timezone  # noqa: E402

from apps.backend.domain.shares import projections as proj  # noqa: E402
from apps.backend.domain.shares.registry import publish_projection  # noqa: E402
from apps.backend.infrastructure.db import share_projections_db as prdb  # noqa: E402
from apps.backend.infrastructure.db.share_permissions_db import (  # noqa: E402
    share_permission_set,
)

appdb.query("DELETE FROM share_projections")
appdb.user_secret_upsert(LENA, "google_calendar", json.dumps({"ics_url": LENA_ICS}))

pub_events, _ = _with_stubbed_network(lambda: publish_projection(
    resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="events"))

check("step 6: the owner can publish a projection of their own resource",
      pub_events.served and pub_events.projection.kind == "events",
      f"refusal={pub_events.refusal}")

_row = prdb.projection_get(
    owner_user_id=LENA, resource_type="google_calendar", resource_identifier="primary"
)
check("step 6: the published row is keyed on the OWNER, not the reader",
      _row is not None and str(_row["owner_user_id"]) == str(LENA)
      and _row["projection_kind"] == "events",
      f"kind={_row and _row['projection_kind']}")
check("step 6: no credential is at rest in the projection table",
      _row is not None and LENA_ICS not in json.dumps(_row["payload"])
      and find_credential_keys(_row["payload"]) == [],
      f"leaks={find_credential_keys(_row['payload']) if _row else 'no row'}")
check("step 6: the freshness bound is in the future, not null",
      _row is not None and _row["expires_at"] is not None
      and _row["expires_at"] > datetime.now(timezone.utc),
      f"expires={_row and _row['expires_at']}")

pub_avail, _ = _with_stubbed_network(lambda: publish_projection(
    resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="availability"))
_avail_row = prdb.projection_get(
    owner_user_id=LENA, resource_type="google_calendar", resource_identifier="primary"
)
_avail_events = (_avail_row or {}).get("payload", {}).get("events", [])
check("step 6: the availability shape stores no event titles",
      pub_avail.served and _avail_row["projection_kind"] == "availability"
      and all("summary" not in e for e in _avail_events) and len(_avail_events) == 2,
      f"events={_avail_events}")

bad = publish_projection(
    resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="everything")
check("step 6: an unknown projection shape is refused",
      not bad.served and bad.refusal == "unknown_projection_kind",
      f"refusal={bad.refusal}")

live = publish_projection(
    resource_type="dashboard", owner_user_id=LENA, identifier="dash-1")
check("step 6: a live-read type refuses to publish rather than pretend",
      not live.served and live.refusal == "not_projection_backed",
      f"refusal={live.refusal}")

none = publish_projection(
    resource_type="payroll_export", owner_user_id=LENA, identifier="primary")
check("step 6: an unregistered type cannot publish",
      not none.served and none.refusal == "no_adapter_registered",
      f"refusal={none.refusal}")

# Revoke cascade: the projection is shared by shape, so one revoke must not
# blind the other grantee; only the last one may take the row with it.
share_permission_set(LENA, TIM, "google_calendar", "primary", True, policy={"days_ahead": 7})
share_permission_set(LENA, BOB, "google_calendar", "primary", True, policy={"days_ahead": 3})
_with_stubbed_network(lambda: publish_projection(
        resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="events"))
share_permission_set(LENA, TIM, "google_calendar", "primary", False)
check("step 6: revoking one grantee keeps the projection the other can still read",
      prdb.projection_get(
          owner_user_id=LENA, resource_type="google_calendar",
          resource_identifier="primary") is not None,
      "BOB still holds a grant")
share_permission_set(LENA, BOB, "google_calendar", "primary", False)
check("step 6: the last revoke takes the projection with it",
      prdb.projection_get(
          owner_user_id=LENA, resource_type="google_calendar",
          resource_identifier="primary") is None,
      "no live grant remains for that resource")

# A row past its bound must be collectable, and must not read as fresh.
_with_stubbed_network(lambda: publish_projection(
        resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="events"))
appdb.query(
    "UPDATE share_projections SET expires_at = %s WHERE owner_user_id = %s",
    (datetime.now(timezone.utc) - timedelta(hours=1), LENA),
)
_stale = proj.load_projection(
    owner_user_id=LENA, resource_type="google_calendar", resource_identifier="primary"
)
check("step 6: an aged row reads as not fresh",
      _stale is not None and not _stale.is_fresh(),
      f"expires={_stale and _stale.expires_at}")
check("step 6: the sweeper collects expired rows",
      proj.sweep_expired() >= 1
      and prdb.projection_get(
          owner_user_id=LENA, resource_type="google_calendar",
          resource_identifier="primary") is None,
      "expired row removed")

cal_entry = next(c for c in catalog_for_api() if c["id"] == "google_calendar")
dash_entry = next(c for c in catalog_for_api() if c["id"] == "dashboard")
check("step 6: the catalog tells the UI which types have a shape to choose",
      cal_entry["projection_kinds"] == ["events", "availability"]
      and dash_entry["projection_kinds"] == [],
      f"calendar={cal_entry['projection_kinds']} dashboard={dash_entry['projection_kinds']}")
check("step 6: the agent help names the publishable shapes",
      "Publishable shapes" in _help and "availability" in _help,
      f"excerpt={_help[_help.find('Publishable shapes'):][:90]!r}")


# ── scheduled refresh (ADR 0014 step 7) ──────────────────────────────────────
# The due-list query is real SQL over a real table. Nothing in the unit suite
# can reach it, because the unit store is a dict.

def _set_expiry(user_id, seconds):
    appdb.query(
        "UPDATE share_projections SET expires_at = now() + make_interval(secs => %s) "
        "WHERE owner_user_id = %s",
        (seconds, user_id),
    )


def _row_for(user_id):
    return prdb.projection_get(
        owner_user_id=user_id, resource_type="google_calendar", resource_identifier="primary"
    )


appdb.user_secret_upsert(ANNA, "google_calendar", json.dumps({"ics_url": LENA_ICS}))
_with_stubbed_network(lambda: publish_projection(
    resource_type="google_calendar", owner_user_id=ANNA,
    identifier="primary", kind="events"))
_with_stubbed_network(lambda: publish_projection(
    resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="events"))
# Lena is about to expire; Anna is nowhere near it.
_set_expiry(LENA, 120)
_set_expiry(ANNA, 900)
_annna_gen = _row_for(ANNA)["generated_at"]

_due = prdb.projection_list_due(limit=50, within_seconds=240)
_due_owners = {str(r["owner_user_id"]) for r in _due}
check("step 7: the due query catches a row expiring inside the window and not one outside it",
      str(LENA) in _due_owners and str(ANNA) not in _due_owners,
      f"due={sorted(_due_owners)}")
check("step 7: the due query does not drag every payload along",
      bool(_due) and "payload" not in _due[0],
      f"columns={sorted(_due[0]) if _due else []}")

_rep, _ = _with_stubbed_network(lambda: proj.refresh_due(limit=50, within_seconds=240))
check("step 7: the refresh pass republished what was about to expire",
      _rep.refreshed >= 1 and _rep.failed == 0,
      f"refreshed={_rep.refreshed} failed={_rep.failed} skipped={_rep.skipped}")
check("step 7: the refreshed row's bound moved forward off the read path",
      _row_for(LENA)["expires_at"] > datetime.now(timezone.utc),
      f"expires={_row_for(LENA)['expires_at']}")
check("step 7: a row nowhere near its bound was left alone",
      _row_for(ANNA)["generated_at"] == _annna_gen,
      "generated_at unchanged")

# The half-life bound, against the real table: a one-hour window must not
# turn into a one-hour poll of the owner's upstream.
_set_expiry(LENA, 500)
_lena_gen = _row_for(LENA)["generated_at"]
_with_stubbed_network(lambda: proj.refresh_due(limit=50, within_seconds=3600))
check("step 7: a window wider than the TTL does not refresh a row early again",
      _row_for(LENA)["generated_at"] == _lena_gen,
      "500s left of a 900s life is past the half-life")

# A scheduled refresh must not quietly widen the shape the owner picked.
_with_stubbed_network(lambda: publish_projection(
    resource_type="google_calendar", owner_user_id=LENA,
    identifier="primary", kind="availability"))
_set_expiry(LENA, 60)
_rep2, _ = _with_stubbed_network(lambda: proj.refresh_due(limit=50, within_seconds=120))
check("step 7: a scheduled refresh keeps the shape the owner chose",
      _rep2.refreshed >= 1 and _row_for(LENA)["projection_kind"] == "availability",
      f"kind={_row_for(LENA)['projection_kind']} refreshed={_rep2.refreshed}")
check("step 7: a refreshed projection still holds no credential",
      LENA_ICS not in json.dumps(_row_for(LENA)["payload"])
      and find_credential_keys(_row_for(LENA)["payload"]) == [],
      "the gate runs on every write, not only the first")

appdb.query(
    "DELETE FROM user_secrets WHERE user_id = ANY(%s::uuid[]) "
    "AND service_key IN ('google_calendar', 'calendar_ics')",
    ([LENA, ANNA],),
)
appdb.query("DELETE FROM share_projections")


# ── report ────────────────────────────────────────────────────────────────────

width = max(len(n) for n, _, _ in results)
failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")

print(f"\n{len(results) - len(failed)}/{len(results)} checks behaved as expected")
if failed:
    print(f"{len(failed)} unexpected — see above", file=sys.stderr)
    sys.exit(1)
