"""Path jail for client-side workspace tools (ADR 0009).

The TUI must not import backend modules; this is the local equivalent of
``resolve_path_under_workspace`` plus the bind-root refusals the server cannot enforce,
because the path lives on this machine.
"""

from __future__ import annotations

from pathlib import Path

# Exact match only: a project may live *under* these (e.g. /tmp/my-repo, /usr/local/src/app).
_EXACT_BIND_REFUSALS = frozenset(
    {
        Path("/"),
        Path("/usr"),
        Path("/var"),
        Path("/opt"),
        Path("/home"),
        Path("/Users"),
        Path("/tmp"),
        Path("/private"),
    }
)

# Any path at or under these is a system tree, not a project.
_PREFIX_BIND_REFUSALS = (
    Path("/etc"),
    Path("/sys"),
    Path("/proc"),
    Path("/dev"),
    Path("/boot"),
    Path("/root"),
    Path("/bin"),
    Path("/sbin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/run"),
)


class JailError(ValueError):
    """A relative path escaped the workspace or a bind target is too broad."""


def resolve_under_root(root: Path, rel: str | None) -> Path:
    """Resolve ``rel`` under ``root``; reject absolute paths and ``..`` escapes after ``resolve()``."""
    root_r = root.expanduser().resolve()
    r = (rel or "").strip().replace("\\", "/")
    if r in ("", "."):
        return root_r
    if r.startswith("/") or (len(r) >= 3 and r[1] == ":" and r[2] in "/\\"):
        raise JailError("path must be relative to the workspace, not absolute")
    if "\0" in r:
        raise JailError("invalid path")
    target = (root_r / r).resolve()
    try:
        target.relative_to(root_r)
    except ValueError as exc:
        raise JailError("path must stay inside the workspace") from exc
    return target


def bind_refusal_reason(path: Path) -> str | None:
    """Why ``/bind --local`` must not accept this directory, or ``None`` if it is a project root."""
    try:
        resolved = path.expanduser().resolve()
    except OSError as exc:
        return str(exc)
    if not resolved.exists():
        return f"{resolved} does not exist"
    if not resolved.is_dir():
        return f"{resolved} is not a directory"
    try:
        home = Path.home().resolve()
    except OSError:
        home = None
    if home is not None and resolved == home:
        return "refusing to bind the home directory — pick a project folder"
    for candidate in _EXACT_BIND_REFUSALS:
        try:
            exact = candidate.resolve()
        except OSError:
            exact = candidate
        if resolved == exact:
            return f"refusing to bind {resolved} — pick a project folder"
    for prefix in _PREFIX_BIND_REFUSALS:
        try:
            pref = prefix.resolve()
        except OSError:
            pref = prefix
        if resolved == pref or pref in resolved.parents:
            return f"refusing to bind under {pref}"
    return None
