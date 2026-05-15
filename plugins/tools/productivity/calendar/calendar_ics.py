"""Read-only calendar events from a user-provided ICS (iCal) URL (Google secret iCal, Nextcloud, …)."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from icalendar import Calendar

from apps.backend.core.config import config
from apps.backend.infrastructure.db import db
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure.secret_otp_bundle import secret_otp_bundle

logger = logging.getLogger(__name__)

__version__ = "1.2.0"
TOOL_ID = "calendar_ics"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "calendar"
TOOL_LABEL = "Calendar"
TOOL_DESCRIPTION = (
    "Read events from ICS/iCal URLs (Google Calendar secret link, Nextcloud, etc.). "
    "Use for work shifts, hours, and time off when the user asks — no need for them to say \"calendar\" explicitly."
)
# Router: registry matches user text (lowercased) by **substring** against each entry; union of categories → tools[].
# Keep triggers in this module only — not in ``tool_routing.py``.
TOOL_TRIGGERS = (
    "calendar",
    "kalender",
    "ical",
    "ics",
    "schedule",
    "appointment",
    "termine",
    "schicht",
    "arbeitszeit",
    "dienstplan",
    "schichtplan",
    "feiertag",
    "urlaub",
    "shift",
    "work schedule",
    "next shift",
    "time off",
    "days off",
    "when do i work",
    "when am i working",
    "wann muss ich",
    "wann arbeite",
    "wieder arbeiten",
    "nächste schicht",
)
TOOL_CAPABILITIES = ("calendar.read",)

# Try Google-specific key first (same JSON shape), then generic ICS.
SECRET_KEYS_TRY_ORDER: tuple[str, ...] = ("google_calendar", "calendar_ics")

# Catalog: both keys (same JSON); runtime tries ``google_calendar`` first, then ``calendar_ics``.
TOOL_SECRETS_REQUIRED = ("google_calendar", "calendar_ics")
_TOOL_ICS_FORM: dict[str, Any] = {
    "title": "Calendar (HTTPS iCal / ICS URL)",
    "help": (
        "Read-only feed URL (must be https://). Google Calendar: calendar.google.com → gear → Settings for your "
        "calendar → **Integrate calendar** → *Secret address in iCal format* (…/basic.ics). "
        "Nextcloud / others: use their “subscribe” HTTPS ICS link. "
        "If you already saved the same JSON under **google_calendar**, you do not need a second secret — "
        "the tool tries that key first, then **calendar_ics**."
    ),
    "fields": [
        {
            "name": "ics_url",
            "label": "ICS / iCal HTTPS URL",
            "type": "text",
            "required": True,
        },
    ],
}
TOOL_USER_SECRET_FORMS: dict[str, dict[str, Any]] = {
    "calendar_ics": dict(_TOOL_ICS_FORM),
    # Same JSON shape; lets users who prefer the Google-specific key get the same form in the UI.
    "google_calendar": {
        **_TOOL_ICS_FORM,
        "title": "Google Calendar (secret iCal URL)",
        "help": (
            "Same as **calendar_ics**: store `{\"ics_url\":\"https://calendar.google.com/calendar/ical/…/basic.ics\"}`. "
            "Google: Settings for the calendar → Integrate calendar → *Secret address in iCal format*. "
            "The agent tries **google_calendar** before **calendar_ics**."
        ),
    },
}

HTTP_TIMEOUT = 45.0
MAX_ICS_BYTES = 2_000_000
MAX_EVENTS_RETURN = 120
MAX_TITLES_PER_MONTH = 30
# ~24 months forward + margin
MAX_EFFECTIVE_DAYS_AHEAD = 800
MAX_EFFECTIVE_DAYS_BACK = 400


def _url_host_safe(url: str) -> tuple[bool, str]:
    try:
        p = urlparse(url.strip())
    except Exception:
        return False, "bad_url"
    if p.scheme not in ("http", "https"):
        return False, "blocked_scheme"
    host = (p.hostname or "").lower()
    if not host:
        return False, "blocked_scheme"
    if host == "localhost" or host.endswith(".localhost"):
        return False, "blocked_ssrf"
    if host in ("metadata.google.internal", "metadata.goog"):
        return False, "blocked_ssrf"
    h = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False, "blocked_ssrf"
    except ValueError:
        pass
    if re.match(r"^(127\.|169\.254\.)", host):
        return False, "blocked_ssrf"
    return True, ""


def _parse_secret(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    u = str(obj.get("ics_url") or obj.get("url") or "").strip()
    return u or None


def _ics_url_for_user() -> str | dict[str, Any]:
    _tid, uid = get_identity()
    if uid is None:
        return {
            "ok": False,
            "error": "No user identity in this request (need chat/user headers for per-user calendar secrets).",
        }
    url: str | None = None
    for sk in SECRET_KEYS_TRY_ORDER:
        raw = db.user_secret_get_plaintext(uid, sk)
        u = _parse_secret(raw)
        if u:
            url = u
            break
    if not url:
        return {
            "ok": False,
            "error": (
                "No calendar ICS URL stored. In the web app: **Settings → Connections**, pick **calendar_ics** or "
                "**google_calendar** and paste the HTTPS iCal URL (saved as JSON with key `ics_url`). "
                "Or use chat tool **register_secrets** with service_key_example `google_calendar` or `calendar_ics` "
                'and the OTP curl — same JSON shape: {"ics_url":"https://..."}.'
            ),
            "google_calendar_setup_de": (
                "Google Kalender (read-only, ohne OAuth): In calendar.google.com → Zahnrad → Einstellungen → "
                "links die richtige Kalenderzeile wählen → „Geheime Adresse im iCal-Format“ kopieren "
                "(beginnt mit https://calendar.google.com/calendar/ical/…/basic.ics). "
                "Diese URL per register_secrets + OTP als Secret unter service_key **google_calendar** speichern "
                "(oder **calendar_ics** — gleiches JSON). Niemals die URL in den Chat posten."
            ),
            "nextcloud_setup_de": (
                "Nextcloud: Kalender öffnen → Teilen / Link zum Abonnieren → HTTPS-ICS-URL; "
                'als calendar_ics mit {"ics_url":"…"} speichern.'
            ),
        }
    ok, reason = _url_host_safe(url)
    if not ok:
        return {"ok": False, "error": f"ics_url not allowed ({reason})"}
    return url


def _to_utc_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        # ✅ Fix icalendar vDatetime Bug: native datetime casten ZUERST!
        # vDatetime.astimezone() ist seit 2019 kaputt und macht gar nichts
        native = datetime(
            val.year, val.month, val.day,
            val.hour, val.minute, val.second, val.microsecond,
            val.tzinfo
        )
        return native.astimezone(UTC)
    if isinstance(val, date):
        return datetime.combine(val, time.min, tzinfo=UTC)
    return None


def _event_bounds(comp: Any) -> tuple[datetime | None, datetime | None]:
    ds = comp.get("dtstart")
    de = comp.get("dtend")
    dur = comp.get("duration")
    start_raw = ds.dt if ds is not None else None
    end_raw = de.dt if de is not None else None
    start = _to_utc_datetime(start_raw)
    end = _to_utc_datetime(end_raw)
    if start and end is None and dur is not None:
        try:
            delta = dur.dt
            if isinstance(delta, timedelta):
                end = start + delta
        except Exception:
            pass
    if start and end is None:
        if isinstance(start_raw, date) and not isinstance(start_raw, datetime):
            end = start + timedelta(days=1)
        else:
            end = start + timedelta(hours=1)
    return start, end


def _overlaps(
    ev_start: datetime | None,
    ev_end: datetime | None,
    win_start: datetime,
    win_end: datetime,
) -> bool:
    if ev_start is None:
        return False
    if ev_end is None:
        ev_end = ev_start + timedelta(hours=1)
    return ev_start < win_end and ev_end > win_start


def _int_arg(arguments: dict[str, Any], key: str, default: int) -> int:
    v = arguments.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# Small models (e.g. Nemotron) sometimes emit wrong keys: monthsahead, dayesahead, …
_CAL_ARG_ALIASES: dict[str, str] = {
    "monthsahead": "months_ahead",
    "daysahead": "days_ahead",
    "daysback": "days_back",
    "monthsback": "months_back",
    "includebymonth": "include_by_month",
}


def _normalize_calendar_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (arguments or {}).items():
        flat = str(k).lower().replace("-", "").replace("_", "")
        canon = _CAL_ARG_ALIASES.get(flat)
        if canon is not None:
            out[canon] = v
        else:
            out[k] = v
    return out


def calendar_ics_list_events(arguments: dict[str, Any]) -> str:
    arguments = _normalize_calendar_arguments(arguments)

    url_or_err = _ics_url_for_user()
    if isinstance(url_or_err, dict):
        err: dict[str, Any] = dict(url_or_err)
        if config.SECRETS_MASTER_KEY:
            try:
                err["otp_registration"] = secret_otp_bundle.build_otp_curl_payload(
                    "google_calendar", 600
                )
                err["one_shot_registration_de"] = (
                    "Noch kein Kalender-Secret: **kein zweiter Tool-Call nötig.** "
                    "Der Nutzer verwendet `otp_registration` → `curl_bash` oder `jq_register_example_de` "
                    "aus **dieser** Tool-Antwort (eine Zeile, lokal ausführen, echte iCal-URL einsetzen, nie in den Chat). "
                    "Nach `stored:true` erneut `calendar_ics_list_events` aufrufen. "
                    "Entspricht demselben OTP-Flow wie `register_secrets` mit service_key **google_calendar**."
                )
            except Exception:
                logger.exception("calendar: failed to attach otp_registration bundle")
        else:
            err["otp_registration_unavailable_de"] = (
                "OTP-Einbettung aus: Betreiber muss AGENT_SECRETS_MASTER_KEY setzen. "
                "Sonst manuell Tool register_secrets mit service_key_example google_calendar."
            )
        return json.dumps(err, ensure_ascii=False)
    url = url_or_err

    days_ahead = _int_arg(arguments, "days_ahead", 14)
    days_back = _int_arg(arguments, "days_back", 0)
    months_ahead = _int_arg(arguments, "months_ahead", 0)
    months_back = _int_arg(arguments, "months_back", 0)
    days_ahead = max(0, min(days_ahead, 366))
    days_back = max(0, min(days_back, 366))
    months_ahead = max(0, min(months_ahead, 24))
    months_back = max(0, min(months_back, 12))
    include_by_month = arguments.get("include_by_month")
    if include_by_month is None:
        by_month_default = True
    elif isinstance(include_by_month, bool):
        by_month_default = include_by_month
    else:
        s = str(include_by_month).strip().lower()
        by_month_default = s in ("1", "true", "yes", "on")

    now = datetime.now(UTC)
    
    # ✅ Korrekte Kalender Monat Berechnung statt * 31
    win_end = now + timedelta(days=days_ahead) + relativedelta(months=+months_ahead)
    win_start = now - timedelta(days=days_back) - relativedelta(months=months_back)
    
    # Noch immer Limits respektieren
    max_win_end = now + timedelta(days=MAX_EFFECTIVE_DAYS_AHEAD)
    max_win_start = now - timedelta(days=MAX_EFFECTIVE_DAYS_BACK)
    
    if win_end > max_win_end:
        win_end = max_win_end
    if win_start < max_win_start:
        win_start = max_win_start

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            r = client.get(
                url, headers={"User-Agent": "jetpack-agent-layer-calendar/1.0"}
            )
    except httpx.HTTPError as e:
        return json.dumps(
            {"ok": False, "error": f"fetch failed: {e}"}, ensure_ascii=False
        )

    if r.status_code >= 400:
        return json.dumps(
            {"ok": False, "error": f"http {r.status_code}", "detail": r.text[:300]},
            ensure_ascii=False,
        )
    raw_bytes = r.content
    if len(raw_bytes) > MAX_ICS_BYTES:
        return json.dumps(
            {"ok": False, "error": f"ics larger than {MAX_ICS_BYTES} bytes"},
            ensure_ascii=False,
        )
    try:
        text = raw_bytes.decode("utf-8", errors="replace")
        cal = Calendar.from_ical(text)
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"parse ics failed: {e}"}, ensure_ascii=False
        )

    events_out: list[dict[str, Any]] = []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        summary = str(comp.get("summary") or "").strip() or "(no title)"
        uid = str(comp.get("uid") or "")[:200]
        loc = str(comp.get("location") or "").strip()
        ev_start, ev_end = _event_bounds(comp)
        if not _overlaps(ev_start, ev_end, win_start, win_end):
            continue
        events_out.append(
            {
                "summary": summary[:500],
                "uid": uid,
                "location": loc[:300] if loc else None,
                "start": ev_start.isoformat() if ev_start else None,
                "end": ev_end.isoformat() if ev_end else None,
            }
        )

    events_out.sort(key=lambda x: (x.get("start") or "", x.get("summary") or ""))
    if len(events_out) > MAX_EVENTS_RETURN:
        events_out = events_out[:MAX_EVENTS_RETURN]
        truncated = True
    else:
        truncated = False

    by_month_payload: dict[str, Any] | None = None
    if by_month_default and events_out:
        titles_by_month: dict[str, list[str]] = defaultdict(list)
        for e in events_out:
            st = e.get("start") or ""
            ym = st[:7] if len(st) >= 7 and st[4:5] == "-" else "undated"
            titles_by_month[ym].append(str(e.get("summary") or "")[:200])
        by_month_payload = {}
        for ym in sorted(titles_by_month.keys()):
            titles = titles_by_month[ym][:MAX_TITLES_PER_MONTH]
            by_month_payload[ym] = {
                "count": len(titles_by_month[ym]),
                "titles": titles,
                "truncated": len(titles_by_month[ym]) > MAX_TITLES_PER_MONTH,
            }

    out: dict[str, Any] = {
        "ok": True,
        "source_hint": (
            "google_ical" if "calendar.google.com" in url.lower() else "ics_url"
        ),
        "window": {
            "from": win_start.isoformat(),
            "to": win_end.isoformat(),
            "days_back": days_back,
            "days_ahead": days_ahead,
            "months_back": months_back,
            "months_ahead": months_ahead,
            "effective_days_back": (now - win_start).days,
            "effective_days_ahead": (win_end - now).days,
        },
        "count": len(events_out),
        "truncated": truncated,
        "events": events_out,
    }
    if by_month_payload is not None:
        out["by_month"] = by_month_payload

    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "calendar_ics_list_events": calendar_ics_list_events,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "calendar_ics_list_events",
            "TOOL_DESCRIPTION": (
                "List calendar events from the user's secret ICS/iCal HTTPS URL. "
                "If no secret is stored yet, the response still includes otp_registration (curl_bash / jq) "
                "for service_key google_calendar — same OTP flow as register_secrets; user runs curl locally once, then call this tool again. "
                "Google: secret iCal URL from Calendar settings. Use months_ahead for multi-month overview; optional by_month. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Extra days forward (0–366, default 14). Added to months_ahead×31.",
                    },
                    "days_back": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Extra days into the past (0–366, default 0). Added to months_back×31.",
                    },
                    "months_ahead": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Whole months forward (0–24, default 0). E.g. 6 with days_ahead 0 ≈ half a year.",
                    },
                    "months_back": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Whole months backward (0–12, default 0).",
                    },
                    "include_by_month": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "If true (default), add by_month: YYYY-MM → counts and titles for planning.",
                    },
                },
            },
        },
    },
]