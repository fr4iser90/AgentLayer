import logging
import os
from pathlib import Path

from apps.backend.infrastructure.platform.config_env import env_bool as _env_bool
from apps.backend.infrastructure.platform.config_env import env_int as _env_int
from apps.backend.infrastructure.platform.config_model_rounds import *  # noqa: F403
from apps.backend.infrastructure.platform.config_paths import *  # noqa: F403
from apps.backend.infrastructure.platform.config_workspace_tools import *  # noqa: F403

logger = logging.getLogger(__name__)


def _agent_mode_from_env() -> str:
    """Deployment class: ``sandbox`` (default) = treat tool execution as container-bound; ``host`` = allow host-class policy."""
    v = (os.environ.get("AGENT_MODE") or "sandbox").strip().lower()
    if v in ("sandbox", "host"):
        return v
    if v:
        logger.warning("unknown AGENT_MODE %r — using sandbox", v)
    return "sandbox"


AGENT_MODE = _agent_mode_from_env()

from apps.backend.infrastructure.platform.loop_guard_env import *  # noqa: E402,F403
# Doom-loop exclusions (idempotent reads). ``-`` disables; empty env = defaults below.
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
# Chat tools[]: real JSON Schema per tool. Catalog mode (type-only param stubs) is the fallback for
# tiny context windows — it is not actually cheaper, because the shared param hint is repeated per
# tool (measure with scripts/measure_tool_schema_cost.py: coding = 7.5k full vs 10.1k catalog).
AGENT_TOOLS_FULL_SCHEMA = _env_bool("AGENT_TOOLS_FULL_SCHEMA", True)
# Tool loop round 2+: downgrade to catalog mode to save prompt tokens. Off by default — dropping the
# parameter docs mid-loop is what makes models call tools with empty or invented arguments.
AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND = _env_bool("AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND", False)

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

# DSH-style once+on-change: omit unchanged file/tool-recoverable injects from the LLM.
CHAT_CONTEXT_INJECT_OMIT = _env_bool("CHAT_CONTEXT_INJECT_OMIT", True)
# Re-send omitable injects in full at least every N user turns (0 = only on change/compaction).
CHAT_CONTEXT_INJECT_REFRESH_EVERY_N_TURNS = max(
    0, _env_int("CHAT_CONTEXT_INJECT_REFRESH_EVERY_N_TURNS", 8)
)

AGENT_TOOLS_RANKING_ENABLED = _env_bool("AGENT_TOOLS_RANKING_ENABLED", True)
# Dynamic tool forward budget — ratios of provider context window only (context_budget.py).
# 0.25 fits our largest agent (coding: 49 tools ≈ 7.5k tokens with real schemas) from a 32k window
# on. Below that the plan logs how many tools it had to drop.
AGENT_TOOLS_BUDGET_RATIO = max(0.01, min(0.25, float(os.environ.get("AGENT_TOOLS_BUDGET_RATIO", "0.25"))))
# Max tools[] count ≈ ratio × context_window (safety ceiling; fit enforced by tools_budget_tokens).
# 0.002 → 65 slots at 32k, so a declared allowlist is bounded by real token cost, not by this cap.
AGENT_TOOLS_COUNT_CAP_RATIO = max(
    0.00001, min(0.01, float(os.environ.get("AGENT_TOOLS_COUNT_CAP_RATIO", "0.002")))
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


_MCP_AGENT_DEFAULT = "general,knowledge_companion,research,lifestyle,outdoor,dashboard,creative,media,communications,integrations,math"
AGENT_MCP_AGENT_IDS = frozenset(x.strip() for x in (os.environ.get("AGENT_MCP_AGENT_IDS") or _MCP_AGENT_DEFAULT).split(",") if x.strip())

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