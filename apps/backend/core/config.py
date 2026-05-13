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
OLLAMA_DEFAULT_MODEL = (os.environ.get("OLLAMA_DEFAULT_MODEL") or "nemotron-3-nano:4b").strip()

# Hybrid model routing: per-profile defaults (empty = fall back to OLLAMA_DEFAULT_MODEL).
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

MAX_TOOL_ROUNDS = _env_int("AGENT_MAX_TOOL_ROUNDS", 8)
DATA_DIR = os.environ.get("AGENT_DATA_DIR", "/data")
# Before replace_tool / update_tool / create_tool overwrite, copy prior .py here (UTC timestamp prefix).
TOOLS_BACKUP_ENABLED = _env_bool("AGENT_TOOLS_BACKUP_ENABLED", True)
SYSTEM_PROMPT_EXTRA = os.environ.get("AGENT_SYSTEM_PROMPT", "").strip()

# If Ollama returns no tool_calls but JSON tool intent in message content (e.g. Nemotron), parse and run.
CONTENT_TOOL_FALLBACK = _env_bool("AGENT_CONTENT_TOOL_FALLBACK", True)

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

# Dashboard UI: binary uploads (e.g. gallery). Operator may override max MB / MIME in DB.
WORKSPACE_UPLOAD_MAX_FILE_MB = max(1, min(_env_int("AGENT_WORKSPACE_UPLOAD_MAX_MB", 10), 512))

# --- Coding tools (dashboard-scoped, container-isolated) ---
# Root directory for all coding tool file operations; agent cannot escape this tree.
_CODING_ROOT_RAW = (os.environ.get("AGENT_CODING_ROOT") or "").strip()
CODING_ROOT: Path | None = Path(_CODING_ROOT_RAW).expanduser() if _CODING_ROOT_RAW else None
# When true, coding tools are enabled; false → all coding_* tools return disabled error.
CODING_ENABLED = _env_bool("AGENT_CODING_ENABLED", True)
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


def tool_log_redact_keys() -> frozenset[str]:
    """Argument names to redact in tool_invocations logging (comma-separated env)."""
    raw = (os.environ.get("AGENT_TOOL_LOG_REDACT_KEYS") or "source").strip()
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


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