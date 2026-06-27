"""Client-facing HTTP error strings: avoid leaking internal exception text by default.

Runtime toggles for this belong in ``operator_settings`` (``PATCH /v1/admin/operator-settings``),
not new ``AGENT_*`` environment variables — env is legacy bootstrap only.
"""

from __future__ import annotations

from apps.backend.infrastructure.settings import operator_settings


def http_500_detail(exc: BaseException | None = None) -> str:
    """Detail body for HTTP 500. Generic unless operator enables ``expose_internal_errors``."""
    if operator_settings.expose_internal_errors_in_responses() and exc is not None:
        return str(exc)
    return "Internal server error"
