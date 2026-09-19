from __future__ import annotations

from fastapi import HTTPException

from apps.backend.infrastructure.db.db import user_tenant_id
from apps.backend.infrastructure.db.friends_db import (
    friend_get,
    friend_remove,
    friend_request_accept,
    friend_request_create,
    friend_request_decline,
    friend_request_get,
    friend_request_get_between,
    friend_requests_incoming,
    friend_requests_outgoing,
    friend_update,
    friends_list,
)
from apps.backend.infrastructure.db.share_permissions_db import (
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    list_shares_between,
    list_shares_by_grantee,
    list_shares_by_owner,
    share_permission_check,
    share_permission_get,
    share_permission_set,
)
from apps.backend.infrastructure.settings import operator_settings

FRIEND_SYSTEM_DISABLED_DETAIL = (
    "The friendship and sharing feature is disabled on this instance."
)


async def require_friend_system() -> None:
    """Router-level guard for the whole peer subsystem.

    404 rather than 403: a subsystem the operator has not deployed should not
    tell a caller that it exists and is merely forbidden. Same shape as the
    /org surface, which 404s when the org surface is off.

    Applied as a router dependency rather than per endpoint so that a newly
    added friendship or share route is covered without anyone remembering to
    decorate it.
    """
    if not operator_settings.friend_system_enabled():
        raise HTTPException(status_code=404, detail=FRIEND_SYSTEM_DISABLED_DETAIL)
