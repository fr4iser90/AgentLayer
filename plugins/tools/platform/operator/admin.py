"""Admin-only operator console tools (mirror ``/v1/admin/*`` HTTP where practical).

Every handler checks **DB role admin** for the current chat identity. Prefer these tools
from ``agent_id: operator``; they are also allowlisted only for that agent by default.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.domain.identity import get_identity
from apps.backend.domain.rag_docs_file_ingest import ingest_markdown_tree, resolve_docs_root
from apps.backend.domain.plugin_system.registry import get_registry, reload_registry
from apps.backend.domain.plugin_system.tools_api import ToolPoliciesPutBody
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.auth import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    list_all_users,
    update_user_tenant,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import (
    InterfaceHintsPayload,
    OperatorSettingsPatch,
    apply_interface_hints,
    apply_operator_settings_patch,
    external_api_headers,
    external_models_list_url,
    interface_hints_public,
    invalidate_operator_settings_cache,
    operator_settings_patch_client_error,
    operator_settings_patch_tool_parameters,
    public_dict as operator_settings_public_dict,
    resolve_external_llm_credentials_for_catalog,
)
from apps.backend.infrastructure import scheduler_jobs_store
from apps.backend.infrastructure import project_runs_store
from apps.backend.infrastructure.public_error import http_500_detail
import apps.backend.api.rag as rag_service
from apps.backend.infrastructure.chat_secret_ingress import (
    consume_placeholders_in_obj,
    resolve_placeholders_deep,
)

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
TOOL_ID = "operator_admin"
TOOL_BUCKET = "meta"
# Own domain so ``AGENT_TOOL_DOMAINS`` / broad ``meta`` filters do not sweep admin tools into other agents.
TOOL_DOMAIN = "operator"
TOOL_LABEL = "Operator admin console"
TOOL_DESCRIPTION = (
    "Admin-only: read/patch operator_settings, interfaces, external LLM endpoints, tenants/users, "
    "tool catalog/policies, reload registry, RAG ingest, persisted scheduler_jobs, presets, project_runs."
)
# Router phrases: co-located admin.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_MIN_ROLE = "admin"
TOOL_CAPABILITIES = ("operator.console",)

_CAP = ("operator.console",)
AGENT_TOOL_META_BY_NAME = {}


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def _err_obj(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False, default=str)


def _admin_tid_uid() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    if db.user_role(uid) != "admin":
        return None
    try:
        t = int(tid)
    except (TypeError, ValueError):
        return None
    return t, uid


def _require_admin() -> tuple[int, uuid.UUID] | str:
    g = _admin_tid_uid()
    if g is None:
        return _err("authentication and admin role required for this tool")
    return g


def _parse_uuid(raw: Any, *, field: str) -> uuid.UUID | None:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError):
        return None


# --- operator settings / interfaces ---


def settings_get(arguments: dict[str, Any]) -> str:
    """Return masked operator_settings (``public_dict``) plus interface hints."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    settings = operator_settings_public_dict()
    interfaces = interface_hints_public()
    return _ok({"settings": settings, "interfaces": interfaces})


def settings_patch(arguments: dict[str, Any]) -> str:
    """Partial update; keys must match ``OperatorSettingsPatch`` (no unknown fields)."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    tid, uid = g_adm
    if not isinstance(arguments, dict) or not arguments:
        return _err_obj(
            operator_settings_patch_client_error(
                "missing arguments: at least one OperatorSettingsPatch field as top-level JSON property",
                reason="empty_arguments",
            )
        )
    resolved = resolve_placeholders_deep(dict(arguments), tenant_id=int(tid), user_id=uid)
    try:
        body = OperatorSettingsPatch.model_validate(resolved)
    except Exception as e:
        return _err_obj(
            operator_settings_patch_client_error(
                f"invalid field values: {e}",
                reason="validation_failed",
            )
        )
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return _err_obj(
            operator_settings_patch_client_error(
                "no effective changes: pass at least one key with a new value",
                reason="empty_patch",
            )
        )
    try:
        apply_operator_settings_patch(body)
    except Exception as e:
        logger.exception("settings_patch")
        return _err(http_500_detail(e))
    consume_placeholders_in_obj(arguments, tenant_id=int(tid), user_id=uid)
    return settings_get({})


def interfaces_get(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    return _ok({"interfaces": interface_hints_public()})


def interfaces_put(arguments: dict[str, Any]) -> str:
    """Set Discord/Telegram application ids and agent_mode (sandbox|host)."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    try:
        body = InterfaceHintsPayload.model_validate(arguments)
    except Exception as e:
        return _err(f"invalid body: {e}")
    apply_interface_hints(body)
    return operator_interfaces_get({})


# --- external LLM endpoints ---


class _ExtEndpointItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    sort_order: int = 0
    enabled: bool = True
    label: str = ""
    base_url: str = ""
    api_key: str | None = None
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None


class _ExtEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[_ExtEndpointItem] = Field(default_factory=list)


def external_llm_endpoints_get(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    out: list[dict[str, Any]] = []
    for r in db.external_llm_endpoints_list_all():
        k = str(r.get("api_key") or "")
        out.append(
            {
                "id": r["id"],
                "sort_order": r["sort_order"],
                "enabled": r["enabled"],
                "label": r.get("label") or "",
                "base_url": r.get("base_url") or "",
                "api_key_configured": bool(k.strip()),
                "api_key_last4": (k[-4:] if len(k) >= 4 else None),
                "model_default": r.get("model_default"),
                "model_vlm": r.get("model_vlm"),
                "model_agent": r.get("model_agent"),
                "model_coding": r.get("model_coding"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
        )
    return _ok({"endpoints": out})


def external_llm_endpoints_put(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    tid, uid = g_adm
    resolved = resolve_placeholders_deep(dict(arguments or {}), tenant_id=int(tid), user_id=uid)
    try:
        body = _ExtEndpointsPutBody.model_validate(resolved)
    except Exception as e:
        return _err(f"invalid body: {e}")
    raw = [e.model_dump() for e in body.endpoints]
    try:
        db.external_llm_endpoints_sync(raw)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("external_llm_endpoints_put")
        return _err(http_500_detail(e))
    invalidate_operator_settings_cache()
    consume_placeholders_in_obj(arguments, tenant_id=int(tid), user_id=uid)
    return operator_external_llm_endpoints_get({})


class _ExtModelsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    endpoint_id: int | None = None


def external_llm_models_list(arguments: dict[str, Any]) -> str:
    """Sync ``GET {base}/v1/models`` using body overrides or stored endpoint credentials."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    tid, uid = g_adm
    resolved = resolve_placeholders_deep(dict(arguments or {}), tenant_id=int(tid), user_id=uid)
    try:
        body = _ExtModelsBody.model_validate(resolved)
    except Exception as e:
        return _err(f"invalid body: {e}")
    try:
        bu, key = resolve_external_llm_credentials_for_catalog(
            body.base_url, body.api_key, endpoint_id=body.endpoint_id
        )
    except ValueError as e:
        tag = str(e)
        hints = {
            "missing_base_url": "base_url missing (set in body or save endpoints first)",
            "missing_api_key": "api_key missing",
            "unknown_endpoint": "unknown endpoint_id",
            "no_external_endpoint": "no enabled external LLM endpoint configured",
        }
        return _err(hints.get(tag, tag))
    url = external_models_list_url(bu)
    try:
        with httpx.Client(timeout=httpx.Timeout(45.0)) as client:
            resp = client.get(url, headers=external_api_headers(bu, key))
    except httpx.RequestError as e:
        return _err(f"connection failed: {e}")
    if resp.status_code != 200:
        snippet = (resp.text or "").strip()[:4000]
        return _err(snippet or f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return _err("response was not JSON")
    return _ok({"models_response": data})


# --- tenants / users ---


def tenants_list(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    return _ok({"tenants": db.tenants_list()})


def tenant_create(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    name = str(arguments.get("name") or "").strip()
    if not name:
        return _err("name is required")
    try:
        row = db.tenant_insert(name[:128])
    except Exception as e:
        logger.exception("tenant_create")
        return _err(http_500_detail(e))
    return _ok({"tenant": row})


def users_list(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    return _ok({"users": list_all_users()})


class _AdminCreateUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)
    role: Literal["user", "admin"] = "user"
    tenant_id: int = Field(default=1, ge=1)


def user_create(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    try:
        body = _AdminCreateUserBody.model_validate(arguments)
    except Exception as e:
        return _err(f"invalid body: {e}")
    if not db.tenant_exists(body.tenant_id):
        return _err("unknown tenant_id")
    if get_user_by_email(body.email):
        return _err("email already registered")
    try:
        u = create_user(body.email, body.password, body.role, tenant_id=body.tenant_id)
    except Exception as e:
        logger.exception("user_create")
        return _err(http_500_detail(e))
    return _ok({"id": str(u.id), "email": u.email, "role": u.role, "tenant_id": body.tenant_id})


class _AdminPatchUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., min_length=8)
    tenant_id: int | None = Field(default=None, ge=1)
    workspace_quota: int | None = Field(default=None, ge=1, le=1000)
    workspace_self_allowed: bool | None = None


def user_patch(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    try:
        body = _AdminPatchUserBody.model_validate(arguments)
    except Exception as e:
        return _err(f"invalid body: {e}")
    if body.tenant_id is None and body.workspace_quota is None and body.workspace_self_allowed is None:
        return _err("at least one of tenant_id, workspace_quota, workspace_self_allowed required")
    try:
        user_id = uuid.UUID(str(body.user_id).strip())
    except (ValueError, TypeError):
        return _err("invalid user_id UUID")
    u = get_user_by_id(user_id)
    if not u:
        return _err("user not found")
    if body.tenant_id is not None:
        if not db.tenant_exists(body.tenant_id):
            return _err("unknown tenant_id")
        if not update_user_tenant(user_id, body.tenant_id):
            return _err("user not found")
    if body.workspace_quota is not None:
        db.query(
            "UPDATE users SET workspace_quota = %s WHERE id = %s",
            (body.workspace_quota, user_id),
        )
    if body.workspace_self_allowed is not None:
        db.query(
            "UPDATE users SET workspace_self_allowed = %s WHERE id = %s",
            (body.workspace_self_allowed, user_id),
        )
    return _ok({"id": str(user_id), "tenant_id": db.user_tenant_id(user_id)})


# --- tool registry ---


def tools_catalog(arguments: dict[str, Any]) -> str:
    """Same data as ``GET /v1/admin/tools`` (metadata + policy rows)."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    try:
        from apps.backend.infrastructure.tool_operator_policy_db import list_policies, policies_map
        from apps.backend.domain.plugin_system.tool_policy import enrich_meta_for_admin

        pmap = policies_map()
        rows = list_policies()
    except Exception:
        logger.debug("admin_tools_catalog policy load failed", exc_info=True)
        pmap = {}
        rows = []
    reg = get_registry()
    tools = enrich_meta_for_admin(reg.tools_meta, pmap)
    return _ok({"tools": tools, "policy_rows": rows})


def tool_policies_put(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    try:
        body = ToolPoliciesPutBody.model_validate(arguments)
    except Exception as e:
        return _err(f"invalid body: {e}")
    try:
        from apps.backend.infrastructure.tool_operator_policy_db import replace_all_policies

        replace_all_policies([p.model_dump() for p in body.policies])
    except Exception as e:
        logger.exception("tool_policies_put")
        return _err(http_500_detail(e))
    return _ok({"count": len(body.policies)})


def reload_tools(arguments: dict[str, Any]) -> str:
    """Rescan plugin tool directories (same as ``POST /v1/admin/reload-tools``)."""
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    scope = str(arguments.get("scope") or "all").strip().lower()
    if scope not in ("all", "extra"):
        scope = "all"
    try:
        reg = reload_registry(scope=scope)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("reload_tools")
        return _err(http_500_detail(e))
    names = []
    for t in reg.chat_tool_specs:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.append(str(fn["name"]))
    return _ok({"scope": scope, "tool_count": len(reg.chat_tool_specs), "tool_names": names})


# --- RAG admin ---


def rag_ingest(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    if not operator_settings.rag_settings()["enabled"]:
        return _err("RAG disabled in operator settings")
    text = arguments.get("text")
    if not isinstance(text, str) or not text.strip():
        return _err("text (non-empty string) is required")
    domain = str(arguments.get("domain") or "").strip()
    title = str(arguments.get("title") or "").strip()
    su_raw = arguments.get("source_uri")
    su = str(su_raw).strip() if isinstance(su_raw, str) and str(su_raw).strip() else None
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    try:
        out = rag_service.ingest_for_user(tenant_id, uid, domain, title, text, su)
    except ValueError as e:
        return _err(str(e))
    except httpx.HTTPStatusError as e:
        detail = (
            f"Embedding API HTTP error: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding API HTTP error"
        )
        return _err(detail)
    except httpx.RequestError as e:
        detail = (
            f"Embedding API unreachable: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding API unreachable"
        )
        return _err(detail)
    except Exception as e:
        logger.exception("rag_ingest")
        return _err(http_500_detail(e))
    return json.dumps({"ok": True, "result": out}, ensure_ascii=False, default=str)


class _IngestDocsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    docs_root: str | None = None
    domain: str = Field(default="agentlayer_docs", min_length=1)
    purge_first: bool = False
    incremental: bool = True


def rag_ingest_docs(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    if not operator_settings.rag_settings()["enabled"]:
        return _err("RAG disabled in operator settings")
    try:
        opts = _IngestDocsArgs.model_validate(arguments or {})
    except Exception as e:
        return _err(f"invalid body: {e}")
    domain = opts.domain.strip()
    if opts.docs_root:
        root = Path(opts.docs_root).expanduser().resolve()
    else:
        root = resolve_docs_root()
    if not root.is_dir():
        return _err(f"docs_root not found or not a directory: {root}")
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    try:
        out = ingest_markdown_tree(
            tenant_id,
            uid,
            root,
            domain,
            purge_first=opts.purge_first,
            incremental=opts.incremental and not opts.purge_first,
        )
    except ValueError as e:
        return _err(str(e))
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("rag_ingest_docs")
        return _err(http_500_detail(e))
    return json.dumps({"ok": True, "result": out}, ensure_ascii=False, default=str)


# --- scheduler jobs (admin store API) ---


def scheduler_job_list(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    ws = _parse_uuid(arguments.get("dashboard_id"), field="dashboard_id")
    if arguments.get("dashboard_id") is not None and str(arguments.get("dashboard_id")).strip() and ws is None:
        return _err("invalid dashboard_id UUID")
    include_global = bool(arguments.get("include_global", False))
    include_archived = bool(arguments.get("include_archived", False))
    tgt_raw = arguments.get("execution_target")
    tgt = str(tgt_raw).strip().lower() or None if tgt_raw is not None else None
    from apps.backend.domain.scheduler_targets import (
        execution_target_error,
        is_valid_execution_target,
        normalize_execution_target,
    )

    tgt = normalize_execution_target(tgt) if tgt is not None else None
    if tgt is not None and not is_valid_execution_target(tgt):
        return _err(execution_target_error(tgt))
    en_raw = arguments.get("enabled")
    enabled = bool(en_raw) if isinstance(en_raw, bool) else None
    try:
        lim = int(arguments.get("limit", 200))
    except (TypeError, ValueError):
        lim = 200
    rows = scheduler_jobs_store.list_jobs_for_tenant(
        tenant_id=tenant_id,
        dashboard_id=ws,
        include_global=include_global,
        execution_target=tgt,
        enabled=enabled,
        include_archived=include_archived,
        limit=lim,
    )
    return _ok({"jobs": [scheduler_jobs_store.row_to_public(r) for r in rows]})


def scheduler_job_create(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    from apps.backend.domain.scheduler_targets import (
        agent_requires_workspace_for_target,
        execution_target_error,
        is_valid_execution_target,
        normalize_execution_target,
    )

    tgt = normalize_execution_target(str(arguments.get("execution_target") or ""))
    if not tgt or not is_valid_execution_target(tgt):
        return _err(execution_target_error(arguments.get("execution_target")))
    instructions = str(arguments.get("instructions") or "").strip()
    if not instructions:
        return _err("instructions is required")
    try:
        interval_m = int(arguments.get("interval_minutes", 60))
    except (TypeError, ValueError):
        return _err("interval_minutes must be an integer")
    if interval_m < 5 or interval_m > 10080:
        return _err("interval_minutes must be between 5 and 10080")
    title_raw = arguments.get("title")
    title = str(title_raw).strip()[:500] if title_raw is not None else None
    if title == "":
        title = None
    ws = _parse_uuid(arguments.get("dashboard_id"), field="dashboard_id")
    if arguments.get("dashboard_id") is not None and str(arguments.get("dashboard_id")).strip() and ws is None:
        return _err("invalid dashboard_id UUID")
    from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow

    wf_raw: dict[str, Any] = {}
    if arguments.get("coding_workflow") is not None:
        if not isinstance(arguments.get("coding_workflow"), dict):
            return _err("coding_workflow must be an object")
        wf_raw = dict(arguments["coding_workflow"])
    ws_arg = arguments.get("workspace_id")
    if ws_arg is not None and str(ws_arg).strip():
        wf_raw.setdefault("workspace_id", str(ws_arg).strip())
    try:
        coding_wf = normalize_coding_workflow(
            wf_raw, require_workspace=agent_requires_workspace_for_target(tgt)
        )
    except (ValueError, TypeError) as e:
        return _err(str(e))
    row = scheduler_jobs_store.insert_job(
        tenant_id=tenant_id,
        created_by_user_id=uid,
        execution_user_id=uid,
        dashboard_id=ws,
        execution_target=tgt,
        title=title,
        instructions=instructions,
        interval_minutes=interval_m,
        enabled=bool(arguments.get("enabled", True)),
        coding_workflow=coding_wf,
    )
    if not row:
        return _err("failed to create job")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


def scheduler_job_patch(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    jid = _parse_uuid(arguments.get("job_id"), field="job_id")
    if jid is None:
        return _err("job_id UUID required")
    title = arguments.get("title")
    instr = arguments.get("instructions")
    interval = arguments.get("interval_minutes")
    iv: int | None = None
    if interval is not None:
        try:
            iv = int(interval)
        except (TypeError, ValueError):
            return _err("interval_minutes must be integer")
    wf = arguments.get("coding_workflow")
    wf_norm: dict[str, Any] | None = None
    if wf is not None:
        try:
            from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow

            wf_norm = normalize_coding_workflow(wf)
        except (ValueError, TypeError) as e:
            return _err(str(e))
    row = scheduler_jobs_store.update_job(
        job_id=jid,
        tenant_id=tenant_id,
        actor_user_id=uid,
        actor_is_admin=True,
        title=str(title).strip() if isinstance(title, str) else None,
        instructions=str(instr).strip() if isinstance(instr, str) else None,
        interval_minutes=iv,
        coding_workflow=wf_norm,
    )
    if not row:
        return _err("job not found")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


def scheduler_job_set_enabled(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    jid = _parse_uuid(arguments.get("job_id"), field="job_id")
    if jid is None:
        return _err("job_id UUID required")
    if "enabled" not in arguments:
        return _err("enabled boolean required")
    row = scheduler_jobs_store.set_enabled(
        job_id=jid,
        tenant_id=tenant_id,
        enabled=bool(arguments.get("enabled")),
        actor_user_id=uid,
        actor_is_admin=True,
    )
    if not row:
        return _err("job not found")
    return _ok({"job": scheduler_jobs_store.row_to_public(row)})


def scheduler_job_set_archived(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    jid = _parse_uuid(arguments.get("job_id"), field="job_id")
    if jid is None:
        return _err("job_id UUID required")
    if "archived" not in arguments:
        return _err("archived boolean required")
    archived = bool(arguments.get("archived"))
    if archived:
        ok = scheduler_jobs_store.archive_job(job_id=jid, tenant_id=tenant_id, actor_user_id=uid, actor_is_admin=True)
    else:
        ok = scheduler_jobs_store.unarchive_job(job_id=jid, tenant_id=tenant_id, actor_user_id=uid, actor_is_admin=True)
    if not ok:
        return _err("job not found")
    row = scheduler_jobs_store.get_job(jid, tenant_id)
    return _ok({"job": scheduler_jobs_store.row_to_public(row or {})})


def scheduler_job_delete(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    jid = _parse_uuid(arguments.get("job_id"), field="job_id")
    if jid is None:
        return _err("job_id UUID required")
    ok = scheduler_jobs_store.hard_delete_job(job_id=jid, tenant_id=tenant_id, actor_user_id=uid, actor_is_admin=True)
    if not ok:
        return _err("job not found")
    return _ok({"deleted": True, "job_id": str(jid)})


def scheduler_presets_list(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    from apps.backend.core.config import PLUGINS_DIR

    root = PLUGINS_DIR / "schedules" / "presets"
    rows: list[dict[str, Any]] = []
    if root.is_dir():
        for p in sorted(root.glob("*.json")):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or "").strip()
            label = str(raw.get("label") or "").strip()
            if not pid or not label:
                continue
            job = raw.get("job")
            rows.append(
                {
                    "id": pid,
                    "label": label,
                    "description": str(raw.get("description") or "").strip(),
                    "job": job if isinstance(job, dict) else {},
                }
            )
    return _ok({"presets": rows})


# --- project runs ---


def project_runs_list(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    ws = _parse_uuid(arguments.get("dashboard_id"), field="dashboard_id")
    if arguments.get("dashboard_id") is not None and str(arguments.get("dashboard_id")).strip() and ws is None:
        return _err("invalid dashboard_id UUID")
    try:
        lim = int(arguments.get("limit", 50))
    except (TypeError, ValueError):
        lim = 50
    prid = str(arguments.get("project_row_id") or "").strip() or None
    rows = project_runs_store.list_runs(
        tenant_id=tenant_id,
        dashboard_id=ws,
        project_row_id=prid,
        limit=lim,
    )
    return _ok({"runs": [project_runs_store.row_to_public(r) for r in rows]})


def run_create(arguments: dict[str, Any]) -> str:
    g_adm = _require_admin()
    if isinstance(g_adm, str):
        return g_adm
    _tid, uid = g_adm
    tenant_id = db.user_tenant_id(uid)
    instructions = str(arguments.get("instructions") or "").strip()
    if not instructions:
        return _err("instructions is required")
    ws = _parse_uuid(arguments.get("dashboard_id"), field="dashboard_id")
    if arguments.get("dashboard_id") is not None and str(arguments.get("dashboard_id")).strip() and ws is None:
        return _err("invalid dashboard_id UUID")
    from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow

    wf_raw: dict[str, Any] = {}
    if isinstance(arguments.get("coding_workflow"), dict):
        wf_raw = dict(arguments["coding_workflow"])
    ws_arg = arguments.get("workspace_id")
    if ws_arg is not None and str(ws_arg).strip():
        wf_raw.setdefault("workspace_id", str(ws_arg).strip())
    try:
        coding_wf = normalize_coding_workflow(wf_raw, require_workspace=True)
    except (ValueError, TypeError) as e:
        return _err(str(e))
    row = project_runs_store.insert_run(
        tenant_id=tenant_id,
        created_by_user_id=uid,
        execution_user_id=uid,
        scheduler_job_id=None,
        dashboard_id=ws,
        project_row_id=str(arguments.get("project_row_id") or "").strip() or None,
        project_title=str(arguments.get("project_title") or "").strip() or None,
        execution_target="coding",
        instructions=instructions,
        coding_workflow=coding_wf,
    )
    if not row:
        return _err("failed to create run")
    return _ok({"run": project_runs_store.row_to_public(row)})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "settings_get": settings_get,
    "settings_patch": settings_patch,
    "interfaces_get": interfaces_get,
    "interfaces_put": interfaces_put,
    "external_llm_endpoints_get": external_llm_endpoints_get,
    "external_llm_endpoints_put": external_llm_endpoints_put,
    "external_llm_models_list": external_llm_models_list,
    "tenants_list": tenants_list,
    "tenant_create": tenant_create,
    "users_list": users_list,
    "user_create": user_create,
    "user_patch": user_patch,
    "tools_catalog": tools_catalog,
    "tool_policies_put": tool_policies_put,
    "reload_tools": reload_tools,
    "rag_ingest": rag_ingest,
    "rag_ingest_docs": rag_ingest_docs,
    "scheduler_job_list": scheduler_job_list,
    "scheduler_job_create": scheduler_job_create,
    "scheduler_job_patch": scheduler_job_patch,
    "scheduler_job_set_enabled": scheduler_job_set_enabled,
    "scheduler_job_set_archived": scheduler_job_set_archived,
    "scheduler_job_delete": scheduler_job_delete,
    "scheduler_presets_list": scheduler_presets_list,
    "project_runs_list": project_runs_list,
    "run_create": run_create,
}

for _name in HANDLERS:
    AGENT_TOOL_META_BY_NAME[_name] = {"min_role": "admin", "capabilities": _CAP}


def _tool_fn(name: str, desc: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "TOOL_DESCRIPTION": desc,
            "parameters": parameters,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool_fn(
        "settings_get",
        "Read masked operator_settings plus interface hints (admin).",
        {"type": "object", "properties": {}},
    ),
    _tool_fn(
        "settings_patch",
        "Partial update of operator_settings (OperatorSettingsPatch fields as top-level arguments).",
        operator_settings_patch_tool_parameters(),
    ),
    _tool_fn(
        "interfaces_get",
        "Read interface hints (Discord/Telegram application ids, agent_mode).",
        {"type": "object", "properties": {}},
    ),
    _tool_fn(
        "interfaces_put",
        "PUT interface hints: discord_application_id, telegram_application_id, agent_mode (sandbox|host).",
        {
            "type": "object",
            "properties": {
                "discord_application_id": {"type": "string"},
                "telegram_application_id": {"type": "string"},
                "agent_mode": {"type": "string", "enum": ["", "sandbox", "host"]},
            },
        },
    ),
    _tool_fn(
        "external_llm_endpoints_get",
        "List external LLM endpoints (api keys redacted).",
        {"type": "object", "properties": {}},
    ),
    _tool_fn(
        "external_llm_endpoints_put",
        "Replace all external LLM endpoints; body: {endpoints: [{id, sort_order, enabled, label, base_url, api_key, model_* ...}]}.",
        {"type": "object", "properties": {"endpoints": {"type": "array"}}, "required": ["endpoints"]},
    ),
    _tool_fn(
        "external_llm_models_list",
        "GET /v1/models from an external endpoint; optional base_url, api_key, endpoint_id.",
        {
            "type": "object",
            "properties": {
                "base_url": {"type": "string"},
                "api_key": {"type": "string"},
                "endpoint_id": {"type": "integer"},
            },
        },
    ),
    _tool_fn("tenants_list", "List tenants.", {"type": "object", "properties": {}}),
    _tool_fn(
        "tenant_create",
        "Create tenant; name (string).",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    ),
    _tool_fn("users_list", "List all users.", {"type": "object", "properties": {}}),
    _tool_fn(
        "user_create",
        "Create user: email, password, role (user|admin), tenant_id.",
        {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "password": {"type": "string"},
                "role": {"type": "string", "enum": ["user", "admin"]},
                "tenant_id": {"type": "integer"},
            },
            "required": ["email", "password"],
        },
    ),
    _tool_fn(
        "user_patch",
        "Patch user: user_id (UUID), optional tenant_id, workspace_quota, workspace_self_allowed.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "tenant_id": {"type": "integer"},
                "workspace_quota": {"type": "integer"},
                "workspace_self_allowed": {"type": "boolean"},
            },
            "required": ["user_id"],
        },
    ),
    _tool_fn("tools_catalog", "Tool metadata + operator policy rows.", {"type": "object", "properties": {}}),
    _tool_fn(
        "tool_policies_put",
        "Replace tool policies: {policies: [{package_id, tool_name, enabled, min_role, allowed_tenant_ids, execution_context}]}.",
        {"type": "object", "properties": {"policies": {"type": "array"}}, "required": ["policies"]},
    ),
    _tool_fn(
        "reload_tools",
        "Rescan tool plugins; optional scope all|extra (default all).",
        {"type": "object", "properties": {"scope": {"type": "string", "enum": ["all", "extra"]}}},
    ),
    _tool_fn(
        "rag_ingest",
        "Ingest one text into RAG: text (required), optional domain, title, source_uri.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "domain": {"type": "string"},
                "title": {"type": "string"},
                "source_uri": {"type": "string"},
            },
            "required": ["text"],
        },
    ),
    _tool_fn(
        "rag_ingest_docs",
        "Ingest markdown tree: optional docs_root, domain (default agentlayer_docs), purge_first (default false), incremental (default true).",
        {
            "type": "object",
            "properties": {
                "docs_root": {"type": "string"},
                "domain": {"type": "string"},
                "purge_first": {"type": "boolean"},
                "incremental": {"type": "boolean"},
            },
        },
    ),
    _tool_fn(
        "scheduler_job_list",
        "Admin list scheduler_jobs: optional dashboard_id, include_global, include_archived, execution_target, enabled, limit.",
        {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "include_global": {"type": "boolean"},
                "include_archived": {"type": "boolean"},
                "execution_target": {"type": "string"},
                "enabled": {"type": "boolean"},
                "limit": {"type": "integer"},
            },
        },
    ),
    _tool_fn(
        "scheduler_job_create",
        "Create scheduler job (admin): execution_target, instructions, optional title, dashboard_id, interval_minutes, enabled, workspace_id, coding_workflow.",
        {
            "type": "object",
            "properties": {
                "execution_target": {"type": "string"},
                "instructions": {"type": "string"},
                "title": {"type": "string"},
                "dashboard_id": {"type": "string"},
                "interval_minutes": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "workspace_id": {"type": "string"},
                "coding_workflow": {"type": "object"},
            },
            "required": ["execution_target", "instructions"],
        },
    ),
    _tool_fn(
        "scheduler_job_patch",
        "Patch job by job_id: optional title, instructions, interval_minutes, coding_workflow.",
        {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "title": {"type": "string"},
                "instructions": {"type": "string"},
                "interval_minutes": {"type": "integer"},
                "coding_workflow": {"type": "object"},
            },
            "required": ["job_id"],
        },
    ),
    _tool_fn(
        "scheduler_job_set_enabled",
        "Enable/disable job: job_id, enabled.",
        {
            "type": "object",
            "properties": {"job_id": {"type": "string"}, "enabled": {"type": "boolean"}},
            "required": ["job_id", "enabled"],
        },
    ),
    _tool_fn(
        "scheduler_job_set_archived",
        "Archive (soft-delete) or unarchive: job_id, archived.",
        {
            "type": "object",
            "properties": {"job_id": {"type": "string"}, "archived": {"type": "boolean"}},
            "required": ["job_id", "archived"],
        },
    ),
    _tool_fn(
        "scheduler_job_delete",
        "Hard-delete scheduler job by job_id.",
        {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    ),
    _tool_fn(
        "scheduler_presets_list",
        "List built-in scheduler job presets from plugins/schedules/presets.",
        {"type": "object", "properties": {}},
    ),
    _tool_fn(
        "project_runs_list",
        "List project runs: optional dashboard_id, project_row_id, limit.",
        {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string"},
                "project_row_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    ),
    _tool_fn(
        "run_create",
        "Enqueue coding project run (execution_target=coding): instructions, workspace_id; optional dashboard_id, project_row_id, project_title, coding_workflow.",
        {
            "type": "object",
            "properties": {
                "instructions": {"type": "string"},
                "workspace_id": {"type": "string"},
                "dashboard_id": {"type": "string"},
                "project_row_id": {"type": "string"},
                "project_title": {"type": "string"},
                "coding_workflow": {"type": "object"},
            },
            "required": ["instructions", "workspace_id"],
        },
    ),
]
