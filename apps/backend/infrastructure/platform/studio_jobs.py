"""
Execute Image Studio presets against ComfyUI (POST /prompt + history poll).

Workflow JSON paths are relative to the repository root.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any, cast

import httpx

from apps.backend.domain.studio.catalog import WORKFLOW_IMAGE2IMAGE, WORKFLOW_TXT2IMG

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMFY_URL = (
    (os.environ.get("COMFYUI_URL") or os.environ.get("COMFYUI_BASE_URL") or "http://127.0.0.1:8188")
    .strip()
    .rstrip("/")
)
_CLIENT_ID = str(uuid.uuid4())
_SUBMIT_TIMEOUT = float(os.environ.get("AGENT_STUDIO_COMFY_SUBMIT_TIMEOUT", "60"))
_POLL_TIMEOUT = int(os.environ.get("AGENT_STUDIO_COMFY_POLL_TIMEOUT", "180"))
_POLL_INTERVAL = float(os.environ.get("AGENT_STUDIO_COMFY_POLL_INTERVAL", "2"))
_MAX_OUTPUT_BYTES = int(os.environ.get("AGENT_STUDIO_MAX_OUTPUT_BYTES", "25000000"))
_CKPT_LIST_CACHE_SEC = float(os.environ.get("AGENT_STUDIO_CKPT_LIST_CACHE_SEC", "60"))

_ckpt_cache_mono: float = 0.0
_ckpt_cache_names: list[str] = []


class StudioComfyError(Exception):
    """ComfyUI HTTP or logical failure."""


def _parse_ckpt_allowlist_env() -> frozenset[str] | None:
    raw = (os.environ.get("AGENT_STUDIO_ALLOWED_CKPTS") or "").strip()
    if not raw:
        return None
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    return frozenset(parts) if parts else None


def _combo_choices(spec: object) -> list[str]:
    """Parse ComfyUI ``/object_info`` combo field (first element = choice list)."""
    if spec is None or not isinstance(spec, (list, tuple)) or len(spec) < 1:
        return []
    first = spec[0]
    if isinstance(first, list):
        return [str(x) for x in first]
    return []


def _checkpoint_names_from_object_info(info: dict[str, Any]) -> list[str]:
    node = info.get("CheckpointLoaderSimple")
    if not isinstance(node, dict):
        return []
    inp = node.get("input")
    if not isinstance(inp, dict):
        return []
    required = inp.get("required")
    if not isinstance(required, dict):
        return []
    return _combo_choices(required.get("ckpt_name"))


def _filter_ckpts_with_allowlist(names: list[str], allow: frozenset[str] | None) -> list[str]:
    if allow is None:
        return sorted(set(names))
    return sorted({n for n in names if n in allow})


def _fetch_comfy_object_info() -> dict[str, Any]:
    try:
        with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
            r = client.get(f"{_COMFY_URL}/object_info")
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:2000]
        raise StudioComfyError(
            f"ComfyUI /object_info HTTP {e.response.status_code}: {detail}"
        ) from e
    except httpx.RequestError as e:
        raise StudioComfyError(f"ComfyUI unreachable at {_COMFY_URL}: {e}") from e
    if not isinstance(body, dict):
        raise StudioComfyError("ComfyUI /object_info returned non-object JSON")
    return cast(dict[str, Any], body)


def list_studio_checkpoints(*, force_refresh: bool = False) -> list[str]:
    """
    Checkpoint filenames ComfyUI exposes for ``CheckpointLoaderSimple``,
    optionally restricted by ``AGENT_STUDIO_ALLOWED_CKPTS`` (comma-separated).

    Cached for ``AGENT_STUDIO_CKPT_LIST_CACHE_SEC`` (default 60s).
    """
    global _ckpt_cache_mono, _ckpt_cache_names
    now = time.monotonic()
    if (
        not force_refresh
        and _ckpt_cache_names
        and (now - _ckpt_cache_mono) < _CKPT_LIST_CACHE_SEC
    ):
        return list(_ckpt_cache_names)

    info = _fetch_comfy_object_info()
    raw = _checkpoint_names_from_object_info(info)
    allow = _parse_ckpt_allowlist_env()
    filtered = _filter_ckpts_with_allowlist(raw, allow)
    _ckpt_cache_names = filtered
    _ckpt_cache_mono = now
    return list(filtered)


def _sanitize_checkpoint_name(name: str) -> str:
    s = name.strip()
    if not s:
        raise ValueError("checkpoint name is empty")
    if ".." in s or "/" in s or "\\" in s:
        raise ValueError("checkpoint must be a filename, not a path")
    return s


def _apply_checkpoint_input(w: dict[str, Any], raw_ckpt: object) -> None:
    """If ``raw_ckpt`` is set, validate against Comfy list and set first ``CheckpointLoaderSimple``."""
    if raw_ckpt is None:
        return
    s = str(raw_ckpt).strip()
    if not s:
        return
    name = _sanitize_checkpoint_name(s)
    allowed = list_studio_checkpoints()
    if name not in allowed:
        raise ValueError(f"checkpoint not in allowed list: {name!r}")
    for node in w.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "CheckpointLoaderSimple":
            continue
        node.setdefault("inputs", {})["ckpt_name"] = name
        return
    raise StudioComfyError("workflow has no CheckpointLoaderSimple node")


def _checkpoint_from_inputs(inputs: dict) -> object:
    return inputs.get("checkpoint") if inputs.get("checkpoint") is not None else inputs.get("ckpt_name")


def _workflow_path(rel: str) -> Path:
    p = _REPO_ROOT / rel
    if not p.is_file():
        raise StudioComfyError(f"workflow file missing: {rel}")
    return p


def _load_workflow(rel: str) -> dict[str, dict]:
    with _workflow_path(rel).open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise StudioComfyError("workflow JSON must be an object")
    return data


def _strip_data_url_b64(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("data:"):
        comma = s.find(",")
        if comma != -1:
            return s[comma + 1 :].strip()
    return s


def _decode_b64_image(b64_str: str) -> bytes:
    raw = _strip_data_url_b64(b64_str).strip().replace("-", "+").replace("_", "/")
    pad = (-len(raw)) % 4
    raw += "=" * pad
    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        return base64.b64decode(raw, validate=False)


def _mime_from_magic(b: bytes) -> tuple[str, str]:
    if len(b) >= 3 and b[0:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if len(b) >= 8 and b[0:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return ".png", "image/png"


def _guess_mime_from_bytes(data: bytes, content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct and ct not in ("application/octet-stream", "binary/octet-stream"):
        return ct
    _, magic = _mime_from_magic(data)
    return magic


def _upload_to_comfy_input(client: httpx.Client, image_bytes: bytes, label: str) -> str:
    """POST /upload/image; return filename for LoadImage ``inputs.image``."""
    ext, mime = _mime_from_magic(image_bytes)
    fname = f"agent_studio_{label}_{uuid.uuid4().hex[:12]}{ext}"
    files = {"image": (fname, image_bytes, mime)}
    data = {"type": "input", "overwrite": "true"}
    try:
        r = client.post(f"{_COMFY_URL}/upload/image", files=files, data=data)
        r.raise_for_status()
        body = r.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:2000]
        raise StudioComfyError(
            f"ComfyUI /upload/image HTTP {e.response.status_code}: {detail}"
        ) from e
    except httpx.RequestError as e:
        raise StudioComfyError(f"ComfyUI upload failed: {e}") from e
    name = body.get("name")
    if not name:
        raise StudioComfyError(f"ComfyUI upload returned no name: {body!r}")
    return str(name)


def _post_prompt(client: httpx.Client, workflow: dict) -> str:
    payload = {"prompt": workflow, "client_id": _CLIENT_ID}
    r = client.post(f"{_COMFY_URL}/prompt", json=payload)
    r.raise_for_status()
    body = r.json()
    pid = body.get("prompt_id")
    if not pid:
        raise StudioComfyError(f"ComfyUI returned no prompt_id: {body!r}")
    return str(pid)


def _queue_prompt(workflow: dict) -> str:
    try:
        with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
            return _post_prompt(client, workflow)
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:2000]
        raise StudioComfyError(f"ComfyUI /prompt HTTP {e.response.status_code}: {detail}") from e
    except httpx.RequestError as e:
        raise StudioComfyError(f"ComfyUI unreachable at {_COMFY_URL}: {e}") from e


def _collect_output_specs(prompt_id: str) -> list[tuple[str, str, str]]:
    """Return (basename filename, subfolder, type) for each Comfy output image."""
    deadline = time.monotonic() + _POLL_TIMEOUT
    specs: list[tuple[str, str, str]] = []
    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(f"{_COMFY_URL}/history/{prompt_id}")
                r.raise_for_status()
                history = r.json()
            except httpx.HTTPError as e:
                logger.warning("comfy history poll failed: %s", e)
                time.sleep(_POLL_INTERVAL)
                continue
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for _nid, node_output in outputs.items():
                    if "images" not in node_output:
                        continue
                    for img in node_output["images"]:
                        raw_fn = str(img.get("filename") or "")
                        fn = Path(raw_fn).name
                        if not fn:
                            continue
                        sub = str(img.get("subfolder") or "")
                        typ = str(img.get("type") or "output")
                        specs.append((fn, sub, typ))
                return specs
            time.sleep(_POLL_INTERVAL)
    return []


def _download_comfy_view_b64(
    client: httpx.Client, filename: str, subfolder: str, output_type: str
) -> dict[str, str]:
    """GET Comfy ``/view``; return ``mime``, ``base64``, ``data_url`` for the WebUI."""
    r = client.get(
        f"{_COMFY_URL}/view",
        params={
            "filename": filename,
            "subfolder": subfolder,
            "type": output_type,
        },
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.content
    if len(data) > _MAX_OUTPUT_BYTES:
        raise StudioComfyError(
            f"ComfyUI output too large ({len(data)} bytes); raise AGENT_STUDIO_MAX_OUTPUT_BYTES or use smaller images"
        )
    mime = _guess_mime_from_bytes(data, r.headers.get("content-type"))
    b64 = base64.b64encode(data).decode("ascii")
    return {
        "mime": mime,
        "base64": b64,
        "data_url": f"data:{mime};base64,{b64}",
    }


def _embed_all_outputs(prompt_id: str) -> list[dict[str, str]]:
    specs = _collect_output_specs(prompt_id)
    if not specs:
        return []
    out: list[dict[str, str]] = []
    with httpx.Client(timeout=120.0) as client:
        for fn, sub, typ in specs:
            try:
                out.append(_download_comfy_view_b64(client, fn, sub, typ))
            except httpx.HTTPStatusError as e:
                detail = (e.response.text or "")[:500]
                raise StudioComfyError(
                    f"ComfyUI /view HTTP {e.response.status_code} for {fn!r}: {detail}"
                ) from e
    return out


def _run_txt2img(inputs: dict) -> dict:
    prompt = str(inputs.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    wf = _load_workflow(WORKFLOW_TXT2IMG)
    w = copy.deepcopy(wf)

    _apply_checkpoint_input(w, _checkpoint_from_inputs(inputs))

    neg = str(inputs.get("negative_prompt") or "").strip()
    if "3" in w and w["3"].get("class_type") == "CLIPTextEncode":
        w["3"]["inputs"]["text"] = prompt
    if "4" in w and w["4"].get("class_type") == "CLIPTextEncode":
        w["4"]["inputs"]["text"] = neg if neg else w["4"]["inputs"].get("text", "")

    if "6" in w and w["6"].get("class_type") == "EmptyLatentImage":
        if "width" in inputs and inputs["width"] is not None:
            w["6"]["inputs"]["width"] = int(inputs["width"])
        if "height" in inputs and inputs["height"] is not None:
            w["6"]["inputs"]["height"] = int(inputs["height"])

    if "5" in w and w["5"].get("class_type") == "KSampler":
        ins = w["5"]["inputs"]
        if inputs.get("seed") is not None:
            ins["seed"] = int(inputs["seed"])
        else:
            ins["seed"] = random.randint(0, 2**48 - 1)
        if inputs.get("steps") is not None:
            ins["steps"] = int(inputs["steps"])
        if inputs.get("cfg") is not None:
            ins["cfg"] = float(inputs["cfg"])

    pid = _queue_prompt(w)
    embedded = _embed_all_outputs(pid)
    if not embedded:
        raise StudioComfyError("No output image from ComfyUI (timeout or empty history)")

    return {
        "ok": True,
        "run_key": "comfy_txt2img_default",
        "prompt_id": pid,
        "images": embedded,
        "primary_image": embedded[0],
    }


def _run_inpaint_masked(inputs: dict) -> dict:
    prompt = str(inputs.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    src_b64 = str(inputs.get("source_image") or "").strip()
    msk_b64 = str(inputs.get("mask_image") or "").strip()
    if not src_b64 or not msk_b64:
        raise ValueError("source_image and mask_image (base64) are required")

    wf = _load_workflow(WORKFLOW_IMAGE2IMAGE)
    w = copy.deepcopy(wf)

    _apply_checkpoint_input(w, _checkpoint_from_inputs(inputs))

    try:
        src_bytes = _decode_b64_image(src_b64)
        msk_bytes = _decode_b64_image(msk_b64)
    except Exception as e:
        raise ValueError(f"invalid base64 image: {e}") from e

    if "8" not in w or w["8"].get("class_type") != "LoadImage":
        raise StudioComfyError("workflow missing LoadImage node 8 (source)")
    if "7" not in w or w["7"].get("class_type") != "LoadImage":
        raise StudioComfyError("workflow missing LoadImage node 7 (mask)")

    if "3" in w and w["3"].get("class_type") == "CLIPTextEncode":
        w["3"]["inputs"]["text"] = prompt
    neg = str(inputs.get("negative_prompt") or "").strip()
    if "4" in w and w["4"].get("class_type") == "CLIPTextEncode":
        w["4"]["inputs"]["text"] = neg if neg else w["4"]["inputs"].get("text", "")

    if "5" in w and w["5"].get("class_type") == "KSampler":
        ins = w["5"]["inputs"]
        if inputs.get("seed") is not None:
            ins["seed"] = int(inputs["seed"])
        else:
            ins["seed"] = random.randint(0, 2**48 - 1)
        if inputs.get("steps") is not None:
            ins["steps"] = int(inputs["steps"])
        if inputs.get("cfg") is not None:
            ins["cfg"] = float(inputs["cfg"])
        if inputs.get("denoise") is not None:
            ins["denoise"] = float(inputs["denoise"])

    try:
        with httpx.Client(timeout=_SUBMIT_TIMEOUT) as client:
            w["8"]["inputs"]["image"] = _upload_to_comfy_input(client, src_bytes, "src")
            w["7"]["inputs"]["image"] = _upload_to_comfy_input(client, msk_bytes, "msk")
            pid = _post_prompt(client, w)
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:2000]
        raise StudioComfyError(f"ComfyUI HTTP {e.response.status_code}: {detail}") from e
    except httpx.RequestError as e:
        raise StudioComfyError(f"ComfyUI unreachable at {_COMFY_URL}: {e}") from e
    embedded = _embed_all_outputs(pid)
    if not embedded:
        raise StudioComfyError("No output image from ComfyUI (timeout or empty history)")

    return {
        "ok": True,
        "run_key": "comfy_inpaint_masked_default",
        "prompt_id": pid,
        "images": embedded,
        "primary_image": embedded[0],
    }


_RUNNERS = {
    "comfy_txt2img_default": _run_txt2img,
    "comfy_inpaint_masked_default": _run_inpaint_masked,
}


def run_studio_job(run_key: str, inputs: dict) -> dict:
    """
    Run a studio preset synchronously (call via ``asyncio.to_thread`` from FastAPI).

    Raises:
        ValueError: bad client input
        StudioComfyError: ComfyUI failure
    """
    fn = _RUNNERS.get(run_key)
    if not fn:
        raise ValueError(f"unknown run_key: {run_key!r}")
    return fn(inputs or {})
