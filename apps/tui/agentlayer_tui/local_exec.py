"""Run advertised workspace tools against a local directory (ADR 0009 milestone 2).

Kept free of Textual and of backend imports: the jail, the blocklist and the JSON
payloads are the parts worth testing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .jail import JailError, resolve_under_root

ADVERTISED_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "list_dir",
        "glob",
        "search",
        "apply_patch",
        "edit",
        "replace",
        "bash",
        "git_sync",
    }
)

# Minimum set the client MUST prompt for (ADR 0009 §2). Reads are not gated.
GATED_TOOLS = frozenset(
    {
        "bash",
        "git_sync",
        "write_file",
        "edit",
        "apply_patch",
        "replace",
    }
)

MAX_FILE_BYTES = 2_000_000
MAX_READ_LINES = 8000
MAX_LIST_ENTRIES = 500
MAX_GLOB_FILES = 2000
MAX_SEARCH_FILES = 2000
MAX_SEARCH_MATCHES = 100
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_BASH_OUTPUT = 50_000
DEFAULT_BASH_TIMEOUT = 60
MAX_BASH_TIMEOUT = 120

_CREDENTIAL_ENV_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
    }
)

_BLOCKED_COMMANDS = frozenset(
    {
        "rm -rf /",
        "rm -rf /*",
        "rm -rf .",
        "rm -rf ./",
        "chmod -R 777 /",
        "dd if=/dev/zero",
        "mkfs",
        "fdisk",
        "parted",
        "iptables",
        "ufw",
    }
)

_BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+\*",
    r"rm\s+-rf\s+\.($|\s)",
    r"rm\s+-R\s+/",
    r"wget\s+.*\|\s*sh",
    r"wget\s+.*\|\s*bash",
    r"curl\s+.*\|\s*sh",
    r"curl\s+.*\|\s*bash",
    r":\(\)\s*:",
    r"fork\(\)",
    r"\$\s*\(\s*\$\s*\)",
    r"dd\s+if=/dev/zero",
    r"dd\s+if=/dev/urandom",
    r">\s*/dev/sd[a-z]",
    r"chmod\s+-R\s+777",
    r"mv\s+/.*\s+/bin",
    r"cp\s+.*\s+/bin",
    r":\|",
    r"git\s+clean\s+-[a-z]*f",
]
_BLOCKED_REGEX = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

_SECRET_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "API_KEY",
    "APIKEY",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "DB_URL",
    "AWS_",
    "GITHUB_PAT",
    "OPENAI",
    "BEARER",
    "CREDENTIAL",
)
_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "PWD",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TZ",
        "COLORTERM",
        "NO_COLOR",
        "FORCE_COLOR",
        "CI",
        "DEBIAN_FRONTEND",
    }
)
_SAFE_ENV_PREFIXES = (
    "NODE_",
    "NPM_",
    "npm_",
    "PYTHON",
    "UV_",
    "VIRTUAL_ENV",
    "RUST",
    "CARGO",
    "GOPATH",
    "GOROOT",
    "JAVA_",
    "MAVEN_",
    "GRADLE_",
    "PNPM_",
    "YARN_",
    "BUN_",
    "COMPOSE_",
    "DOCKER_",
)


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _is_probably_text(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def _is_blocked_credential_path(rel: str) -> bool:
    s = (rel or "").strip().replace("\\", "/")
    if not s:
        return False
    parts = [p for p in s.split("/") if p]
    base = (parts[-1] if parts else s).lower()
    if base in _CREDENTIAL_ENV_BASENAMES:
        return True
    if base.startswith(".env.") or base.endswith(".env"):
        return True
    return False


def _coalesce_content(arguments: dict[str, Any]) -> tuple[str, str | None]:
    for key in ("content", "text", "source"):
        v = arguments.get(key)
        if v is not None:
            return str(v), None
    return "", "content is required (use 'content', 'text', or 'source' key)"


def bash_blocked(command: str) -> str | None:
    lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in lower:
            return f"command blocked: '{blocked}' is not allowed"
    for i, regex in enumerate(_BLOCKED_REGEX):
        if regex.search(lower):
            return f"command blocked: matches dangerous pattern '{_BLOCKED_PATTERNS[i]}'"
    return None


def _env_key_allowed(key: str) -> bool:
    ku = key.upper()
    if ku in _SAFE_ENV_KEYS:
        return True
    for prefix in _SAFE_ENV_PREFIXES:
        if ku.startswith(prefix):
            return True
    for marker in _SECRET_ENV_MARKERS:
        if marker in ku:
            return False
    return True


def _subprocess_env(*, home: str, cwd: str) -> dict[str, str]:
    out: dict[str, str] = {"HOME": home, "PWD": cwd, "GIT_TERMINAL_PROMPT": "0"}
    for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "TMPDIR"):
        val = os.environ.get(key)
        if val is not None:
            out[key] = val
    if not out.get("PATH"):
        out["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    for key, val in os.environ.items():
        if key in out or not isinstance(val, str):
            continue
        if _env_key_allowed(key):
            out[key] = val
    out["HOME"] = home
    out["PWD"] = cwd
    out["GIT_TERMINAL_PROMPT"] = "0"
    return out


def _tail(text: str, max_bytes: int, max_lines: int = 200) -> tuple[str, bool]:
    lines = text.split("\n")
    if len(lines) <= max_lines and len(text.encode("utf-8")) <= max_bytes:
        return text, False
    out: list[str] = []
    total_bytes = 0
    for line in reversed(lines):
        line_bytes = len(line.encode("utf-8"))
        if total_bytes + line_bytes > max_bytes or len(out) >= max_lines:
            break
        out.append(line)
        total_bytes += line_bytes
    out.reverse()
    return "\n".join(out), True


def _read_file(root: Path, arguments: dict[str, Any]) -> str:
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return _dumps({"ok": False, "error": "path is required"})
    try:
        resolved = resolve_under_root(root, rel)
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not resolved.is_file():
        return _dumps({"ok": False, "error": "not a regular file", "path": rel})
    try:
        size = os.path.getsize(resolved)
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    if size > MAX_FILE_BYTES:
        return _dumps({"ok": False, "error": f"file too large (>{MAX_FILE_BYTES} bytes)", "size": size})
    try:
        raw = resolved.read_bytes()
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not _is_probably_text(raw):
        return _dumps({"ok": False, "error": "file looks binary; not returned as text"})
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    start = 1
    limit = arguments.get("limit_lines")
    raw_start = arguments.get("start_line")
    if raw_start is not None:
        try:
            start = max(1, int(raw_start))
        except (TypeError, ValueError):
            return _dumps({"ok": False, "error": "start_line must be an integer"})
    if limit is not None:
        try:
            lim = max(0, int(limit))
        except (TypeError, ValueError):
            return _dumps({"ok": False, "error": "limit_lines must be an integer"})
        chunk = lines[start - 1 : start - 1 + lim]
        return _dumps(
            {
                "ok": True,
                "path": rel.replace("\\", "/"),
                "start_line": start,
                "line_count_total": len(lines),
                "content": "".join(chunk),
                "truncated_lines": (start - 1 + len(chunk)) < len(lines),
            }
        )
    if len(lines) > MAX_READ_LINES:
        return _dumps(
            {
                "ok": True,
                "path": rel.replace("\\", "/"),
                "content": "".join(lines[:MAX_READ_LINES]),
                "truncated": True,
                "line_count_total": len(lines),
                "max_lines": MAX_READ_LINES,
            }
        )
    return _dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "content": text,
            "truncated": False,
            "line_count_total": len(lines),
        }
    )


def _write_file(root: Path, arguments: dict[str, Any]) -> str:
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return _dumps({"ok": False, "error": "path is required"})
    if _is_blocked_credential_path(rel):
        return _dumps({"ok": False, "error": f"Refusing to modify credential/env file {rel!r}."})
    content, cerr = _coalesce_content(arguments)
    if cerr:
        return _dumps({"ok": False, "error": cerr})
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        return _dumps({"ok": False, "error": f"content too large (>{MAX_FILE_BYTES} bytes)"})
    try:
        resolved = resolve_under_root(root, rel)
        resolve_under_root(root, str(Path(rel).parent) if Path(rel).parent.parts else ".")
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8", newline="")
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    return _dumps({"ok": True, "path": rel.replace("\\", "/"), "bytes_written": len(data)})


def _list_dir(root: Path, arguments: dict[str, Any]) -> str:
    rel = (arguments.get("path") or "").strip() or "."
    try:
        resolved = resolve_under_root(root, rel)
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not resolved.is_dir():
        return _dumps({"ok": False, "error": "not a directory", "path": rel})
    want_files = bool(arguments.get("include_files", True))
    want_dirs = bool(arguments.get("include_directories", True))
    entries: list[dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(resolved)):
            if name in (".", ".."):
                continue
            fp = resolved / name
            try:
                is_dir = fp.is_dir()
                is_link = fp.is_symlink()
            except OSError:
                continue
            if is_dir and not want_dirs:
                continue
            if not is_dir and not want_files:
                continue
            rel_child = str(Path(rel) / name) if rel not in (".", "") else name
            entries.append(
                {
                    "name": name,
                    "path": rel_child.replace("\\", "/"),
                    "is_dir": is_dir,
                    "is_symlink": is_link,
                }
            )
            if len(entries) >= MAX_LIST_ENTRIES:
                break
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    return _dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "entries": entries,
            "truncated": len(entries) >= MAX_LIST_ENTRIES,
            "max_entries": MAX_LIST_ENTRIES,
        }
    )


def _glob(root: Path, arguments: dict[str, Any]) -> str:
    pattern = (arguments.get("pattern") or "").strip()
    if not pattern:
        path_given = arguments.get("path")
        if isinstance(path_given, str) and path_given.strip():
            pattern = path_given.strip()
        else:
            return _dumps({"ok": False, "error": "pattern is required. Use glob like **/*.py"})
    path_rel = (arguments.get("path") or "").strip() or "."
    try:
        resolved = resolve_under_root(root, path_rel)
        root_r = resolve_under_root(root, ".")
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not resolved.is_dir():
        return _dumps({"ok": False, "error": "path must be a directory"})
    matches: list[str] = []
    try:
        for p in resolved.glob(pattern):
            if not p.is_file():
                continue
            try:
                real = p.resolve()
                real.relative_to(root_r)
            except (ValueError, OSError):
                continue
            try:
                rel = real.relative_to(resolved)
            except ValueError:
                continue
            matches.append(str(rel).replace("\\", "/"))
            if len(matches) >= MAX_GLOB_FILES:
                break
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    truncated = len(matches) >= MAX_GLOB_FILES
    return _dumps(
        {
            "ok": True,
            "pattern": pattern,
            "path": path_rel.replace("\\", "/"),
            "files": matches,
            "truncated": truncated,
            "max_files": MAX_GLOB_FILES,
            "count": len(matches),
        }
    )


def _search(root: Path, arguments: dict[str, Any]) -> str:
    query = arguments.get("query")
    if query is None or str(query).strip() == "":
        return _dumps({"ok": False, "error": "query is required"})
    use_regex = bool(arguments.get("regex", False))
    path_prefix = str(arguments.get("path_prefix") or "").strip()
    try:
        search_root = resolve_under_root(root, path_prefix or ".")
        root_r = resolve_under_root(root, ".")
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not search_root.is_dir():
        return _dumps({"ok": False, "error": "path_prefix must be a directory"})
    try:
        cre = re.compile(str(query)) if use_regex else None
    except re.error as e:
        return _dumps({"ok": False, "error": f"invalid regex: {e}"})
    needle = str(query)
    matches: list[dict[str, Any]] = []
    files_scanned = 0
    truncated_matches = False
    truncated_scan = False
    for dirpath, dirnames, filenames in os.walk(search_root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
        for name in filenames:
            if files_scanned >= MAX_SEARCH_FILES:
                truncated_scan = True
                break
            fp = Path(dirpath) / name
            try:
                real = fp.resolve()
                real.relative_to(root_r)
            except (ValueError, OSError):
                continue
            files_scanned += 1
            try:
                if fp.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                raw = fp.read_bytes()
            except OSError:
                continue
            if not _is_probably_text(raw):
                continue
            text = raw.decode("utf-8", errors="replace")
            rel = str(real.relative_to(root_r)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), start=1):
                hit = bool(cre.search(line)) if cre is not None else needle in line
                if not hit:
                    continue
                matches.append({"path": rel, "line": i, "text": line[:400]})
                if len(matches) >= MAX_SEARCH_MATCHES:
                    truncated_matches = True
                    break
            if truncated_matches:
                break
        if truncated_scan or truncated_matches:
            break
    return _dumps(
        {
            "ok": True,
            "query": str(query),
            "path_prefix": path_prefix or None,
            "matches": matches,
            "count": len(matches),
            "files_scanned": files_scanned,
            "truncated_matches": truncated_matches,
            "truncated_scan": truncated_scan,
            "search_engine": "python",
        }
    )


def _replace(root: Path, arguments: dict[str, Any]) -> str:
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return _dumps({"ok": False, "error": "path is required"})
    if _is_blocked_credential_path(rel):
        return _dumps({"ok": False, "error": f"Refusing to modify credential/env file {rel!r}."})
    old = arguments.get("old_string")
    new = arguments.get("new_string")
    if old is None:
        return _dumps({"ok": False, "error": "old_string is required"})
    if new is None:
        new = ""
    try:
        resolved = resolve_under_root(root, rel)
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not resolved.is_file():
        return _dumps({"ok": False, "error": "not a regular file", "path": rel})
    try:
        raw = resolved.read_bytes()
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    if len(raw) > MAX_FILE_BYTES:
        return _dumps({"ok": False, "error": "file too large"})
    if not _is_probably_text(raw):
        return _dumps({"ok": False, "error": "refusing to edit binary file"})
    text = raw.decode("utf-8", errors="strict")
    old_s, new_s = str(old), str(new)
    count = text.count(old_s)
    if count == 0:
        return _dumps({"ok": False, "error": "old_string not found", "path": rel})
    replace_all = bool(arguments.get("replace_all", False))
    if not replace_all and count != 1:
        return _dumps(
            {
                "ok": False,
                "error": (
                    f"old_string matches {count} times; set replace_all true to replace all, "
                    "or make old_string unique"
                ),
                "matches": count,
            }
        )
    updated = text.replace(old_s, new_s) if replace_all else text.replace(old_s, new_s, 1)
    try:
        resolved.write_text(updated, encoding="utf-8", newline="")
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    return _dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "replacements": count if replace_all else 1,
            "bytes_written": len(updated.encode("utf-8")),
        }
    )


def _edit(root: Path, arguments: dict[str, Any]) -> str:
    """Exact unique replace, then a line-stripped fallback (same contract as the server tool)."""
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return _dumps({"ok": False, "error": "path is required"})
    if _is_blocked_credential_path(rel):
        return _dumps({"ok": False, "error": f"Refusing to modify credential/env file {rel!r}."})
    old = arguments.get("old_string")
    new = arguments.get("new_string")
    if old is None:
        return _dumps({"ok": False, "error": "old_string is required"})
    if new is None:
        new = ""
    if old == new:
        return _dumps({"ok": False, "error": "old_string and new_string are identical"})
    try:
        resolved = resolve_under_root(root, rel)
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not resolved.is_file():
        return _dumps({"ok": False, "error": "not a regular file", "path": rel})
    try:
        raw = resolved.read_bytes()
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    if len(raw) > MAX_FILE_BYTES:
        return _dumps({"ok": False, "error": "file too large"})
    if not _is_probably_text(raw):
        return _dumps({"ok": False, "error": "refusing to edit binary file"})
    content = raw.decode("utf-8", errors="strict")
    old_s, new_s = str(old), str(new)
    replace_all = bool(arguments.get("replace_all", False))
    updated: str | None = None
    if replace_all and old_s in content:
        updated = content.replace(old_s, new_s)
    elif content.count(old_s) == 1:
        updated = content.replace(old_s, new_s, 1)
    else:
        old_lines = content.split("\n")
        search_lines = old_s.split("\n")
        if search_lines and search_lines[-1] == "":
            search_lines = search_lines[:-1]
        hits: list[int] = []
        for i in range(len(old_lines) - len(search_lines) + 1):
            if all(
                old_lines[i + j].strip() == search_lines[j].strip()
                for j in range(len(search_lines))
            ):
                hits.append(i)
        if len(hits) == 1:
            i = hits[0]
            start = sum(len(old_lines[k]) + 1 for k in range(i))
            end = start + sum(len(old_lines[i + j]) + 1 for j in range(len(search_lines))) - 1
            updated = content[:start] + new_s + content[end:]
    if updated is None:
        return _dumps(
            {
                "ok": False,
                "error": "Could not find old_string with exact or line-trimmed matching",
                "hint": "Ensure old_string matches the file content exactly or with similar whitespace.",
            }
        )
    try:
        resolved.write_text(updated, encoding="utf-8", newline="")
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    return _dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "bytes_written": len(updated.encode("utf-8")),
        }
    )


def _parse_patch(patch_text: str) -> list[dict[str, Any]]:
    lines = patch_text.splitlines()
    files: list[dict[str, Any]] = []
    current_file: str | None = None
    current_hunks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git"):
            if current_file is not None and current_hunks:
                files.append({"path": current_file, "hunks": current_hunks})
            parts = line.split()
            current_file = parts[2].lstrip("b/") if len(parts) >= 3 else None
            current_hunks = []
        elif line.startswith("--- ") or line.startswith("+++ "):
            if line.startswith("+++ ") and current_file is None:
                current_file = line[4:].strip().lstrip("b/")
        elif line.startswith("@@") and current_file is not None:
            hunk_lines = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                hunk_lines.append(lines[i])
                i += 1
            current_hunks.extend(hunk_lines)
            continue
        elif current_file is not None and current_hunks:
            current_hunks.append(line)
        i += 1
    if current_file is not None and current_hunks:
        files.append({"path": current_file, "hunks": current_hunks})
    return files


def _apply_hunks(old_content: str, hunks: list[str]) -> tuple[str, list[str]]:
    old_lines = old_content.splitlines(keepends=True)
    current_line = 0
    new_lines: list[str] = []
    errors: list[str] = []
    i = 0
    while i < len(hunks):
        hunk = hunks[i]
        if not hunk.startswith("@@"):
            i += 1
            continue
        header = hunk
        hunk_body: list[str] = []
        i += 1
        while i < len(hunks) and not hunks[i].startswith("@@"):
            hunk_body.append(hunks[i])
            i += 1
        try:
            parts = header.split("@@")
            range_str = parts[1].strip()
            old_range = range_str.split()[0]
            start = int(old_range.lstrip("-").split(",")[0])
        except (ValueError, IndexError):
            errors.append(f"invalid hunk header: {header}")
            continue
        target_line = max(start - 1, 0)
        new_lines.extend(old_lines[current_line:target_line])
        current_line = target_line
        for hline in hunk_body:
            if hline.startswith("+"):
                new_lines.append(hline[1:] + ("" if hline.endswith("\n") else "\n"))
            elif hline.startswith("-"):
                if current_line < len(old_lines):
                    old_l = old_lines[current_line].rstrip("\n")
                    new_l = hline[1:].rstrip("\n")
                    if old_l != new_l:
                        errors.append(
                            f"line mismatch at {current_line + 1}: expected {new_l!r}, got {old_l!r}"
                        )
                    current_line += 1
                else:
                    errors.append(f"line {current_line + 1} out of range")
            elif hline.startswith(" ") or hline == "":
                current_line += 1
    new_lines.extend(old_lines[current_line:])
    result = "".join(new_lines)
    if not result.endswith("\n") and old_content.endswith("\n"):
        result += "\n"
    return result, errors


def _apply_patch(root: Path, arguments: dict[str, Any]) -> str:
    patch_text = (arguments.get("patch_text") or arguments.get("patch") or "").strip()
    if not patch_text:
        return _dumps({"ok": False, "error": "patch_text is required"})
    files = _parse_patch(patch_text)
    if not files:
        return _dumps({"ok": False, "error": "no valid hunks found in patch"})
    results: list[dict[str, Any]] = []
    all_ok = True
    for file_info in files:
        fpath = str(file_info["path"]).lstrip("a/").lstrip("b/")
        try:
            resolved = resolve_under_root(root, fpath)
        except JailError as e:
            results.append({"path": fpath, "ok": False, "error": str(e)})
            all_ok = False
            continue
        is_new = not resolved.exists()
        if not is_new:
            if not resolved.is_file():
                results.append({"path": fpath, "ok": False, "error": "not a regular file"})
                all_ok = False
                continue
            try:
                raw = resolved.read_bytes()
            except OSError as e:
                results.append({"path": fpath, "ok": False, "error": str(e)})
                all_ok = False
                continue
            if len(raw) > MAX_FILE_BYTES:
                results.append({"path": fpath, "ok": False, "error": "file too large"})
                all_ok = False
                continue
            if not _is_probably_text(raw):
                results.append({"path": fpath, "ok": False, "error": "refusing to patch binary file"})
                all_ok = False
                continue
            old_content = raw.decode("utf-8", errors="replace")
        else:
            old_content = ""
        new_content, hunk_errors = _apply_hunks(old_content, file_info["hunks"])
        if hunk_errors:
            results.append({"path": fpath, "ok": False, "error": "; ".join(hunk_errors)})
            all_ok = False
            continue
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(new_content, encoding="utf-8", newline="")
        except OSError as e:
            results.append({"path": fpath, "ok": False, "error": f"write failed: {e}"})
            all_ok = False
            continue
        results.append(
            {
                "path": fpath.replace("\\", "/"),
                "ok": True,
                "action": "created" if is_new else "modified",
            }
        )
    return _dumps({"ok": all_ok, "files": results})


def _bash(root: Path, arguments: dict[str, Any]) -> str:
    command = (arguments.get("command") or "").strip()
    if not command:
        return _dumps({"ok": False, "error": "bash requires a non-empty string field \"command\""})
    blocked = bash_blocked(command)
    if blocked:
        return _dumps({"ok": False, "error": blocked})
    try:
        cwd = resolve_under_root(root, (arguments.get("workdir") or "").strip() or ".")
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    if not cwd.is_dir():
        return _dumps({"ok": False, "error": "workdir is not a directory"})
    try:
        timeout_s = max(1, min(MAX_BASH_TIMEOUT, int(arguments.get("timeout", DEFAULT_BASH_TIMEOUT))))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_BASH_TIMEOUT
    try:
        args = shlex.split(command)
    except ValueError as e:
        return _dumps({"ok": False, "error": f"could not parse command: {e}"})
    if not args:
        return _dumps({"ok": False, "error": "empty command"})
    env = _subprocess_env(home=str(root.resolve()), cwd=str(cwd))
    try:
        result = subprocess.run(
            args,
            shell=False,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        out_text = str(e.stdout or "") + ("\n" + str(e.stderr) if e.stderr else "")
        preview, cut = _tail(out_text, MAX_BASH_OUTPUT)
        return _dumps(
            {
                "ok": False,
                "error": f"command timed out after {timeout_s}s",
                "exit_code": -1,
                "truncated": cut,
                "output": preview,
            }
        )
    except OSError as e:
        return _dumps({"ok": False, "error": str(e)})
    combined = result.stdout or ""
    if result.stderr:
        combined += ("\n--- stderr ---\n" if combined else "") + result.stderr
    if not combined:
        combined = "(no output)"
    preview, cut = _tail(combined, MAX_BASH_OUTPUT)
    exit_code = int(result.returncode)
    payload: dict[str, Any] = {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "truncated": cut,
        "output": preview,
        "command": command,
    }
    if exit_code != 0:
        payload["error"] = preview[:500]
    return _dumps(payload)


def _git_sync(root: Path, arguments: dict[str, Any]) -> str:
    op = str(arguments.get("operation") or arguments.get("op") or "pull").strip().lower()
    if op not in ("pull", "fetch"):
        return _dumps({"ok": False, "error": "operation must be pull or fetch"})
    try:
        cwd = resolve_under_root(root, ".")
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    git_dir = cwd / ".git"
    if not git_dir.exists():
        return _dumps({"ok": False, "error": "not a git repository"})
    args = ["git", "-C", str(cwd), op]
    if op == "pull":
        args.extend(["--ff-only", "--no-edit"])
    env = _subprocess_env(home=str(cwd), cwd=str(cwd))
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=90, check=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return _dumps({"ok": False, "error": str(e)})
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    preview, cut = _tail(out, MAX_BASH_OUTPUT)
    return _dumps(
        {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "operation": op,
            "truncated": cut,
            "output": preview,
            **({"error": preview[:500]} if proc.returncode != 0 else {}),
        }
    )


_HANDLERS = {
    "read_file": _read_file,
    "write_file": _write_file,
    "list_dir": _list_dir,
    "glob": _glob,
    "search": _search,
    "replace": _replace,
    "edit": _edit,
    "apply_patch": _apply_patch,
    "bash": _bash,
    "git_sync": _git_sync,
}


def execute(tool_name: str, arguments: dict[str, Any] | None, root: Path) -> str:
    name = (tool_name or "").strip()
    if name not in ADVERTISED_TOOLS:
        return _dumps({"ok": False, "error": "unsupported"})
    handler = _HANDLERS[name]
    try:
        return handler(root, arguments or {})
    except JailError as e:
        return _dumps({"ok": False, "error": str(e)})
    except Exception as e:  # noqa: BLE001 — surface to the agent as a normal tool error
        return _dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})
