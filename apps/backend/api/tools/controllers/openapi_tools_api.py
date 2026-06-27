from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.identity.use_cases.request_auth import (
    LoginRequest,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_for_bearer_token,
    list_all_users,
    require_admin,
    revoke_refresh_token,
    update_user_tenant,
    validate_refresh_token,
    verify_password,
)
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.platform.use_cases.platform_controller_services import http_500_detail
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.domain.tools.invocation_context import bind_capability_confirmed, reset_capability_confirmed

router = APIRouter()
logger = logging.getLogger(__name__)

def _generate_openapi_spec(title: str, tool_filter=None):
    reg = get_registry()
    
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": title,
            "version": "0.7.0"
        },
        "paths": {},
        "components": {
            "schemas": {}
        }
    }
    
    for tool_spec in reg.chat_tool_specs:
        fn = tool_spec.get("function", {})
        name = fn.get("name")
        if not name:
            continue
            
        if tool_filter and name not in tool_filter:
            continue
            
        description = fn.get("TOOL_DESCRIPTION", fn.get("description", ""))
        parameters = fn.get("parameters", {})
        
        spec["paths"][f"/{name}"] = {
            "post": {
                "summary": description,
                "operationId": name,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": parameters
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Tool execution result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "result": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    return spec


@router.get("/openapi.json")
async def openapi_spec_all():
    """OpenAPI 3.0 Specification (all tools)"""
    return _generate_openapi_spec("Jetpack Agent Layer All Tools")


@router.get("/openapi/{domain}/openapi.json")
async def openapi_spec_domain(domain: str):
    """OpenAPI 3.0 Specification filtered by tool domain"""
    reg = get_registry()
    domain_tools = []
    
    for meta in reg.tools_meta:
        if meta.get("domain") == domain:
            domain_tools.extend(meta.get("tools", []))
    
    if not domain_tools:
        raise HTTPException(status_code=404, detail="domain not found")
        
    return _generate_openapi_spec(f"Jetpack Agent: {domain}", tool_filter=domain_tools)


@router.get("/openapi/{domain}.json")
async def openapi_spec_domain_legacy(domain: str):
    return await openapi_spec_domain(domain)


@router.get("/openapi/tool/{tool_name}/openapi.json")
async def openapi_spec_single_tool(tool_name: str):
    """OpenAPI 3.0 Specification for a single individual tool"""
    return _generate_openapi_spec(f"Jetpack Agent: {tool_name}", tool_filter=[tool_name])


@router.get("/openapi/domains")
async def list_openapi_domains():
    """List available tool domains for separate OpenAPI endpoints"""
    reg = get_registry()
    domains = {}
    
    for meta in reg.tools_meta:
        domain = meta.get("domain")
        if domain:
            if domain not in domains:
                domains[domain] = []
            domains[domain].extend(meta.get("tools", []))
    
    result = []
    for domain, tools in domains.items():
        result.append({
            "domain": domain,
            "tool_count": len(tools),
            "openapi_url": f"/openapi/{domain}.json"
        })
    
    return {"domains": result}


def _merge_capability_confirm(request: Request, body_confirm: Any) -> frozenset[str]:
    """Header X-Agent-Capability-Confirm (comma) ∪ JSON ``agent_capability_confirm`` (body route only)."""
    raw = (request.headers.get("X-Agent-Capability-Confirm") or "").strip()
    hdr: frozenset[str] = frozenset()
    if raw:
        hdr = frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return hdr | parse_user_capability_confirm(body_confirm)


@router.post("/{tool_name}")
async def run_tool_direct(tool_name: str, request: Request):
    """Direct tool execution endpoint (Open WebUI calls this directly per tool)"""
    try:
        arguments = await request.json()
    except Exception:
        arguments = {}
    
    from apps.backend.domain.plugin_system.tools import run_tool
    
    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)
    _cf_tok = bind_capability_confirmed(_merge_capability_confirm(request, None))

    try:
        result = run_tool(tool_name, arguments)
        return {
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Direct tool execution failed for {tool_name}")
        raise HTTPException(status_code=500, detail=http_500_detail(e))
    finally:
        reset_capability_confirmed(_cf_tok)
        reset_identity(id_token)


@router.post("/tools/run")
async def run_tool_openwebui(request: Request):
    """Generic tool execution endpoint for Open WebUI Tool Server"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    
    tool_name = body.get("name")
    arguments = body.get("arguments", {})
    body_confirm = body.get("agent_capability_confirm")

    if not tool_name:
        raise HTTPException(status_code=400, detail="missing tool name")
    
    from apps.backend.domain.plugin_system.tools import run_tool
    
    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)
    _cf_tok = bind_capability_confirmed(_merge_capability_confirm(request, body_confirm))

    try:
        result = run_tool(tool_name, arguments)
        return {
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Open WebUI tool execution failed for {tool_name}")
        raise HTTPException(status_code=500, detail=http_500_detail(e))
    finally:
        reset_capability_confirmed(_cf_tok)
        reset_identity(id_token)

