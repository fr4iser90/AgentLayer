"""Image Studio: catalog (schema-driven UI) and ComfyUI job execution."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.backend.domain.studio.catalog import studio_catalog_payload
from apps.backend.application.studio.use_cases.studio_controller_services import StudioComfyError, list_studio_checkpoints, run_studio_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/studio", tags=["studio"])


def _inject_checkpoint_enum_into_catalog(payload: dict, names: list[str]) -> None:
    """
    Add JSON Schema ``enum`` on string checkpoint fields so UIs render a <select>,
    not a plain text input (same values as GET /v1/studio/comfy/checkpoints).

    Leading ``""`` = workflow default (submit empty string or omit ``checkpoint``).
    """
    if not names:
        return
    enum_values = ["", *names]
    presets = payload.get("presets")
    if not isinstance(presets, list):
        return
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        schema = preset.get("inputs_schema")
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties")
        if not isinstance(props, dict):
            continue
        for key in ("checkpoint", "ckpt_name"):
            entry = props.get(key)
            if isinstance(entry, dict) and entry.get("type") == "string":
                entry["enum"] = list(enum_values)


@router.get("/catalog")
async def get_studio_catalog() -> dict:
    """Presets + ``inputs_schema`` for Studio forms (ComfyUI workflows shipped in repo)."""
    payload = studio_catalog_payload()
    try:
        names = await asyncio.to_thread(list_studio_checkpoints)
    except StudioComfyError as e:
        logger.info("studio catalog: checkpoint enum omitted (ComfyUI list failed): %s", e)
        names = []
    _inject_checkpoint_enum_into_catalog(payload, names)
    return payload


@router.get("/comfy/checkpoints")
async def get_studio_comfy_checkpoints() -> dict:
    """
    Filenames ComfyUI exposes for ``CheckpointLoaderSimple`` (for Studio checkpoint dropdown).

    Restrict with env ``AGENT_STUDIO_ALLOWED_CKPTS`` (comma-separated exact names).
    """
    try:
        names = await asyncio.to_thread(list_studio_checkpoints)
    except StudioComfyError as e:
        logger.warning("studio checkpoints list failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"checkpoints": names}


class StudioJobRequest(BaseModel):
    run_key: str = Field(..., min_length=1, description="Preset id from catalog")
    inputs: dict = Field(default_factory=dict, description="Field values matching inputs_schema")


@router.post("/jobs")
async def create_studio_job(body: StudioJobRequest) -> dict:
    """
    Run a studio preset against ComfyUI (blocking work offloaded to a thread).

    **200:** ``images`` / ``primary_image`` are objects ``{ mime, base64, data_url }`` (Agent Layer fetched bytes from ComfyUI; browser needs no Comfy URL).
    """
    try:
        return await asyncio.to_thread(run_studio_job, body.run_key, body.inputs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except StudioComfyError as e:
        logger.warning("studio job failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception:
        logger.exception("studio job unexpected error run_key=%s", body.run_key)
        raise HTTPException(status_code=500, detail="studio job failed") from None
