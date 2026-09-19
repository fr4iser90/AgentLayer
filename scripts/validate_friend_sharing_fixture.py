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

# ── report ────────────────────────────────────────────────────────────────────

width = max(len(n) for n, _, _ in results)
failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")

print(f"\n{len(results) - len(failed)}/{len(results)} checks behaved as expected")
if failed:
    print(f"{len(failed)} unexpected — see above", file=sys.stderr)
    sys.exit(1)
