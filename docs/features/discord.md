---
doc_id: feature-discord
domain: agentlayer_docs
tags: [discord, bot, commands]
---

## What it is

AgentLayer can run a Discord bridge that forwards messages (e.g. `!agent ...`) into the chat/tool loop.

## Where it lives

- Bridge: `src/integrations/discord_bridge.py`
- Tool registry is shared (same tools as UI chat)

## Recommended command conventions

### Memory (opt-in)

- `!agent remember key=value` → `fact_upsert`
- `!agent remember note: ...` → `note_add`
- `!agent memory` → `fact_list` + `note_search`
- `!agent forget key` / `!agent forget note <id>`

### Dashboards

Prefer “open in UI” for complex edits. Use tools for quick reads/patches:

- pets: `pets_*`
- shopping_list: `shopping_list_*`
- ideas: `ideas_*`

## Troubleshooting

### DNS / Discord gateway failures

If logs show `Temporary failure in name resolution` for `gateway.discord.gg`, the container/host DNS is unstable.

