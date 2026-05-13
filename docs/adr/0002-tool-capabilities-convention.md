# ADR 0002: `TOOL_CAPABILITIES` naming (`domain.action`)

## Status

Accepted — complements ADR 0001.

## Convention

- **Format:** `domain.action` (lowercase, dot-separated).
- **Semantics:** stable **user- or operator-facing capability**, not a brand (`gmail`) or file path.
- **Examples:** `mail.read`, `weather.observe`, `meta.discover`, `recreation.fishing.advise`.

## Bundles used in this repo (round 1)

| Capability | Meaning |
|------------|---------|
| `meta.discover` | List/browse what exists (registry catalog, categories, extra-tool filenames). |
| `meta.inspect` | Load full schema or source (`get_tool_help`, `read_tool`). |
| `meta.author` | Create/update/replace/rename tool modules. |
| `secrets.user` | Register or document user secrets. |
| `dashboard.files` | Local filesystem read/write/search on host. |
| `environment.snapshot` | Structured outdoor/device snapshot (not “weather API” — that is `weather.observe`). |
| `weather.observe` | Current conditions + forecast from a weather API. |
| `web.search` | Web search / crawl helpers. |
| `code.repository` | Hosted git: repos, issues, PRs, file content (provider via secret, not in capability id). |
| `tasks.manage` | Todo CRUD. |
| `calendar.read` | Read calendar from ICS/HTTPS feeds. |
| `time.query` | Current time / timezone helpers. |
| `knowledge.note` | User KB notes (append/search/read). |
| `knowledge.retrieve` | Semantic / RAG retrieval over indexed content. |
| `image.edit` | Image-to-image or inpainting generation. |
| `creative.web.build` | Iterative HTML/asset build workflows. |
| `automation.browser.validate` | Validate a structured local-browser automation plan (no writes). |
| `automation.browser.package` | Generate downloadable Playwright bundle + ZIP for user-local execution. |
| `debug.echo` | Sample / smoke-test only. |
| `recreation.fishing.advise` | Heuristic fishing advice (domain demos). |
| `recreation.hunting.advise` | Heuristic hunting advice. |
| `recreation.survival.advise` | Heuristic survival advice. |

## Per-tool overrides

When handlers in one file differ (e.g. `tool_help`), use **`AGENT_TOOL_META_BY_NAME`** with a `capabilities` list for that function name.

## Gmail

Keeps existing `mail.read`, `mail.search`, `secrets.user` (already aligned with this style).
