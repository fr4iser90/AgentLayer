#!/usr/bin/env python3
"""Step 0 of ADR 0014 — audit existing share grants before activating a type.

Registering an adapter for a resource type is not a neutral refactor: every
existing grant of that type starts working the moment the adapter lands,
including grants made long ago to friends who have since fallen out
(ADR 0014 §6.1). The decision to keep or clear those rows has to be made
deliberately, per type, and re-made whenever the situation changes.

This script produces the decision input. It answers, per type:

  * how many rows exist, how many are still active, how many revoked
  * who granted what to whom
  * whether the participants are real users or fixture users
  * whether a reader exists today, so the type is already live
  * whether the type is unknown to the ADR, i.e. it appeared after the
    last audit and nobody has decided anything about it

Run inside the app container:

    docker compose run --rm -e PYTHONPATH=/code agent-layer \
        python /code/scripts/audit_share_grants.py

Exit 0 = audit produced. It does not fail on findings; the findings are the
point. It exits non-zero only if it could not read the table.
"""

from __future__ import annotations

import sys
import uuid

import psycopg.rows

from apps.backend.infrastructure.db import db as appdb

appdb.init_pool()

# The deterministic identities written by scripts/seed_friend_sharing_fixture.sql.
# Anything else in the users table is a real account.
FIXTURE_USERS = {
    "a1111111-1111-4111-8111-111111111111": "anna@nord.example",
    "a2222222-2222-4222-8222-222222222222": "tim@nord.example",
    "a3333333-3333-4333-8333-333333333333": "lena@west.example",
    "a4444444-4444-4444-8444-444444444444": "bob@west.example",
}

# Reader status as recorded in ADR 0014 §1.3. This is a claim about the code at
# the time of writing, not something the table can show — so the script prints
# it as a label and treats any type NOT listed here as "undecided", which is the
# signal that the audit needs re-reading against current code.
#
#   live    — a reader honours the grant today
#   alias   — a legacy resource_type string that resolves through another type
#   inert   — grantable and readable, but nothing acts on it
TYPE_STATUS = {
    "dashboard": "live",
    "collection": "live",
    "google_calendar": "live",
    "haustiere": "alias",
    "github_activity": "inert",
    "todoist": "inert",
    "notes": "inert",
    "roadmap": "inert",
}

STATUS_NOTE = {
    "live": "reader exists — grant already honoured",
    "alias": "legacy string, resolves via another canonical type",
    "inert": "no reader today — registering one activates every row",
    "unknown": "not in ADR 0014 §1.3 — nobody has decided this type",
}


def rows_by_type() -> list[dict]:
    with appdb.pool().connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type::text            AS resource_type,
                       sp.resource_identifier::text    AS resource_identifier,
                       sp.owner_user_id::text          AS owner_id,
                       sp.grantee_user_id::text        AS grantee_id,
                       sp.is_allowed                   AS is_allowed,
                       sp.revoked_at                   AS revoked_at,
                       sp.policy                       AS policy,
                       sp.created_at                   AS created_at,
                       ou.email                        AS owner_email,
                       gu.email                        AS grantee_email
                FROM share_permissions sp
                JOIN users ou ON ou.id = sp.owner_user_id
                JOIN users gu ON gu.id = sp.grantee_user_id
                ORDER BY sp.resource_type, sp.created_at
                """
            )
            return cur.fetchall()


def origin_of(*ids: str) -> str:
    if all(i in FIXTURE_USERS for i in ids):
        return "fixture"
    if any(i in FIXTURE_USERS for i in ids):
        return "MIXED"
    return "REAL"


def is_active(row: dict) -> bool:
    return row["is_allowed"] and row["revoked_at"] is None


def main() -> int:
    try:
        rows = rows_by_type()
    except Exception as exc:  # pragma: no cover - operator-facing guard
        print(f"could not read share_permissions: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("share_permissions is empty — nothing to decide.")
        print("This is the cheapest possible moment to build the registry "
              "(ADR 0014 §6.1).")
        return 0

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["resource_type"], []).append(r)

    print(f"{len(rows)} grant row(s) across {len(by_type)} resource type(s)\n")

    hazards: list[str] = []
    decisions: list[tuple[str, str, str]] = []

    for rtype in sorted(by_type):
        group = by_type[rtype]
        active = [r for r in group if is_active(r)]
        revoked = [r for r in group if r["revoked_at"] is not None]
        origins = {origin_of(r["owner_id"], r["grantee_id"]) for r in group}
        status = TYPE_STATUS.get(rtype, "unknown")

        print(f"── {rtype}  [{status}]")
        print(f"   {STATUS_NOTE[status]}")
        print(f"   rows={len(group)}  active={len(active)}  revoked={len(revoked)}"
              f"  origin={', '.join(sorted(origins))}")
        for r in group:
            flag = "active " if is_active(r) else "revoked"
            print(f"     {flag} {r['owner_email']} -> {r['grantee_email']}"
                  f"  identifier={r['resource_identifier']}"
                  f"  policy={r['policy']}")

        real_rows = [r for r in group if origin_of(r["owner_id"], r["grantee_id"]) != "fixture"]

        if status == "unknown":
            hazards.append(
                f"{rtype}: {len(group)} row(s) of a type ADR 0014 §1.3 never "
                f"classified. Nothing has decided whether it may be shared."
            )
        if status == "inert" and real_rows:
            hazards.append(
                f"{rtype}: {len(real_rows)} REAL row(s) sit inert today. "
                f"Writing an adapter makes them all live at once."
            )
        if status == "live" and real_rows:
            hazards.append(
                f"{rtype}: {len(real_rows)} REAL row(s) already honoured. "
                f"Verify each owner still means it."
            )
        if "MIXED" in origins:
            hazards.append(
                f"{rtype}: a grant spans fixture and real users — the fixture "
                f"leaked into a real relationship, or a real user took a fixture id."
            )

        decisions.append((rtype, status, "fixture-only" if not real_rows else "HAS REAL ROWS"))
        print()

    print("── decision table ─────────────────────────────────────────────────")
    w = max(len(d[0]) for d in decisions)
    for rtype, status, reality in decisions:
        print(f"  {rtype.ljust(w)}  {status.ljust(8)}  {reality}")

    print("\n── hazards ────────────────────────────────────────────────────────")
    if hazards:
        for h in hazards:
            print(f"  ! {h}")
    else:
        print("  none — no real user data is exposed by any type above")

    fixture_only = all(d[2] == "fixture-only" for d in decisions)
    print("\n── reading ────────────────────────────────────────────────────────")
    if fixture_only:
        print("  Every grant row belongs to the sharing fixture. No real user")
        print("  has shared anything, so no adapter activation is a migration")
        print("  event yet. ADR 0014 §6.1's 'cheapest moment' still holds.")
    else:
        print("  Real grants exist. Each adapter activation from here on is a")
        print("  data-sharing event with an audit obligation (ADR 0014 §6.1).")

    print("\n  Re-run this script before acting on §6.1 again — the snapshot is")
    print("  not a permanent property of the deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
