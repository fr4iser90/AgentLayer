"""The one rule that turns identity rows into a role word.

ADR 0011 §1 made ``users.site_role`` the only source of elevation and left ``users.role``
as a compatibility column. This module is the only place that column may still speak —
and only for a row that was never migrated (``site_role IS NULL``), which is the sole
case where the compatibility column carries information ``site_role`` does not.

Every other reader of a role reads the *result* of these two functions, so removing the
legacy column later is a change here and nothing else.
"""

from __future__ import annotations

from typing import Literal

# ``users.site_role`` values.
SITE_ADMIN = "site_admin"
SITE_USER = "site_user"

# The role word every elevation check in this code base speaks.
RoleWord = Literal["admin", "user"]
ADMIN: RoleWord = "admin"
USER: RoleWord = "user"

# SQL mirror of :func:`normalize_site_role`, for the few statements that must answer "is
# this row elevated?" inside the database rather than in Python. Outside the identity
# resolver this is the only SQL that may name the compatibility column, so a statement
# cannot invent its own reading of it. ``site_role IS NULL`` is exactly the "never
# migrated" case: the schema constrains the column to the two values above
# (``schema_111_identity_roles_deployment_mode``).
ELEVATED_SQL = "(site_role = 'site_admin' OR (site_role IS NULL AND role = 'admin'))"

__all__ = [
    "ADMIN",
    "ELEVATED_SQL",
    "SITE_ADMIN",
    "SITE_USER",
    "USER",
    "RoleWord",
    "effective_role",
    "normalize_site_role",
]


def normalize_site_role(site_role: object, legacy_role: object) -> str:
    """Return ``site_admin``/``site_user`` for a row, preferring ``users.site_role``.

    ``legacy_role`` is consulted only when ``site_role`` is unset or holds a value outside
    the domain — i.e. an install that has not run the migration. An account demoted
    through ``site_role='site_user'`` that still carries ``role='admin'`` normalizes to
    ``site_user``.
    """
    site = str(site_role or "").strip().lower()
    if site in (SITE_ADMIN, SITE_USER):
        return site
    return SITE_ADMIN if str(legacy_role or "").strip().lower() == "admin" else SITE_USER


def effective_role(site_role: object, legacy_role: object) -> RoleWord:
    """The role word (``admin``/``user``) implied by a row's two role columns."""
    return ADMIN if normalize_site_role(site_role, legacy_role) == SITE_ADMIN else USER
