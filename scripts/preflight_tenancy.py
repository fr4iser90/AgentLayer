#!/usr/bin/env python3
"""Read-only tenancy preflight: what a deployment-mode switch would actually touch.

Answers the question the setup endpoint cannot: given the data in *this* database,
is ``agent_system`` a safe place to land, or is there real tenancy here that would
be stranded without an admin surface?

Nothing here writes. The connection runs in a read-only transaction and every
statement is a SELECT against catalog or row counts.

    python3 scripts/preflight_tenancy.py                     # uses config.DATABASE_URL
    python3 scripts/preflight_tenancy.py --dsn "postgresql://user:pw@host/db"
    python3 scripts/preflight_tenancy.py --json              # machine-readable

Run it against the real instance before deciding, not against a local dev DB.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Tables that carry a tenant_id and are worth counting per tenant.
CORE_TENANT_TABLES = [
    "users",
    "chat_conversations",
    "agent_runs",
    "agent_tasks",
    "scheduler_jobs",
    "media_items",
    "user_dashboards",
    "tenant_content",
    "user_collections",
    "todos",
    "delegate_runs",
    "user_notifications",
]

# Surfaces that go 404 when deployment_mode becomes agent_system.
ORG_SURFACE_TABLES = [
    "tenant_memberships",
    "tenant_departments",
    "tenant_profession_roles",
    "user_profession_assignments",
    "user_qualifications",
    "tenant_content",
]


def _connect(dsn: str):
    import psycopg  # noqa: PLC0415  (optional dependency, only needed to run)

    conn = psycopg.connect(dsn, row_factory=psycopg.rows.dict_row)
    conn.read_only = True
    return conn


def _scalar(conn, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def _table_exists(conn, table: str) -> bool:
    return _scalar(
        conn,
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (table,),
    ) is not None


def _rows(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def _deployment_mode(conn) -> str:
    if not _table_exists(conn, "operator_settings"):
        return "(no operator_settings table)"
    return str(_scalar(conn, "SELECT deployment_mode FROM operator_settings LIMIT 1") or "(unset)")


def _tenant_scoped_tables(conn) -> list[str]:
    return [
        r["table_name"]
        for r in _rows(
            conn,
            "SELECT DISTINCT table_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='tenant_id' ORDER BY table_name",
        )
    ]


def _tables_without_fk(conn) -> list[str]:
    rows = _rows(
        conn,
        """
        WITH scoped AS (
            SELECT DISTINCT table_name FROM information_schema.columns
            WHERE table_schema='public' AND column_name='tenant_id'
        ),
        keyed AS (
            SELECT DISTINCT kcu.table_name
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.constraint_column_usage ccu
              ON kcu.constraint_name = ccu.constraint_name
            WHERE kcu.column_name='tenant_id' AND ccu.table_name='tenants'
        )
        SELECT scoped.table_name FROM scoped
        LEFT JOIN keyed ON scoped.table_name = keyed.table_name
        WHERE keyed.table_name IS NULL ORDER BY 1
        """,
    )
    return [r["table_name"] for r in rows]


def _orphans(conn, tables: list[str]) -> dict[str, int]:
    """Rows whose tenant_id points at a tenant that does not exist."""
    out: dict[str, int] = {}
    for table in tables:
        if not _table_exists(conn, table):
            continue
        count = _scalar(
            conn,
            f'SELECT COUNT(*) FROM "{table}" t '
            f"WHERE t.tenant_id IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM tenants x WHERE x.id = t.tenant_id)",
        )
        if count:
            out[table] = int(count)
    return out


def _per_tenant(conn, tenants: list[int]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for tid in tenants:
        entry: dict[str, Any] = {"tenant_id": tid}
        for table in CORE_TENANT_TABLES:
            if not _table_exists(conn, table):
                continue
            entry[table] = int(
                _scalar(conn, f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id = %s', (tid,)) or 0
            )
        report.append(entry)
    return report


def _site_admins(conn) -> int:
    if not _table_exists(conn, "users"):
        return 0
    col = _scalar(
        conn,
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='users' AND column_name='site_role'",
    )
    if col is None:
        return 0
    return int(
        _scalar(conn, "SELECT COUNT(*) FROM users WHERE site_role = 'site_admin'") or 0
    )


def build_report(conn) -> dict[str, Any]:
    tenants = [
        int(r["id"])
        for r in _rows(conn, "SELECT id FROM tenants ORDER BY id")
    ] if _table_exists(conn, "tenants") else []

    scoped = _tenant_scoped_tables(conn)
    no_fk = _tables_without_fk(conn)
    orphans = _orphans(conn, scoped)
    per_tenant = _per_tenant(conn, tenants)

    org_surface = {
        table: int(_scalar(conn, f'SELECT COUNT(*) FROM "{table}"') or 0)
        for table in ORG_SURFACE_TABLES
        if _table_exists(conn, table)
    }

    outside_default = sum(
        row.get("users", 0) for row in per_tenant if row["tenant_id"] != 1
    )

    return {
        "deployment_mode": _deployment_mode(conn),
        "tenant_count": len(tenants),
        "tenants": tenants,
        "site_admins": _site_admins(conn),
        "users_outside_tenant_1": outside_default,
        "per_tenant": per_tenant,
        "tenant_scoped_tables": len(scoped),
        "tables_without_fk": no_fk,
        "orphan_rows": orphans,
        "org_surface_rows": org_surface,
    }


def _verdict(report: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    mode = report["deployment_mode"]

    if report["tenant_count"] <= 1:
        notes.append(
            "Single tenant in this DB — switching to agent_system strands nothing here."
        )
    else:
        notes.append(
            f"{report['tenant_count']} tenants exist. agent_system returns 404 on the whole "
            "/v1/org/* surface, so tenant admins lose their admin area while the tenant data "
            "stays behind. Decide what happens to those admins before switching."
        )
    if report["users_outside_tenant_1"]:
        notes.append(
            f"{report['users_outside_tenant_1']} user(s) live outside tenant 1. "
            "In agent_system they keep their data but lose any org-scoped identity."
        )
    if report["orphan_rows"]:
        worst = ", ".join(f"{t}={n}" for t, n in sorted(report["orphan_rows"].items()))
        notes.append(f"ORPHANED rows pointing at missing tenants: {worst}. Clean these up first.")
    if report["tables_without_fk"]:
        notes.append(
            f"{len(report['tables_without_fk'])} tenant-scoped tables have no FK to tenants "
            f"({', '.join(report['tables_without_fk'][:6])}…). Orphans are possible there by design "
            "of the schema — that is the integrity gap, not an accident of this data."
        )
    if mode == "multi_tenant" and report["tenant_count"] <= 1:
        notes.append(
            "Running multi_tenant with one tenant: the org surface is available but unused. "
            "Cheap to move to agent_system, expensive to move back once tenants exist."
        )
    return notes


def _print_human(report: dict[str, Any]) -> None:
    print("Tenancy preflight (read-only)")
    print("=" * 58)
    print(f"deployment_mode        : {report['deployment_mode']}")
    print(f"tenants                : {report['tenant_count']} {report['tenants']}")
    print(f"site admins            : {report['site_admins']}")
    print(f"users outside tenant 1 : {report['users_outside_tenant_1']}")
    print(f"tenant-scoped tables   : {report['tenant_scoped_tables']}")

    if report["per_tenant"]:
        print("\nPer-tenant volume")
        keys = [k for k in CORE_TENANT_TABLES if any(k in r for r in report["per_tenant"])]
        print("  {:<10}".format("tenant") + "".join(f"{k:>20}" for k in keys))
        for row in report["per_tenant"]:
            print("  {:<10}".format(row["tenant_id"]) + "".join(
                f"{row.get(k, 0):>20}" for k in keys
            ))

    if report["org_surface_rows"]:
        print("\nOrg surface rows (would become unreachable under agent_system)")
        for table, count in sorted(report["org_surface_rows"].items()):
            print(f"  {table:<34} {count}")

    if report["tables_without_fk"]:
        print(f"\nTenant-scoped tables WITHOUT a FK to tenants ({len(report['tables_without_fk'])})")
        for table in report["tables_without_fk"]:
            print(f"  {table}")

    if report["orphan_rows"]:
        print("\nOrphaned rows (tenant_id points at a missing tenant)")
        for table, count in sorted(report["orphan_rows"].items()):
            print(f"  {table:<34} {count}")

    print("\nAssessment")
    for note in _verdict(report):
        print(f"  - {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", default=os.environ.get("AGENT_PREFLIGHT_DSN") or None,
                      help="Postgres DSN. Defaults to the app's resolved DATABASE_URL.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a report.")
    args = parser.parse_args()

    dsn = args.dsn
    if not dsn:
        try:
            from apps.backend.infrastructure.platform.config import DATABASE_URL  # noqa: PLC0415

            dsn = DATABASE_URL
        except Exception as exc:  # noqa: BLE001  (report, don't traceback on config)
            print(f"could not resolve DATABASE_URL from app config: {exc}", file=sys.stderr)
            print("pass --dsn or set AGENT_PREFLIGHT_DSN", file=sys.stderr)
            return 2

    try:
        conn = _connect(dsn)
    except Exception as exc:  # noqa: BLE001
        print(f"could not connect: {exc}", file=sys.stderr)
        return 2

    try:
        report = build_report(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
