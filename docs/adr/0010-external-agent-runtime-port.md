---
doc_id: adr-0010-external-agent-runtime-port
domain: agentlayer_docs
tags: [adr, coding-agent, external-runtime, qwen-code, agents, architecture, security]
---

# ADR 0010: External agent runtime port (Qwen Code as first adapter)

## Status

**Accepted.** Implemented: port, Qwen Code adapter, the single fork in `chat_completion`,
`schema_127`, the `coding_qwen` manifest, and the chat-surface wiring. `pytest tests/unit`
is green (1237 passed, 2 skipped). **A live end-to-end run against a deployed instance has
not happened yet** — see [Verification](#verification). The posture in §5 is a decision to
accept residual risk, so it is the part worth re-reading before enabling the flag.

Feature doc with the concrete anchors: [`docs/features/external-agent-runtimes.md`](../features/external-agent-runtimes.md).

## Context

Until now there was exactly one way to execute an agent turn: AgentLayer's planner loop
(`application/agent_runtime/use_cases/chat_completion.py` → `chat_tool_loop.py`), which
offers the agent our plugin tools and iterates until it stops asking for tools. The coding
agent is that same loop with the `coding` tool domain — no separate runtime.

Terminal-first coding agents have meanwhile become the stronger product at exactly the work
`coding`/`coding_build` does: they hold their own session, plan, edit, shell, and re-read
without a caller supervising each step. Reimplementing that loop tool-by-tool inside
AgentLayer is a treadmill we lose, and the user's ask was explicit: make the coding agent
**replaceable behind an interface**, with Qwen Code as the first thing plugged in, and keep
the interface generic for other agents and vendors.

What must **not** be handed to a vendor is everything AgentLayer already does correctly:
identity and role checks, workspace authorization and path jail, provider credentials,
streaming to the web client, cancellation, delegation, and audit. Any design that makes the
vendor own those is a non-starter, because they are the product's security boundary.

Vendor side, three attachment points exist and differ in real ways:

| Option | Mechanism | Consequence |
| --- | --- | --- |
| `qwen-code-sdk` (PyPI) | Python package that spawns the CLI per session and yields structured messages | In-process async call, structured options (`resume`, permission mode, tool exclusion), `interrupt()`/`close()` on the stream |
| `qwen serve` | Long-lived daemon, HTTP + SSE, ACP-speaking | Shared stateful process, health and port management, unclear per-conversation isolation on a multi-tenant host |
| Headless CLI | `qwen -p … --output-format stream-json` | No pip dependency, but no `interrupt()` and options only as argv |

Precedent for the shape of the fix already exists in this codebase: `McpRuntime` is an
application-owned port with an infrastructure adapter, and the agent registry is pure
manifest. Both let a new capability arrive without the loop learning vendor names.

## Decision

### 1. A domain port, an infrastructure adapter

`domain/agent_runtime/external_runtime.py` declares the contract and holds the registry;
`infrastructure/agent_runtime/external_runtimes/qwen_code.py` implements it. The contract is
deliberately two methods:

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

`available()` returning a **reason**, not a bool, is what lets `GET /v1/chat/runtime` tell the
client why nothing will build. The import is lazy: with neither the SDK nor the binary
installed, the backend behaves exactly as before and the runtime reports itself unavailable.

Adding a vendor is one adapter module, one line in `_ADAPTERS`, one `agent.yaml`.

### 2. Selection is declarative, in the manifest

`plugins/agents/<id>/agent.yaml` gains `external_runtime: <runtime-id>`; the loader
(`domain/agent_runtime/plugin_loader.py`) reads it into the registry. Nothing in the
application or domain layer knows the string `qwen`. This keeps the decision about *who codes*
reviewable in a diff, which a per-request toggle would not be.

The same manifest sets `schedulable: false` on `coding_qwen`: an interactive full-auto run is
reviewable as a diff the next minute, an unattended 3 a.m. build is not.

### 3. Exactly one fork, same return shape

The branch sits immediately before `run_chat_tool_loop(...)` in `chat_completion` and returns
the **same** OpenAI-style completion dict. That single constraint is what keeps the WebSocket
wrapper, client-side message persistence, `agent_runs` bookkeeping, and thread grouping
untouched — the client cannot tell an external turn from an internal one except by the agent
title.

Delegation costs no code: `delegate` already runs a nested `chat_completion` with the
specialist's `agent_id`, so it hits the same branch, and
`domain/agent_runtime/subagent_events.py` forwards child events into the existing subagent
card. `general` can hand a build to Qwen with the same tool it uses for `coding`.

Because there is no upstream LLM call to mirror, the upstream SSE passthrough
(`stream: true` on plain HTTP) is skipped for external turns; deltas arrive over the WebSocket.
The HTTP call still returns the final result.

### 4. One provider, passed through

There is no second provider configuration for the vendor. The provider AgentLayer already
resolved for this turn (`get_provider_spec()` + `resolve_model_for_provider()`) becomes an
OpenAI-compatible endpoint for the child: `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`,
with a private `$HOME/.qwen/settings.json` per conversation selecting that model. The key lives
in the child environment only — never in that settings file, an event, a log line, or an audit row.

The child gets a **curated** environment (PATH, HOME, locale, plus this workspace's bound user
secrets), never the backend environment, which holds the database DSN and
`AGENT_SECRETS_MASTER_KEY`. With several providers configured, the request must name
one; guessing which LLM would build someone's repo is worse than refusing.

### 5. Safety posture: reviewable and attributable, not per-call approval

Decided posture: **no per-tool approval prompt.** An external loop that asked us to approve
each edit would be slower than the loop we replaced, and the vendor's callback shape is not
ours to control. In exchange, a run is bounded and reconstructible: workspace must be
authorized and bound; client-execution workspaces are refused ([ADR 0009](0009-client-side-execution.md));
paths stay inside `AGENT_CODING_ROOT` and honour `AGENT_CODING_PATH_BLOCKLIST`;
`permission_mode` is clamped to `auto-edit` unless the operator raises the ceiling;
Git HEAD/status/diff is snapshotted before and after and the touched paths are reported;
every run is audited as `external_runtime.run` in `tool_invocations`; one run per conversation.

**Accepted residual risk, stated plainly:** Qwen Code's own shell is *not* subject to
`plugins/tools/workspace/lib/bash_policy.py` — no command blocklist, no package admission — and
it runs as the same container user that owns the workspaces. Inside the workspace jail that is a
build agent behaving normally; it means AgentLayer's bash policy is not a control on external
turns, and nobody should describe it as one. Raising the ceiling to `yolo` widens exactly this.

### 6. One conversation, one vendor session

`chat_conversations.external_runtime` / `external_session_id` (`schema_127`) store the vendor's
native session id, passed back as `resume` on the next turn. Resumed turns send only the new
request; the first turn includes a compact digest of earlier messages, because the vendor
session does not know AgentLayer's history. Two concurrent runs in one conversation are refused:
two vendor sessions editing one tree fight each other.

### 7. Fail loudly, degrade on purpose

If the declared runtime is unavailable, the turn **fails** with the adapter's reason.
`AGENT_EXTERNAL_RUNTIME_FALLBACK_INTERNAL=true` degrades to AgentLayer's own loop instead —
opt-in, because a silent downgrade changes *who* is coding in someone's repository.

## Consequences

- Goal bar, todo panel and `agent.goal_round` auto-continue stay empty for external turns:
  those are driven by AgentLayer tools the external loop never calls. Same for
  `agent.permission_ask` — a per-tool approval UI needs an interruptible round-trip into the
  vendor loop, which the SDK does not offer today.
- Two execution paths now need coverage. The unit suite stubs the port, which proves the
  guards and the event mapping but **not** that the vendor behaves as documented.
- The vendor's MCP servers are not configured from AgentLayer, so a workspace's
  `mcp_stdio_servers` apply to the internal loop only. Wiring both is a follow-up.
- `qwen-code-sdk` is a preview release on PyPI and is pinned exactly; an open range resolves to
  nothing. A vendor change to the message schema lands on our adapter, which is the point of
  having exactly one place for it.
- The runtime catalog on `GET /v1/chat/runtime` is client-visible availability, not a secret
  store: reasons are operator-facing strings.

## Alternatives considered

- **`qwen serve` daemon (HTTP/SSE, ACP).** Would give a long-lived process we could interrupt
  mid-tool and later route per-call approvals through. Rejected for slice 1: a shared stateful
  daemon per host is the wrong isolation model when several users' workspaces are in scope, and
  health, ports, and restart semantics are new ops surface for no gain on the first slice.
- **Headless `qwen -p --output-format stream-json`.** Fewest dependencies. Rejected: no
  `interrupt()`, so cancellation would mean killing a process group and losing the session id,
  and every option becomes argv string-building.
- **Rewriting our coding tools to the vendor's names, staying in our loop.** That is the
  treadmill this ADR exists to end.
- **Exposing AgentLayer tools to the vendor over MCP.** Our loop and the vendor loop would both
  own tool execution, and the vendor would receive our entire surface, including platform tools
  it has no business calling. The vendor's own file/shell tools already cover a workspace.
- **A per-request runtime selector instead of a manifest field.** More flexible at runtime, but
  the decision "an external full-auto agent may build this" would then live in a request body
  instead of a reviewable file.

## Verification

Done:

- `tests/unit/test_external_runtime_port.py` — registry, availability, clamp rules.
- `tests/unit/test_external_runtime_qwen_adapter.py` — message → event mapping, provider env,
  per-conversation HOME, cancel → `interrupt()`, resume id capture.
- `tests/unit/test_external_runtime_guardrails.py` — workspace jail, blocklist, client-execution
  refusal, provider ambiguity refusal.
- `tests/unit/test_external_runtime_chat_turn.py` — the fork, refusal paths, concurrency, audit.
- `tests/unit/test_agent_plugin_loader.py` — the `coding_qwen` manifest contract.

Not done (the open end):

1. Rebuild the image (`@qwen-code/qwen-code` is pinned in `Dockerfile`, `qwen-code-sdk` in
   `requirements.txt`) and run `alembic upgrade head` for `schema_127`.
2. `python scripts/verify_external_runtime_live.py --workspace <uuid>` — status, one
   permission-mode-`plan` turn, then a second turn on the same conversation to prove resume.
3. Confirm an audit row lands in `tool_invocations` and the touched-paths summary renders.

## See also

- [`docs/features/external-agent-runtimes.md`](../features/external-agent-runtimes.md) — how it runs, events, enable steps.
- [`docs/planning/coding-agent-roadmap.md`](../planning/coding-agent-roadmap.md) — Epic I.
- [ADR 0001](0001-tool-and-agent-architecture.md) — layering the port follows.
- [ADR 0009](0009-client-side-execution.md) — workspaces the backend must not open.
