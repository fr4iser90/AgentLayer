"""Admin Markdown/skill import analyzer for future tool/workflow generation."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from apps.backend.application.identity.use_cases.request_auth import require_admin

router = APIRouter(prefix="/v1/admin/tools/import", tags=["tools-import-admin"])

_ALLOWED_EXT = {".md", ".markdown", ".txt", ".yaml", ".yml", ".json"}
_MAX_FILES = 20
_MAX_ZIP_ENTRIES = 50
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_TEXT_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_TEXT_BYTES = 4 * 1024 * 1024


def _safe_path(raw: str) -> str:
    path = (raw or "source.md").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    return ("/".join(parts) or "source.md")[:240]


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def _decode_text(path: str, raw: bytes) -> str:
    if len(raw) > _MAX_TEXT_BYTES:
        raise HTTPException(status_code=413, detail=f"{path}: file exceeds 2 MiB text limit")
    if b"\x00" in raw[:4096]:
        raise HTTPException(status_code=400, detail=f"{path}: binary content is not allowed")
    return raw.decode("utf-8", errors="replace")


def _append_source(out: list[dict[str, str]], path: str, raw: bytes) -> None:
    safe = _safe_path(path)
    if _ext(safe) not in _ALLOWED_EXT:
        return
    if len(out) >= _MAX_FILES:
        raise HTTPException(status_code=413, detail=f"too many import files (max {_MAX_FILES})")
    out.append({"path": safe, "content": _decode_text(safe, raw)})


def _sources_from_zip(filename: str, raw: bytes) -> list[dict[str, str]]:
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{filename}: zip exceeds 10 MiB limit")
    try:
        zf = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"{filename}: invalid zip file") from exc

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > _MAX_ZIP_ENTRIES:
        raise HTTPException(status_code=413, detail=f"{filename}: too many zip entries")

    out: list[dict[str, str]] = []
    total_uncompressed = 0
    for info in infos:
        normalized = info.filename.replace("\\", "/").strip().lstrip("/")
        path = _safe_path(info.filename)
        if path != normalized:
            raise HTTPException(status_code=400, detail=f"{filename}: unsafe zip path {info.filename!r}")
        if _ext(path) not in _ALLOWED_EXT:
            continue
        total_uncompressed += int(info.file_size or 0)
        if total_uncompressed > _MAX_TOTAL_TEXT_BYTES:
            raise HTTPException(status_code=413, detail=f"{filename}: uncompressed text exceeds 4 MiB")
        if info.compress_size and info.file_size > max(1024 * 1024, info.compress_size * 100):
            raise HTTPException(status_code=413, detail=f"{filename}: suspicious compression ratio")
        with zf.open(info, "r") as fh:
            _append_source(out, path, fh.read(_MAX_TEXT_BYTES + 1))
    return out


def _slug(raw: str, fallback: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip().lower()).strip("_") or fallback
    if not re.match(r"^[a-zA-Z_]", base):
        base = f"tool_{base}"
    return base[:64]


def _detect_source_type(source_type: str, sources: list[dict[str, str]]) -> tuple[str, float]:
    requested = (source_type or "auto").strip().lower()
    if requested and requested != "auto":
        return requested, 1.0
    names = " ".join(s["path"].lower() for s in sources)
    text = "\n".join(s["content"][:4000].lower() for s in sources)
    if "skill.md" in names or ("cursor" in text and "skill" in text):
        return "cursor_skill", 0.78
    if "openclaw" in text or ("claw" in text and "skill" in text):
        return "openclaw_skill", 0.72
    if "slash command" in text or ("claude" in text and "command" in text):
        return "claude_command", 0.68
    return "generic_markdown", 0.55


def _analyze_sources(source_type: str, sources: list[dict[str, str]]) -> dict[str, Any]:
    detected, confidence = _detect_source_type(source_type, sources)
    candidates: list[dict[str, Any]] = []
    for idx, src in enumerate(sources[:_MAX_FILES], start=1):
        text = src["content"]
        heading = next(
            (line.lstrip("#").strip() for line in text.splitlines() if line.strip().startswith("#")),
            src["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0],
        )
        lower = text.lower()
        has_steps = any(tok in lower for tok in ("step", "workflow", "first", "then", "run ", "execute"))
        has_inputs = any(tok in lower for tok in ("input", "argument", "parameter", "config", "variable"))
        risky = any(tok in lower for tok in ("secret", "token", "api key", "password", "shell", "network", "delete"))
        kind = "workflow" if has_steps and text.count("\n") > 12 else "tool"
        if "policy" in lower and not has_steps:
            kind = "prompt_only"
        candidates.append(
            {
                "kind": kind,
                "name": _slug(heading, f"imported_skill_{idx}"),
                "title": heading[:120],
                "summary": "Draft candidate extracted from Markdown. Review before generating code.",
                "confidence": 0.62 if kind != "prompt_only" else 0.48,
                "risk": "high" if risky else "medium" if has_inputs else "low",
                "source_paths": [src["path"]],
                "inputs_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "User request or task context"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "side_effects": {
                    "filesystem": "unknown" if risky else "none",
                    "network": "unknown" if "http" in lower or "api" in lower else "none",
                    "secrets": "possible" if any(tok in lower for tok in ("secret", "token", "api key")) else "none",
                },
                "target_dir": "plugins/tools/agent_created" if kind == "tool" else "plugins/workflows/agent_created",
                "determinism_notes": [
                    "Generated from Markdown; require human review before activation.",
                    "Convert ambiguous prose into explicit input schema and bounded steps.",
                ],
            }
        )
    return {
        "ok": True,
        "source_type": detected,
        "source_type_confidence": confidence,
        "source_count": len(sources),
        "limits": {
            "max_files": _MAX_FILES,
            "max_zip_entries": _MAX_ZIP_ENTRIES,
            "max_text_bytes_per_file": _MAX_TEXT_BYTES,
            "max_total_text_bytes": _MAX_TOTAL_TEXT_BYTES,
        },
        "sources": [{"path": s["path"], "chars": len(s["content"])} for s in sources],
        "candidates": candidates,
    }


@router.post("/analyze")
async def analyze_import(
    request: Request,
    source_type: str = Form("auto"),
    markdown: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
):
    await require_admin(request)
    sources: list[dict[str, str]] = []
    if markdown.strip():
        sources.append({"path": "pasted.md", "content": markdown})
    for up in files or []:
        name = _safe_path(up.filename or "upload.md")
        raw = await up.read(_MAX_UPLOAD_BYTES + 1)
        if len(raw) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{name}: upload exceeds 10 MiB limit")
        if name.lower().endswith(".zip"):
            sources.extend(_sources_from_zip(name, raw))
        else:
            _append_source(sources, name, raw)

    if not sources:
        raise HTTPException(status_code=400, detail="Provide Markdown text or upload .md/.txt/.yaml/.json/.zip files")
    if len(sources) > _MAX_FILES:
        raise HTTPException(status_code=413, detail=f"too many source files (max {_MAX_FILES})")
    if sum(len(s["content"].encode("utf-8")) for s in sources) > _MAX_TOTAL_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="total source text exceeds 4 MiB")
    return _analyze_sources(source_type, sources)
