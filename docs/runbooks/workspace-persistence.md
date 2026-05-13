---
doc_id: runbook-workspace-persistence
domain: agentlayer_docs
tags: [runbook, workspaces, docker, coding-agent]
---

## What this covers

Project workspaces (`GET /v1/workspaces`, coding agent, `agentlayer-self`) store files under **`AGENTLAYER_WORKSPACE_PATH`** (see ADR `docs/adr/0005-agentlayer-self-workspace-contract.md`). Without a volume, that path lived only in the container layer and was **lost on recreate**.

## Docker Compose (default in this repo)

`compose.yaml` sets:

- **`AGENTLAYER_WORKSPACE_PATH=/data/project_workspaces`**
- Named volume **`agent_project_workspaces`** mounted read-write at that path

The read-only seed for copying AgentLayer itself stays at **`/workspace/AgentLayer`** (separate mount); writable trees are only under **`/data/project_workspaces/{user_id}/…`**.

## Changing `AGENTLAYER_WORKSPACE_PATH` later

Postgres stores the **absolute path** per row in `project_workspaces.path`. If you move the env mount to a new prefix:

- **New** workspaces get paths under the new root.
- **Old** rows may still point at paths that no longer exist on disk — users see missing directories until workspaces are **recreated** or paths are **updated in the DB** (operator / SQL).

## Host bind instead of a named volume

Example pattern:

```yaml
environment:
  AGENTLAYER_WORKSPACE_PATH: /srv/agentlayer/workspaces
volumes:
  - /srv/agentlayer/workspaces:/srv/agentlayer/workspaces:rw
```

Ensure the host directory exists and the container user can write there.

## Quick verification

After `docker compose up`:

1. Enable self-editing (operator + user flag), open Coding Agent, pick **agentlayer-self** (or any workspace).
2. Create a trivial file via the agent or shell in the workspace tree.
3. `docker compose restart agent-layer` — file should still be present under the same volume mount.
