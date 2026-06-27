"""Admin import analyzer for migrating external agent definitions."""

from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from typing import Any

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.application.identity.use_cases.request_auth import require_admin

router = APIRouter(prefix="/v1/admin/agents/import", tags=["agents-import-admin"])

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


def _slug(raw: str, fallback: str = "imported_agent") -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip().lower()).strip("_") or fallback
    if not re.match(r"^[a-zA-Z_]", base):
        base = f"agent_{base}"
    return base[:64]


def _loads_structured(source: dict[str, str]) -> dict[str, Any]:
    path = source["path"].lower()
    text = source["content"]
    try:
        if path.endswith(".json"):
            parsed = json.loads(text)
        elif path.endswith((".yaml", ".yml")):
            parsed = yaml.safe_load(text)
        else:
            return {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _as_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [str(v).strip() for v in raw if str(v).strip()]
    return []


def _detect_source_type(requested: str, sources: list[dict[str, str]]) -> tuple[str, float]:
    source_type = (requested or "auto").strip().lower()
    if source_type and source_type != "auto":
        return source_type, 1.0
    names = " ".join(s["path"].lower() for s in sources)
    text = "\n".join(s["content"][:6000].lower() for s in sources)
    if "openclaw" in text:
        return "openclaw_agent", 0.76
    if "hermes" in names or "hermes" in text:
        return "hermes_agent", 0.72
    if "langgraph" in text:
        return "langgraph_agent", 0.7
    if "crewai" in text or "crew ai" in text:
        return "crewai_agent", 0.68
    if "autogen" in text:
        return "autogen_agent", 0.68
    return "generic_agent", 0.55


def _extract_prompt(sources: list[dict[str, str]], structured: list[dict[str, Any]]) -> str:
    for row in structured:
        prompt = _first_str(row, ("system_prompt", "instructions", "prompt", "persona", "role"))
        if prompt:
            return prompt
    for source in sources:
        lines = source["content"].splitlines()
        heading_seen = False
        body: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                heading_seen = True
                continue
            if heading_seen and stripped:
                body.append(line)
            if len("\n".join(body)) > 4000:
                break
        if body:
            return "\n".join(body).strip()
    return ""


def _suggest_tool_domains(text: str) -> list[str]:
    lower = text.lower()
    domains: list[str] = []
    checks = [
        ("github", ("git", "github", "repo", "pull request", "commit")),
        ("network", ("http", "api", "webhook", "request", "download")),
        ("knowledge", ("search", "rag", "knowledge", "document", "memory")),
        ("files", ("file", "folder", "path", "read", "write")),
        ("comms", ("email", "slack", "telegram", "discord", "message")),
        ("media", ("image", "audio", "video", "transcribe")),
    ]
    for domain, terms in checks:
        if any(term in lower for term in terms):
            domains.append(domain)
    return domains[:5]


def _known_tool_matches(text: str) -> list[dict[str, Any]]:
    lower = text.lower()
    matches: list[dict[str, Any]] = []
    try:
        reg = get_registry()
    except Exception:
        return []
    for entry in reg.tools_meta:
        names = [str(n) for n in entry.get("tools") or [] if n]
        haystack = " ".join([str(entry.get("id") or ""), str(entry.get("domain") or ""), *names]).lower()
        score = 0
        for word in re.findall(r"[a-zA-Z0-9_]{4,}", haystack):
            if word in lower:
                score += 1
        if score:
            matches.append(
                {
                    "package_id": entry.get("id"),
                    "domain": entry.get("domain"),
                    "tools": names[:8],
                    "score": score,
                }
            )
    return sorted(matches, key=lambda m: int(m["score"]), reverse=True)[:8]


def _analyze_sources(source_type: str, sources: list[dict[str, str]]) -> dict[str, Any]:
    detected, confidence = _detect_source_type(source_type, sources)
    structured = [_loads_structured(s) for s in sources]
    structured = [s for s in structured if s]
    joined = "\n".join(s["content"] for s in sources)
    primary = structured[0] if structured else {}
    title = _first_str(primary, ("name", "title", "agent_name")) or next(
        (line.lstrip("#").strip() for line in joined.splitlines() if line.strip().startswith("#")),
        "Imported Agent",
    )
    agent_id = _slug(_first_str(primary, ("id", "slug", "name")) or title)
    explicit_tools = _as_list(primary.get("tool_allowlist") or primary.get("tools"))
    tool_domains = _as_list(primary.get("tool_domains")) or _suggest_tool_domains(joined)
    prompt = _extract_prompt(sources, structured)
    requires_workspace = any(term in joined.lower() for term in ("workspace", "repository", "repo", "codebase"))
    model_profile = _first_str(primary, ("model_profile", "model", "llm_model")) or None
    risky = any(term in joined.lower() for term in ("secret", "token", "api key", "password", "shell", "delete", "exec"))
    config_patches: list[dict[str, Any]] = []
    if "delegate" in joined.lower() or "subagent" in joined.lower():
        config_patches.append({"knob_id": "operator.delegate_enabled", "value": True, "reason": "Source mentions delegation/subagents."})
    if "strict" in joined.lower() or explicit_tools:
        config_patches.append({"knob_id": "tool_routing.router_strict_default", "value": True, "reason": "Imported agent appears tool-specific."})
    if model_profile:
        config_patches.append({"knob_id": "operator.llm_smart_routing_enabled", "value": False, "reason": "Source declares an explicit model hint."})

    agent_yaml = {
        "id": agent_id,
        "name": title[:80],
        "description": _first_str(primary, ("description", "summary")) or "Imported external agent draft.",
        "system_prompt_file": "system_prompt.md",
        "requires_workspace": requires_workspace,
        "execution_context": "auto",
        "min_role": "admin" if risky else "user",
        "model_profile": model_profile,
        "tool_domains": tool_domains,
        "tool_allowlist": explicit_tools[:50],
        "tool_include_introspection": True,
    }
    return {
        "ok": True,
        "source_type": detected,
        "source_type_confidence": confidence,
        "source_count": len(sources),
        "sources": [{"path": s["path"], "chars": len(s["content"])} for s in sources],
        "agent_draft": {
            "target_dir": f"plugins/agents/{agent_id}",
            "agent_yaml": agent_yaml,
            "system_prompt_preview": prompt[:4000],
            "risk": "high" if risky else "medium" if explicit_tools or tool_domains else "low",
            "notes": [
                "Review before writing files; imported agent configs can contain unsafe tool or shell assumptions.",
                "Secrets are intentionally not imported. Convert them to operator/user secret placeholders.",
            ],
        },
        "tool_mapping": {
            "matched_existing": _known_tool_matches(joined),
            "missing_or_ambiguous": explicit_tools if explicit_tools else [],
        },
        "config_patches": config_patches,
    }


@router.post("/analyze")
async def analyze_agent_import(
    request: Request,
    source_type: str = Form("auto"),
    text: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> dict[str, Any]:
    await require_admin(request)
    sources: list[dict[str, str]] = []
    if text.strip():
        sources.append({"path": "pasted-agent.md", "content": text})
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
        raise HTTPException(status_code=400, detail="Provide agent text or upload .md/.txt/.yaml/.json/.zip files")
    if len(sources) > _MAX_FILES:
        raise HTTPException(status_code=413, detail=f"too many source files (max {_MAX_FILES})")
    if sum(len(s["content"].encode("utf-8")) for s in sources) > _MAX_TOTAL_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="total source text exceeds 4 MiB")
    return _analyze_sources(source_type, sources)
