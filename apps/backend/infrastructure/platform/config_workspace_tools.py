"""Workspace file limits, coding tools, LSP, and package admission settings."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from apps.backend.infrastructure.platform.config_env import env_bool as _env_bool
from apps.backend.infrastructure.platform.config_env import env_int as _env_int

logger = logging.getLogger(__name__)

# Local files tools (local_files / fs_*): size/list limits; path scope is admin/OS (no AGENT_WORKSPACE_ROOT).
WORKSPACE_MAX_FILE_BYTES = _env_int("AGENT_WORKSPACE_MAX_FILE_BYTES", 1_200_000)
WORKSPACE_MAX_LIST_ENTRIES = _env_int("AGENT_WORKSPACE_MAX_LIST_ENTRIES", 500)
WORKSPACE_MAX_SEARCH_FILES = _env_int("AGENT_WORKSPACE_MAX_SEARCH_FILES", 2000)
WORKSPACE_MAX_SEARCH_MATCHES = _env_int("AGENT_WORKSPACE_MAX_SEARCH_MATCHES", 100)
WORKSPACE_SEARCH_MAX_FILE_BYTES = _env_int("AGENT_WORKSPACE_SEARCH_MAX_FILE_BYTES", 400_000)
WORKSPACE_MAX_GLOB_FILES = _env_int("AGENT_WORKSPACE_MAX_GLOB_FILES", 2000)
WORKSPACE_MAX_READ_LINES = _env_int("AGENT_WORKSPACE_MAX_READ_LINES", 8000)
# coding_search literal mode: prefer ``rg`` when installed (override path with AGENT_RIPGREP_PATH).
AGENT_CODING_SEARCH_USE_RIPGREP = _env_bool("AGENT_CODING_SEARCH_USE_RIPGREP", True)
AGENT_RIPGREP_PATH = (os.environ.get("AGENT_RIPGREP_PATH") or "").strip() or None
AGENT_RIPGREP_TIMEOUT_SEC = max(15, min(_env_int("AGENT_RIPGREP_TIMEOUT_SEC", 120), 600))

# --- Coding tools (dashboard-scoped, container-isolated) ---
# Root directory for all coding tool file operations; agent cannot escape this tree.
_CODING_ROOT_RAW = (os.environ.get("AGENT_CODING_ROOT") or "").strip()
CODING_ROOT: Path | None = Path(_CODING_ROOT_RAW).expanduser() if _CODING_ROOT_RAW else None
# When true, coding tools are enabled; false → all coding_* tools return disabled error.
CODING_ENABLED = _env_bool("AGENT_CODING_ENABLED", True)
# Optional background semantic index when a stale/empty workspace is bound to a coding chat.
AGENT_WORKSPACE_INDEX_ON_ATTACH = _env_bool("AGENT_WORKSPACE_INDEX_ON_ATTACH", False)
# Post-write incremental index: off | debounced (default) | immediate — touched files only (Qdrant + Neo4j).
_AGENT_INDEX_ON_WRITE_RAW = (os.environ.get("AGENT_WORKSPACE_INDEX_ON_WRITE") or "debounced").strip().lower()
AGENT_WORKSPACE_INDEX_ON_WRITE = (
    _AGENT_INDEX_ON_WRITE_RAW
    if _AGENT_INDEX_ON_WRITE_RAW in ("off", "debounced", "immediate")
    else "debounced"
)
AGENT_WORKSPACE_INDEX_DEBOUNCE_SEC = max(
    0, min(_env_int("AGENT_WORKSPACE_INDEX_DEBOUNCE_SEC", 3), 120)
)
# Max file size for coding read/write operations.
CODING_MAX_FILE_BYTES = _env_int("AGENT_CODING_MAX_FILE_BYTES", 2_000_000)
# Comma-separated path prefixes that coding tools must NEVER access (resolved, lowercase).
CODING_PATH_BLOCKLIST = frozenset(
    x.strip().lower()
    for x in (
        os.environ.get("AGENT_CODING_PATH_BLOCKLIST")
        or "/app,/data/tools,/data/tool_backups,/etc,/usr,/var,/proc,/sys,/root"
    ).split(",")
    if x.strip()
)
# coding_bash: strip operator secrets from subprocess env (PATH/toolchain vars kept).
CODING_BASH_ENV_SCRUB = _env_bool("AGENT_CODING_BASH_ENV_SCRUB", True)
# Opt-in strict prefix allowlist for coding_bash (default off — normal agent keeps broad shell).
CODING_BASH_STRICT = _env_bool("AGENT_CODING_BASH_STRICT", False)
# Inject AGENTS.md / CLAUDE.md into selected agent prompts (DSH-style; labeled untrusted).
WORKSPACE_AGENT_INSTRUCTIONS_ENABLED = _env_bool("AGENT_WORKSPACE_AGENT_INSTRUCTIONS", True)
WORKSPACE_AGENT_INSTRUCTIONS_MAX_BYTES = max(
    1024, min(_env_int("AGENT_WORKSPACE_AGENT_INSTRUCTIONS_MAX_BYTES", 65_536), 262_144)
)
# Comma-separated agent ids that receive workspace instruction injection.
# Default: general,coding,coding_plan
_WORKSPACE_AGENT_INSTRUCTIONS_AGENTS_RAW = (
    os.environ.get("AGENT_WORKSPACE_AGENT_INSTRUCTIONS_AGENTS") or ""
).strip()
WORKSPACE_AGENT_INSTRUCTIONS_AGENTS: str | None = (
    _WORKSPACE_AGENT_INSTRUCTIONS_AGENTS_RAW or None
)

# LSP tool: cap diagnostics returned to the model; timeout waiting for publishDiagnostics.
AGENT_LSP_DIAGNOSTICS_MAX = max(1, min(_env_int("AGENT_LSP_DIAGNOSTICS_MAX", 40), 200))
AGENT_LSP_DIAGNOSTICS_TIMEOUT_SEC = max(1, min(_env_int("AGENT_LSP_DIAGNOSTICS_TIMEOUT_SEC", 10), 120))


def lsp_server_cmd_override(language: str) -> list[str] | None:
    """Optional per-language LSP argv from env, e.g. AGENT_LSP_PYTHON_CMD='pyright-langserver --stdio'."""
    import shlex

    lang = (language or "").strip().lower()
    if not lang:
        return None
    raw = (os.environ.get(f"AGENT_LSP_{lang.upper()}_CMD") or "").strip()
    if not raw:
        return None
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    return parts or None

# Package admission for coding_bash pip/npm installs (off | monitor | enforce).
PACKAGE_ADMISSION_MODE = (os.environ.get("AGENT_PACKAGE_ADMISSION") or "monitor").strip().lower()
if PACKAGE_ADMISSION_MODE not in ("off", "monitor", "enforce"):
    logger.warning("unknown AGENT_PACKAGE_ADMISSION %r — using monitor", PACKAGE_ADMISSION_MODE)
    PACKAGE_ADMISSION_MODE = "monitor"
PACKAGE_MIN_VERSION_AGE_DAYS = max(0, _env_int("AGENT_PACKAGE_MIN_AGE_DAYS", 0))
PACKAGE_UNATTENDED_MIN_AGE_DAYS = max(0, _env_int("AGENT_PACKAGE_UNATTENDED_MIN_AGE_DAYS", 7))
PACKAGE_BLOCK_SEVERITY_RAW = (os.environ.get("AGENT_PACKAGE_BLOCK_SEVERITY") or "CRITICAL,HIGH").strip()
PACKAGE_ASK_SEVERITY_RAW = (os.environ.get("AGENT_PACKAGE_ASK_SEVERITY") or "MEDIUM").strip()
PACKAGE_NPM_IGNORE_SCRIPTS = _env_bool("AGENT_PACKAGE_NPM_IGNORE_SCRIPTS", True)
PACKAGE_BLOCK_GLOBAL_INSTALL = _env_bool("AGENT_PACKAGE_BLOCK_GLOBAL_INSTALL", True)
PACKAGE_BLOCK_CUSTOM_INDEX = _env_bool("AGENT_PACKAGE_BLOCK_CUSTOM_INDEX", True)
PACKAGE_BLOCK_BULK_REQUIREMENTS = _env_bool("AGENT_PACKAGE_BLOCK_BULK_REQUIREMENTS", True)
PACKAGE_UNATTENDED_STRICT = _env_bool("AGENT_PACKAGE_UNATTENDED_STRICT", True)
PACKAGE_OSV_TIMEOUT_SEC = max(1, min(_env_int("AGENT_PACKAGE_OSV_TIMEOUT_SEC", 8), 60))
PACKAGE_LOOKUP_FAILURE_ACTION_RAW = (os.environ.get("AGENT_PACKAGE_LOOKUP_FAILURE") or "").strip()
PACKAGE_BLOCKLIST_RAW = (os.environ.get("AGENT_PACKAGE_BLOCKLIST") or "").strip()
PACKAGE_ALLOWLIST_RAW = (os.environ.get("AGENT_PACKAGE_ALLOWLIST") or "").strip()
