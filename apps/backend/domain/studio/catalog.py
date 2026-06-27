"""
Backend-driven Image Studio preset list for schema-driven UIs.

Workflow JSON paths are relative to the repository root (Docker: ``/app``).
Job execution is implemented separately (see ``POST /v1/studio/jobs``).
"""

from __future__ import annotations

from typing import Any

# ComfyUI graph JSON under repo root — plug-and-play: ``plugins/image_generation/workflows/``.
WORKFLOW_TXT2IMG = "plugins/image_generation/workflows/txt2image.json"
WORKFLOW_IMAGE2IMAGE = "plugins/image_generation/workflows/image2image.json"


def studio_catalog_payload() -> dict[str, Any]:
    """
    Machine-readable catalog for Open WebUI / Studio front ends.

    ``inputs_schema`` follows JSON Schema ``type: object`` conventions
    (subset: string, integer, number, boolean). Use ``format`` hints for files.
    """
    return {
        "studio_version": 2,
        "engine_default": "comfyui",
        "presets": [
            {
                "run_key": "comfy_txt2img_default",
                "title": "Text → Image",
                "description": (
                    "Classic txt2img: empty latent + KSampler. "
                    f"Workflow file: {WORKFLOW_TXT2IMG}. "
                    "Optional checkpoint: GET /v1/studio/comfy/checkpoints."
                ),
                "kind": "txt2img",
                "engine": "comfyui",
                "workflow_file": WORKFLOW_TXT2IMG,
                "inputs_schema": {
                    "type": "object",
                    "properties": {
                        "checkpoint": {
                            "type": "string",
                            "title": "Checkpoint",
                            "description": (
                                "ComfyUI checkpoint. Omit for workflow default. "
                                "GET /v1/studio/catalog adds enum (dropdown); "
                                "GET /v1/studio/comfy/checkpoints is the same list."
                            ),
                        },
                        "prompt": {
                            "type": "string",
                            "title": "Prompt",
                            "description": "Positive prompt (CLIP encode).",
                        },
                        "negative_prompt": {
                            "type": "string",
                            "title": "Negative prompt",
                            "default": "",
                        },
                        "width": {
                            "type": "integer",
                            "title": "Width",
                            "default": 512,
                            "minimum": 64,
                            "maximum": 2048,
                        },
                        "height": {
                            "type": "integer",
                            "title": "Height",
                            "default": 768,
                            "minimum": 64,
                            "maximum": 2048,
                        },
                        "seed": {
                            "type": "integer",
                            "title": "Seed",
                            "description": "Optional; random if omitted.",
                        },
                    },
                    "required": ["prompt"],
                },
            },
            {
                "run_key": "comfy_inpaint_masked_default",
                "title": "Inpaint (image + mask)",
                "description": (
                    "Load source image + mask image, SetLatentNoiseMask, KSampler. "
                    "Matches the current API workflow JSON (not plain img2img). "
                    f"Workflow file: {WORKFLOW_IMAGE2IMAGE}. "
                    "Optional checkpoint: GET /v1/studio/comfy/checkpoints."
                ),
                "kind": "inpaint",
                "engine": "comfyui",
                "workflow_file": WORKFLOW_IMAGE2IMAGE,
                "inputs_schema": {
                    "type": "object",
                    "properties": {
                        "checkpoint": {
                            "type": "string",
                            "title": "Checkpoint",
                            "description": (
                                "ComfyUI checkpoint; omit for workflow default. "
                                "Catalog response adds enum for dropdown when ComfyUI is reachable."
                            ),
                        },
                        "prompt": {
                            "type": "string",
                            "title": "Prompt",
                        },
                        "negative_prompt": {
                            "type": "string",
                            "title": "Negative prompt",
                            "default": "",
                        },
                        "source_image": {
                            "type": "string",
                            "format": "byte",
                            "contentEncoding": "base64",
                            "title": "Source image",
                            "description": "Original RGB image as base64; server uploads to ComfyUI /upload/image then references it in LoadImage.",
                        },
                        "mask_image": {
                            "type": "string",
                            "format": "byte",
                            "contentEncoding": "base64",
                            "title": "Mask image",
                            "description": "Mask image as base64; uploaded to ComfyUI input before the workflow runs.",
                        },
                        "denoise": {
                            "type": "number",
                            "title": "Denoise",
                            "default": 0.43,
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "steps": {
                            "type": "integer",
                            "title": "Steps",
                            "default": 30,
                            "minimum": 1,
                            "maximum": 150,
                        },
                        "cfg": {
                            "type": "number",
                            "title": "CFG",
                            "default": 4.0,
                            "minimum": 1.0,
                        },
                        "seed": {
                            "type": "integer",
                            "title": "Seed",
                        },
                    },
                    "required": ["prompt", "source_image", "mask_image"],
                },
            },
        ],
    }
