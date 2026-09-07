---
doc_id: feature-dashboards
domain: agentlayer_docs
tags: [dashboards, ui, sharing]
---

## What it is

**Source of truth:** user data lives in the **domain layer** (`user_collections`, `collection_items`, `user_attachments`). Dashboards are **views/projections** only.

Dashboard rows in `user_dashboards` store:

- `ui_layout` (blocks + grid positions)
- `view_bindings` (optional map `dataPath → collection_slug`)
- `kind` (template kind)
- sharing/access (`access_role`)

On **read**, `dashboard_get` projects domain collections into the `data` shape the UI expects (`data_source: "domain"`). On **write**, `list_append`, `patch_data`, and uploads go through domain services — `user_dashboards.data` is **not** updated (legacy JSON may be imported once on first projection).

Chat-only users can use `collection.*` tools without any dashboard (`collection.item_append(slug: "pets", …)`).

Backend: `apps/backend/domain/collections/` (CRUD, bindings, projection, service). Migration: `schema_083_user_collections`.

## Backend

- Router: `src/dashboard/router.py`
- CRUD: `src/dashboard/db.py`
- Template discovery: `src/dashboard/bundle.py`

### Sharing roles

- `owner`: full control, can delete
- `co_owner`: can edit content + manage members (cannot delete)
- `editor`: can edit content
- `viewer`: read-only

Sharing UI is in `interfaces/agent-ui/src/pages/DashboardPage.tsx` (Settings drawer).

### Public read-only links (no account)

Owner/co-owner can create token links under **Settings → Öffentlicher Link / Public link**:

- Empty block selection = entire dashboard read-only
- Selected blocks = same filtering as granular tenant block-shares
- URL: `/app/dashboard/shared?t=<token>` (token shown once on create)
- Optional **expiry** (`expires_at` ISO) and **password** (min 4 chars; sent as header `X-Dashboard-Share-Password` on public views)
- **Gallery presentation:** when the shared layout contains only `gallery` / `hero` / `markdown` blocks, `/app/dashboard/shared` renders a full-width album view (no app nav, no dashboard grid). Mixed boards (e.g. pets table + gallery) still use the grid layout.
- API: `GET /v1/dashboards/shared/{token}`, file content via `GET /v1/dashboards/shared/{token}/files/{id}/content`
- Revoke: `DELETE /v1/dashboards/{dashboard_id}/public-shares/{share_id}`

Agent tool: `create_public_share` in `plugins/tools/personal/dashboard/dashboard.py` (same options as API).

## Frontend

- Page: `interfaces/agent-ui/src/pages/DashboardPage.tsx`
- Grid: `interfaces/agent-ui/src/features/dashboard/DashboardGridCanvas.tsx`
- Block renderer: `interfaces/agent-ui/src/features/dashboard/DashboardBlocks.tsx`

## Block types (current)

Examples (not exhaustive):

- `table`
- `markdown`
- `rich_markdown`
- `gallery`
- `hero`
- `timeline`
- `stat` (KPI)
- `chart`
- `sparkline`
- `kanban`
- `embed` (iframe allowlist, e.g. Google Calendar)

## Data paths

Blocks read/write data via `dataPath`.

Supported:

- top-level keys (e.g. `pets`, `items`)
- dotted paths for nested structures (e.g. `albums.0.photos`)

Helper functions:

- `interfaces/agent-ui/src/features/dashboard/dashboardDataPaths.ts` (`getPath`, `setPath`)

## Agent tools (dashboard id)

`dashboard_id` may be **omitted** when the user has exactly **one** dashboard; the server picks it automatically. If there are several, the tool returns a short list of `id` + `title` so the model can ask or pass the UUID. If none exist, call `dashboard.create_dashboard` first. Logic: `apps/backend/infrastructure/dashboard_tool_dashboard_resolve.py`.

### Generic tools (any kind)

Module: `plugins/tools/personal/dashboard/dashboard.py`

| Tool | Purpose |
|------|---------|
| `list` | All accessible boards (`id`, `kind`, `title`, `access_role`) |
| `read` | `ui_layout`, `data`, `block_ids` (large payloads may truncate) |
| `list_append` | Append rows via domain (`list_path` + `rows`; dedupe optional) |
| `list_update` | Update rows by `id` (domain) |
| `list_delete` | Remove rows by `id` (domain) |
| `upload_file` | Image → `user_attachments`; returns `file:{uuid}`; optional `append_list_path` |
| `patch_data` | Scalar/list patches on domain collections (dotted paths; granular shares: allowed keys only) |
| `patch_layout` | `add_block`, `remove_block`, `set_grid`, `set_props` (not for granular block-only shares) |
| `create_public_share` | Public read-only link; optional `block_ids`, `expires_at`, `password` (returns `token` + `url_path` once) |

Capabilities: `dashboard.read`, `dashboard.write`. Use `list_append` / `list_update` / `list_delete` for table rows; `list_path` comes from block `props.dataPath` in `ui_layout` (or pass explicitly, e.g. `pets`, `items`, `albums.0.photos`).

### Domain tools (no dashboard required)

Module: `plugins/tools/domain/collections/collections.py`

| Tool | Purpose |
|------|---------|
| `collection.ensure` | Create or fetch a collection by `slug` |
| `collection.item_append` | Append rows to a list key |
| `collection.items_list` | List rows |
| `collection.metadata_patch` | Patch scalar metadata on the collection |
| `collection.item_update` / `collection.item_delete` | Row CRUD |

Use these when the user has no board or when sharing data across multiple views (`view_bindings` / `props.collectionSlug`).

## Terminology: dashboard vs project path

In AgentLayer, a **dashboard** is a UI dashboard/board stored in `user_dashboards` (identified by `dashboard_id`).

When scheduling IDE/Git jobs, use **`project_path`** for the local filesystem path to a repository/project folder. Do not call this a "dashboard path" to avoid confusion with UI dashboards.

## Block: schedules

The `schedules` block shows persisted user-defined schedules from `scheduler_jobs` via `/v1/user/scheduler-jobs` (jobs the user created or executes).

`execution_target` values:

- `general` — recurring run with chat agent **`general`** (`plugins/agents/general.py`)
- `coding` — recurring run with agent **`coding`** on a workspace (and other schedulable workspace agents from the registry)

Example block props:

- `scope`: `"dashboard"` | `"global"` | `"both"` (default `"dashboard"`)
- `executionTarget`: `"all"` or any registry `agent_id` from `GET /v1/user/scheduler-jobs/execution-targets` (e.g. `general`, `coding`, `coding_plan`, `security_auditor` when `AGENT_SCHEDULABLE` is true).

## Files / uploads

Uploads produce a `file:<uuid>` reference (`user_attachments`).

- Upload endpoint: `POST /v1/dashboards/{dashboard_id}/files`
- Content fetch: `GET /v1/dashboards/files/{id}/content`

Frontend renders `file:` via:

- `interfaces/agent-ui/src/features/dashboard/DashboardBlocks.tsx` (`GalleryImage`)

