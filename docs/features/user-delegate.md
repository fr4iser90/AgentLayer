---
doc_id: feature-user-delegate
domain: agentlayer_docs
tags: [delegate, stellvertreter, autonomy, settings]
---

## What it is

The **Delegate** (DE: **Stellvertreter**) is explicit **decision authority** — who may act on your behalf when autonomous actions run (e.g. future **Auto-Respond** in chat). It is **not** agent persona (tone/vocabulary).

- **Global:** Settings → **Stellvertreter** / **Delegate** — goals, engineering priorities, autonomy bounds.
- **Per workspace:** same page, workspace picker — overlay merges over global config.

Subtitle: *Acts on your behalf when autonomous actions are enabled.*

## API

| Method | Path |
|--------|------|
| GET/PUT | `/v1/user/delegate` |
| GET/PUT | `/v1/workspaces/{workspace_id}/delegate` |

Config shape: `communication`, `engineering` (incl. `primary_goal`, `priorities`), `autonomy`, `decisioning.risk_tolerance`, `escalation.*`, `goals`.

## Related docs

- [ADR 0007](../adr/0007-user-delegate.md)
- [Implementation roadmap](../planning/user-delegate-roadmap.md)

## Status

**P0 shipped:** persistence, API, settings UI. **P1 next:** Auto-Respond (idle timeout + delegate decision call).
