#!/usr/bin/env python3
"""Vision audit of stack-validation screenshots.

Why: DOM assertions pass on layouts that are visibly broken to a human —
rows stretched to a hidden tall cell, read-only fields that look editable,
clipped column headers. This stage sends each screenshot from the CURRENT
run's screenshot dir to a vision-capable model and records what it sees.

Freshness-bound by contract: the caller passes the single $OUT/screenshots
dir this run produced. This script never globs output/stack-validation/*,
so it cannot grade a stale PNG.

Advisory by contract: a visual finding is a report line, not a build
failure. The script exits non-zero only when it could not audit ANY image
(no config, no PNGs, every call errored) — a subjective "looks off" never
reddens the suite.

Stdlib-only (urllib), matching scripts/bootstrap_instance.py.

Env:
  VISION_BASE_URL  OpenAI-compatible base, e.g. https://ai.fr4iser.com/v1
  VISION_API_KEY   bearer token for that base
  VISION_MODEL     a model that accepts image_url parts (e.g. coder)
Usage:
  python3 scripts/vision_audit.py --screenshots DIR --out FILE [--limit N]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROMPT = (
    "You are auditing a UI screenshot for visual defects that a DOM assertion "
    "would miss. Report ONLY things that look wrong to a human:\n"
    "- broken or shifted layout, overlapping elements\n"
    "- clipped or truncated text or elements (including inside scroll containers)\n"
    "- a control that looks disabled but is active, or vice versa\n"
    "- unreadable contrast or wrong-rendered colors\n"
    "- missing or mis-rendered icons\n"
    "For each defect, write one bullet starting with '- ' naming the region and "
    "what is wrong. If you see nothing wrong, reply exactly: NO DEFECTS. "
    "Do not describe content that is merely present; only defects."
)


def _extract_content(data: dict) -> str:
    choices = data.get("choices") or [{}]
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "\n".join(parts).strip()
    return ""


def _audit_one(path: Path, base_url: str, api_key: str, model: str, timeout: float) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
        "stream": False,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return _extract_content(data)


def main() -> int:
    ap = argparse.ArgumentParser(description="Vision audit of stack-validation screenshots")
    ap.add_argument("--screenshots", required=True, help="dir of PNGs from THIS run only")
    ap.add_argument("--out", required=True, help="markdown report path")
    ap.add_argument("--limit", type=int, default=0, help="audit at most N images (0 = all)")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    base_url = os.environ.get("VISION_BASE_URL", "").strip()
    api_key = os.environ.get("VISION_API_KEY", "").strip()
    model = os.environ.get("VISION_MODEL", "").strip()

    missing = [
        name
        for name, val in (
            ("VISION_BASE_URL", base_url),
            ("VISION_API_KEY", api_key),
            ("VISION_MODEL", model),
        )
        if not val
    ]
    if missing:
        sys.stderr.write(
            "vision_audit: missing env "
            + ", ".join(missing)
            + " — set them to a vision-capable OpenAI-compatible endpoint\n"
        )
        return 1

    shots_dir = Path(args.screenshots)
    if not shots_dir.is_dir():
        sys.stderr.write(f"vision_audit: not a directory: {shots_dir}\n")
        return 1

    pngs = sorted(shots_dir.glob("*.png"))
    if args.limit > 0:
        pngs = pngs[: args.limit]
    if not pngs:
        sys.stderr.write(f"vision_audit: no PNGs in {shots_dir}\n")
        return 1

    out_path = Path(args.out)
    audited = 0
    failed = 0
    lines = [
        f"# Vision audit — {len(pngs)} screenshot(s)",
        "",
        f"model: `{model}`  base: `{base_url}`",
        "",
        "Advisory only. A finding is a human-visible defect a DOM assertion missed.",
        "",
    ]
    for png in pngs:
        try:
            reply = _audit_one(png, base_url, api_key, model, args.timeout)
        except urllib.error.HTTPError as exc:
            failed += 1
            detail = exc.read().decode("utf-8", "replace")[:400]
            lines.append(f"## {png.name}\n\nERROR {exc.code}: {detail}\n")
            continue
        except Exception as exc:  # noqa: BLE001 — one bad image must not kill the pass
            failed += 1
            lines.append(f"## {png.name}\n\nERROR: {exc}\n")
            continue
        audited += 1
        lines.append(f"## {png.name}\n\n{reply or '(empty response)'}\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"vision_audit: {audited} audited, {failed} errored -> {out_path}")

    # Advisory: findings never fail the suite. Only a pass that audited nothing fails.
    return 0 if audited > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
