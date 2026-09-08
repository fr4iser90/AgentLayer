# Agent Layer

visit https://github.com/fr4iser90/AgentLayer_-_Jetson-Orin-Nano-Super-Developer-Kit-dedicated

**Open WebUI / custom front ends:** [docs/WEBUI_CONTRACT.md](docs/WEBUI_CONTRACT.md) (HTTP/API); [docs/WEBUI_DESIGNS.md](docs/WEBUI_DESIGNS.md) (dashboard, chat badges, image page — copy or link from your UI repo).

**First-party web UI (plan, stack, English):** [docs/FRONTEND_AGENT_UI_PLAN.md](docs/FRONTEND_AGENT_UI_PLAN.md).

**Repo layout (``apps/`` vs ``plugins/``):** [docs/architecture/repo-layout.md](docs/architecture/repo-layout.md).

**Collaborate (branches, PRs, CI gate):** [docs/runbooks/collaboration.md](docs/runbooks/collaboration.md).

RAG-Docs / Embed: 404 auf Ollama-Embed-Routen → Embedding-Modell auf dem Ollama-Host ziehen (z. B. ollama pull nomic-embed-text) oder OLLAMA_BASE_URL/Modell prüfen – betrifft nur die automatische Doku-Ingestion, nicht den Rest.

## TUI client (no server checkout)

`apps/tui/` is a standalone package (`agentlayer-tui`). It talks HTTP + WebSocket only; it does not import the backend. Install it without cloning this tree:

```bash
pipx install "git+https://github.com/fr4iser90/AgentLayer---Jetson-Orin-Nano-Super-Developer-Kit-dedicated-.git#subdirectory=apps/tui"
agentlayer --login --server https://your-agentlayer-host
agentlayer
```

From a clone of this repo: `pipx install ./apps/tui` (or `uv tool install ./apps/tui`). On NixOS, use a venv instead of pipx — see [ADR 0008](docs/adr/0008-tui-client-contract.md). PyPI (`pipx install agentlayer-tui`) is not published yet.

**Operator surfaces:** Admin → Interfaces → Platform can set `WEB_ONLY` / `WEB_AND_TUI` / `TUI_ONLY`, API-key workspace modes (`server`|`client`|`both`), and the index-consent cap. See [ADR 0009](docs/adr/0009-client-side-execution.md#operator-client-surfaces). Traefik may gate paths at the edge; the server still enforces.
