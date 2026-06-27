# Image generation (ComfyUI)

This folder is the **product home** for image-generation workflows and documentation. The HTTP API remains under **`/v1/studio/*`** (stable for clients); the UI labels this area **“Image generation”**.

## Layout

| Path | Role |
|------|------|
| `workflows/` | ComfyUI **workflow graphs** (`.json`) — **add new graphs here** (plug & play). |
| `presets/` | Reserved for small JSON preset definitions once the loader is implemented (see `dashboard/PLAN_PLUG_AND_PLAY.md`). |
| `README.md` | This file |

The built-in Studio presets (`txt2image`, `image2image`) load from `image_generation/workflows/*.json`. To register a new preset in the UI, extend `apps/backend/domain/studio/catalog.py` (or the future preset loader) and point `workflow_file` at a path under `image_generation/workflows/`.

## Forks

Drop ComfyUI-exported graphs into `image_generation/workflows/`, then wire them in the catalog or future `presets/` loader.
