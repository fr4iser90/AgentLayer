"""Match per-model harness override rows (exact model, then provider-wide)."""

from __future__ import annotations

from typing import Any


def match_model_override(
    rows: list[dict[str, Any]],
    *,
    catalog_owned_by: str,
    model: str,
) -> tuple[dict[str, Any] | None, str]:
    """Return ``(row, source)`` — source is ``model_db_override`` or ``provider_db_override``."""
    catalog = str(catalog_owned_by or "").strip()
    model_id = str(model or "").strip()
    if not catalog:
        return None, "global"

    exact: dict[str, Any] | None = None
    provider_only: dict[str, Any] | None = None
    for row in rows:
        row_catalog = str(row.get("catalog_owned_by") or "").strip()
        row_model = str(row.get("model") or "").strip()
        if row_catalog != catalog:
            continue
        if row_model and row_model == model_id:
            exact = row
            break
        if not row_model and provider_only is None:
            provider_only = row
    if exact is not None:
        return exact, "model_db_override"
    if provider_only is not None:
        return provider_only, "provider_db_override"
    return None, "global"
