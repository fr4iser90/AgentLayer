"""
Manage share permissions between you and friends (grant, revoke, list, check).

One tool for all resource types — calendar, GitHub, notes, etc.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.domain.shares.catalog import (
    catalog_for_api,
    canonical_resource_type,
    resource_type_label,
)
from apps.backend.domain.shares.policy import normalize_policy
from apps.backend.infrastructure.db.share_permissions_db import (
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    list_shares_between,
    list_shares_by_grantee,
    list_shares_by_owner,
    share_permission_check_resolved,
    share_permission_get,
    share_permission_set,
)

from apps.backend.domain.friends.common import resolve_friend_by_name

__version__ = "2.0.0"
TOOL_ID = "shares"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "friends"
TOOL_TRIGGERS = (
    "was teilt",
    "was share",
    "was hat",
    "geteilt",
    "sharing",
    "shares",
    "freigabe",
    "freigaben",
    "zugriff auf",
    "wer darf",
    "wer hat zugriff",
    "teile meinen",
    "teile mein",
    "kalender teilen",
    "share my calendar",
    "grant access",
    "revoke access",
    "entziehe zugriff",
)
TOOL_CAPABILITIES = ("friends.shares", "default")


def _normalize_share_rows(rows: list[dict[str, Any]], *, direction: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        resource_type = str(row.get("resource_type") or "").strip().lower()
        if not resource_type:
            continue
        peer_id = row.get("grantee_user_id") if direction == "outgoing" else row.get("owner_user_id")
        out.append(
            {
                "resource_type": resource_type,
                "resource_label": resource_type_label(resource_type),
                "resource_identifier": row.get("resource_identifier") or "primary",
                "policy": row.get("policy") or {},
                "peer_user_id": str(peer_id) if peer_id else None,
                "peer_display_name": row.get("display_name") or row.get("email"),
                "peer_email": row.get("email"),
            }
        )
    return out


def _group_shares_by_peer(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        peer_id = row.get("peer_user_id") or ""
        if peer_id not in grouped:
            grouped[peer_id] = {
                "user_id": peer_id,
                "display_name": row.get("peer_display_name"),
                "email": row.get("peer_email"),
                "resources": [],
            }
        grouped[peer_id]["resources"].append(
            {
                "resource_type": row["resource_type"],
                "resource_label": row["resource_label"],
                "resource_identifier": row.get("resource_identifier") or "primary",
                "policy": row.get("policy") or {},
            }
        )
    return list(grouped.values())


def _validate_collection_grant(
    *,
    owner_user_id: uuid.UUID,
    resource_identifier: str,
) -> str | None:
    from apps.backend.domain.collections import db as col_db

    ident = (resource_identifier or "").strip().lower()
    if ident in ("", "primary"):
        return "resource_identifier must be a collection slug (e.g. pets, shopping)"
    if col_db.normalize_slug(ident) is None:
        return "resource_identifier must be a valid collection slug (lowercase, a-z0-9._-)"
    if col_db.collection_get(owner_user_id, ident) is None:
        return f"collection '{ident}' not found — create it first (collection.ensure)"
    return None


def _validate_dashboard_grant(
    *,
    owner_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
    raw_policy: dict[str, Any],
) -> str | None:
    if resource_type != "dashboard":
        return None
    from apps.backend.dashboard import db as dashboard_db
    from apps.backend.domain.shares.dashboard_grant import grant_matches_dashboard
    from apps.backend.infrastructure.db.db import user_tenant_id

    tid = user_tenant_id(owner_user_id)
    ident = (resource_identifier or "primary").strip().lower()
    try:
        wid = uuid.UUID(ident)
    except ValueError:
        return "resource_identifier must be a dashboard UUID"

    ws = dashboard_db.dashboard_get(owner_user_id, tid, wid)
    if ws is None:
        return "dashboard not found or you are not the owner"

    block_ids = raw_policy.get("block_ids")
    if isinstance(block_ids, list) and block_ids:
        ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
        from apps.backend.dashboard.layout_tree import flatten_block_ids

        valid = flatten_block_ids(ul)
        bad = [str(x) for x in block_ids if str(x).strip() not in valid]
        if bad:
            return f"unknown block_ids in policy: {', '.join(bad[:5])}"
    elif not grant_matches_dashboard(
        dashboard_id=wid,
        resource_type=resource_type,
        resource_identifier=ident,
        dashboard_kind=str(ws.get("kind") or ""),
    ):
        return "dashboard grant identifier does not match this board"
    return None


def _resolve_friend_or_error(
    requesting_user_id: uuid.UUID,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    name_query = (
        arguments.get("entity")
        or arguments.get("name")
        or arguments.get("friend")
        or arguments.get("friend_name")
    )
    if not name_query:
        return None, "name or friend parameter is required for this action"
    friend = resolve_friend_by_name(requesting_user_id, str(name_query))
    if not friend:
        return None, f"Could not find {name_query} in your friends list."
    return friend, None


def _action_grant(requesting_user_id: uuid.UUID, arguments: dict[str, Any]) -> dict[str, Any]:
    friend, err = _resolve_friend_or_error(requesting_user_id, arguments)
    if err or not friend:
        return {"ok": False, "result": err}

    resource_type = arguments.get("resource_type")
    if not resource_type:
        return {"ok": False, "result": "resource_type is required for grant (e.g. google_calendar)"}

    canonical = canonical_resource_type(str(resource_type))
    if not canonical:
        catalog = catalog_for_api()
        ids = [r["id"] for r in catalog]
        return {
            "ok": False,
            "result": f"Unknown resource_type '{resource_type}'. Known types: {', '.join(ids)}",
        }

    raw_policy = arguments.get("policy")
    if raw_policy is None and arguments.get("days_ahead") is not None:
        raw_policy = {"days_ahead": arguments.get("days_ahead")}
    if raw_policy is None and arguments.get("expires_at"):
        raw_policy = {"expires_at": arguments.get("expires_at")}

    clean_policy, policy_err = normalize_policy(canonical, raw_policy if isinstance(raw_policy, dict) else {})
    if policy_err:
        return {"ok": False, "result": policy_err}

    identifier = str(arguments.get("resource_identifier") or "primary").strip().lower()
    friend_user_id = uuid.UUID(friend["friend_user_id"])

    if canonical == "collection":
        col_err = _validate_collection_grant(
            owner_user_id=requesting_user_id,
            resource_identifier=identifier,
        )
        if col_err:
            return {"ok": False, "result": col_err}
    else:
        dash_err = _validate_dashboard_grant(
            owner_user_id=requesting_user_id,
            resource_type=canonical,
            resource_identifier=identifier,
            raw_policy=raw_policy if isinstance(raw_policy, dict) else {},
        )
        if dash_err:
            return {"ok": False, "result": dash_err}

    share_permission_set(
        owner_user_id=requesting_user_id,
        grantee_user_id=friend_user_id,
        resource_type=canonical,
        resource_identifier=identifier,
        allowed=True,
        policy=clean_policy,
    )

    return {
        "ok": True,
        "result": f"Granted {resource_type_label(canonical)} access to {friend.get('display_name') or friend.get('email')}.",
        "grant": {
            "friend_user_id": str(friend_user_id),
            "resource_type": canonical,
            "resource_identifier": identifier,
            "policy": clean_policy,
        },
    }


def _action_revoke(requesting_user_id: uuid.UUID, arguments: dict[str, Any]) -> dict[str, Any]:
    friend, err = _resolve_friend_or_error(requesting_user_id, arguments)
    if err or not friend:
        return {"ok": False, "result": err}

    resource_type = arguments.get("resource_type")
    if not resource_type:
        return {"ok": False, "result": "resource_type is required for revoke"}

    canonical = canonical_resource_type(str(resource_type))
    if not canonical:
        return {"ok": False, "result": f"Unknown resource_type '{resource_type}'"}

    identifier = str(arguments.get("resource_identifier") or "primary").strip().lower()
    friend_user_id = uuid.UUID(friend["friend_user_id"])

    share_permission_set(
        owner_user_id=requesting_user_id,
        grantee_user_id=friend_user_id,
        resource_type=canonical,
        resource_identifier=identifier,
        allowed=False,
    )

    return {
        "ok": True,
        "result": f"Revoked {resource_type_label(canonical)} access for {friend.get('display_name') or friend.get('email')}.",
    }


def _action_check(requesting_user_id: uuid.UUID, arguments: dict[str, Any]) -> dict[str, Any]:
    friend, err = _resolve_friend_or_error(requesting_user_id, arguments)
    if err or not friend:
        return {"ok": False, "result": err}

    resource_type = arguments.get("resource_type")
    if not resource_type:
        return {"ok": False, "result": "resource_type is required for check"}

    canonical = canonical_resource_type(str(resource_type))
    if not canonical:
        return {"ok": False, "result": f"Unknown resource_type '{resource_type}'"}

    identifier = str(arguments.get("resource_identifier") or "primary").strip().lower()
    friend_user_id = uuid.UUID(friend["friend_user_id"])

    direction = str(arguments.get("direction") or "incoming").strip().lower()
    if direction == "outgoing":
        owner_id, grantee_id = requesting_user_id, friend_user_id
    else:
        owner_id, grantee_id = friend_user_id, requesting_user_id

    grant = share_permission_get(
        owner_user_id=owner_id,
        grantee_user_id=grantee_id,
        resource_type=canonical,
        resource_identifier=identifier,
    )

    return {
        "ok": True,
        "allowed": grant is not None,
        "direction": direction,
        "grant": grant,
        "friend": {
            "user_id": str(friend_user_id),
            "display_name": friend.get("display_name") or friend.get("email"),
        },
    }


def _shares_for_friend(requesting_user_id: uuid.UUID, friend_user_id: uuid.UUID) -> dict[str, Any]:
    between = list_shares_between(requesting_user_id, friend_user_id)
    outgoing = between.get("outgoing_grants") or []
    incoming = between.get("incoming_grants") or []

    calendar_incoming = share_permission_check_resolved(
        owner_user_id=friend_user_id,
        grantee_user_id=requesting_user_id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    )
    calendar_outgoing = share_permission_check_resolved(
        owner_user_id=requesting_user_id,
        grantee_user_id=friend_user_id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    )
    return {
        "you_share_with_them": [
            {
                "resource_type": g.get("resource_type"),
                "resource_label": resource_type_label(str(g.get("resource_type") or "")),
                "resource_identifier": g.get("resource_identifier") or "primary",
                "policy": g.get("policy") or {},
                "granted": True,
            }
            for g in outgoing
        ],
        "they_share_with_you": [
            {
                "resource_type": g.get("resource_type"),
                "resource_label": resource_type_label(str(g.get("resource_type") or "")),
                "resource_identifier": g.get("resource_identifier") or "primary",
                "policy": g.get("policy") or {},
                "granted": True,
            }
            for g in incoming
        ],
        "calendar_access_you_have": calendar_incoming,
        "calendar_access_they_have": calendar_outgoing,
    }


def _action_list(requesting_user_id: uuid.UUID, arguments: dict[str, Any]) -> dict[str, Any]:
    name_query = (
        arguments.get("entity")
        or arguments.get("name")
        or arguments.get("friend")
        or arguments.get("friend_name")
    )
    if name_query:
        friend = resolve_friend_by_name(requesting_user_id, str(name_query))
        if not friend:
            return {
                "ok": False,
                "result": f"Could not find {name_query} in your friends list.",
            }
        friend_user_id = uuid.UUID(friend["friend_user_id"])
        return {
            "ok": True,
            "friend": {
                "user_id": str(friend_user_id),
                "display_name": friend.get("display_name") or friend.get("email"),
                "email": friend.get("email"),
            },
            **_shares_for_friend(requesting_user_id, friend_user_id),
            "catalog": catalog_for_api(),
        }

    outgoing = _normalize_share_rows(
        list_shares_by_owner(requesting_user_id),
        direction="outgoing",
    )
    incoming = _normalize_share_rows(
        list_shares_by_grantee(requesting_user_id),
        direction="incoming",
    )
    return {
        "ok": True,
        "outgoing_by_friend": _group_shares_by_peer(outgoing),
        "incoming_by_friend": _group_shares_by_peer(incoming),
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming),
        "catalog": catalog_for_api(),
    }


def shares(arguments: dict[str, Any]) -> str:
    """Grant, revoke, list, or check friend share permissions."""
    _tid, requesting_user_id = get_identity()
    if not requesting_user_id:
        return json.dumps({"error": "no user identity available"}, ensure_ascii=False)

    action = str(arguments.get("action") or "list").strip().lower()
    handlers = {
        "list": _action_list,
        "grant": _action_grant,
        "revoke": _action_revoke,
        "check": _action_check,
    }
    handler = handlers.get(action)
    if not handler:
        return json.dumps(
            {"ok": False, "error": f"unknown action '{action}'; use list, grant, revoke, or check"},
            ensure_ascii=False,
        )

    try:
        payload = handler(requesting_user_id, arguments)
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "shares": shares,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "shares",
            "TOOL_DESCRIPTION": (
                "Manage friend share permissions: grant, revoke, list, or check access to resources "
                "(google_calendar, github_activity, todoist, notes, roadmap, dashboard, collection). "
                "For dashboard: resource_identifier = dashboard UUID. "
                "For collection: resource_identifier = slug (e.g. pets). Optional policy: "
                "{permission: edit|view, block_ids: [layout block ids], expires_at: ISO}. "
                "Use action=grant to share e.g. calendar with days_ahead:7. "
                "Use action=list without name for full summary; with friend name for one person."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "grant", "revoke", "check"],
                        "TOOL_DESCRIPTION": "list (default), grant, revoke, or check permission.",
                    },
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Friend name or email (required for grant/revoke/check; optional for list).",
                    },
                    "entity": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Auto-filled name/email from the trigger system.",
                    },
                    "resource_type": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Resource id from catalog: google_calendar, github_activity, todoist, notes, "
                            "roadmap, dashboard, collection."
                        ),
                    },
                    "resource_identifier": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Usually 'primary' (default).",
                    },
                    "policy": {
                        "type": "object",
                        "TOOL_DESCRIPTION": (
                            "Optional scope, e.g. {\"days_ahead\": 7, \"expires_at\": \"2026-06-11T00:00:00Z\"}."
                        ),
                    },
                    "days_ahead": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Shortcut for policy.days_ahead when granting calendar access.",
                    },
                    "expires_at": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Shortcut for policy.expires_at (ISO-8601 UTC).",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["incoming", "outgoing"],
                        "TOOL_DESCRIPTION": "For check: incoming = they share with you; outgoing = you share with them.",
                    },
                },
            },
        },
    },
]
