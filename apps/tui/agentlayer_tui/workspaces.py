"""Workspace resolution and rendering for ``/workspace``, ``/bind`` and ``/index``.

Textual-free like ``events.py``: the id/name matching and the status rendering are the parts
worth testing, and both depend only on the JSON shapes of ``/v1/workspaces`` and
``/v1/workspaces/{id}/index/status``.
"""

from __future__ import annotations

from typing import Any

OK = "\u2713"
NO = "\u2717"


def _s(row: dict[str, Any], key: str) -> str:
    v = row.get(key)
    return v.strip() if isinstance(v, str) else ""


def short_id(value: Any) -> str:
    return str(value or "")[:8]


def is_client_workspace(row: dict[str, Any]) -> bool:
    return _s(row, "execution_mode").lower() == "client"


def take_flag(args: str, flag: str) -> tuple[bool, str]:
    """Strip a leading ``--local``-style flag. The rest is left intact so paths may contain spaces."""
    raw = (args or "").strip()
    token = flag.strip()
    if raw == token:
        return True, ""
    prefix = token + " "
    if raw.startswith(prefix):
        return True, raw[len(prefix) :].strip()
    return False, raw


def resolve_workspace(
    rows: list[dict[str, Any]], query: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Match a workspace by id, id prefix or name.

    Returns ``(match, candidates)``: exactly one of the two is meaningful. Candidates are
    returned instead of guessing when a query is ambiguous, so ``/bind api`` never silently
    binds the wrong repository.
    """
    q = (query or "").strip()
    if not q:
        return None, []

    for row in rows:
        if _s(row, "id") == q:
            return row, []

    def unique(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
        return matches[0] if len(matches) == 1 else None

    by_name = [r for r in rows if _s(r, "name") == q]
    if (hit := unique(by_name)) is not None:
        return hit, []

    lowered = q.lower()
    by_name_ci = [r for r in rows if _s(r, "name").lower() == lowered]
    if (hit := unique(by_name_ci)) is not None:
        return hit, []

    by_prefix = [r for r in rows if _s(r, "id").startswith(q)]
    if (hit := unique(by_prefix)) is not None:
        return hit, []

    by_substring = [r for r in rows if lowered in _s(r, "name").lower()]
    if (hit := unique(by_substring)) is not None:
        return hit, []

    return None, by_name_ci or by_prefix or by_substring


def format_workspace_rows(rows: list[dict[str, Any]], bound_id: str = "") -> list[str]:
    """One line per workspace; an arrow marks the one bound to this conversation."""
    if not rows:
        return ["no workspaces — /workspace create <name> [git url]  or  /workspace create --local <name> [path]"]
    width = min(max((len(_s(r, "name")) for r in rows), default=4) + 2, 32)
    out: list[str] = []
    for row in rows:
        marker = "\u2192" if bound_id and _s(row, "id") == bound_id else " "
        name = _s(row, "name")
        if is_client_workspace(row):
            origin = _s(row, "path") or "local"
            consent = _s(row, "index_consent") or "none"
            out.append(
                f"{marker} {short_id(row.get('id'))}  {name.ljust(width)}"
                f"{'client':<10}{consent:<8}  on this machine  {origin[:44]}"
            )
            continue
        flags = "".join(
            (
                "s" if row.get("semantic_index_enabled") else "-",
                "r" if row.get("retrieval_enabled") else "-",
                "d" if row.get("docs_rag_enabled") else "-",
                "g" if row.get("graph_index_enabled") else "-",
            )
        )
        indexed = "indexed" if row.get("last_index_at") else "not indexed"
        origin = _s(row, "git_url") or _s(row, "source") or "manual"
        out.append(
            f"{marker} {short_id(row.get('id'))}  {name.ljust(width)}"
            f"{_s(row, 'git_branch') or '?':<10}{flags}  {indexed:<12}{origin[:44]}"
        )
    out.append("  flags: s=semantic r=retrieval d=docs g=graph   client = files stay on this machine")
    out.append("  consent: none | symbols | text  (server decides who may raise it)")
    return out


def format_index_status(payload: dict[str, Any]) -> list[str]:
    """Render ``/v1/workspaces/{id}/index/status`` — why an index is stale, not just that."""
    if not payload or not payload.get("ok"):
        return [f"index status unavailable: {payload.get('error') or 'unknown'}"]

    out: list[str] = []
    stale = bool(payload.get("index_stale"))
    reason = payload.get("index_stale_reason")
    behind = payload.get("files_out_of_date")
    state = "stale" if stale else "up to date"
    if reason:
        state = f"{state} ({reason})"
    if isinstance(behind, int) and behind > 0:
        state = f"{state}, {behind} file(s) behind"
    out.append(f"index    {state}")

    last = payload.get("last_index_at")
    error = payload.get("last_index_error")
    out.append(f"last     {last or 'never'}{f'  error: {error}' if error else ''}")

    job = payload.get("index_job")
    if isinstance(job, dict) and job:
        running = job.get("running") or job.get("state") or job.get("status")
        done, total = job.get("files_done"), job.get("files_total")
        bits = [str(running)] if running else []
        if done is not None and total:
            bits.append(f"{done}/{total} files")
        if bits:
            out.append("job      " + "  ".join(bits))

    out.append(f"writes   index_on_write = {payload.get('index_on_write_effective') or '?'}")

    stores = []
    for name in ("qdrant", "neo4j", "embedding"):
        meta = payload.get(name)
        if not isinstance(meta, dict):
            continue
        if not meta.get("configured") and not meta.get("enabled"):
            stores.append(f"{name} off")
            continue
        reachable = meta.get("reachable")
        mark = OK if reachable or (reachable is None and meta.get("enabled")) else NO
        extra = meta.get("collection") or (
            f"{meta.get('embedding_dim')}d" if meta.get("embedding_dim") else ""
        )
        stores.append(f"{name} {mark}{f' {extra}' if extra else ''}")
    if stores:
        out.append("stores   " + "  \u00b7  ".join(stores))

    flags = " ".join(
        f"{label} {OK if payload.get(key) else NO}"
        for label, key in (
            ("semantic", "semantic_index_enabled"),
            ("retrieval", "retrieval_enabled"),
            ("docs", "docs_rag_enabled"),
            ("graph", "graph_index_enabled"),
            ("coding", "coding_enabled"),
        )
    )
    out.append(f"flags    {flags}")
    consent = payload.get("index_consent_effective") or payload.get("index_consent")
    cap = payload.get("index_consent_operator_max")
    if consent or cap:
        out.append(f"consent  {consent or '?'}  (operator max {cap or '?'})")
    return out


INDEX_MODES = ("full", "code", "docs", "symbols", "text")


def normalize_index_mode(raw: str) -> str | None:
    """``None`` for an unknown mode so the caller can complain instead of silently indexing."""
    mode = (raw or "").strip().lower()
    if not mode:
        return "full"
    return mode if mode in INDEX_MODES else None
