"""
Iterative HTML “mini product” loop (library module).

LLM loop: generate HTML → static checks → LLM QA JSON → if issues, next round with feedback.
Output: ``workflows/creative/output/iterative-html/<timestamp>/``.

**Start from chat:** tool ``run_iterative_html_build`` (see ``plugins/tools/capabilities/creative/run_iterative_html_build.py``)
with ``goal`` and optional ``assets``. Images the user attached in the same chat turn are merged in
server-side (filenames preserved) — the model does not need to repeat them as base64 in ``assets``.
This file is **not** registered as a cron job
(no ``RUN_EVERY_MINUTES``).

**Configuration:** the chat tool always passes ``arguments["goal"]`` from the user/model.
``WORKFLOW_PRODUCT_GOAL`` is only a fallback when ``goal`` is missing (direct Python call / tests).
Model via global Ollama / ``AGENT_MODEL_PROFILE_*``; max rounds = ``AGENT_MAX_TOOL_ROUNDS``.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.backend.core.config import config
from apps.backend.domain.agent import chat_completion

logger = logging.getLogger(__name__)

__version__ = "1.1.0"

_MAX_HTML_CHARS = 160_000
_MAX_ASSET_FILES = 5
_MAX_ASSET_DECODED_BYTES = 400_000
_MAX_DATA_URL_INLINE_CHARS = 45_000
_ALLOWED_IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml"}
)


def _max_rounds() -> int:
    """Align with agent chat tool-loop limit (``AGENT_MAX_TOOL_ROUNDS``)."""
    return max(1, min(int(config.MAX_TOOL_ROUNDS), 32))


# Fallback only when ``arguments["goal"]`` is absent — not used by ``run_iterative_html_build`` from chat.
WORKFLOW_PRODUCT_GOAL = """Build one static index.html (inline CSS/JS only): a simple page with a
clear title and short body text; responsive layout. Reply each round with only the HTML document
(optional ```html … ``` fence)."""


def _goal(arguments: dict[str, Any] | None) -> str:
    if isinstance(arguments, dict):
        for key in ("goal", "description", "brief", "prompt"):
            g = arguments.get(key)
            if isinstance(g, str) and g.strip():
                return g.strip()
    return WORKFLOW_PRODUCT_GOAL.strip()


def _safe_asset_filename(name: str, idx: int) -> str:
    raw = (name or "").strip() or f"asset_{idx}"
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)[:120]
    return s or f"asset_{idx}"


def _materialize_assets(arguments: dict[str, Any], session_dir: Path) -> tuple[str, list[str]]:
    """
    Decode optional ``assets`` list into ``session_dir/uploads/`` and return (prompt_block, warnings).
    Each item: ``{name?, media_type|mime_type, data_base64}``.
    """
    warnings: list[str] = []
    raw = arguments.get("assets") if isinstance(arguments, dict) else None
    if not isinstance(raw, list) or not raw:
        return "", warnings

    upload_dir = session_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    for i, item in enumerate(raw[:_MAX_ASSET_FILES]):
        if not isinstance(item, dict):
            warnings.append(f"assets[{i}]: skipped (not an object)")
            continue
        fname = _safe_asset_filename(
            str(item.get("name") or item.get("filename") or ""),
            i,
        )
        mt = str(item.get("media_type") or item.get("mime_type") or "").strip().lower()
        if mt == "image/jpg":
            mt = "image/jpeg"
        b64 = item.get("data_base64")
        if not isinstance(b64, str) or not b64.strip():
            warnings.append(f"assets[{i}] {fname}: missing data_base64")
            continue
        try:
            data = base64.b64decode(b64.strip(), validate=True)
        except Exception:
            warnings.append(f"assets[{i}] {fname}: invalid base64")
            continue
        if len(data) > _MAX_ASSET_DECODED_BYTES:
            warnings.append(f"assets[{i}] {fname}: too large (max {_MAX_ASSET_DECODED_BYTES} bytes)")
            continue
        if mt not in _ALLOWED_IMAGE_TYPES:
            warnings.append(
                f"assets[{i}] {fname}: unsupported type {mt!r} "
                f"(allowed: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))})"
            )
            continue
        if mt == "image/svg+xml" and len(data) > 50_000:
            warnings.append(f"assets[{i}] {fname}: SVG too large (max 50000 bytes)")
            continue

        dest = upload_dir / fname
        dest.write_bytes(data)
        data_url = f"data:{mt};base64,{base64.standard_b64encode(data).decode('ascii')}"
        if len(data_url) <= _MAX_DATA_URL_INLINE_CHARS:
            lines.append(
                f"### {fname} ({mt})\n"
                f"On disk: `uploads/{fname}`. **Embed in HTML** with e.g. "
                f"`<img alt=\"{fname}\" src=\"{data_url}\" />` (data URL is authoritative for this run).\n"
            )
        else:
            lines.append(
                f"### {fname} ({mt})\n"
                f"Saved under `uploads/{fname}` ({len(data)} bytes). Too large to repeat full data URL "
                "here — use a smaller image if the page must inline it.\n"
            )

    if not lines:
        return "", warnings
    block = (
        "\n## User-supplied assets\n"
        "Use these in the page when the product goal asks for them (images, mascot, etc.).\n\n"
        + "\n".join(lines)
    )
    return block, warnings


_BUILDER_SYSTEM = """You are a meticulous front-end developer. You MUST output one self-contained HTML5
document (inline CSS and JS only — no external URLs except optional https fonts if truly needed).
Follow the user's product goal exactly. If the user lists QA issues from a prior attempt, fix every
blocking issue before returning the next version."""

_VALIDATOR_SYSTEM = """You are a strict QA reviewer for a static HTML deliverable.
Given the PRODUCT GOAL and the HTML source, decide if the HTML satisfies the goal for a static demo.

Reply with JSON ONLY, no markdown fences, no prose:
{"valid": true}
or
{"valid": false, "issues": ["short actionable issue 1", "issue 2", ...]}

Use at most 8 issues. Mark valid:true only if the HTML clearly implements the goal (including any
animation / layout requirements). Minor cosmetic nits are not blocking."""


def _output_dir() -> Path:
    p = Path(__file__).resolve().parent / "output" / "iterative-html"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _strip_outer_fence(text: str) -> str:
    s = text.strip()
    m = re.match(r"^```(?:html|HTML)?\s*\r?\n([\s\S]*?)\r?\n```\s*$", s)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```(?:html|HTML)?\s*\r?\n([\s\S]*?)\r?\n```", s)
    if m2:
        return m2.group(1).strip()
    return s


def _extract_html(raw: str) -> str | None:
    body = _strip_outer_fence(raw)
    low = body.lower()
    if "<html" in low or "<!doctype" in low:
        if len(body) > _MAX_HTML_CHARS:
            return None
        return body
    return None


def _static_sanity(html: str) -> list[str]:
    issues: list[str] = []
    low = html.lower()
    if len(html) < 120:
        issues.append("HTML seems too short to be a full page.")
    if "<html" not in low:
        issues.append("Missing <html> root element.")
    if "</html>" not in low:
        issues.append("Missing closing </html> tag.")
    if "<script" in low and "src=" in low:
        issues.append("External <script src=…> is discouraged; use inline JS only for this workflow.")
    return issues


def _parse_validator_json(raw: str) -> dict[str, Any]:
    s = raw.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    i = s.find("{")
    j = s.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(s[i : j + 1])
        except json.JSONDecodeError:
            pass
    return {"valid": False, "issues": ["validator did not return parseable JSON"]}


async def _llm(messages: list[dict[str, Any]], *, temperature: float, max_tokens: int) -> str:
    body: dict[str, Any] = {
        "stream": False,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Registry tools are merged by default; inner HTML/validator calls must be plain text-only
        # or some models (e.g. Nemotron via Ollama) fail with tool-template XML errors.
        "agent_plain_completion": True,
    }
    out = await chat_completion(body)
    try:
        return str(out["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected chat_completion shape: {e}") from e


def _run_llm(messages: list[dict[str, Any]], *, temperature: float, max_tokens: int) -> str:
    """
    ``chat_completion`` is async; this workflow is sync. ``asyncio.run()`` is invalid when the
    caller already has a running loop (e.g. FastAPI tool handler), so we isolate ``asyncio.run``
    in a short-lived thread in that case.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_llm(messages, temperature=temperature, max_tokens=max_tokens))

    def _in_thread() -> str:
        return asyncio.run(_llm(messages, temperature=temperature, max_tokens=max_tokens))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_in_thread).result()


def iterative_html_build(arguments: dict[str, Any]) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    goal = _goal(args)
    max_rounds = _max_rounds()
    out_dir = _output_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = out_dir / stamp
    session_dir.mkdir(parents=True, exist_ok=True)

    if not goal:
        return json.dumps({"ok": False, "error": "empty goal"}, ensure_ascii=False)

    asset_block, asset_warnings = _materialize_assets(args, session_dir)
    if asset_warnings:
        (session_dir / "asset_warnings.txt").write_text("\n".join(asset_warnings), encoding="utf-8")

    full_goal = goal + (asset_block if asset_block else "")
    if len(full_goal) > 120_000:
        return json.dumps(
            {
                "ok": False,
                "error": "goal + inlined assets exceed ~120000 characters; use fewer or smaller images.",
                "asset_warnings": asset_warnings,
            },
            ensure_ascii=False,
        )

    logger.info(
        "iterative_html_build: session=%s rounds_max=%d (AGENT_MAX_TOOL_ROUNDS=%s)",
        session_dir.name,
        max_rounds,
        config.MAX_TOOL_ROUNDS,
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _BUILDER_SYSTEM},
        {
            "role": "user",
            "content": (
                "PRODUCT GOAL:\n"
                + full_goal
                + "\n\nReturn one complete HTML5 document only (optional ```html fence). "
                "No explanations outside the document."
            ),
        },
    ]

    last_html = ""
    rounds_meta: list[dict[str, Any]] = []

    for round_i in range(1, max_rounds + 1):
        logger.info("iterative_html_build: round %d/%d", round_i, max_rounds)
        try:
            raw = _run_llm(messages, temperature=0.35, max_tokens=8192)
        except Exception as e:
            logger.exception("builder LLM failed")
            rounds_meta.append({"round": round_i, "error": str(e)})
            break

        (session_dir / f"round-{round_i}-raw.txt").write_text(raw, encoding="utf-8")
        html = _extract_html(raw)
        if not html:
            fb = (
                "Your last message was not a single parseable HTML document. "
                "Return exactly one HTML5 file, optionally wrapped in a ```html code fence."
            )
            messages.append({"role": "assistant", "content": raw[:8000]})
            messages.append({"role": "user", "content": fb})
            rounds_meta.append({"round": round_i, "parse_error": True})
            continue

        last_html = html
        (session_dir / f"round-{round_i}.html").write_text(html, encoding="utf-8")

        static_issues = _static_sanity(html)
        val_messages = [
            {"role": "system", "content": _VALIDATOR_SYSTEM},
            {
                "role": "user",
                "content": "PRODUCT GOAL:\n"
                + full_goal
                + "\n\nHTML:\n"
                + html[: min(len(html), 50_000)],
            },
        ]
        try:
            vraw = _run_llm(val_messages, temperature=0.1, max_tokens=900)
        except Exception as e:
            logger.exception("validator LLM failed")
            rounds_meta.append({"round": round_i, "validator_error": str(e)})
            break

        (session_dir / f"round-{round_i}-validator.txt").write_text(vraw, encoding="utf-8")
        vobj = _parse_validator_json(vraw)
        llm_issues: list[str] = []
        if vobj.get("valid") is True:
            llm_ok = True
        else:
            llm_ok = False
            raw_issues = vobj.get("issues")
            if isinstance(raw_issues, list):
                llm_issues = [str(x).strip() for x in raw_issues if str(x).strip()][:8]

        all_issues = [*static_issues, *llm_issues]
        rounds_meta.append(
            {
                "round": round_i,
                "static_issues": static_issues,
                "llm_valid": bool(llm_ok),
                "llm_issues": llm_issues,
            }
        )

        if llm_ok and not static_issues:
            final_path = session_dir / "index.html"
            final_path.write_text(html, encoding="utf-8")
            (session_dir / "report.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "rounds": round_i,
                        "final": str(final_path),
                        "goal": goal,
                        "asset_warnings": asset_warnings,
                        "rounds_meta": rounds_meta,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            # Latest symlink-style copy at stable path for quick open
            latest = out_dir / "latest"
            if latest.exists() or latest.is_symlink():
                try:
                    if latest.is_dir() and not latest.is_symlink():
                        shutil.rmtree(latest)
                    else:
                        latest.unlink()
                except OSError:
                    pass
            try:
                latest.symlink_to(session_dir, target_is_directory=True)
            except OSError:
                # Windows / some FS: no symlink — copy index only
                (out_dir / "latest-index.html").write_text(html, encoding="utf-8")

            return json.dumps(
                {
                    "ok": True,
                    "rounds": round_i,
                    "session_dir": str(session_dir),
                    "index_html": str(final_path),
                    "report": str(session_dir / "report.json"),
                    "asset_warnings": asset_warnings,
                },
                ensure_ascii=False,
            )

        feedback_lines = [f"- {x}" for x in all_issues] or ["- Unspecified QA failure"]
        messages.append({"role": "assistant", "content": raw[:12000]})
        messages.append(
            {
                "role": "user",
                "content": (
                    "QA did not accept this version yet. Fix ALL of the following, then return the "
                    "full corrected HTML5 document only:\n"
                    + "\n".join(feedback_lines)
                ),
            }
        )

    # exhausted rounds or error
    report = {
        "ok": False,
        "reason": "max_rounds_or_error",
        "last_html_saved": str(session_dir / "last.html") if last_html else None,
        "rounds_meta": rounds_meta,
    }
    if last_html:
        (session_dir / "last.html").write_text(last_html, encoding="utf-8")
    (session_dir / "report.json").write_text(
        json.dumps({**report, "goal": goal, "asset_warnings": asset_warnings}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return json.dumps(report, ensure_ascii=False)
