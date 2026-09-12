---
doc_id: features-external-agent-runtimes
domain: agentlayer_docs
tags: [coding-agent, external-runtime, qwen-code, agents, architecture]
---

## What it is

An **external agent runtime** executes an agent turn in its own process instead of
AgentLayer's planner loop. The first adapter is **Qwen Code**; the port is generic, so
Claude Code, Codex or a local runner plug in the same way.

AgentLayer keeps ownership of everything around the loop: identity, workspace
authorization, streaming to the web client, cancellation, provider credentials and audit.
The vendor only sees a working directory, a prompt and one model endpoint.

Related decision: [`docs/adr/0010-external-agent-runtime-port.md`](../adr/0010-external-agent-runtime-port.md).

## Which agent runs where

`agent.yaml` decides; no code knows vendor names outside its adapter.

| Agent | Loop | How to reach it |
|-------|------|-----------------|
| `general`, `dashboard`, … | AgentLayer planner (`chat_tool_loop`) | Chat, default |
| `coding`, `coding_plan`, `security_auditor` | AgentLayer planner, delegate-only | `general` delegates via `delegate` |
| `coding_qwen` | **Qwen Code process** | `/chat?agent=coding_qwen` + bound workspace, or `delegate(agent_id="coding_qwen")` |

```yaml
# plugins/agents/coding_qwen/agent.yaml
id: coding_qwen
external_runtime: qwen_code
requires_workspace: true
strict_workspace: true
schedulable: false
delegatable: true
```

## Where the branch happens

One place, `apps/backend/application/agent_runtime/use_cases/chat_completion.py`, right
before `run_chat_tool_loop(...)`:

```python
if _external_runtime_active:
    return await maybe_run_external_runtime_turn(...)
return await run_chat_tool_loop(...)
```

`maybe_run_external_runtime_turn` returns the same OpenAI-style completion dict the tool
loop would have returned, so the WebSocket wrapper, client-side message persistence and
`agent_runs` bookkeeping are unchanged. Delegation needs **no extra code**:
`delegate` runs a nested `chat_completion` with the specialist's `agent_id`, hits the same
branch, and `domain/agent_runtime/subagent_events.py` forwards the child events to the
subagent card.

The upstream SSE passthrough (`stream: true` + plain completion) is skipped for external
turns — there is no upstream LLM call to mirror; deltas arrive over the WebSocket instead.

## Port and adapter

| Piece | Path |
|-------|------|
| Port (contracts + registry, domain layer) | `apps/backend/domain/agent_runtime/external_runtime.py` |
| Normalized events → chat events | `apps/backend/domain/agent_runtime/external_runtime_events.py` |
| Turn orchestration (guards, git, audit, resume) | `apps/backend/application/agent_runtime/use_cases/chat_external_runtime.py` |
| Qwen Code adapter | `apps/backend/infrastructure/agent_runtime/external_runtimes/qwen_code.py` |
| Adapter registration (import side effect) | `apps/backend/infrastructure/agent_runtime/external_runtimes/__init__.py`, wired by `application/platform/use_cases/server_lifecycle.py` |
| Config | `apps/backend/infrastructure/platform/config_external_runtimes.py` (`.env.example` → “External agent runtimes”) |

The contract, in short:

```python
class ExternalAgentRuntime(Protocol):
    id: str
    supports_resume: bool
    supports_write: bool
    default_permission_mode: str
    def available(self) -> tuple[bool, str]: ...
    async def run(self, request: ExternalRunRequest, *,
                  emit: EventSink, cancel_event: asyncio.Event | None) -> ExternalRunResult: ...
```

Adapters emit normalized events (`status`, `delta`, `tool_call`, `tool_result`, `done`,
`error`) and never build WebSocket payloads themselves. Adding a runtime = one adapter
module + one line in `_ADAPTERS` + one `agent.yaml`.

## Provider pass-through

There is no second provider configuration. The turn's already-resolved provider
(`get_provider_spec()` + `resolve_model_for_provider()` in
`apps/backend/infrastructure/providers/model_catalog_providers.py`) becomes an
OpenAI-compatible endpoint for the child process:

- `OPENAI_BASE_URL` = `{normalized base}/v1`, `OPENAI_API_KEY` = the provider key, `OPENAI_MODEL` = the resolved model;
- a private `$HOME/.qwen/settings.json` per conversation selects `security.auth.selectedType: "openai"` and that model id;
- the key exists in the child environment only — never in the settings file, an event, a log line or an audit row.

The child gets a **curated** environment (`PATH`, `HOME`, locale, plus this workspace's
bound user secrets via `plugins/tools/workspace/lib/env_secret_bridge.py`). It never
inherits the backend environment, which holds the database DSN and
`AGENT_SECRETS_MASTER_KEY`.

`AGENT_QWEN_MODEL` overrides the model when a vendor-specific coder model is preferred.
With several providers configured, the request must name one
(`agent_model_catalog_owned_by`), otherwise the run is refused instead of guessing.

## Session model

One conversation = one vendor session. The native id is stored on
`chat_conversations.external_session_id` (`external_runtime` alongside it) by
`infrastructure/agent_runtime/conversation_external_session_store.py` and passed back as
`resume` on the next turn. A second concurrent run in the same conversation is refused.

First turn of a conversation includes a compact digest of the earlier messages; resumed
turns send only the new request, because the vendor session already remembers.

## Safety posture (full-auto file edits)

Decided posture: no per-call approval; the run is **reviewable and attributable** instead.

| Guard | Where |
|-------|-------|
| Workspace must be authorized and bound | existing `chat_run_bootstrap.py` (unchanged) |
| Client-execution workspaces refused (ADR 0009) | `_workspace_path_for_run` |
| Path confined to `AGENT_CODING_ROOT`, `AGENT_CODING_PATH_BLOCKLIST` honoured | `_workspace_path_for_run` |
| `permission_mode` ceiling: `auto-edit`; `yolo` needs `AGENT_EXTERNAL_RUNTIME_ALLOW_YOLO` | adapter + `clamp_permission_mode` |
| Git HEAD/status/diff snapshotted before and after; touched paths reported | `_git_state`, `_change_summary` |
| Every run audited as `external_runtime.run` in `tool_invocations` | `_audit` → `infrastructure/db/db.py::log_tool_invocation` |
| One run per conversation | `_busy_conversations` |
| Not schedulable (no unattended full-auto builds) | `plugins/agents/coding_qwen/agent.yaml` |

**Accepted residual risk:** Qwen Code's own shell is *not* subject to
`plugins/tools/workspace/lib/bash_policy.py` (no command blocklist, no package admission)
and it runs as the same container user that owns the workspaces. See ADR 0010.

## Events the web client sees

```json
{"type": "agent.llm_delta", "agent_run_id": "…", "round": 0, "delta": "Reading the repo. "}
{"type": "agent.tool_start", "agent_run_id": "…", "round": 0, "name": "edit_file",
 "summary": "{\"path\":\"a.py\"}", "step_label": "edit_file #1", "rejected": false}
{"type": "agent.tool_done", "agent_run_id": "…", "round": 0, "name": "edit_file",
 "result_chars": 7, "result_ok": true, "result_display": "patched"}
{"type": "agent.tool_done", "name": "external_runtime_changes", "result_display": "1 path(s) touched: a.py …"}
{"type": "agent.done", "agent_run_id": "…", "kind": "final_text", "round": 1}
```

`step_label` carries a sequence number on purpose: the client pairs tool durations by
tool *name* (`agentChatWsCore.ts`, `buildRunCards.ts`), so repeated `shell` calls would
otherwise overwrite each other.

`GET /v1/chat/runtime` answers with the runtime catalog so a client can hide the entry
point when the binary is missing:

```json
{"external_runtimes": {"enabled": true, "fallback_internal": false,
  "runtimes": [{"id": "qwen_code", "available": true, "reason": "",
                "supports_resume": true, "supports_write": true,
                "default_permission_mode": "auto-edit"}]}}
```

## Enable it

```bash
# .env
AGENT_EXTERNAL_RUNTIME_ENABLED=true
# AGENT_EXTERNAL_RUNTIME_ALLOW_YOLO=false     # ceiling
# AGENT_QWEN_MODEL=                            # empty = turn's resolved model
```

```bash
docker compose build && docker compose up -d   # image ships node 22 + @qwen-code/qwen-code
alembic -c apps/backend/infrastructure/db/alembic.ini upgrade head   # schema_127
python scripts/verify_external_runtime_live.py --workspace <workspace-uuid>
```

`GET /v1/chat/runtime` shows why a runtime is unavailable; with
`AGENT_EXTERNAL_RUNTIME_FALLBACK_INTERNAL=true` a missing runtime degrades to AgentLayer's
own loop instead of failing the turn (default: fail, so nobody silently builds with a
different agent).

## Known limits

- Goal bar, todo panel and `agent.goal_round` auto-continue stay empty: they are driven by
  AgentLayer tools, which the external loop does not call.
- No per-tool approval UI (`agent.permission_ask` is not used by external runtimes yet).
- `POST /v1/chat/completions` with `stream: true` delivers the final result only; deltas
  need the WebSocket.
- Qwen's own MCP servers are not configured from AgentLayer; workspace
  `mcp_stdio_servers` apply to AgentLayer's loop only.
- `qwen-code-sdk` is a preview release on PyPI (pinned in `requirements.txt`).

## See also

- `docs/adr/0010-external-agent-runtime-port.md` — decision, alternatives, residual risk.
- `docs/planning/coding-agent-roadmap.md` — Epic I, where this fits in the coding vertical.
- `docs/features/agent-registry-and-allowlists.md` — `agent.yaml` fields.
- `docs/adr/0009-client-side-execution.md` — workspaces the backend cannot open.
