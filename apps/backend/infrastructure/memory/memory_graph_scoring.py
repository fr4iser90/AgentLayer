"""Memory graph decay, activation scoring, conflict hints, and prompt compression for graph memory."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from apps.backend.infrastructure.settings import operator_settings

# Half-life proxy (seconds) for exponential decay by ``stability``.
_STABILITY_TAU_SEC: dict[str, float] = {
    "volatile": 86_400.0,  # ~1 day
    "normal": 604_800.0,  # ~7 days
    "stable": 31_536_000.0,  # ~365 days
}


def _as_utc(dt: Any) -> datetime:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    if isinstance(dt, str) and dt.strip():
        try:
            s = dt.strip().replace("Z", "+00:00")
            parsed = datetime.fromisoformat(s)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def decay_multiplier(updated_at: Any, stability: str | None) -> float:
    """exp(-age / tau) with ``tau`` from stability (default ``normal``)."""
    st = (stability or "normal").strip().lower()
    tau = _STABILITY_TAU_SEC.get(st, _STABILITY_TAU_SEC["normal"])
    if tau <= 0:
        return 1.0
    t0 = _as_utc(updated_at)
    age = max(0.0, (datetime.now(UTC) - t0).total_seconds())
    return math.exp(-age / tau)


def activation_score(row: dict[str, Any]) -> float:
    """Higher = more relevant to inject (decay × confidence × importance × priority × goal boost)."""
    d = decay_multiplier(row.get("updated_at"), str(row.get("stability") or "normal"))
    c = max(0.0, min(1.0, float(row.get("confidence") or 1.0)))
    imp = max(0.0, float(row.get("importance") or 1.0))
    pr = float(row.get("priority") or 0.0)
    pr = max(-50.0, min(50.0, pr))
    kind = str(row.get("kind") or "").strip().lower()
    goal_boost = 1.35 if kind == "goal" else 1.0
    return d * c * imp * (1.0 + 0.05 * pr) * goal_boost


def rank_and_filter_nodes(
    rows: list[dict[str, Any]],
    *,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    ms = min_score
    if ms is None:
        ms = float(operator_settings.memory_graph_prompt_settings()["min_score"])
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        s = activation_score(r)
        if s >= ms:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


def subject_key_conflicts(rows: list[dict[str, Any]]) -> list[tuple[str, list[int]]]:
    """Groups with the same non-empty ``subject_key`` and more than one node id."""
    by_k: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        k = str(r.get("subject_key") or "").strip()
        if not k:
            continue
        by_k[k].append(int(r["id"]))
    out: list[tuple[str, list[int]]] = []
    for k, ids in by_k.items():
        u = sorted(set(ids))
        if len(u) > 1:
            out.append((k, u))
    return sorted(out, key=lambda x: x[0])


def format_graph_lines(
    rows: list[dict[str, Any]],
    *,
    max_bullet_chars: int | None = None,
    max_bullets: int | None = None,
) -> list[str]:
    """One line per node; optional truncation by count and total char budget."""
    lim = operator_settings.memory_graph_prompt_settings()
    mb = max_bullets
    if mb is None:
        mb = int(lim["max_bullets"])
    mb = max(1, min(mb, 50))
    mc = max_bullet_chars
    if mc is None:
        mc = int(lim["max_prompt_chars"])

    lines: list[str] = []
    total = 0
    for i, r in enumerate(rows):
        if i >= mb:
            lines.append(f"… and {len(rows) - mb} more nodes omitted (limit).")
            break
        lab = str(r.get("label") or "").strip()
        sm = str(r.get("summary") or "").strip().replace("\n", " ")
        kind = str(r.get("kind") or "event").strip()
        cf = float(r.get("confidence") or 1.0)
        sk = str(r.get("subject_key") or "").strip()
        meta = f"conf={cf:.2f}"
        if sk:
            meta += f", key={sk}"
        if len(sm) > 200:
            sm = sm[:200] + "…"
        piece = f"- ({kind}) {lab}: {sm} ({meta})" if sm else f"- ({kind}) {lab} ({meta})"
        if total + len(piece) > mc and lines:
            lines.append("… (truncated to stay within size budget)")
            break
        lines.append(piece)
        total += len(piece) + 1
    return lines


def build_graph_prompt_section(
    rows: list[dict[str, Any]],
) -> str:
    """Full ``[User memory — graph]`` block including optional conflict footer."""
    if not rows:
        return ""
    lines: list[str] = ["[User memory — graph]"]
    lines.extend(format_graph_lines(rows))
    confs = subject_key_conflicts(rows)
    if confs:
        lines.append("")
        lines.append("[Possible conflicting memories — same subject_key, verify manually:]")
        for key, ids in confs[:8]:
            lines.append(f"- {key}: node ids {ids}")
        if len(confs) > 8:
            lines.append(f"… +{len(confs) - 8} more conflict groups")
    return "\n".join(lines).strip()
