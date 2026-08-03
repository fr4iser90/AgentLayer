---
doc_id: runbook-lsp
domain: agentlayer_docs
tags: [runbook, lsp, coding-agent, docker]
---

## What this covers

How the coding agent’s **`lsp`** tool finds language servers, how to install **Python** and **TypeScript** servers (minimum smoke), and how diagnostics look in tool JSON.

Implementation: `plugins/tools/workspace/lsp/lsp.py`, `plugins/tools/workspace/lib/lsp_client.py`.

## PATH and Docker

Language servers are **not** baked into the default `Dockerfile`. The backend process must see them on **`PATH`** (same process as `uvicorn` / `agent-layer`).

| Setup | What to do |
|-------|------------|
| Local `uvicorn` on the host | Install servers into the host env; ensure `which pyright-langserver` / `which typescript-language-server` works. |
| `docker compose` (`agent-layer`) | Install inside the image (custom Dockerfile layer) **or** mount a tools bin dir and prepend it to `PATH` in `compose.yaml` `environment`. |
| Override without PATH | Set `AGENT_LSP_<LANGUAGE>_CMD` (shlex-split argv), e.g. `AGENT_LSP_PYTHON_CMD=pyright-langserver --stdio`. |

Compose hint (optional bind of host binaries — adjust paths):

```yaml
# compose.yaml → services.agent-layer
environment:
  PATH: /opt/lsp/bin:/usr/local/bin:/usr/bin:/bin
  # AGENT_LSP_PYTHON_CMD: pyright-langserver --stdio
  # AGENT_LSP_TYPESCRIPT_CMD: typescript-language-server --stdio
volumes:
  # - /usr/local/bin/pyright-langserver:/opt/lsp/bin/pyright-langserver:ro
```

Related: workspace files live under `AGENTLAYER_WORKSPACE_PATH` — see [`workspace-persistence.md`](./workspace-persistence.md). LSP `cwd` / root is the **workspace** path for that chat, not `/code`.

## Preferred servers (auto-detect order)

| Language | Primary | Fallbacks |
|----------|---------|-----------|
| Python | `pyright-langserver --stdio` | `pylsp --stdio`, `jedi-language-server --stdio` |
| TypeScript / JS | `typescript-language-server --stdio` | `tsserver`, `deno lsp` |

Env overrides: `AGENT_LSP_PYTHON_CMD`, `AGENT_LSP_TYPESCRIPT_CMD`, … (`AGENT_LSP_<LANG>_CMD`).

Caps: `AGENT_LSP_DIAGNOSTICS_MAX` (default 40), `AGENT_LSP_DIAGNOSTICS_TIMEOUT_SEC` (default 10).

## Install (smoke minimum)

### Python

```bash
pip install pyright
# binary: pyright-langserver
# alternative: pip install python-lsp-server
```

### TypeScript

```bash
npm install -g typescript typescript-language-server
# binary: typescript-language-server
```

### PATH smoke (no chat required)

```bash
python scripts/lsp_path_smoke.py
# or inside the container:
docker compose exec agent-layer python scripts/lsp_path_smoke.py
```

Exit `0` if at least one Python **and** one TypeScript/JS candidate is on `PATH` (or overridden via env). Exit `1` with install hints otherwise.

### Chat / tool smoke

With a workspace bound and coding agent:

1. `lsp` → `operation=status` — lists running servers (empty until first file op).
2. On a `.py` file: `operation=diagnostics`, `path=…`, `wait=true` (default).
3. On a `.ts` / `.tsx` file: same.
4. Expect JSON with `summary` (`error` / `warning` / …) and `diagnostics[]` using **1-based** `line` / `character` and workspace-relative `path` (not raw `file://` URIs).
5. Missing binary → `ok: false` and an error naming tried binaries + `docs/runbooks/lsp.md`.

## Diagnostics JSON (model-facing)

```json
{
  "ok": true,
  "operation": "diagnostics",
  "path": "src/app.py",
  "language": "python",
  "summary": {"error": 1, "warning": 0, "information": 0, "hint": 0, "unknown": 0, "total": 1},
  "diagnostics": [
    {
      "path": "src/app.py",
      "severity": "error",
      "line": 12,
      "character": 5,
      "end_line": 12,
      "end_character": 9,
      "message": "\"x\" is not defined",
      "source": "Pyright"
    }
  ],
  "hint": "Fix diagnostic errors before claiming the change is done; use apply_patch / edit on the cited path:line locations."
}
```

If more than `AGENT_LSP_DIAGNOSTICS_MAX` items exist, `truncated: true` and `truncation_hint` are set (errors sorted first).

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `not found in PATH` | `scripts/lsp_path_smoke.py`; install or set `AGENT_LSP_*_CMD`. |
| Empty diagnostics always | Use `wait=true`; call `restart` then retry; confirm the language server supports `publishDiagnostics`. |
| Works on host, not in Compose | Servers only on host PATH — install in image or mount + extend container `PATH`. |
| Wrong project root | Ensure workspace markers (`pyproject.toml`, `package.json`, `tsconfig.json`, …) exist under the workspace tree. |
