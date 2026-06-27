"""Effective model and provider capability access policies."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.model_catalog_providers import normalize_catalog_provider_id

AccessState = str

POLICY_SCOPES = {"global", "tenant", "user"}
MODEL_PROFILES = {"default", "agent", "coding", "vlm", "embedding", "extractor", "stt", "tts"}
PROVIDER_CAPABILITIES = {"chat", "embedding", "extractor", "stt", "tts", "voice_realtime"}


def normalize_policy_scope(scope: str) -> str:
    s = (scope or "").strip().lower()
    if s not in POLICY_SCOPES:
        raise ValueError("invalid policy scope")
    return s


def normalize_policy_target(
    scope: str,
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | str | None = None,
) -> tuple[str, int | None, uuid.UUID | None]:
    s = normalize_policy_scope(scope)
    if s == "global":
        return s, None, None
    if s == "tenant":
        if tenant_id is None or int(tenant_id) < 1:
            raise ValueError("tenant_id required")
        return s, int(tenant_id), None
    if user_id is None:
        raise ValueError("user_id required")
    uid = uuid.UUID(str(user_id))
    return s, tenant_id if tenant_id is not None else None, uid


def normalize_access_state(raw: Any) -> AccessState:
    state = str(raw or "inherit").strip().lower()
    if state not in {"inherit", "allow", "deny"}:
        raise ValueError(f"invalid access_state {state!r}")
    return state


def _row_key(row: dict[str, Any]) -> tuple[str, str] | None:
    provider_id = normalize_catalog_provider_id(row.get("provider_id"))
    model_id = str(row.get("model_id") or "").strip()
    if not provider_id or not model_id:
        return None
    return provider_id, model_id


def effective_model_access_index(
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> dict[tuple[str, str], bool]:
    """Effective model allowlist: absent row means allowed."""
    out: dict[tuple[str, str], bool] = {}
    for row in db.model_access_policies_for_subject(int(tenant_id), user_id):
        key = _row_key(row)
        if key is None:
            continue
        state = normalize_access_state(row.get("access_state"))
        if state == "inherit":
            continue
        out[key] = state == "allow"
    return out


def is_model_allowed(
    provider_id: str,
    model_id: str,
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> bool:
    provider = normalize_catalog_provider_id(provider_id)
    model = str(model_id or "").strip()
    if not provider or not model:
        return False
    access = effective_model_access_index(tenant_id=tenant_id, user_id=user_id)
    if access.get((provider, model), True) is False:
        return False
    if not is_provider_capability_allowed(
        "chat",
        provider,
        tenant_id=tenant_id,
        user_id=user_id,
    ):
        return False
    return True


def filter_catalog_rows_for_user(
    rows: list[dict[str, Any]],
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    access = effective_model_access_index(tenant_id=tenant_id, user_id=user_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        provider_id = normalize_catalog_provider_id(row.get("owned_by"))
        model_id = str(row.get("id") or "").strip()
        if not provider_id or not model_id:
            continue
        if access.get((provider_id, model_id), True) is False:
            continue
        if not is_provider_capability_allowed("chat", provider_id, tenant_id=tenant_id, user_id=user_id):
            continue
        out.append(row)
    return out


def effective_model_defaults(
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> dict[str, dict[str, str]]:
    """Profile -> {provider_id, model_id}, resolved by global < tenant < user order."""
    out: dict[str, dict[str, str]] = {}
    for row in db.model_default_policies_for_subject(int(tenant_id), user_id):
        profile = str(row.get("profile") or "").strip().lower()
        if profile not in MODEL_PROFILES:
            continue
        provider_id = normalize_catalog_provider_id(row.get("provider_id"))
        model_id = str(row.get("model_id") or "").strip()
        if provider_id and model_id:
            out[profile] = {"provider_id": provider_id, "model_id": model_id}
    return out


def effective_provider_capability_index(
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> dict[tuple[str, str], bool]:
    """(capability, provider_id) -> allowed; absent row means allowed."""
    out: dict[tuple[str, str], bool] = {}
    for row in db.provider_capability_policies_for_subject(int(tenant_id), user_id):
        capability = str(row.get("capability") or "").strip().lower()
        provider_id = normalize_catalog_provider_id(row.get("provider_id"))
        if capability not in PROVIDER_CAPABILITIES or not provider_id:
            continue
        state = normalize_access_state(row.get("access_state"))
        if state == "inherit":
            continue
        out[(capability, provider_id)] = state == "allow"
    return out


def is_provider_capability_allowed(
    capability: str,
    provider_id: str,
    *,
    tenant_id: int,
    user_id: uuid.UUID | str,
) -> bool:
    cap = str(capability or "").strip().lower()
    provider = normalize_catalog_provider_id(provider_id)
    if cap not in PROVIDER_CAPABILITIES or not provider:
        return False
    access = effective_provider_capability_index(tenant_id=tenant_id, user_id=user_id)
    return access.get((cap, provider), True) is not False


def effective_policy_preview(
    *,
    scope: str,
    tenant_id: int | None = None,
    user_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Admin preview for one scope target."""
    s, tid, uid = normalize_policy_target(scope, tenant_id=tenant_id, user_id=user_id)
    default_model_access_state = "allow" if s == "global" else "inherit"
    default_provider_capability_state = "allow" if s == "global" else "inherit"
    if s == "global":
        access_rows = db.model_access_policies_list("global")
        default_rows = db.model_default_policies_list("global")
        capability_rows = db.provider_capability_policies_list("global")
        return {
            "scope": s,
            "default_model_access_state": default_model_access_state,
            "default_provider_capability_state": default_provider_capability_state,
            "model_access": access_rows,
            "model_defaults": default_rows,
            "provider_capabilities": capability_rows,
            "effective": {
                "model_access": access_rows,
                "model_defaults": default_rows,
                "provider_capabilities": capability_rows,
            },
        }
    if s == "tenant":
        access_rows = db.model_access_policies_list("tenant", tenant_id=tid)
        default_rows = db.model_default_policies_list("tenant", tenant_id=tid)
        capability_rows = db.provider_capability_policies_list("tenant", tenant_id=tid)
        return {
            "scope": s,
            "tenant_id": tid,
            "default_model_access_state": default_model_access_state,
            "default_provider_capability_state": default_provider_capability_state,
            "model_access": access_rows,
            "model_defaults": default_rows,
            "provider_capabilities": capability_rows,
            "effective": {
                "model_access": db.model_access_policies_list("global") + access_rows,
                "model_defaults": db.model_default_policies_list("global") + default_rows,
                "provider_capabilities": db.provider_capability_policies_list("global") + capability_rows,
            },
        }
    assert uid is not None
    if tid is None:
        tid = db.user_tenant_id(uid)
    access_rows = db.model_access_policies_list("user", user_id=uid)
    default_rows = db.model_default_policies_list("user", user_id=uid)
    capability_rows = db.provider_capability_policies_list("user", user_id=uid)
    return {
        "scope": s,
        "tenant_id": tid,
        "user_id": str(uid),
        "default_model_access_state": default_model_access_state,
        "default_provider_capability_state": default_provider_capability_state,
        "model_access": access_rows,
        "model_defaults": default_rows,
        "provider_capabilities": capability_rows,
        "effective": {
            "model_access": db.model_access_policies_for_subject(tid, uid),
            "model_defaults": db.model_default_policies_for_subject(tid, uid),
            "provider_capabilities": db.provider_capability_policies_for_subject(tid, uid),
        },
    }
