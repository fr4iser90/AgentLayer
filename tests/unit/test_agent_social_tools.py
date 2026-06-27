"""Tests for mail.send, dashboard sharing tools, and friend request tool."""

from __future__ import annotations

import json
import unittest
import uuid
from unittest import mock

from apps.backend.domain.shares import policy as share_policy


class TestDashboardSharePolicy(unittest.TestCase):
    def test_permission_and_block_ids_allowed_for_dashboard(self) -> None:
        clean, err = share_policy.normalize_policy(
            "dashboard",
            {"permission": "edit", "block_ids": ["pets-album-0"]},
        )
        self.assertIsNone(err)
        self.assertEqual(clean["permission"], "edit")
        self.assertEqual(clean["block_ids"], ["pets-album-0"])

    def test_open_resource_type_normalization(self) -> None:
        from apps.backend.domain.shares.catalog import canonical_resource_type

        self.assertEqual(canonical_resource_type("my_custom_thing"), "my_custom_thing")
        self.assertEqual(canonical_resource_type("Google-Calendar"), "google-calendar")
        self.assertIsNone(canonical_resource_type(""))
        self.assertIsNone(canonical_resource_type("bad id!"))


class TestGrantMatchesDashboard(unittest.TestCase):
    def test_uuid_match(self) -> None:
        from apps.backend.domain.shares.dashboard_grant import grant_matches_dashboard

        wid = uuid.uuid4()
        self.assertTrue(
            grant_matches_dashboard(
                dashboard_id=wid,
                resource_type="dashboard",
                resource_identifier=str(wid),
                dashboard_kind="custom",
            )
        )
        self.assertFalse(
            grant_matches_dashboard(
                dashboard_id=wid,
                resource_type="dashboard",
                resource_identifier="primary",
                dashboard_kind="custom",
            )
        )


class TestMailSendTool(unittest.TestCase):
    def test_compose_dry_run(self) -> None:
        from plugins.tools.integrations.mail.tools import mail as mail_tools

        uid = uuid.uuid4()
        session = mock.Mock()
        session.provider.id = "gmail"
        session.email = "me@example.com"
        with mock.patch.object(mail_tools, "resolve_mail_session", return_value=session):
            with mock.patch.object(mail_tools, "resolve_contact_email", return_value="sandra@example.com"):
                with mock.patch(
                    "apps.backend.domain.shared.identity.get_identity", return_value=(1, uid)
                ):
                    out = json.loads(
                        mail_tools.compose(
                            {
                                "to": "Sandra",
                                "subject": "Hundefotos",
                                "body": "Bitte lade Fotos hoch.",
                            }
                        )
                    )
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("dry_run"))
        self.assertEqual(out.get("to"), ["sandra@example.com"])


class TestFriendRequestTool(unittest.TestCase):
    def test_send_request_unknown_user(self) -> None:
        from plugins.tools.integrations.friends import request as fr

        uid = uuid.uuid4()
        with mock.patch.object(fr, "get_identity", return_value=(1, uid)):
            with mock.patch.object(fr, "resolve_contact_email", return_value="nobody@example.com"):
                with mock.patch.object(fr, "get_user_by_email", return_value=None):
                    out = json.loads(fr.send_request({"email": "nobody@example.com"}))
        self.assertFalse(out.get("ok"))
        self.assertIn("no AgentLayer account", out.get("error", ""))


class TestDashboardInviteMemberTool(unittest.TestCase):
    def test_invite_resolves_name(self) -> None:
        from plugins.tools.personal.dashboard import dashboard as dash_tools

        uid = uuid.uuid4()
        wid = uuid.uuid4()
        target = mock.Mock()
        target.id = uuid.uuid4()
        with mock.patch.object(dash_tools, "get_identity", return_value=(1, uid)):
            with mock.patch.object(dash_tools, "resolve_dashboard_id", return_value=(wid, None)):
                with mock.patch.object(dash_tools, "resolve_contact_email", return_value="sandra@example.com"):
                    with mock.patch.object(dash_tools, "get_user_by_email", return_value=target):
                        with mock.patch.object(dash_tools.db, "user_tenant_id", return_value=1):
                            with mock.patch.object(dash_tools.dashboard_db, "member_add", return_value=True):
                                with mock.patch.object(
                                    dash_tools.dashboard_db, "members_list", return_value=[]
                                ):
                                    out = json.loads(
                                        dash_tools.invite_member({"name": "Sandra", "role": "editor"})
                                    )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("member_email"), "sandra@example.com")


class TestMessageSendTool(unittest.TestCase):
    def test_message_dry_run_auto(self) -> None:
        from plugins.tools.integrations.messaging import message as msg_tools

        uid = uuid.uuid4()
        friend_uid = uuid.uuid4()
        with mock.patch.object(msg_tools, "get_identity", return_value=(1, uid)):
            with mock.patch.object(
                msg_tools,
                "resolve_message_recipient",
                return_value={
                    "friend_user_id": str(friend_uid),
                    "display_name": "Sandra",
                    "email": "sandra@example.com",
                    "telegram_user_id": "12345",
                    "discord_user_id": None,
                    "is_confirmed_friend": True,
                },
            ):
                out = json.loads(
                    msg_tools.send(
                        {
                            "to": "Sandra",
                            "body": "Lade Hundefotos hoch",
                            "photo_upload_hint": True,
                            "dry_run": True,
                        }
                    )
                )
        self.assertTrue(out.get("dry_run"))
        self.assertIn("Telegram-Bot", out.get("body", ""))


class TestCollectionSharePolicy(unittest.TestCase):
    def test_edit_permission_on_collection_share(self) -> None:
        clean, err = share_policy.normalize_policy(
            "collection",
            {"permission": "edit", "list_keys": ["pets"]},
        )
        self.assertIsNone(err)
        self.assertEqual(clean.get("permission"), "edit")
        self.assertEqual(clean.get("list_keys"), ["pets"])


if __name__ == "__main__":
    unittest.main()
