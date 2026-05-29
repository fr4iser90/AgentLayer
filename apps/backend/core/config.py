import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

_PLUGINS_DIR_RAW = os.environ.get("AGENT_PLUGINS_DIR", "").strip()
if _PLUGINS_DIR_RAW:
    PLUGINS_DIR = Path(_PLUGINS_DIR_RAW)
else:
    PLUGINS_DIR = Path(__file__).resolve().parents[3] / "plugins"


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


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
# Optional legacy hint for non-chat tools (e.g. memory extract). Chat uses Admin catalog + UI model picker only.
OLLAMA_DEFAULT_MODEL = (os.environ.get("OLLAMA_DEFAULT_MODEL") or "").strip()

# Optional OpenAI-compatible llama.cpp server (same names as typical compose .env).
# When ``LLAMA_CPP_BASE_URL`` is set, :mod:`model_catalog_providers` registers provider ``llama_cpp``
# before ``operator_settings`` (Admin → Interfaces), if present.
LLAMA_CPP_BASE_URL = (os.environ.get("LLAMA_CPP_BASE_URL") or "").strip().rstrip("/")
LLAMA_CPP_ENABLED = _env_bool("LLAMA_CPP_ENABLED", True)
# Secret for ``Authorization: Bearer`` or for the header named ``LLAMA_CPP_API_HEADER_NAME`` (must match what the gateway expects).
_LLAMA_SECRET_RAW = (os.environ.get("LLAMA_CPP_API_HEADER_VALUE") or "").strip()
LLAMA_CPP_API_HEADER_VALUE = _LLAMA_SECRET_RAW or None
_LLAMA_HDR_RAW = (os.environ.get("LLAMA_CPP_API_HEADER_NAME") or "").strip()
LLAMA_CPP_API_HEADER_NAME = _LLAMA_HDR_RAW or None
LLAMA_CPP_ROUTER_MODEL = (os.environ.get("LLAMA_CPP_ROUTER_MODEL") or "").strip() or None
LLAMA_CPP_MODEL_DEFAULT = (os.environ.get("LLAMA_CPP_MODEL_DEFAULT") or "").strip() or None
LLAMA_CPP_MODEL_VLM = (os.environ.get("LLAMA_CPP_MODEL_VLM") or "").strip() or None
LLAMA_CPP_MODEL_AGENT = (os.environ.get("LLAMA_CPP_MODEL_AGENT") or "").strip() or None
LLAMA_CPP_MODEL_CODING = (os.environ.get("LLAMA_CPP_MODEL_CODING") or "").strip() or None

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


def _resolve_max_tool_rounds() -> int:
    """``AGENT_MAX_TOOL_ROUNDS``: positive = limit (capped at ``MAX_TOOL_ROUNDS_CAP``); 0 or negative = use cap (\"practical unlimited\" for local runs)."""
    raw = (os.environ.get("AGENT_MAX_TOOL_ROUNDS") or "").strip()
    if not raw:
        return 8
    try:
        v = int(raw)
    except ValueError:
        logger.warning("invalid AGENT_MAX_TOOL_ROUNDS %r — using default 8", raw)
        return 8
    if v <= 0:
        logger.info(
            "AGENT_MAX_TOOL_ROUNDS=%s → using high cap %s tool rounds (override with AGENT_MAX_TOOL_ROUNDS_CAP)",
            raw,
            MAX_TOOL_ROUNDS_CAP,
        )
        return MAX_TOOL_ROUNDS_CAP
    return max(1, min(v, MAX_TOOL_ROUNDS_CAP))


MAX_TOOL_ROUNDS = _resolve_max_tool_rounds()
# Phase 1 (coding-agent-roadmap): break identical tool failure loops (e.g. empty JSON / same parameter error).
AGENT_TOOL_THRASH_ENABLED = _env_bool("AGENT_TOOL_THRASH_ENABLED", True)
AGENT_TOOL_THRASH_STREAK_MAX = max(2, _env_int("AGENT_TOOL_THRASH_STREAK_MAX", 10))
# Doom loop guard: same tool + same arguments repeated (any result). Default streak 10 is a common industry default.
AGENT_TOOL_DOOM_LOOP_ENABLED = _env_bool("AGENT_TOOL_DOOM_LOOP_ENABLED", True)
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
# Max wall time for ``coding_workspace_verify`` (runs ``verify_command`` from ``.agentlayer.json`` only).
AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC = max(30, min(_env_int("AGENT_WORKSPACE_VERIFY_TIMEOUT_SEC", 600), 3600))
DATA_DIR = os.environ.get("AGENT_DATA_DIR", "/data")
# Before replace_tool / update_tool / create_tool overwrite, copy prior .py here (UTC timestamp prefix).
TOOLS_BACKUP_ENABLED = _env_bool("AGENT_TOOLS_BACKUP_ENABLED", True)
SYSTEM_PROMPT_EXTRA = os.environ.get("AGENT_SYSTEM_PROMPT", "").strip()

# If Ollama returns no tool_calls but JSON tool intent in message content (e.g. Nemotron), parse and run.
# Optional legacy: infer tool calls from assistant message text when the backend sends no wire-format
# ``tool_calls``. Off by default — prefer models that emit native tool_calls.
CONTENT_TOOL_FALLBACK = _env_bool("AGENT_CONTENT_TOOL_FALLBACK", False)

# If the first completion (planner round 0 only) returns text but no tool_calls while tools[] was
# sent, retry once with tool_choice=required (OpenAI-compatible). Later rounds are not retried.
AGENT_TOOL_CHOICE_REQUIRED_RETRY = _env_bool("AGENT_TOOL_CHOICE_REQUIRED_RETRY", True)

# Per Ollama round: INFO log reply type (TOOLS vs TEXT), context size, optional assistant preview (redacted).
AGENT_LOG_LLM_ROUNDS = _env_bool("AGENT_LOG_LLM_ROUNDS", True)
AGENT_LOG_ASSISTANT_PREVIEW_CHARS = _env_int("AGENT_LOG_ASSISTANT_PREVIEW_CHARS", 0)
AGENT_LOG_LARGE_CONTEXT_CHARS = _env_int("AGENT_LOG_LARGE_CONTEXT_CHARS", 120_000)
# Log serialized tools[] size + rough token bounds before chat/completions.
AGENT_LOG_TOOLS_REQUEST_ESTIMATE = _env_bool("AGENT_LOG_TOOLS_REQUEST_ESTIMATE", True)

# --- Tool list sent to Ollama (merged registry tools; no per-request "agent tool mode") ---
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
AGENT_ROUTER_STRICT_DEFAULT = _env_bool("AGENT_ROUTER_STRICT_DEFAULT", False)
# Remove these registered tool function names from tools[] after routing (comma-separated). Introspection tools are not exempt.
AGENT_TOOLS_DENYLIST = frozenset(
    x.strip()
    for x in (os.environ.get("AGENT_TOOLS_DENYLIST") or "").split(",")
    if x.strip()
)
# Tool Ranking (Semantic Search based)
# Chat tools[]: send full JSON Schema per tool (default on). Set false for compact catalog (empty parameters).
AGENT_TOOLS_FULL_SCHEMA = _env_bool("AGENT_TOOLS_FULL_SCHEMA", True)

# LLM text degeneration: abort when the same tail block repeats consecutively at stream end.
AGENT_STREAM_REPETITION_GUARD = _env_bool("AGENT_STREAM_REPETITION_GUARD", True)
AGENT_STREAM_REPETITION_MIN_BLOCK = max(40, _env_int("AGENT_STREAM_REPETITION_MIN_BLOCK", 80))
AGENT_STREAM_REPETITION_REPEAT_COUNT = max(2, _env_int("AGENT_STREAM_REPETITION_REPEAT_COUNT", 3))
AGENT_STREAM_REPETITION_TAIL_WINDOW = max(500, _env_int("AGENT_STREAM_REPETITION_TAIL_WINDOW", 1500))

AGENT_TOOLS_RANKING_ENABLED = _env_bool("AGENT_TOOLS_RANKING_ENABLED", True)
AGENT_TOOLS_MAX_RANKING = max(1, int(os.environ.get("AGENT_TOOLS_MAX_RANKING", "10")))
AGENT_TOOLS_SEMANTIC_WEIGHT = max(0.0, float(os.environ.get("AGENT_TOOLS_SEMANTIC_WEIGHT", "1.0")))
AGENT_TOOLS_TRIGGER_BOOST = max(0.0, min(1.0, float(os.environ.get("AGENT_TOOLS_TRIGGER_BOOST", "0.1"))))
AGENT_TOOLS_CONTEXT_BOOST = max(0.0, min(1.0, float(os.environ.get("AGENT_TOOLS_CONTEXT_BOOST", "0.05"))))
AGENT_TOOLS_MIN_SCORE_THRESHOLD = max(0.0, min(1.0, float(os.environ.get("AGENT_TOOLS_MIN_SCORE_THRESHOLD", "0.1"))))
AGENT_TOOLS_RANKING_FALLBACK_ALL = _env_bool("AGENT_TOOLS_RANKING_FALLBACK_ALL", True)


def _resolve_database_url() -> str:
    """
    Prefer explicit DATABASE_URL. If unset/empty, build from POSTGRES_* / PGHOST (same as compose postgres service),
    so the agent starts without duplicating the full URL in compose.yaml.
    """
    direct = os.environ.get("DATABASE_URL", "").strip()
    if direct:
        return direct
    user = (os.environ.get("POSTGRES_USER") or "agent").strip()
    dbn = (os.environ.get("POSTGRES_DB") or "agent").strip()
    if not user or not dbn:
        return ""
    raw_pw = os.environ.get("POSTGRES_PASSWORD")
    password = "agent" if raw_pw is None else str(raw_pw)
    host = (
        os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "postgres"
    ).strip() or "postgres"
    port = (os.environ.get("PGPORT") or "5432").strip() or "5432"
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(dbn)}"
    )


# postgresql://USER:PASSWORD@HOST:5432/DBNAME (psycopg / libpq URI)
DATABASE_URL = _resolve_database_url()


def _sqlalchemy_postgresql_url(url: str) -> str:
    """SQLAlchemy maps plain postgresql:// to psycopg2; we only ship psycopg (v3)."""
    u = (url or "").strip()
    if not u or "://" not in u:
        return u
    scheme, rest = u.split("://", 1)
    if "+" in scheme:
        return u
    if scheme in ("postgresql", "postgres"):
        return f"postgresql+psycopg://{rest}"
    return u


# Same DB as DATABASE_URL; use for Alembic / SQLAlchemy create_engine.
SQLALCHEMY_DATABASE_URL = _sqlalchemy_postgresql_url(DATABASE_URL)

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
    """
    Tool **roots** to scan **recursively** for ``*.py`` (TOOLS + HANDLERS), including subfolders.
    If ``AGENT_TOOL_DIRS`` is set (comma-separated), only those paths are used (must exist).
    Otherwise: shipped ``tools`` tree (sibling of the ``app`` package), then ``AGENT_TOOLS_EXTRA_DIR`` if set.
    Earlier roots / lexicographically earlier paths win when two files define the same tool name.
    """
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            logger.warning("tool directory not resolvable: %s", p)
            return
        if not r.is_dir():
            return
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)

    raw = (os.environ.get("AGENT_TOOL_DIRS") or "").strip()
    if raw:
        for part in raw.split(","):
            add(Path(part.strip()).expanduser())
        return out

    # Repository root: use central PLUGINS_DIR.
    add(PLUGINS_DIR / "tools")
    add(PLUGINS_DIR / "workflows")
    if TOOLS_EXTRA_DIR:
        add(Path(TOOLS_EXTRA_DIR).expanduser())
    return out


def skill_scan_directories() -> list[Path]:
    """
    Skill plugin **roots** to scan **recursively** for ``*.py`` (same layout idea as ``plugins/tools``).

    If ``AGENT_SKILL_DIRS`` is set (comma-separated), only those paths are used (must exist).
    Otherwise: ``plugins/skills`` under :data:`PLUGINS_DIR`.
    """
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            logger.warning("skill directory not resolvable: %s", p)
            return
        if not r.is_dir():
            return
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)

    raw = (os.environ.get("AGENT_SKILL_DIRS") or "").strip()
    if raw:
        for part in raw.split(","):
            add(Path(part.strip()).expanduser())
        return out

    add(PLUGINS_DIR / "skills")
    return out


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


# create_tool limits / codegen (CREATE_TOOL_ENABLED is set above with TOOLS_EXTRA_DIR).
CREATE_TOOL_MAX_BYTES = _env_int("AGENT_CREATE_TOOL_MAX_BYTES", 120_000)
# When create_tool is called without ``source``, Ollama generates the module (same base URL as chat).
CREATE_TOOL_CODEGEN_MODEL = (
    os.environ.get("AGENT_CREATE_TOOL_CODEGEN_MODEL") or "qwen2.5-coder:7b"
).strip()
CREATE_TOOL_CODEGEN_TIMEOUT = _env_int("AGENT_CREATE_TOOL_CODEGEN_TIMEOUT", 120)
# Codegen prompt: allow httpx/urllib HTTP (keys only via os.environ — set in compose .env).
CREATE_TOOL_CODEGEN_ALLOW_NETWORK = _env_bool("AGENT_CREATE_TOOL_CODEGEN_ALLOW_NETWORK", False)
# Codegen: max Ollama attempts (validate + write + reload + test_tool probe). 1 = no retry; cap 20.
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
NEO4J_PASSWORD = (os.environ.get("NEO4J_PASSWORD") or "changeme").strip()

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
# POST {EMBEDDING_BASE_URL}/embeddings with EMBEDDING_API_HEADER_NAME / EMBEDDING_API_HEADER_VALUE.
def _strip_env_quotes(raw: str | None) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


_EMBED_BASE_RAW = (os.environ.get("EMBEDDING_BASE_URL") or "").strip().rstrip("/")
EMBEDDING_BASE_URL = _strip_env_quotes(_EMBED_BASE_RAW).rstrip("/")
# Optional: preferred embedding model id when not in operator_settings or not on provider list.
EMBEDDING_MODEL = _strip_env_quotes((os.environ.get("EMBEDDING_MODEL") or "").strip())[:256]
EMBEDDING_API_HEADER_NAME = _strip_env_quotes(
    (os.environ.get("EMBEDDING_API_HEADER_NAME") or "").strip()
) or "X-API-KEY"
_EMBED_SECRET_RAW = _strip_env_quotes(
    (os.environ.get("EMBEDDING_API_HEADER_VALUE") or os.environ.get("EMBEDDING_API_KEY") or "").strip()
)
EMBEDDING_API_HEADER_VALUE = _EMBED_SECRET_RAW


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


def _parse_skills_prompt_agent_ids() -> frozenset[str]:
    raw = (os.environ.get("AGENT_SKILLS_PROMPT_AGENT_IDS") or "coding,coding_plan").strip()
    if not raw:
        return frozenset()
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


AGENT_SKILLS_PROMPT_AGENT_IDS = _parse_skills_prompt_agent_ids()

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
        return f"Config(OLLAMA_BASE_URL={getattr(self, 'OLLAMA_BASE_URL', None)}, DATA_DIR={getattr(self, 'DATA_DIR', None)})"


# This is what main.py imports
config = Config()