---
doc_id: adr-0008-tui-client-contract
domain: agentlayer_docs
tags: [adr, tui, cli, client, websocket, api-key, headless]
---

# ADR 0008: TUI client contract — AgentLayer without the WebUI

## Status

**Accepted and in progress.** API-key minting shipped (see [Auth](#auth-implemented)) and the client
exists at `apps/tui/` through milestone 4: it renders live tool activity, nested delegation, the
goal/todo strip and permission prompts, and it can list, create, bind and index workspaces so the
coding agent has somewhere to work. Milestone 5 (scriptable one-shot) works for the final answer only.

## Context

Users want to drive AgentLayer from a terminal the way they drive Claude Code or a Hermes-style agent:
a prompt line, slash commands, visible tool calls, a goal/todo strip — and no browser. Today the only
interactive surface is the React WebUI; the Telegram and Discord bridges are **server-side** surfaces
(`bridge_agent_turn.py` imports `chat_completion` in-process), so they are not a template for a client
that runs on someone else's machine.

The question is whether a TUI needs a new backend surface. It does not. `chat_completion` is already
reachable over HTTP and WebSocket, and the WebSocket already emits the full per-round event stream the
WebUI renders.

## Decision

**The TUI is a remote client over the existing HTTP + WebSocket API. No new chat surface, no new
runtime path.** It authenticates with a user API key, opens `/ws/v1/chat`, and renders the `agent.*`
events. It lives at `apps/tui/` beside `apps/backend` and `apps/frontend`.

Consequence of this choice: the TUI is *one more consumer of one contract*. Anything the WebUI can do
that the TUI cannot is a gap in the TUI, not in the backend — which keeps the runtime single-sourced.

This holds as long as tools run on the server. Executing them on the client machine instead is the one
extension that genuinely needs a new runtime path, and it is specified separately in
[ADR 0009](0009-client-side-execution.md); until that is implemented, workspaces are server-side and
the statement above is unqualified.

### Transport

Two options exist; the TUI uses the WebSocket.

| Transport | Gets you | Use for |
|---|---|---|
| `POST /v1/chat/completions` | final answer, optional text streaming | scripting, `agentlayer -p "..."` one-shots |
| `WS /ws/v1/chat` | per-round tool events, goal/todo pushes, permission prompts, cancel | the interactive TUI |

`POST /v1/chat/completions` forces `agent_id` to a chat-surface agent (see
[Agent selection](#agent-selection-is-not-an-agent-picker)), so both transports share the same routing
semantics.

### Protocol contract

Authoritative source: the module docstring of
[`apps/backend/api/chat/controllers/chat_websocket.py`](../../apps/backend/api/chat/controllers/chat_websocket.py).
Summarised here so the client has a checklist.

Connect with `GET /ws/v1/chat?token=<JWT_or_api_key>`, or send `Authorization: Bearer` on the
handshake. Unauthorised connections receive `{"type":"error"}` and close with code `4401`.

Client → server:

| Message | Effect |
|---|---|
| `{"type":"chat","body":{…}}` | starts a turn; `body` is an OpenAI-shaped request, `stream` is ignored |
| `{"type":"cancel"}` | aborts the in-flight turn immediately, without waiting for the round boundary |
| `{"type":"continue_step"}` | resumes after `agent.step_wait` when `agent_pause_between_rounds` is set |
| `{"type":"permission_reply","request_id":…,"reply":"once"\|"always"\|"reject"}` | answers `agent.permission_ask` |
| `{"type":"tool_result","request_id":…,"ok":true,"result":…}` / `"ok":false,"error":…` | answers `agent.tool_invoke` (ADR 0009; unknown `request_id` is ignored) |
| `{"type":"client_capabilities","workspace_tools":[…]}` | tools this client can run locally; sent on connect and again on `/bind` |
| `{"type":"add_tools","names":[…]}` | merges extra allowed tools before the next LLM call |
| `{"type":"secret_saved",…}` | acknowledges an in-chat secret prompt |
| `{"type":"ping"}` | → `{"type":"pong"}`; the server drops idle sockets after 3600s |

Server → client, all as `{"type": …}` JSON:

- Turn lifecycle: `agent.session`, `agent.llm_round_start`, `agent.llm_round`, `agent.done`,
  `agent.cancelled`, `agent.aborted`, and finally `chat.completion` with the OpenAI-shaped result.
- Token streaming: `agent.llm_delta`, only when the request sets `body.agent_stream_llm`.
- Tools: `agent.tool_start` and `agent.tool_done`, carrying `agent_run_id`, `round`, `name`, a
  human-readable `step_label` and a `summary` — this is what a Claude-Code-style tool line renders
  from. `agent.tool_start` also reports `rejected` with a `validation` breakdown when the model sent
  malformed arguments, which is worth surfacing: it is the signal that a model is guessing at a
  schema. For a client-placed workspace the server also emits `agent.tool_invoke` (path, arguments,
  `request_id`); the client runs the tool locally and replies with `tool_result`.
- Sub-runs: `agent.subagent_start`, `agent.subagent_step`, `agent.subagent_done`. Delegation to
  `coding` shows up here, so the TUI can nest specialist activity under the parent turn.
- Context: `agent.context_update`, `agent.context_compacted`.
- Interaction: `agent.permission_ask`, `agent.secret_prompt`.
- Goal layer: `agent.goal`, `agent.todos`, `agent.plan_mode`, produced by
  [`conversation_goal_events.py`](../../apps/backend/application/agent_runtime/use_cases/conversation_goal_events.py)
  whenever a goal/todo tool succeeds. `agent.todos` includes a `counts` summary, so the status strip
  needs no client-side aggregation.

A client that ignores an unknown `type` stays forward-compatible; the event set grows.

Two details cost real debugging time when the client was built, so they belong in the contract:

- **The goal layer needs a saved thread.** `chat_run_bootstrap` copies `body.conversation_id` into the
  tool context, and the goal/todo tools refuse to run without it
  (`conversation_id required (open a saved chat thread)`). A client that never sends one gets a silent
  no-goal experience where every `goal_*` and `todo_*` call fails. The TUI therefore creates a
  conversation via `POST /v1/user/conversations` on the first turn — lazily, so merely starting the
  client does not litter the thread list.
- **Never strip an `agent.llm_delta`.** Chunk boundaries fall between words, so trimming each delta
  concatenates the answer into `TheTUIclientworks`. Regression-tested in
  `tests/unit/test_tui_events.py::TestTurnLifecycle::test_deltas_keep_their_whitespace`.

### Slash commands map onto existing endpoints

No backend work — each command is a call the WebUI already makes.

| Command | Backend |
|---|---|
| `/agents` | `GET /v1/agents` |
| `/model`, `/models` | `GET /v1/models` (also reports provider reachability) |
| `/new`, `/resume`, `/threads` | `/v1/user/conversations` |
| `/goal`, `/todos`, `/plan` | `GET /v1/chat/runtime` for the snapshot, `PATCH /v1/user/conversations/{id}/goal` to edit |
| `/workspace`, `/workspace create <name> [git url]` | `GET`/`POST /v1/workspaces` |
| `/bind <id\|name>`, `/bind off` | `PUT /v1/user/conversations/{id}` with `workspace_id` (stores `pref_workspace_id`) |
| `/index [full\|code\|docs]`, `/index status` | `POST /v1/workspaces/{id}/index`, status via `GET /v1/workspaces/{id}/index/status` |
| `/delegate <agent> <task>` | a `chat` turn phrased as a delegation (see below) |
| `/cancel` | WS `{"type":"cancel"}` |
| `/tools` | `forwarded_tools` from the completion payload; WS `add_tools` to extend |

`GET /v1/chat/runtime?model=…&conversation_id=…` is the natural startup call: it returns MCP status,
the context budget with its quotas, vision availability and the current goal/todos in one response.

### Agent selection is not an agent picker

`chat_completion` forces any `agent_id` outside `{general, dashboard, creative}` back to `general`,
and logs it. Specialists — `coding`, `coding_plan`, `security_auditor` — are reachable **only** as
sub-runs via `delegate`. A `/agent coding` command would therefore silently not do what its name says.

The TUI exposes `/delegate coding <task>` instead, and renders the resulting
`agent.subagent_*` events as a nested activity block. This matches the runtime instead of papering
over it.

### Auth: implemented

API keys are the right fit for a headless client — no refresh-token rotation in a terminal app.
`get_user_for_bearer_token` accepts either a JWT or an API key, and both `get_current_user` (HTTP) and
`_ws_connection_authorized` (WebSocket) go through it, so one key covers every call the TUI makes.

The `api_keys` table was already read on every bearer resolution but nothing ever inserted into it, so
the mechanism was dormant. It now has a management surface in
[`api_keys_api.py`](../../apps/backend/api/platform/controllers/api_keys_api.py):

| Endpoint | Behaviour |
|---|---|
| `POST /v1/user/api-keys` | mints `al_<urlsafe>`, returns the secret exactly once; optional `expires_in_days` (1–365) |
| `GET /v1/user/api-keys` | metadata only — `id`, `name`, `created_at`, `last_used_at`, `expires_at`, `expired` |
| `DELETE /v1/user/api-keys/{id}` | revokes; scoped by `user_id`, so one user cannot revoke another's key |

Three properties are worth stating because they are easy to regress:

1. **The secret is never stored.** `create_api_key` writes `sha256(token)` and the lookup hashes the
   presented token — SHA-256 rather than bcrypt for the same reason as refresh tokens, since these are
   high-entropy secrets, not passwords, and the digest is the indexed lookup key.
2. **`expires_at` is enforced in the query** (`expires_at IS NULL OR expires_at > NOW()`), not merely
   selected. An expired key fails to authenticate on HTTP and on the WebSocket.
3. **Key management requires a logged-in session, not a key.** Minting and revoking reject API-key
   bearers with `403`, so a leaked key cannot mint a successor that outlives its own revocation. The
   TUI therefore gets its key from a `POST /auth/login` session once, the way a GitHub PAT is created
   in the browser rather than by another PAT.

Verified end to end by [`scripts/verify_api_keys.py`](../../scripts/verify_api_keys.py) — mint, hashed
storage, HTTP and WebSocket authentication, the `403` on self-minting, revocation taking effect on both
transports, and TTL bounds. Hashing, expiry and revocation scoping are also covered by
[`tests/unit/test_auth_api_keys.py`](../../tests/unit/test_auth_api_keys.py).

### Technology

Python with [Textual](https://textual.textualize.io/), packaged for `pipx`/`uv tool install`.

The reason is reuse, not preference: the repo is already Python with `httpx`, the auth and client
patterns in `tests/e2e/support/helpers.py` transfer directly, and the event contract stays in one
language. A Go or Rust binary distributes more nicely as a single file, at the cost of maintaining the
client contract twice — worth revisiting only if the TUI outgrows the team that owns the backend.

`apps/tui/` carries its own `pyproject.toml` and depends on nothing from `apps/backend`, so it installs
on a machine that has no server checkout:

```bash
pipx install ./apps/tui       # or: uv tool install ./apps/tui
agentlayer --login --server https://agent.example.com
agentlayer
```

Where `pipx` is unavailable — NixOS, for instance, where the system Python has no `pip` — a plain
virtualenv gives the same entry point:

```bash
python3 -m venv apps/tui/.venv && apps/tui/.venv/bin/pip install -e ./apps/tui
apps/tui/.venv/bin/agentlayer --login --server http://127.0.0.1:8088
```

`--login` mints a key through `POST /v1/user/api-keys` and writes it to
`~/.config/agentlayer/config.toml` with mode `600`; every later start reads it from there.

It also resolves and stores a model, because `POST /v1/chat/completions` rejects a request that names
none ("No LLM catalog provider for this request") and the server publishes no default of its own — the
provider's `model_default` is known to `llm_env_providers` but is not exposed on `/v1/models`. The
client therefore picks the first model belonging to a provider that `/v1/models` reports as
`reachable`, states which one it chose, and leaves it editable via the config file or `/model`.
Surfacing the operator's intended default on `/v1/models` would be the better fix and would help every
client, not just this one.

Inside the package, `events.py` holds the whole event-to-row mapping and imports no Textual, which is
what makes the contract testable: `tests/unit/test_tui_events.py` covers it without starting a
terminal. `app.py` only owns widgets and keyed row updates — a tool's result rewrites the row its
`tool_start` created, keyed by name and round, which is how one line can show both the call and its
outcome.

## Milestones

1. ~~**Talks.** API-key minting endpoint; TUI connects, sends one `chat`, prints `chat.completion`.~~
   **Done.**
2. ~~**Watchable.** Render `agent.tool_start`/`tool_done` and `agent.llm_delta` live; `/cancel`
   works.~~ **Done** — `ctrl-c` sends `{"type":"cancel"}` and is bound with `priority=True` so it
   cancels the turn instead of quitting the app; `ctrl-d` quits.
3. ~~**Harness-grade.** Goal/todo strip from `agent.goal`/`agent.todos`/`agent.plan_mode`; nested
   `agent.subagent_*` blocks; `permission_reply` prompts.~~ **Done** — permission asks open a modal
   answered with `y`/`a`/`n`.
4. ~~**Daily driver.** Workspace slash commands, `/index`, `/model`, `/models`, `/agents`, `/new`,
   `/resume`, `/threads`, `/runtime` and the config file.~~ **Done.**
5. **Scriptable.** `agentlayer -p "…"` over `POST /v1/chat/completions` works for pipes; it prints the
   final answer only, with no tool visibility.

Verified live by [`scripts/verify_tui_client.py`](../../scripts/verify_tui_client.py), which drives the
real app headlessly through `App.run_test()` against a running backend and asserts the rendered rows —
tool lines, nested delegation, the goal strip, whitespace-preserving streaming and the permission
round-trip. It also exercises the workspace commands end to end — creating a throwaway workspace,
asserting the binding lands in `pref_workspace_id`, starting an index job and deleting the workspace
again — and writes [`docs/assets/tui-milestone4.svg`](../assets/tui-milestone4.svg) and
[`docs/assets/tui-workspaces.svg`](../assets/tui-workspaces.svg) as regenerable screenshots.

That run is what surfaced a broken `POST /v1/workspaces/{id}/index`: `workspace_index_runner.py` used
`_index_job_get`, `index_job_for_status` and `qdrant_status` without importing them, so the endpoint
answered 500 for every client, the Web UI included.

### Binding a workspace

There is no bind endpoint; binding is a conversation preference. `/bind` therefore does two things:
it `PUT`s `workspace_id` onto the conversation, which the backend stores as `pref_workspace_id`, and
it keeps the id client-side so every following `chat` body carries an explicit `workspace_id`.
`chat_run_bootstrap` prefers the body over the stored preference, so a fresh `/bind` applies to the
very next turn even if persisting the preference failed. Consequences worth knowing:

- Binding needs a conversation, so `/bind` creates one first if the session has not saved one yet.
- `/new` keeps the current workspace and passes it to the conversation it creates; `/bind off` is the
  only way to detach.
- `/resume` adopts whatever the resumed conversation has stored, so a thread stays in its repository.
- Ambiguous queries list candidates instead of binding a guess, since `/bind api` must never silently
  pick `api-gateway`.

## Consequences

The runtime stays single-sourced: the TUI adds no code to the agent loop, so behaviour cannot drift
between terminal and browser. In exchange, the TUI inherits every backend constraint — including
delegation-only specialists — and any new `agent.*` event needs a rendering decision in two places.

Documenting the WebSocket contract here also makes it a contract. It has so far been an internal detail
between `chat_websocket.py` and the React hook; a second consumer means additive changes only.

## Related

- [ADR 0001: Tool and agent architecture](0001-tool-and-agent-architecture.md)
- [ADR 0006: Chat secret ingress pipeline](0006-chat-secret-ingress-pipeline.md) — `agent.secret_prompt` / `secret_saved`
- [`docs/planning/agent-runtime-ux-goal-todos-plan.md`](../planning/agent-runtime-ux-goal-todos-plan.md) — the goal/todo layer the TUI renders
