from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreparedChatRequest:
    plain_completion: bool
    stream_llm_ws: bool
    extra_cats_body: frozenset[str]
    extra_cats_hdr: frozenset[str]
    cap_hints: frozenset[str]
    tool_domain: str | None
    capability_confirm_token: Any
    dashboard_ctx: Any
    agent_storage_images: list[dict[str, Any]]
    raw_max_rounds: Any
    raw_llm_backend: Any
    catalog_owned_by: str | None
    raw_tool_allowlist: Any
    tools_ranking_enabled: bool
    agent_id: str | None
    parent_agent_run_id: str | None
    pre_run_id: Any
    active_task_body: Any
    permission_ask: bool
    agent_unattended: bool
    tools_full_schema: bool
    agent_require_workspace_verify: bool
    agent_delegate_mode: str | None
    delegate_allowed_paths: list[str] | None
    delegate_required_branch: str | None
    handoff_collector: Any
    harness_profile_token: Any = None
    parent_cancel_bridge_task: asyncio.Task[None] | None = None
