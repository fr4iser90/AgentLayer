---
doc_id: adr-0009-client-side-execution
domain: agentlayer_docs
tags: [adr, tui, workspaces, coding-agent, security, indexing, retrieval]
---

# ADR 0009: Client-side tool execution and indexing consent

## Status

**Accepted and in progress.** Milestones 1 and 2 are implemented: `project_workspaces.execution_mode`
exists, client workspaces store a client path the backend never opens, unattended enqueue and
server-side browse/index refuse them, and the TUI can `/workspace create --local` / `/bind --local`.
Workspace-path tools on a client workspace are dispatched over the chat WebSocket
(`agent.tool_invoke` / `tool_result`) and run in the TUI behind a path jail and mandatory prompts.
Indexing consent (milestones 3–4) is not implemented yet.

## Context

[ADR 0008](0008-tui-client-contract.md) deliberately made the TUI a thin remote client: it speaks the
existing HTTP and WebSocket API and adds no runtime path. Consequently every tool runs inside the
backend container. `bash` shells out with `subprocess.run(..., cwd=cwd)`, the file tools resolve
`context["workspace"]["path"]` with `pathlib`, and workspaces live in the `agent_project_workspaces`
volume under `/data/project_workspaces/{user_id}/{name}`.

That is correct for a hosted server and wrong for the case that prompted this ADR: somebody runs the
TUI against a server they do not own, on a repository that should not be copied to that server.

Three of the four pieces needed already exist.

- **The backend can already pause mid-run and wait for the client.** `_wait_for_tool_permission_reply`
  emits `agent.permission_ask` and then blocks on `control_queue.get()` until a `permission_reply`
  carrying the matching `request_id` arrives, while honouring cancellation
  (`apps/backend/application/agent_runtime/runtime/prompts.py`). A client-executed tool needs exactly
  this loop with a payload instead of a yes/no.
- **The manifest vocabulary already names where code is meant to run:**
  `execution_context: host | container | remote | browser`
  (`apps/backend/domain/plugin_system/tool_manifest_dimensions.py`). `remote` and `browser` are
  declared but have no execution pipeline.
- **`run_tool` already enforces a placement policy:** under `AGENT_MODE=sandbox` a `host` tool is
  refused (`apps/backend/domain/plugin_system/tools.py`, `tool_policy.py`).

What is missing is the return channel. The chat WebSocket accepts eight inbound types — `chat`,
`cancel`, `add_tools`, `continue_step`, `permission_reply`, `secret_saved`, `ping` — and none of them
carries a tool result.

### What indexing actually persists

The design below hinges on a fact that is easy to assume wrongly, so it was verified in code:

| Store | File bodies at rest? | What is written |
| --- | --- | --- |
| Qdrant `code_symbols` | **No** | vector plus `kind`, `name`, `file_path`, `line`/`col` ranges, `signature`, `language`, `workspace_id` (`code_index_qdrant.py`) |
| Neo4j `:Symbol` / `:File` | **No** | name, kind, lines, `signature`, `file_path`; files carry only `sha256` (`code_graph_neo4j.py`) |
| Postgres `workspace_index_file_state` | **No** | path plus `content_sha256` |
| Postgres `rag_chunks` | **Yes** | full markdown chunk text plus embedding |
| Neo4j `:KnowledgeUnit` | **Yes** | extracted line/section text, truncated at 4000 chars |
| Postgres `user_memory_notes` | **Yes** | free note text |

`signature` is the first line of a definition, capped at 200 characters, and the embedding input is
only `name + signature + language`. More importantly, `code_semantic` and `graph` retrieval return
**citations, not snippets** — the tool description already instructs the agent to follow up with
`coding_read_file` on the cited `path:line`, and the fused result shape for `code_semantic` has no
`text` field at all (`plugins/tools/workspace/lib/retrieval_fusion.py`).

So semantic and graph search over a local repository can work with the server never holding a single
file body. That is what makes a tiered consent model worth building rather than an all-or-nothing
switch.

## Decision

### 1. Workspaces gain an execution mode

`project_workspaces.execution_mode`: `server` (default, today's behaviour) or `client`.

For a `client` workspace, `path` is a path on the client machine and is meaningless to the backend;
the backend MUST never open it. The mode is fixed at creation and is not editable, because flipping it
would silently invalidate every index and citation attached to the row.

This is distinct from the manifest's `execution_context`, which describes a tool's intent. Placement
is decided by the **workspace**, since the same `bash` runs server-side for a server workspace and
client-side for a client workspace.

### 2. Dispatch fork on the existing control channel

For a `client` workspace, workspace-scoped tools — the ones that consume `context["workspace"]` — are
dispatched to the client. Everything else (web, memory, platform tools) stays server-side.

The fork sits in `chat_tool_execution.py` where the permission gate already sits, and reuses the same
queue, request-id matching and cancel semantics:

- Server → client: `{"type":"agent.tool_invoke","request_id":"…","tool_name":"…","arguments":{…},"round":N}`
- Client → server: `{"type":"tool_result","request_id":"…","ok":true,"result":"…"}` or
  `{"type":"tool_result","request_id":"…","ok":false,"error":"…"}`

Rules that keep a laptop from hanging a run:

- A per-tool timeout turns into a normal tool error, which the agent can react to, not a stuck turn.
- A socket that drops while a tool is outstanding cancels the run; there is no reconnect-and-resume.
- Results are size-capped like server-side tool output, and the cap is enforced on the server.
- An unknown `request_id` is ignored, exactly as `permission_reply` already does.

Permission prompts move fully to the client for these tools: the client asks its own user before
touching the filesystem, and the server neither sends `agent.permission_ask` nor expects a reply for
them. The server-side gate list (`bash`, `git_sync`, `write_file`, `edit`, `apply_patch`, `replace`) is
the minimum a client MUST prompt for.

### 3. Clients advertise what they can run

On connect, and again on `/bind`, the client sends the workspace tools it implements. The backend drops
the ones it cannot run from the forwarded tool set, reusing the existing allowlist and budget
machinery, so the model is never offered a tool that would land nowhere. A tool that is advertised but
then fails returns `ok:false, error:"unsupported"`, which the agent sees as an ordinary tool failure.

### 4. Indexing is opt-in, in tiers

`project_workspaces.index_consent`: `none` | `symbols` | `text`. Default `text` for server workspaces
(today's behaviour) and `none` for client workspaces.

| Tier | What leaves the machine | What works |
| --- | --- | --- |
| `none` | nothing | `code_grep` (runs client-side), plus everything the agent reads itself |
| `symbols` | symbol metadata: name, kind, path, line ranges, the ≤200-char signature line, file `sha256`, language | additionally `code_semantic` and `graph`, both returning citations the client resolves locally |
| `text` | file and document text | additionally `docs` RAG, `knowledge_*`, `memory` — i.e. text at rest on the server |

At tier `symbols` the client runs the scan locally and uploads only the symbol table through a new
`POST /v1/workspaces/{id}/index/symbols`. The server embeds `name + signature + language` and upserts
Qdrant and Neo4j exactly as it does today, because neither store ever held bodies. Note honestly what
this still discloses: symbol names and signature lines reach both the server and the embedding
provider.

Tier `text` is a separate, explicit consent and is never implied by `symbols`, because it is a
different promise: `rag_chunks.content` holds whole markdown chunks, `:KnowledgeUnit.text` up to 4000
characters per unit, and memory notes hold whatever the agent chose to remember.

`POST /v1/workspaces/{id}/index` refuses a mode the consent does not cover and says which consent it
would need. The server-side crawl (`mode=full|docs`) is impossible for a client workspace regardless of
consent, since there is no server path to walk.

### 5. What client workspaces cannot do

Every unattended path runs without a connected client and MUST refuse a client workspace at enqueue
time rather than failing halfway: scheduler jobs, `agent_tasks`, `project_runs`, and any delegated
subagent expected to outlive the socket. The read-only server-side browse endpoints
(`GET /v1/workspaces/{id}/git/changes`, the file endpoints) MUST answer 400 for a client workspace.

### 6. What this protects, and what it does not

It removes file bodies at rest on the server (at tier `none` or `symbols`) and removes server-side
shell access to the user's code.

It does **not** hide the code from the model. The moment the agent reads a file in order to reason
about it, that content is in the prompt and goes to the configured LLM provider. Client-side execution
changes where files live and where commands run, not what the model sees; only a locally hosted model
closes that gap. This is stated plainly because it is the assumption users get wrong.

Forcing is also asymmetric. "Server only" is genuinely enforceable. "Client only" can be commanded —
the backend refuses to execute the tool itself — but the backend cannot verify that the client ran what
it reports; a client could fabricate results. That is acceptable: the client acts on behalf of its own
user, so a lying client only deceives itself. What the backend must never do is *trust* a client
result as though it were server-produced, e.g. for governance or benchmark records.

## Consequences

- Half the tool surface starts depending on a round-trip to a laptop that may sleep or lose Wi-Fi.
  Timeouts and the disconnect-cancels-the-run rule are load-bearing, not polish.
- The TUI grows a real local executor with a path jail. This is the part deserving the most care:
  `/bind --local ~/` would otherwise hand the agent an entire home directory.
- Two workspace kinds mean every server-side workspace consumer needs an explicit branch. The
  enqueue-time refusals in §5 are the safety net that keeps that from degrading into scattered
  `FileNotFoundError`s.
- Citations become the normal currency of retrieval for local repositories, which is already how the
  coding agent is told to work, so the prompt side needs no change.

### Alternatives considered

- **Bind-mount the repository into the backend** (`~/code/repo:/data/project_workspaces/{uid}/repo`).
  Zero code, keeps indexing and the scheduler fully working, and is the right answer whenever the
  backend runs on the user's own machine. It does not help when the client talks to someone else's
  server, which is the case this ADR exists for.
- **Client-hosted MCP server.** The backend starts MCP servers as local stdio subprocesses
  (`mcp_runtime.py`), and a client behind NAT is not reachable over the network, so this would need a
  tunnel over the socket the client already holds — the same round-trip as §2 with more moving parts.
- **Syncing the repository to the server** on bind. Simple, and defeats the entire purpose.

## Milestones

1. ~~**Placement.** `execution_mode` column, refusals in §5, `/workspace create --local`, `/bind --local`.
   No execution yet: the agent gets a clear "this workspace runs on the client" error.~~ **Done.**
2. ~~**Round-trip.** `agent.tool_invoke` / `tool_result`, the dispatch fork, timeouts, capability
   advertisement, and a local executor in the TUI for reads, writes, patches, glob, grep and `bash`
   behind mandatory prompts.~~ **Done.** `/bind --local` of `/`, `$HOME`, `/etc`, `/usr` and the other
   system trees is refused; tool paths are jailed with `resolve()` + `relative_to`.
3. **Symbols tier.** Local scan, `POST /v1/workspaces/{id}/index/symbols`, `index_consent` enforcement,
   `code_semantic` and `graph` over a local repository with client-resolved snippets.
4. **Text tier.** Explicit opt-in that enables docs RAG, `knowledge_*` and `memory` for client
   workspaces by uploading chunks, with the consent visible wherever a workspace is listed.
