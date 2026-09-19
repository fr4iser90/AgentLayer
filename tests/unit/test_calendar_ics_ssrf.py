"""SSRF guard tests for the ICS fetch.

The guard (`_url_host_safe`) used to run once on the initial URL while the
client used ``follow_redirects=True``. An allowed public host answering
``302 → http://169.254.169.254/...`` was therefore followed straight to the
cloud metadata endpoint. Redirects are now followed by hand so the guard
applies to every hop.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from plugins.tools.personal.calendar import ics


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


class TestFetchIcsRedirectGuard(unittest.TestCase):
    def test_redirect_to_link_local_metadata_is_refused(self) -> None:
        client = _FakeClient(
            [
                _Resp(302, "http://169.254.169.254/latest/meta-data/"),
                _Resp(200, content=b"SECRET-METADATA"),
            ]
        )
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/a.ics")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "blocked_ssrf")
        # The internal address must never have been requested at all.
        self.assertEqual(client.requested, ["https://calendar.example.com/a.ics"])

    def test_redirect_to_loopback_is_refused(self) -> None:
        client = _FakeClient([_Resp(302, "http://127.0.0.1:8080/internal")])
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/a.ics")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "blocked_ssrf")
        self.assertEqual(len(client.requested), 1)

    def test_redirect_to_localhost_is_refused(self) -> None:
        client = _FakeClient([_Resp(302, "https://localhost/secret")])
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/a.ics")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "blocked_ssrf")

    def test_legitimate_redirect_chain_is_followed(self) -> None:
        client = _FakeClient(
            [
                _Resp(302, "https://cdn.example.net/a.ics"),
                _Resp(301, "https://hosting.example.org/feed.ics"),
                _Resp(200, content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR"),
            ]
        )
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/a.ics")
        self.assertIsNone(refusal)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            client.requested,
            [
                "https://calendar.example.com/a.ics",
                "https://cdn.example.net/a.ics",
                "https://hosting.example.org/feed.ics",
            ],
        )

    def test_relative_location_resolves_against_the_current_hop(self) -> None:
        client = _FakeClient(
            [
                _Resp(302, "feeds/next.ics"),
                _Resp(200, content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR"),
            ]
        )
        resp, refusal = ics._fetch_ics(
            client, "https://calendar.example.com/pub/a.ics"
        )
        self.assertIsNone(refusal)
        self.assertEqual(
            client.requested,
            [
                "https://calendar.example.com/pub/a.ics",
                "https://calendar.example.com/pub/feeds/next.ics",
            ],
        )

    def test_relative_location_escaping_to_internal_host_is_refused(self) -> None:
        # A relative Location that normalises onto a blocked host must still be
        # caught, because the guard runs on the resolved URL, not the raw one.
        client = _FakeClient(
            [_Resp(302, "http://[::1]/x.ics"), _Resp(200, content=b"SECRET")]
        )
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/a.ics")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "blocked_ssrf")

    def test_redirect_loop_is_bounded(self) -> None:
        hops = [_Resp(302, f"https://hop{i}.example.com/a.ics") for i in range(ics.MAX_REDIRECTS + 1)]
        hops.append(_Resp(200, content=b"never reached"))
        client = _FakeClient(hops)
        resp, refusal = ics._fetch_ics(client, "https://start.example.com/a.ics")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "too_many_redirects")
        # initial + MAX_REDIRECTS hops, no further.
        self.assertEqual(len(client.requested), ics.MAX_REDIRECTS + 1)

    def test_initial_internal_url_never_reaches_the_client(self) -> None:
        client = _FakeClient([_Resp(200)])
        resp, refusal = ics._fetch_ics(client, "http://169.254.169.254/latest/meta-data/")
        self.assertIsNone(resp)
        self.assertEqual(refusal, "blocked_ssrf")
        self.assertEqual(client.requested, [])

    def test_non_redirect_status_is_returned_as_is(self) -> None:
        client = _FakeClient([_Resp(404)])
        resp, refusal = ics._fetch_ics(client, "https://calendar.example.com/gone.ics")
        self.assertIsNone(refusal)
        self.assertEqual(resp.status_code, 404)


class TestListEventsSurfacesRefusal(unittest.TestCase):
    """The refusal must reach the caller as an error, not a silent empty result."""

    def test_redirect_refusal_becomes_an_error_response(self) -> None:
        client = _FakeClient([_Resp(302, "http://169.254.169.254/latest/meta-data/")])

        with mock.patch.object(
            ics, "_ics_url_for_user", return_value="https://calendar.example.com/a.ics"
        ):
            with mock.patch.object(ics.httpx, "Client", return_value=_ClientCtx(client)):
                out = json.loads(ics.list_events({"days_ahead": 7}))

        self.assertFalse(out["ok"])
        self.assertIn("ics_url not allowed", out["error"])
        self.assertIn("blocked_ssrf", out["error"])
        self.assertEqual(client.requested, ["https://calendar.example.com/a.ics"])

    def test_blocked_initial_url_becomes_an_error_response(self) -> None:
        # _ics_url_for_user guards the stored URL itself; a bypass attempt must
        # still be refused by the fetch rather than reaching the network.
        client = _FakeClient([_Resp(200, content=b"SECRET")])
        with mock.patch.object(
            ics, "_ics_url_for_user", return_value="http://metadata.google.internal/"
        ):
            with mock.patch.object(ics.httpx, "Client", return_value=_ClientCtx(client)):
                out = json.loads(ics.list_events({"days_ahead": 7}))

        self.assertFalse(out["ok"])
        self.assertIn("ics_url not allowed", out["error"])
        self.assertEqual(client.requested, [])


class _ClientCtx:
    def __init__(self, inner: _FakeClient) -> None:
        self._inner = inner

    def __enter__(self) -> _FakeClient:
        return self._inner

    def __exit__(self, *exc: object) -> bool:
        return False


if __name__ == "__main__":
    unittest.main()
