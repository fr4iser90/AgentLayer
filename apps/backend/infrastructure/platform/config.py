import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PLUGINS_DIR_RAW = os.environ.get("AGENT_PLUGINS_DIR", "").strip()
if _PLUGINS_DIR_RAW:
    PLUGINS_DIR = Path(_PLUGINS_DIR_RAW)
else:
    PLUGINS_DIR = Path(__file__).resolve().parents[4] / "plugins"


def tools_backup_directory() -> Path:
    raw = (os.environ.get("AGENT_TOOLS_BACKUP_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "tool_backups"


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _agent_mode_from_env() -> str:
    """Deployment class: ``sandbox`` (default) = treat tool execution as container-bound; ``host`` = allow host-class policy."""
    v = (os.environ.get("AGENT_MODE") or "sandbox").strip().lower()
    if v in ("sandbox", "host"):
        return v
    if v:
        logger.warning("unknown AGENT_MODE %r — using sandbox", v)
    return "sandbox"


AGENT_MODE = _agent_mode_from_env()


def _env_int(key: str, default: int) -> int:
    """Parse integer env; empty or whitespace uses ``default`` (Compose often passes ``VAR=``)."""
    raw = (os.environ.get(key) or "").strip()
    if not raw:
        return default
    return int(raw)


# --- Unified LLM providers (OpenAI-compatible) ---
# Numbered env rows: LLM_PROVIDER_1_BASE_URL, LLM_PROVIDER_1_LABEL, LLM_PROVIDER_1_API_KEY,
# LLM_PROVIDER_1_API_HEADER_NAME (default Authorization), optional _MODEL_DEFAULT/_VLM/_AGENT/_CODING,
# optional LLM_PROVIDER_N_MAX_PARALLEL (1–64, default 1).
# Parsed by :mod:`llm_env_providers`; registered as provider_1, provider_2, … in the catalog.
LLM_HTTP_MAX_PARALLEL_DEFAULT = max(1, min(64, _env_int("LLM_HTTP_MAX_PARALLEL_DEFAULT", 4)))
LLM_AUX_PROVIDER_ID = (os.environ.get("LLM_AUX_PROVIDER_ID") or "").strip() or None
LLM_ROUTER_PROVIDER_ID = (os.environ.get("LLM_ROUTER_PROVIDER_ID") or "").strip() or None
LLM_AUX_MODEL = (os.environ.get("LLM_AUX_MODEL") or "").strip() or None

# Hybrid model routing: per-profile defaults (empty = endpoint catalog model_default / UI picker).
AGENT_MODEL_PROFILE_DEFAULT = (os.environ.get("AGENT_MODEL_PROFILE_DEFAULT") or "").strip() or None
AGENT_MODEL_PROFILE_VLM = (os.environ.get("AGENT_MODEL_PROFILE_VLM") or "").strip() or None
AGENT_MODEL_PROFILE_AGENT = (os.environ.get("AGENT_MODEL_PROFILE_AGENT") or "").strip() or None
AGENT_MODEL_PROFILE_CODING = (os.environ.get("AGENT_MODEL_PROFILE_CODING") or "").strip() or None
# If false, client ``model`` and X-Agent-Model-Override are ignored (profiles / auto-VLM only).
AGENT_ALLOW_MODEL_OVERRIDE = _env_bool("AGENT_ALLOW_MODEL_OVERRIDE", True)
# Comma-separated roles (e.g. admin) allowed to override; empty = any authenticated user (Bearer → DB user).
AGENT_MODEL_OVERRIDE_ROLES = frozenset(
    x.strip().lower()
    for x in (os.environ.get("AGENT_MODEL_OVERRIDE_ROLES") or "").split(",")
    if x.strip()
)
# If true, unauthenticated optional-route callers may still set model / override header.
AGENT_MODEL_OVERRIDE_ANONYMOUS = _env_bool("AGENT_MODEL_OVERRIDE_ANONYMOUS", False)

MAX_TOOL_ROUNDS_CAP = max(256, _env_int("AGENT_MAX_TOOL_ROUNDS_CAP", 16384))


def _parse_tool_rounds_env(raw: str, *, env_name: str) -> int | None:
    """Parse ``AGENT_MAX_TOOL_ROUNDS`` / ``SUBAGENT_MAX_TOOL_ROUNDS``: empty → None; <=0 → cap; else clamped."""
    if not raw.strip():
        return None
    try:
        v = int(raw.strip())
    except ValueError:
        logger.warning("invalid %s %r — ignored", env_name, raw)
        return None
    if v <= 0:
        logger.info(
            "%s=%s → using high cap %s tool rounds (override with AGENT_MAX_TOOL_ROUNDS_CAP)",
            env_name,
            raw.strip(),
            MAX_TOOL_ROUNDS_CAP,
        )
        return MAX_TOOL_ROUNDS_CAP
    return max(1, min(v, MAX_TOOL_ROUNDS_CAP))


def _resolve_max_tool_rounds() -> int:
    """``AGENT_MAX_TOOL_ROUNDS``: positive = limit (capped); 0 or negative = cap; unset = 8."""
    raw = (os.environ.get("AGENT_MAX_TOOL_ROUNDS") or "").strip()
    if not raw:
        return 8
    parsed = _parse_tool_rounds_env(raw, env_name="AGENT_MAX_TOOL_ROUNDS")
    return parsed if parsed is not None else 8


MAX_TOOL_ROUNDS = _resolve_max_tool_rounds()


def _resolve_subagent_max_tool_rounds() -> int:
    """``SUBAGENT_MAX_TOOL_ROUNDS`` overrides ``AGENT_MAX_TOOL_ROUNDS`` for ``delegate`` sub-agents only."""
    raw = (os.environ.get("SUBAGENT_MAX_TOOL_ROUNDS") or "").strip()
    if raw:
        parsed = _parse_tool_rounds_env(raw, env_name="SUBAGENT_MAX_TOOL_ROUNDS")
        if parsed is not None:
            return parsed
    return MAX_TOOL_ROUNDS


SUBAGENT_MAX_TOOL_ROUNDS = _resolve_subagent_max_tool_rounds()


def _resolve_subagent_timeout_sec() -> float | None:
    """``SUBAGENT_TIMEOUT_SEC``: positive = wall-clock cap for ``delegate`` runs; unset or <=0 = no limit."""
    raw = (os.environ.get("SUBAGENT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.warning(
            "invalid SUBAGENT_TIMEOUT_SEC %r — no sub-agent wall-clock timeout",
            raw,
        )
        return None
    if v <= 0:
        return None
    return v


SUBAGENT_TIMEOUT_SEC = _resolve_subagent_timeout_sec()


def _resolve_llm_chat_timeout_sec() -> float | None:
    """``AGENT_LLM_CHAT_TIMEOUT_SEC``: unset or <=0 = no HTTP read timeout; positive = seconds."""
    raw = (os.environ.get("AGENT_LLM_CHAT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        logger.warning("invalid AGENT_LLM_CHAT_TIMEOUT_SEC %r — no LLM HTTP timeout", raw)
        return None
    if v <= 0:
        return None
    return v


LLM_CHAT_TIMEOUT_SEC: float | None = _resolve_llm_chat_timeout_sec()
# Phase 1 (coding-agent-roadmap): break identical tool failure loops (e.g. empty JSON / same parameter error).
# Off by default — forcing text-only rounds breaks some GGUF models (fake <tool_call> markup → empty chat).
AGENT_TOOL_THRASH_ENABLED = _env_bool("AGENT_TOOL_THRASH_ENABLED", False)
AGENT_TOOL_THRASH_STREAK_MAX = max(2, _env_int("AGENT_TOOL_THRASH_STREAK_MAX", 10))
# Doom loop guard: same tool + same arguments repeated (any result).
AGENT_TOOL_DOOM_LOOP_ENABLED = _env_bool("AGENT_TOOL_DOOM_LOOP_ENABLED", False)
AGENT_TOOL_DOOM_LOOP_STREAK_MAX = max(2, _env_int("AGENT_TOOL_DOOM_LOOP_STREAK_MAX", 10))
# Comma-separated tool names that do **not** participate in the doom-loop counter (idempotent reads / search).
# Set to a single ``-`` to disable this exclusion (all tools count). Empty env = use the default list below.
_DOOM_EXCL_ENV = os.environ.get("AGENT_TOOL_DOOM_LOOP_EXCLUDE")
if _DOOM_EXCL_ENV is None:
    _DOOM_EXCL_PARTS = (
        "coding_read_file,coding_list_dir,coding_glob,coding_search,coding_semantic_search,"
        "coding_symbols,coding_lsp,coding_index,coding_git_read,project_explain"
    ).split(",")
elif _DOOM_EXCL_ENV.strip() == "-":
    _DOOM_EXCL_PARTS = []
else:
    _DOOM_EXCL_PARTS = _DOOM_EXCL_ENV.split(",")
AGENT_TOOL_DOOM_LOOP_EXCLUDE = frozenset(x.strip() for x in _DOOM_EXCL_PARTS if x.strip())
# Phase 4 (roadmap): one-line recap after each tool batch; workspace .agentlayer.json hints.
AGENT_SESSION_TOOL_RECAP_ENABLED = _env_bool("AGENT_SESSION_TOOL_RECAP_ENABLED", True)
AGENT_SESSION_TOOL_RECAP_MAX = max(1, _env_int("AGENT_SESSION_TOOL_RECAP_MAX", 12))
# Max wall time for ``workspace_verify`` (runs ``verify_command`` from ``.agentlayer.json`` only).
AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC = max(30, min(_env_int("AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC", 600), 3600))
DATA_DIR = os.environ.get("AGENT_DATA_DIR", "/data")
# Before replace_tool / update_tool / create_tool overwrite, copy prior .py here (UTC timestamp prefix).
TOOLS_BACKUP_ENABLED = _env_bool("AGENT_TOOLS_BACKUP_ENABLED", True)
SYSTEM_PROMPT_EXTRA = os.environ.get("AGENT_SYSTEM_PROMPT", "").strip()

# If the local catalog provider returns no tool_calls but JSON tool intent in message content, parse and run.
# Optional legacy: infer tool calls from assistant message text when the backend sends no wire-format
# ``tool_calls``. Off by default — prefer models that emit native tool_calls.
# If the first completion (planner round 0 only) returns text but no tool_calls while tools[] was
# sent, retry once with tool_choice=required (OpenAI-compatible). Later rounds are not retried.
AGENT_TOOL_CHOICE_REQUIRED_RETRY = _env_bool("AGENT_TOOL_CHOICE_REQUIRED_RETRY", True)

# Per LLM round: INFO log reply type (TOOLS vs TEXT), context size, optional assistant preview (redacted).
AGENT_LOG_LLM_ROUNDS = _env_bool("AGENT_LOG_LLM_ROUNDS", True)
AGENT_LOG_ASSISTANT_PREVIEW_CHARS = _env_int("AGENT_LOG_ASSISTANT_PREVIEW_CHARS", 0)
AGENT_LOG_LARGE_CONTEXT_CHARS = _env_int("AGENT_LOG_LARGE_CONTEXT_CHARS", 120_000)
# One-line tool funnel (allowlist → pre-rank schemas → ranking → forwarded to LLM).
AGENT_LOG_TOOL_PIPELINE = _env_bool("AGENT_LOG_TOOL_PIPELINE", True)
# Repeat full tools[] name list on every llm_round log (noisy; default off).
AGENT_LOG_TOOL_NAMES_EACH_ROUND = _env_bool("AGENT_LOG_TOOL_NAMES_EACH_ROUND", False)

# --- Tool list sent to the chat provider (merged registry tools; no per-request "agent tool mode") ---
# After a tool returns text that looks like an HTTP client/API error, inject a short system hint
# so the model can read_tool / search_web / replace_tool without the user (see TOOLS.md).
AGENT_TOOL_HTTP_ERROR_RECOVERY_HINTS = _env_bool(
    "AGENT_TOOL_HTTP_ERROR_RECOVERY_HINTS", True
)
# Last user message → restrict tools[] to matching category (+ introspection tools).
# Optional: comma-separated TOOL_DOMAIN ids first when classifying (same ids as router categories).
AGENT_TOOL_DOMAIN_ORDER = tuple(
    x.strip().lower()
    for x in (os.environ.get("AGENT_TOOL_DOMAIN_ORDER") or "").split(",")
    if x.strip()
)
# If true: no router match (and no header/body categories) → only minimal introspection tools in tools[].
# Unknown category ids from header/body → same minimal set instead of the full merged list.
# Set false for legacy behavior (no match / unknown → all merged tools). Recommended true for small local models.
AGENT_ROUTER_STRICT_DEFAULT = _env_bool("AGENT_ROUTER_STRICT_DEFAULT", True)
# Remove these registered tool function names from tools[] after routing (comma-separated). Introspection tools are not exempt.
AGENT_TOOLS_DENYLIST = frozenset(
    x.strip()
    for x in (os.environ.get("AGENT_TOOLS_DENYLIST") or "").split(",")
    if x.strip()
)
# Tool Ranking (Semantic Search based)
# Chat tools[]: catalog mode (required field stubs). Full JSON Schema only after reactive promotion.
AGENT_TOOLS_FULL_SCHEMA = _env_bool("AGENT_TOOLS_FULL_SCHEMA", False)
# Tool loop round 2+: re-send tool names in catalog mode (no full JSON Schema) to save prompt tokens.
AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND = _env_bool("AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND", True)

# LLM text degeneration: abort when the same tail block repeats consecutively at stream end.
AGENT_STREAM_REPETITION_GUARD = _env_bool("AGENT_STREAM_REPETITION_GUARD", True)
AGENT_STREAM_REPETITION_MIN_BLOCK = max(40, _env_int("AGENT_STREAM_REPETITION_MIN_BLOCK", 80))
AGENT_STREAM_REPETITION_REPEAT_COUNT = max(2, _env_int("AGENT_STREAM_REPETITION_REPEAT_COUNT", 3))
AGENT_STREAM_REPETITION_TAIL_WINDOW = max(500, _env_int("AGENT_STREAM_REPETITION_TAIL_WINDOW", 1500))

# --- Chat context budget (anti-bloat for LLM prompts; full history stays in DB/UI) ---
CHAT_CONTEXT_PREP_ENABLED = _env_bool("CHAT_CONTEXT_PREP_ENABLED", True)
CHAT_CONTEXT_MAX_MESSAGES = max(8, _env_int("CHAT_CONTEXT_MAX_MESSAGES", 48))
# Per-message char cap = CHAT_CONTEXT_MAX_MESSAGE_RATIO × context_window × ~4 chars/token.
CHAT_CONTEXT_MAX_MESSAGE_RATIO = max(
    0.002, min(0.25, float(os.environ.get("CHAT_CONTEXT_MAX_MESSAGE_RATIO", "0.015")))
)
# Optional fallback context window (tokens) when provider model metadata has no context_length.
# Default 0 = disabled — compaction ratios use provider catalog or CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES only.
CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS = max(0, _env_int("CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS", 0))
# JSON map model_id → context window tokens, e.g. {"Qwen3.6-...gguf":131072}
CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES = (os.environ.get("CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES") or "").strip()
CHAT_CONTEXT_SOFT_LIMIT_RATIO = max(
    0.3, min(0.95, float(os.environ.get("CHAT_CONTEXT_SOFT_LIMIT_RATIO", "0.8")))
)
CHAT_CONTEXT_HARD_LIMIT_RATIO = max(
    0.4, min(0.98, float(os.environ.get("CHAT_CONTEXT_HARD_LIMIT_RATIO", "0.95")))
)
CHAT_CONTEXT_RECENT_VERBATIM_MESSAGES = max(4, _env_int("CHAT_CONTEXT_RECENT_VERBATIM_MESSAGES", 12))
CHAT_CONTEXT_COMPACTION_ENABLED = _env_bool("CHAT_CONTEXT_COMPACTION_ENABLED", True)
CHAT_CONTEXT_COMPACTION_MODEL = (os.environ.get("CHAT_CONTEXT_COMPACTION_MODEL") or "").strip()
# Compaction LLM input cap = ratio × context_window (chars via CHARS_PER_TOKEN_ESTIMATE).
CHAT_CONTEXT_COMPACTION_INPUT_RATIO = max(
    0.01, min(0.5, float(os.environ.get("CHAT_CONTEXT_COMPACTION_INPUT_RATIO", "0.08")))
)
CHAT_CONTEXT_AGENT_LOOP_TRIM_ENABLED = _env_bool("CHAT_CONTEXT_AGENT_LOOP_TRIM_ENABLED", True)
# Tool result message cap = ratio × context_window (chars).
CHAT_CONTEXT_TOOL_RESULT_MAX_RATIO = max(
    0.002, min(0.15, float(os.environ.get("CHAT_CONTEXT_TOOL_RESULT_MAX_RATIO", "0.008")))
)
CHAT_CONTEXT_KEEP_RECENT_TOOL_ROUNDS = max(2, _env_int("CHAT_CONTEXT_KEEP_RECENT_TOOL_ROUNDS", 6))

AGENT_TOOLS_RANKING_ENABLED = _env_bool("AGENT_TOOLS_RANKING_ENABLED", True)
# Dynamic tool forward budget — ratios of provider context window only (context_budget.py).
AGENT_TOOLS_BUDGET_RATIO = max(0.01, min(0.25, float(os.environ.get("AGENT_TOOLS_BUDGET_RATIO", "0.06"))))
# Max tools[] count ≈ ratio × context_window (safety ceiling; fit enforced by tools_budget_tokens).
AGENT_TOOLS_COUNT_CAP_RATIO = max(
    0.00001, min(0.01, float(os.environ.get("AGENT_TOOLS_COUNT_CAP_RATIO", "0.0004")))
)


from apps.backend.infrastructure.platform.config_database_url import (
    resolve_database_url,
    sqlalchemy_postgresql_url,
)


# postgresql://USER:PASSWORD@HOST:5432/DBNAME (psycopg / libpq URI)
DATABASE_URL = resolve_database_url()

# Same DB as DATABASE_URL; use for Alembic / SQLAlchemy create_engine.
SQLALCHEMY_DATABASE_URL = sqlalchemy_postgresql_url(DATABASE_URL)

# First admin when no admin user exists yet: set both before first start, or the process exits.
AGENT_INITIAL_ADMIN_EMAIL = (os.environ.get("AGENT_INITIAL_ADMIN_EMAIL") or "").strip()
AGENT_INITIAL_ADMIN_PASSWORD = os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD") or ""

# Required for POST /auth/setup when set. If unset on first start, a one-time token is generated and logged.
AGENT_SETUP_TOKEN = (os.environ.get("AGENT_SETUP_TOKEN") or "").strip()

# Extra tool tree (optional): scan + create_tool writes here. Two different concerns:
# - ENABLE = whether create_tool may run (security / ops).
# - DIR = filesystem path (must exist in the container; Docker still needs a volume mount for a host folder).
# If ENABLE is true and AGENT_TOOLS_EXTRA_DIR is unset/empty, default /data/tools (typical compose mount target).
CREATE_TOOL_ENABLED = _env_bool("AGENT_CREATE_TOOL_ENABLED", False)
_TOOLS_EXTRA_RAW = (os.environ.get("AGENT_TOOLS_EXTRA_DIR") or "").strip()
TOOLS_EXTRA_DIR = _TOOLS_EXTRA_RAW or ("/data/tools" if CREATE_TOOL_ENABLED else "")


def tool_scan_directories() -> list[Path]:
    from apps.backend.infrastructure.platform.config_scan_dirs import tool_scan_directories as _impl

    return _impl(plugins_dir=PLUGINS_DIR, tools_extra_dir=TOOLS_EXTRA_DIR)


def skill_scan_directories() -> list[Path]:
    from apps.backend.infrastructure.platform.config_scan_dirs import skill_scan_directories as _impl

    return _impl(plugins_dir=PLUGINS_DIR)


# Comma-separated SHA256 hex digests (64 chars). If set, each extra *.py must match one entry.
# Read on each extra-tool scan (reload) so container env updates take effect without code change.

# Fernet URL-safe base64 key for encrypting user_secrets at rest (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SECRETS_MASTER_KEY = (os.environ.get("AGENT_SECRETS_MASTER_KEY") or "").strip()

# Optional base URL for curl examples in register_secrets / secrets_help (e.g. https://agent.example.com). Else 127.0.0.1:AGENT_HTTP_PORT.
PUBLIC_BASE_URL = (os.environ.get("AGENT_PUBLIC_URL") or "").strip().rstrip("/")
HTTP_EXAMPLE_PORT = (os.environ.get("AGENT_HTTP_PORT") or "8088").strip() or "8088"

# POST /v1/user/secrets/register-with-otp: sliding window (per process; client = first X-Forwarded-For or remote).
OTP_REGISTER_RATE_LIMIT_MAX = max(5, min(_env_int("AGENT_OTP_REGISTER_RATE_LIMIT_MAX", 30), 500))
OTP_REGISTER_RATE_LIMIT_WINDOW_SEC = max(
    15, min(_env_int("AGENT_OTP_REGISTER_RATE_LIMIT_WINDOW_SEC", 60), 3600)
)

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

# Dashboard UI: binary uploads (e.g. gallery). Operator may override max MB / MIME in DB.
WORKSPACE_UPLOAD_MAX_FILE_MB = max(1, min(_env_int("AGENT_WORKSPACE_UPLOAD_MAX_MB", 10), 512))

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


def WORKSPACE_upload_dir() -> Path:
    raw = (os.environ.get("AGENT_WORKSPACE_UPLOAD_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "WORKSPACE_uploads"


def WORKSPACE_upload_env_allowed_mime() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_WORKSPACE_UPLOAD_ALLOWED_MIME")
        or "image/jpeg,image/png,image/gif,image/webp"
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def dashboard_upload_dir() -> Path:
    """Gallery uploads (alias for ``WORKSPACE_upload_dir``)."""
    return WORKSPACE_upload_dir()


# --- Media library (user uploads + embed refs; bytes on disk under media_uploads/) ---
MEDIA_DEFAULT_USER_QUOTA_MB = max(1, min(_env_int("AGENT_MEDIA_DEFAULT_USER_QUOTA_MB", 500), 50_000))
MEDIA_UPLOAD_MAX_FILE_MB = max(1, min(_env_int("AGENT_MEDIA_UPLOAD_MAX_FILE_MB", 50), 512))


def media_upload_dir() -> Path:
    raw = (os.environ.get("AGENT_MEDIA_UPLOAD_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(DATA_DIR) / "media_uploads"


def media_upload_env_allowed_mime() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_UPLOAD_ALLOWED_MIME")
        or "audio/mpeg,audio/mp4,audio/flac,audio/ogg,audio/wav,video/mp4"
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def media_embed_env_allowed_hosts() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_EMBED_ALLOWED_HOSTS")
        or "www.youtube.com,youtube.com,www.youtube-nocookie.com,player.vimeo.com"
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def media_stream_env_allowed_hosts() -> frozenset[str]:
    raw = (
        os.environ.get("AGENT_MEDIA_STREAM_ALLOWED_HOSTS")
        or (
            "mdr.de,www.mdr.de,cast.addradio.de,listen.streamtheworld.com,"
            "playerservices.streamtheworld.com,icecast.mdradio.de,stream.radio.co,"
            "akamaized.net,mdr-radio-hls.akamaized.net"
        )
    ).strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


# create_tool limits / codegen (CREATE_TOOL_ENABLED is set above with TOOLS_EXTRA_DIR).
CREATE_TOOL_MAX_BYTES = _env_int("AGENT_CREATE_TOOL_MAX_BYTES", 120_000)
# When create_tool is called without ``source``, catalog LLM generates the module (LLM_AUX_PROVIDER_ID).
CREATE_TOOL_CODEGEN_MODEL = (os.environ.get("AGENT_CREATE_TOOL_CODEGEN_MODEL") or "").strip() or None
CREATE_TOOL_CODEGEN_TIMEOUT = _env_int("AGENT_CREATE_TOOL_CODEGEN_TIMEOUT", 120)
# Codegen prompt: allow httpx/urllib HTTP (keys only via os.environ — set in compose .env).
CREATE_TOOL_CODEGEN_ALLOW_NETWORK = _env_bool("AGENT_CREATE_TOOL_CODEGEN_ALLOW_NETWORK", False)
# Codegen: max catalog LLM attempts (validate + write + reload + test_tool probe). 1 = no retry; cap 20.
CREATE_TOOL_CODEGEN_MAX_ATTEMPTS = max(
    1, min(_env_int("AGENT_CREATE_TOOL_CODEGEN_MAX_ATTEMPTS", 1), 20)
)

# --- Qdrant (vector store for code index) ---
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_API_KEY = (os.environ.get("QDRANT_API_KEY") or "").strip()
QDRANT_COLLECTION_CODE = "code_symbols"

# --- Neo4j (code graph: call-graph, dependency-graph, type hierarchy, impact analysis) ---
NEO4J_URL = (os.environ.get("NEO4J_URL") or "bolt://neo4j:7687").strip()
NEO4J_USER = (os.environ.get("NEO4J_USER") or "neo4j").strip()
NEO4J_PASSWORD = (os.environ.get("NEO4J_PASSWORD") or "").strip()

# --- PIDEA (DOM / Cursor·VSCode·Windsurf via Playwright + CDP) ---
# Cursor mit --remote-debugging-port; Playwright nutzt die HTTP-CDP-URL (nicht ws:// direkt).
# Operator-Override: Admin → IDE Agent (DB). Env nur wenn du bewusst setzt — nicht in compose „mitverdrahten“.
PIDEA_CDP_HTTP_URL = (os.environ.get("PIDEA_CDP_HTTP_URL") or "http://127.0.0.1:9222").strip().rstrip("/")
PIDEA_SELECTOR_IDE = (os.environ.get("PIDEA_SELECTOR_IDE") or "cursor").strip().lower()
PIDEA_SELECTOR_VERSION = (os.environ.get("PIDEA_SELECTOR_VERSION") or "1.7.17").strip()
PIDEA_DEFAULT_TIMEOUT_MS = _env_int("PIDEA_DEFAULT_TIMEOUT_MS", 30_000)

# --- RAG + memory (facts/notes) ---
# Chunking, embedding model, tenant-wide domains, docs ingest path, and memory kill-switch live in
# ``operator_settings`` (Admin → Interfaces), not environment variables.

# Embeddings only (RAG, memory, Qdrant code index, tool ranking). Not used for chat.
# Numbered env: EMBEDDING_PROVIDER_1_BASE_URL, EMBEDDING_PROVIDER_1_API_KEY, …
# Active provider: Admin → Interfaces → Memory & RAG (or auto: first configured).
# Max tokens per /v1/embeddings request (llama.cpp ubatch); RAG chunks stay under this.
EMBEDDING_MAX_INPUT_TOKENS = max(32, min(_env_int("EMBEDDING_MAX_INPUT_TOKENS", 512), 8192))

# --- MCP (Model Context Protocol, stdio servers; optional) ---
AGENT_MCP_ENABLED = _env_bool("AGENT_MCP_ENABLED", False)
AGENT_MCP_SERVERS_JSON = (os.environ.get("AGENT_MCP_SERVERS_JSON") or "").strip()
AGENT_MCP_SERVERS_FILE = (os.environ.get("AGENT_MCP_SERVERS_FILE") or "").strip()
AGENT_MCP_LIST_TIMEOUT_SEC = max(5, min(_env_int("AGENT_MCP_LIST_TIMEOUT_SEC", 45), 600))
AGENT_MCP_CALL_TIMEOUT_SEC = max(5, min(_env_int("AGENT_MCP_CALL_TIMEOUT_SEC", 120), 3600))
AGENT_MCP_MAX_TOOLS = max(1, min(_env_int("AGENT_MCP_MAX_TOOLS", 32), 256))


def _parse_mcp_agent_ids() -> frozenset[str]:
    raw = (os.environ.get("AGENT_MCP_AGENT_IDS") or "coding,coding_plan").strip()
    if not raw:
        return frozenset()
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


AGENT_MCP_AGENT_IDS = _parse_mcp_agent_ids()

# Optional: append one markdown/text file to the system message (plain-text operator “skills” snippet).
AGENT_SKILLS_PROMPT_FILE = (os.environ.get("AGENT_SKILLS_PROMPT_FILE") or "").strip()

# Max combined characters for plugin skills + optional operator file snippet (per chat request).
AGENT_SKILLS_MAX_TOTAL_CHARS = max(512, min(_env_int("AGENT_SKILLS_MAX_TOTAL_CHARS", 48_000), 200_000))


def tool_log_redact_keys() -> frozenset[str]:
    """Argument names to redact in tool_invocations logging (comma-separated env)."""
    raw = (
        os.environ.get("AGENT_TOOL_LOG_REDACT_KEYS")
        or "source,secret,token,api_key,app_password,ics_url"
    ).strip()
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


# Chat secret ingress (ADR 0006): requires Fernet key; see .env.example.
CHAT_SECRET_INGRESS_ENABLED = _env_bool("CHAT_SECRET_INGRESS_ENABLED", False)
# Best-effort regex redaction of common token shapes in user text before LLM (no vault).
# Default off: typical for self-hosted LLM; set true when sending chat to a third-party API.
CHAT_SECRET_HEURISTIC_REDACT_ENABLED = _env_bool("CHAT_SECRET_HEURISTIC_REDACT_ENABLED", False)
CHAT_SECRET_VAULT_TTL_MINUTES = max(5, _env_int("CHAT_SECRET_VAULT_TTL_MINUTES", 30))
CHAT_SECRET_VAULT_FERNET_KEY = (os.environ.get("CHAT_SECRET_VAULT_FERNET_KEY") or "").strip() or None


def tools_allowed_sha256() -> frozenset[str] | None:
    raw = os.environ.get("AGENT_TOOLS_ALLOWED_SHA256", "").strip()
    if not raw:
        return None
    digests = frozenset(p.strip().lower() for p in raw.split(",") if p.strip())
    return digests if digests else None


# Create a config object for backward compatibility
class Config:
    """Compatibility wrapper for the new modular config.

    Include functions (callables) as attributes so code that does `config.some_helper()`
    continues to work. Skip internal names and the Config/config symbols to avoid recursion.
    """
    def __init__(self):
        for key, value in globals().items():
            if key.startswith("_"):
                continue
            if key in ("Config", "config"):
                continue
            setattr(self, key, value)

    def __repr__(self):
        return f"Config(DATA_DIR={getattr(self, 'DATA_DIR', None)})"


# This is what main.py imports
config = Config()