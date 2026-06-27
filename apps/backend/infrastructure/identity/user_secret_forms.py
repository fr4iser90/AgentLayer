"""Resolve ``TOOL_USER_SECRET_FORMS`` for a ``service_key`` from the tool registry."""

from __future__ import annotations

from typing import Any


def form_spec_for_service_key(service_key: str) -> dict[str, Any] | None:
    """Return merged UI form spec for ``service_key``, or None."""
    sk = (service_key or "").strip().lower()
    if not sk:
        return None
    try:
        from apps.backend.domain.plugin_system.registry import get_registry

        for row in get_registry().tools_meta:
            forms = row.get("user_secret_forms") or {}
            if not isinstance(forms, dict):
                continue
            spec = forms.get(sk)
            if isinstance(spec, dict) and spec:
                return dict(spec)
    except Exception:
        return None
    return None
