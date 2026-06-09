"""Journey B — social: friend request, accept, calendar share."""

from __future__ import annotations

import pytest

from tests.e2e.support.helpers import E2EClient, SHARE_RESOURCE_GOOGLE_CALENDAR

pytestmark = pytest.mark.e2e


def _incoming_pending(client: E2EClient) -> list[dict]:
    data = client.get_json("/v1/friends/requests/incoming")
    return [r for r in data.get("requests") or [] if isinstance(r, dict)]


def _ensure_friends(admin_client: E2EClient, user_b_client: E2EClient) -> None:
    user_b_id = user_b_client.user_id
    friends = admin_client.get_json("/v1/friends").get("friends") or []
    if any(
        str(f.get("friend_user_id") or f.get("user_id") or "") == user_b_id
        for f in friends
        if isinstance(f, dict)
    ):
        return

    pending = _incoming_pending(user_b_client)
    if not pending:
        resp = admin_client.post_json_allow(
            "/v1/friends/request",
            {"email": user_b_client.email, "message": "E2E friend"},
            ok={200, 400},
        )
        if resp.status_code == 400 and "already friends" in resp.text.lower():
            return
        if resp.status_code == 400 and "already pending" not in resp.text.lower():
            resp.raise_for_status()
        pending = _incoming_pending(user_b_client)

    assert pending, "User B should have an incoming friend request"
    req_id = pending[0].get("id")
    assert req_id is not None
    user_b_client.post_json(f"/v1/friends/requests/{req_id}/accept", {})


def test_friend_request_accept_and_calendar_share(
    admin_client: E2EClient,
    user_b_client: E2EClient,
) -> None:
    user_b_id = user_b_client.user_id
    assert user_b_id

    _ensure_friends(admin_client, user_b_client)
    friends_after = admin_client.get_json("/v1/friends").get("friends") or []
    assert any(
        str(f.get("friend_user_id") or f.get("user_id") or f.get("id") or "") == user_b_id
        for f in friends_after
        if isinstance(f, dict)
    )

    admin_client.post_json(
        "/v1/shares/set",
        {
            "grantee_user_id": user_b_id,
            "resource_type": SHARE_RESOURCE_GOOGLE_CALENDAR,
            "resource_identifier": "primary",
            "is_allowed": True,
        },
    )

    outgoing = admin_client.get_json("/v1/shares/outgoing").get("shares") or []
    match = [
        s
        for s in outgoing
        if isinstance(s, dict)
        and str(s.get("grantee_user_id") or "") == user_b_id
        and s.get("resource_type") in (SHARE_RESOURCE_GOOGLE_CALENDAR, "calendar")
    ]
    assert match, f"expected outgoing google_calendar share for {user_b_id}"

    check = admin_client.get_json(
        "/v1/shares/check",
        owner_user_id=admin_client.user_id,
        grantee_user_id=user_b_id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
        resource_identifier="primary",
    )
    assert check.get("ok") is True
    assert check.get("allowed") is True

    between = admin_client.get_json(f"/v1/shares/friend/{user_b_id}")
    assert between.get("ok") is True
    outgoing_side = between.get("outgoing") or between.get("granted") or []
    assert isinstance(outgoing_side, list)
