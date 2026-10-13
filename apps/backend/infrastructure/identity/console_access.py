"""The in-process guard for plugin consoles — the twin of the HTTP one in :mod:`auth`.

A tool handler has no ``Request`` to authenticate: it runs inside the agent's tool loop
and knows its caller only through the chat identity the runtime put in a contextvar. That
is exactly why a console can drift looser than the routes it mirrors — it never had to
pass the same gate. :func:`console_scope` closes the gap by asking the same two questions
in the same order and reading the same three columns as
:meth:`~apps.backend.infrastructure.identity.auth.require_admin_scope`, so one confinement
cannot be learned for a route while its console stays permissive.

The denial is an :class:`~apps.backend.domain.access.capabilities.AdminScopeError`, not an
``HTTPException``: a plugin has no status code to return and renders the message into its
own JSON payload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db import db

if TYPE_CHECKING:
    from apps.backend.domain.access.capabilities import AdminScope


def console_scope(capability: str | None = None) -> "AdminScope":
    """Judge the caller of an in-process console tool and return the range it reaches.

    With ``capability`` this is ``require_admin_scope``: the slug is judged and a delegated
    holder is confined to their own company. Without one it mirrors ``require_site_admin``
    — the work that was never delegable has no slug, so only a site admin passes.

    A console handler that creates, moves or grants against a target still has to check
    that target against the returned scope, exactly as a route handler does.
    """
    from apps.backend.domain.access.capabilities import AdminScopeError, scope_for, site_scope

    actor_id = get_identity()[1]
    if actor_id is None:
        raise AdminScopeError("authentication and admin role required for this tool")
    site_role = db.user_site_role(actor_id)
    if capability is None:
        return site_scope(actor_id=actor_id, site_role=site_role)
    return scope_for(
        actor_id=actor_id,
        capability=capability,
        site_role=site_role,
        capabilities=db.user_capabilities(actor_id),
        tenant_id=db.user_tenant_id(actor_id),
    )
