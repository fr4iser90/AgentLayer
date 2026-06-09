"""Delete E2E / IDOR test sandboxes (conversations, dashboards, workspaces)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tests.e2e.support.helpers import E2EClient

# New resources use this prefix; legacy IDOR tests used bare "IDOR …" titles.
E2E_IDOR_PREFIX = "[E2E IDOR]"

_LEGACY_CONV_TITLE = re.compile(r"^IDOR conv [0-9a-f]{8}$", re.I)
_LEGACY_EDITOR_PATCH = re.compile(r"^IDOR editor patch [0-9a-f]{8}(-edited)?$", re.I)


def _is_e2e_idor_conversation_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    if t.startswith(E2E_IDOR_PREFIX):
        return True
    return bool(_LEGACY_CONV_TITLE.match(t))


def _is_e2e_idor_dashboard_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    if t.startswith(E2E_IDOR_PREFIX):
        return True
    if _LEGACY_EDITOR_PATCH.match(t):
        return True
    return t.startswith("IDOR ")


def _is_e2e_idor_workspace_name(name: str) -> bool:
    n = (name or "").strip()
    return n.startswith("e2e-idor-ws-")


def _delete_ok(resp: Any) -> bool:
    return getattr(resp, "status_code", 0) in (200, 204, 404)


@dataclass
class CleanupStats:
    conversations: int = 0
    dashboards: int = 0
    workspaces: int = 0


@dataclass
class E2EResourceTracker:
    """Track resources created in one E2E test; delete them in ``cleanup()``."""

    client: E2EClient
    conversation_ids: list[str] = field(default_factory=list)
    dashboard_ids: list[str] = field(default_factory=list)
    workspace_ids: list[str] = field(default_factory=list)
    secret_service_keys: list[str] = field(default_factory=list)

    def track_conversation(self, conversation_id: str) -> str:
        cid = str(conversation_id or "").strip()
        if cid:
            self.conversation_ids.append(cid)
        return cid

    def track_dashboard(self, dashboard_id: str) -> str:
        did = str(dashboard_id or "").strip()
        if did:
            self.dashboard_ids.append(did)
        return did

    def track_workspace(self, workspace_id: str) -> str:
        wid = str(workspace_id or "").strip()
        if wid:
            self.workspace_ids.append(wid)
        return wid

    def track_secret(self, service_key: str) -> str:
        sk = str(service_key or "").strip().lower()
        if sk:
            self.secret_service_keys.append(sk)
        return sk

    def cleanup(self) -> CleanupStats:
        stats = CleanupStats()
        for cid in self.conversation_ids:
            if _delete_ok(self.client.http.delete(f"/v1/user/conversations/{cid}")):
                stats.conversations += 1
        for did in self.dashboard_ids:
            if _delete_ok(self.client.http.delete(f"/v1/dashboards/{did}")):
                stats.dashboards += 1
        for wid in self.workspace_ids:
            if _delete_ok(self.client.http.delete(f"/v1/workspaces/{wid}")):
                stats.workspaces += 1
        for sk in self.secret_service_keys:
            if _delete_ok(self.client.http.delete(f"/v1/user/secrets/{sk}")):
                pass
        self.conversation_ids.clear()
        self.dashboard_ids.clear()
        self.workspace_ids.clear()
        self.secret_service_keys.clear()
        return stats


def cleanup_idor_orphans(
    client: E2EClient,
    *,
    dry_run: bool = False,
) -> CleanupStats:
    """Remove leftover IDOR/E2E resources (legacy titles + new ``[E2E IDOR]`` prefix)."""
    stats = CleanupStats()

    conv_data = client.get_json("/v1/user/conversations")
    rows: list[Any] = conv_data.get("conversations") or conv_data.get("items") or []
    for conv in rows:
        if not isinstance(conv, dict):
            continue
        title = str(conv.get("title") or "")
        cid = str(conv.get("id") or "")
        if not cid or not _is_e2e_idor_conversation_title(title):
            continue
        if dry_run:
            stats.conversations += 1
            continue
        if _delete_ok(client.http.delete(f"/v1/user/conversations/{cid}")):
            stats.conversations += 1

    dash_data = client.get_json("/v1/dashboards")
    for dash in dash_data.get("dashboards") or []:
        if not isinstance(dash, dict):
            continue
        title = str(dash.get("title") or dash.get("name") or "")
        did = str(dash.get("id") or "")
        if not did or not _is_e2e_idor_dashboard_title(title):
            continue
        if dry_run:
            stats.dashboards += 1
            continue
        if _delete_ok(client.http.delete(f"/v1/dashboards/{did}")):
            stats.dashboards += 1

    ws_data = client.get_json("/v1/workspaces")
    for ws in ws_data.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        name = str(ws.get("name") or "")
        wid = str(ws.get("id") or "")
        if not wid or not _is_e2e_idor_workspace_name(name):
            continue
        if dry_run:
            stats.workspaces += 1
            continue
        if _delete_ok(client.http.delete(f"/v1/workspaces/{wid}")):
            stats.workspaces += 1

    return stats
