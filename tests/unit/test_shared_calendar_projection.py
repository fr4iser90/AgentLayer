"""Principle 1 for the shared-calendar adapter (ADR 0014).

Google's "secret address in iCal format" is a **bearer credential**: whoever
holds it can read that calendar until it is rotated. The friend-share path
used to resolve the owner's secret into a value the *requesting* side then
held and passed around — one leaked tool result, chat line or log entry would
hand out permanent read access to someone else's calendar.

``fetch_shared_calendar`` resolves the URL, guards it and fetches it inside
the adapter, and returns events only. These tests pin that the credential
never leaves it.
"""

from __future__ import annotations

import json
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from plugins.tools.personal.calendar import ics

OWNER_SECRET = (
    "https://calendar.google.com/calendar/ical/s3cr3t-owner%40group/"
    "private-a1b2c3d4/basic.ics"
)


def _ics_bytes(*summaries: str) -> bytes:
    """A valid VCALENDAR whose events sit inside any plausible share window."""
    base = datetime.now(UTC) + timedelta(hours=2)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//agentlayer//test//EN"]
    for i, summary in enumerate(summaries):
        start = base + timedelta(days=i)
        end = start + timedelta(hours=1)
        lines += [
            "BEGIN:VEVENT",
            f"UID:evt-{i}@agentlayer.test",
            f"SUMMARY:{summary}",
            "DTSTART:" + start.strftime("%Y%m%dT%H%M%SZ"),
            "DTEND:" + end.strftime("%Y%m%dT%H%M%SZ"),
            "LOCATION:Vor Ort",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


class _Resp:
    def __init__(
        self,
        status_code: int = 200,
        location: str | None = None,
        content: bytes = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", "replace")
        self.headers: dict[str, str] = {} if location is None else {"location": location}


class _FakeClient:
    """Stands in for httpx.Client; records every URL actually requested."""

    def __init__(self, responses: list[_Resp]) -> None:
        self._responses = list(responses)
        self.requested: list[str] = []

    def get(self, url: str, headers: dict | None = None) -> _Resp:
        self.requested.append(url)
        if not self._responses:
            raise AssertionError(f"no scripted response left for {url}")
        return self._responses.pop(0)


class _ClientCtx:
    def __init__(self, inner: _FakeClient) -> None:
        self._inner = inner

    def __enter__(self) -> _FakeClient:
        return self._inner

    def __exit__(self, *exc: object) -> bool:
        return False


def _run(shared_secret: str | None, responses: list[_Resp]):
    """Drive fetch_shared_calendar with the owner's secret and canned HTTP."""
    owner = uuid.uuid4()
    caller = uuid.uuid4()
    client = _FakeClient(responses)

    secrets: list[tuple[uuid.UUID, str]] = []

    def fake_secret_get(uid, service_key):
        secrets.append((uid, service_key))
        if service_key == "google_calendar" and shared_secret is not None:
            return json.dumps({"ics_url": shared_secret})
        return None

    with mock.patch.object(ics.db, "user_secret_get_plaintext", side_effect=fake_secret_get):
        # The shared path must not consult the request identity at all: doing
        # so is how a share ends up reading the caller's own calendar.
        with mock.patch.object(ics, "get_identity") as identity:
            with mock.patch.object(ics.httpx, "Client", return_value=_ClientCtx(client)):
                result = ics.fetch_shared_calendar(owner, days_ahead=7)

    return result, owner, caller, secrets, client, identity


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


# Names that would mean a credential escaped the adapter. Note that checking the
# serialized blob for the substring "ics_url" is not enough: ``source_hint``
# legitimately takes that exact string as its *value* for non-Google hosts.
_CREDENTIAL_KEYS = {"ics_url", "url", "secret", "token", "ciphertext", "api_key"}


class TestSharedCalendarNeverReturnsTheCredential(unittest.TestCase):
    def test_events_are_returned(self) -> None:
        result, *_ = _run(OWNER_SECRET, [_Resp(200, content=_ics_bytes("Zahnarzt", "Urlaub"))])
        self.assertTrue(result["ok"])
        self.assertEqual([e["summary"] for e in result["events"]], ["Zahnarzt", "Urlaub"])

    def test_the_url_is_not_anywhere_in_the_result(self) -> None:
        result, *_ = _run(OWNER_SECRET, [_Resp(200, content=_ics_bytes("Zahnarzt"))])
        blob = json.dumps(result)
        self.assertNotIn(OWNER_SECRET, blob)
        # Not even a fragment: the private hash and the encoded owner address.
        for fragment in ("private-a1b2c3d4", "s3cr3t-owner", "basic.ics", "ical/"):
            self.assertNotIn(fragment, blob)
        self.assertEqual(
            [k for k in _all_keys(result) if k.lower() in _CREDENTIAL_KEYS], []
        )

    def test_a_non_google_host_is_labelled_without_leaking_its_address(self) -> None:
        # source_hint is a label, not a handle: for a non-Google feed it is the
        # literal string "ics_url", which must not be mistaken for the address.
        result, *_ = _run(
            "https://cloud.example.net/remote.php/dav/calendars/lena/private.ics",
            [_Resp(200, content=_ics_bytes("Zahnarzt"))],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_hint"], "ics_url")
        blob = json.dumps(result)
        self.assertNotIn("cloud.example.net", blob)
        self.assertNotIn("private.ics", blob)
        self.assertEqual(
            [k for k in _all_keys(result) if k.lower() in _CREDENTIAL_KEYS], []
        )

    def test_only_a_non_reversable_source_hint_is_kept(self) -> None:
        result, *_ = _run(OWNER_SECRET, [_Resp(200, content=_ics_bytes("Zahnarzt"))])
        self.assertEqual(result["source_hint"], "google_ical")

    def test_the_by_month_projection_is_not_part_of_the_share(self) -> None:
        # The share widget needs a flat event list; the extra title projection
        # is a planning aid for the owner's own tool call, not for grantees.
        result, *_ = _run(OWNER_SECRET, [_Resp(200, content=_ics_bytes("A", "B"))])
        self.assertNotIn("by_month", result)


class TestSharedCalendarReadsTheOwner(unittest.TestCase):
    def test_the_secret_is_read_for_the_owner_not_the_caller(self) -> None:
        result, owner, caller, secrets, _, _ = _run(
            OWNER_SECRET, [_Resp(200, content=_ics_bytes("Zahnarzt"))]
        )
        self.assertTrue(result["ok"])
        self.assertTrue(secrets)
        for uid, _key in secrets:
            self.assertEqual(uid, owner)
            self.assertNotEqual(uid, caller)

    def test_the_request_identity_is_never_consulted(self) -> None:
        _result, _owner, _caller, _secrets, _client, identity = _run(
            OWNER_SECRET, [_Resp(200, content=_ics_bytes("Zahnarzt"))]
        )
        identity.assert_not_called()


class TestSharedCalendarGuardsTheFetch(unittest.TestCase):
    def test_internal_owner_url_is_refused_before_any_request(self) -> None:
        result, *_ = _run("http://169.254.169.254/latest/meta-data/", [])
        self.assertFalse(result["ok"])
        self.assertIn("blocked_ssrf", result["error"])

    def test_redirect_from_the_owners_host_to_internal_is_refused(self) -> None:
        # The share path reuses the per-hop guard, so an owner (or a hostile
        # redirect service behind the owner's domain) cannot pivot the server.
        result, *_ = _run(
            "https://calendar.example.com/feed.ics",
            [_Resp(302, "http://127.0.0.1:8080/internal"), _Resp(200, content=b"SECRET")],
        )
        self.assertFalse(result["ok"])
        self.assertIn("blocked_ssrf", result["error"])

    def test_missing_owner_secret_is_reported_explicitly(self) -> None:
        result, *_ = _run(None, [])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "owner_has_no_calendar_configured")

    def test_the_horizon_is_clamped_to_the_allowed_maximum(self) -> None:
        result, *_ = _run(
            "https://calendar.example.com/feed.ics",
            [_Resp(200, content=_ics_bytes("Zahnarzt"))],
        )
        # days_ahead=7 in the helper above; clamp behaviour is checked below.
        self.assertLessEqual(result["window"]["effective_days_ahead"], ics.MAX_EFFECTIVE_DAYS_AHEAD)

    def test_a_huge_request_is_clamped_not_rejected(self) -> None:
        owner = uuid.uuid4()
        client = _FakeClient([_Resp(200, content=_ics_bytes("Zahnarzt"))])
        with mock.patch.object(
            ics.db,
            "user_secret_get_plaintext",
            return_value=json.dumps({"ics_url": "https://calendar.example.com/feed.ics"}),
        ):
            with mock.patch.object(ics.httpx, "Client", return_value=_ClientCtx(client)):
                result = ics.fetch_shared_calendar(owner, days_ahead=100000)
        self.assertTrue(result["ok"])
        self.assertLessEqual(result["window"]["effective_days_ahead"], ics.MAX_EFFECTIVE_DAYS_AHEAD)

    def test_a_non_numeric_horizon_falls_back_to_the_default(self) -> None:
        owner = uuid.uuid4()
        client = _FakeClient([_Resp(200, content=_ics_bytes("Zahnarzt"))])
        with mock.patch.object(
            ics.db,
            "user_secret_get_plaintext",
            return_value=json.dumps({"ics_url": "https://calendar.example.com/feed.ics"}),
        ):
            with mock.patch.object(ics.httpx, "Client", return_value=_ClientCtx(client)):
                result = ics.fetch_shared_calendar(owner, days_ahead="sieben")  # type: ignore[arg-type]
        self.assertTrue(result["ok"])
        self.assertEqual(result["window"]["days_ahead"], 7)


if __name__ == "__main__":
    unittest.main()
