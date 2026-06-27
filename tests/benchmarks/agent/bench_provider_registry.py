"""Register bench-only LLM endpoints via Admin API (no server .env changes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from tests.benchmarks.agent.bench_profiles import BenchModelProfile
from tests.e2e.support.helpers import E2EClient

def catalog_owned_by_for_endpoint_id(endpoint_id: int) -> str:
    return f"provider_db_{int(endpoint_id)}"


def _bench_endpoint_label(run_id: str, profile_label: str) -> str:
    safe = profile_label.replace(" ", "-")[:48]
    return f"bench-{run_id}-{safe}"


def _row_for_put(endpoint: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "sort_order": int(endpoint.get("sort_order") or 0),
        "enabled": bool(endpoint.get("enabled", True)),
        "label": str(endpoint.get("label") or ""),
        "base_url": str(endpoint.get("base_url") or "").strip(),
        "model_default": endpoint.get("model_default"),
        "model_vlm": endpoint.get("model_vlm"),
        "model_agent": endpoint.get("model_agent"),
        "model_coding": endpoint.get("model_coding"),
    }
    header = endpoint.get("api_header_name")
    if isinstance(header, str) and header.strip():
        row["api_header_name"] = header.strip()
    if include_id and endpoint.get("id") is not None:
        row["id"] = int(endpoint["id"])
    api_key = endpoint.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        row["api_key"] = api_key.strip()
    return row


@dataclass
class BenchProviderRegistry:
    """Snapshot of admin endpoints before bench registration (for restore)."""

    snapshot: list[dict[str, Any]]

    def restore(self, client: E2EClient) -> None:
        if client.role != "admin":
            return
        rows = [_row_for_put(e, include_id=e.get("id") is not None) for e in self.snapshot]
        client.http.put("/v1/admin/external-llm/endpoints", json={"endpoints": rows})


def register_bench_llm_providers(
    client: E2EClient,
    profiles: list[BenchModelProfile],
    *,
    run_id: str,
) -> tuple[list[BenchModelProfile], BenchProviderRegistry | None]:
    """
    Profiles with ``base_url`` are registered as temporary Admin LLM endpoints.

    Returns resolved profiles (``catalog_owned_by`` set to ``provider_db_<id>``) and
    a registry handle to restore prior endpoints on cleanup.
    """
    needs_register = [p for p in profiles if p.base_url]
    if not needs_register:
        return profiles, None

    if client.role != "admin":
        raise RuntimeError(
            "AGENT_BENCH_LLM_*_BASE_URL requires admin login to register temporary LLM endpoints"
        )

    try:
        before = client.get_json("/v1/admin/external-llm/endpoints")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"cannot list admin LLM endpoints: {exc}") from exc

    existing = before.get("endpoints") or []
    if not isinstance(existing, list):
        existing = []

    snapshot = [dict(e) for e in existing if isinstance(e, dict)]
    max_sort = max((int(e.get("sort_order") or 0) for e in existing), default=0)

    put_rows = [_row_for_put(e, include_id=True) for e in existing]
    label_by_profile: dict[str, str] = {}

    for i, prof in enumerate(needs_register):
        label = _bench_endpoint_label(run_id, prof.label)
        label_by_profile[prof.label] = label
        row: dict[str, Any] = {
            "sort_order": max_sort + 100 + i,
            "enabled": True,
            "label": label,
            "base_url": prof.base_url.strip().rstrip("/"),
            "model_default": prof.model or None,
        }
        if prof.api_key:
            row["api_key"] = prof.api_key
        if prof.api_header_name:
            row["api_header_name"] = prof.api_header_name
        elif prof.api_key:
            row["api_header_name"] = "Authorization"
        put_rows.append(row)

    resp = client.http.put("/v1/admin/external-llm/endpoints", json={"endpoints": put_rows})
    if resp.status_code >= 400:
        raise RuntimeError(f"register bench LLM endpoints failed: HTTP {resp.status_code} {resp.text[:400]}")

    after = client.get_json("/v1/admin/external-llm/endpoints")
    endpoints_after = after.get("endpoints") or []
    id_by_label = {
        str(e.get("label") or ""): int(e["id"])
        for e in endpoints_after
        if isinstance(e, dict) and e.get("id") is not None
    }

    resolved: list[BenchModelProfile] = []
    for prof in profiles:
        if not prof.base_url:
            resolved.append(prof)
            continue
        bench_label = label_by_profile.get(prof.label)
        if not bench_label or bench_label not in id_by_label:
            raise RuntimeError(f"bench endpoint not found after register: {prof.label!r}")
        eid = id_by_label[bench_label]
        resolved.append(
            BenchModelProfile(
                label=prof.label,
                catalog_owned_by=catalog_owned_by_for_endpoint_id(eid),
                model=prof.model,
                agent_id=prof.agent_id,
                base_url=prof.base_url,
                api_key=prof.api_key,
                api_header_name=prof.api_header_name,
            )
        )

    return resolved, BenchProviderRegistry(snapshot=snapshot)
