"""
Friendship System API
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user, get_user_by_email
from apps.backend.application.sharing.use_cases.sharing_controller_services import (
    friend_request_create,
    friend_request_get,
    friend_request_get_between,
    friend_requests_incoming,
    friend_requests_outgoing,
    friend_request_accept,
    friend_request_decline,
    friend_get,
    friends_list,
    friend_remove,
    friend_update,
)
from apps.backend.application.sharing.use_cases.sharing_controller_services import user_tenant_id

router = APIRouter(prefix="/v1/friends", tags=["friends"])


class FriendRequestSendBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    message: str | None = Field(default=None, max_length=500)


@router.post("/request")
async def send_friend_request(request: Request, body: FriendRequestSendBody):
    """Send a friend request to another user by email"""
    user = await get_current_user(request)
    tid = user_tenant_id(user.id)

    target = get_user_by_email(body.email.strip().lower())
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # TENANT CHECK REMOVED - allow cross tenant friend requests
    # if user_tenant_id(target.id) != tid:
    #     raise HTTPException(status_code=400, detail="User must be in the same tenant")

    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot send friend request to yourself")

    # Check if already friends
    existing = friend_get(user.id, target.id)
    if existing:
        raise HTTPException(status_code=400, detail="Already friends")

    # Check if request already exists
    existing_request = friend_request_get_between(user.id, target.id)
    if existing_request:
        raise HTTPException(status_code=400, detail="Friend request already pending")

    ok = friend_request_create(tid, user.id, target.id, body.message)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not send friend request")

    return {"ok": True}


@router.get("/requests/incoming")
async def get_incoming_requests(request: Request):
    """Get all incoming pending friend requests"""
    user = await get_current_user(request)
    requests = friend_requests_incoming(user.id)
    return {"ok": True, "requests": requests}


@router.get("/requests/outgoing")
async def get_outgoing_requests(request: Request):
    """Get all outgoing pending friend requests"""
    user = await get_current_user(request)
    requests = friend_requests_outgoing(user.id)
    return {"ok": True, "requests": requests}


@router.post("/requests/{request_id}/accept")
async def accept_friend_request(request: Request, request_id: int):
    """Accept an incoming friend request"""
    user = await get_current_user(request)
    req = friend_request_get(request_id)
    if not req or req["to_user_id"] != user.id or req["status"] != "pending":
        raise HTTPException(status_code=404, detail="Friend request not found")

    # Use original tenant id from the request not current user tenant
    ok = friend_request_accept(request_id, req["tenant_id"], req["from_user_id"], user.id)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not accept friend request")

    return {"ok": True}


@router.post("/requests/{request_id}/decline")
async def decline_friend_request(request: Request, request_id: int):
    """Decline an incoming friend request"""
    user = await get_current_user(request)

    req = friend_request_get(request_id)
    if not req or req["to_user_id"] != user.id or req["status"] != "pending":
        raise HTTPException(status_code=404, detail="Friend request not found")

    ok = friend_request_decline(request_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not decline friend request")

    return {"ok": True}


@router.get("")
async def list_friends(request: Request):
    """List all confirmed friends"""
    user = await get_current_user(request)
    friends = friends_list(user.id)
    return {"ok": True, "friends": friends}


@router.delete("/{friend_user_id}")
async def remove_friend(request: Request, friend_user_id: str):
    """Remove a friend"""
    user = await get_current_user(request)

    ok = friend_remove(user.id, friend_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Friend not found")

    return {"ok": True, "removed": True}


class FriendUpdateBody(BaseModel):
    relation: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


@router.patch("/{friend_user_id}")
async def update_friend(request: Request, friend_user_id: str, body: FriendUpdateBody):
    """Update friend metadata"""
    user = await get_current_user(request)

    ok = friend_update(
        user.id,
        friend_user_id,
        relation=body.relation,
        note=body.note
    )
    
    if not ok:
        raise HTTPException(status_code=404, detail="Friend not found")

    return {"ok": True, "updated": True}
