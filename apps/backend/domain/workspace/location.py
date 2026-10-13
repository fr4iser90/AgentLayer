"""Where a workspace lives on disk, decided in one place.

Two roots share one base:

    <base>/<user_id>/<name>                private — the historical shape
    <base>/_tenants/<tenant_id>/<name>     visible to a whole tenant

The tenant root exists so one company's bytes sit together: ``du`` per tenant,
one ``mv`` on offboarding, instead of scattered across whichever members
happened to create them. It also makes the disk layout say what the access rule
says — a directory under ``_tenants/7`` is company 7's, without asking the DB.

The tenant segment is a literal and user ids are UUIDs, so the two roots cannot
spell each other. Nothing in the backend enumerates the base directory, so
``_tenants`` is not mistaken for a user id; that is a fact to preserve, not a
property this module can enforce.

``resolve_*`` lives in the infrastructure layer, which applies the containment
check on top of the roots chosen here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.backend.domain.access.entity_access import TENANT_VISIBLE

TENANT_ROOT_SEGMENT = "_tenants"


def user_workspace_root(base: Path, user_id: Any) -> Path:
    """The private root: one directory per person, directly under the base."""
    return base / str(user_id)


def tenant_workspace_root(base: Path, tenant_id: int) -> Path:
    """The shared root for one tenant. ``tenant_id`` is coerced so a bigint
    arriving as a string cannot produce a second directory for the same tenant."""
    return base / TENANT_ROOT_SEGMENT / str(int(tenant_id))


def workspace_root_for(
    *,
    base: Path,
    visibility: str,
    owner_user_id: Any,
    tenant_id: int | None,
) -> Path:
    """Pick the disk root for a workspace being created.

    A tenant-visible workspace with no known tenant is refused rather than sent
    to the creator's private directory: silently landing company data in one
    person's directory is the failure this scheme exists to prevent, and it would
    be invisible in the path.
    """
    if visibility != TENANT_VISIBLE:
        return user_workspace_root(base, owner_user_id)
    if tenant_id is None:
        raise ValueError("a tenant-visible workspace needs a tenant_id to be placed")
    return tenant_workspace_root(base, tenant_id)
