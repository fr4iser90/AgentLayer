"""Database URL resolution for runtime configuration."""
from __future__ import annotations

import os
from urllib.parse import quote_plus


def resolve_database_url() -> str:
    direct = os.environ.get("DATABASE_URL", "").strip()
    if direct:
        return direct
    user = (os.environ.get("POSTGRES_USER") or "agent").strip()
    dbn = (os.environ.get("POSTGRES_DB") or "agent").strip()
    if not user or not dbn:
        return ""
    raw_pw = os.environ.get("POSTGRES_PASSWORD")
    password = "agent" if raw_pw is None else str(raw_pw)
    host = (
        os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "postgres"
    ).strip() or "postgres"
    port = (os.environ.get("PGPORT") or "5432").strip() or "5432"
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(dbn)}"
    )


def sqlalchemy_postgresql_url(url: str) -> str:
    u = (url or "").strip()
    if not u or "://" not in u:
        return u
    scheme, rest = u.split("://", 1)
    if "+" in scheme:
        return u
    if scheme in ("postgresql", "postgres"):
        return f"postgresql+psycopg://{rest}"
    return u
