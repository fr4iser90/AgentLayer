"""HTTP + WebSocket access to AgentLayer.

One turn is one ``{"type":"chat"}`` message on a long-lived socket; the socket stays open
across turns so ``cancel`` and ``permission_reply`` have somewhere to go.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import websockets

from .config import Settings


class AgentLayerError(RuntimeError):
    pass


def resolve_default_model(rows: list[dict[str, Any]], providers: dict[str, Any]) -> str:
    """Pick a model when none is configured.

    ``POST /v1/chat/completions`` rejects a request with no model ("No LLM catalog provider
    for this request"), and the server does not publish its own default, so the client has to
    choose. Prefer a model whose provider reports ``reachable``; otherwise take the first.
    """
    reachable = {
        name
        for name, meta in providers.items()
        if isinstance(meta, dict) and meta.get("reachable")
    }
    for row in rows:
        model_id = str(row.get("id") or "").strip()
        if model_id and str(row.get("owned_by") or "") in reachable:
            return model_id
    for row in rows:
        model_id = str(row.get("id") or "").strip()
        if model_id:
            return model_id
    return ""


class RestClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._http = httpx.AsyncClient(base_url=settings.base_url, timeout=60.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._s.api_key}"} if self._s.api_key else {}

    async def _get(self, path: str, **params: Any) -> Any:
        r = await self._http.get(path, headers=self._headers, params=params or None)
        if r.status_code == 401:
            raise AgentLayerError("unauthorised — check the API key")
        r.raise_for_status()
        return r.json()

    async def login(self, email: str, password: str) -> str:
        r = await self._http.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            raise AgentLayerError(f"login failed (HTTP {r.status_code})")
        token = (r.json() or {}).get("access_token")
        if not token:
            raise AgentLayerError("login returned no access token")
        return str(token)

    async def mint_api_key(self, access_token: str, name: str) -> str:
        """Uses the JWT on purpose: minting with an API key is refused by design."""
        r = await self._http.post(
            "/v1/user/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"name": name},
        )
        if r.status_code != 200:
            raise AgentLayerError(f"could not mint an API key (HTTP {r.status_code})")
        key = (r.json() or {}).get("api_key")
        if not key:
            raise AgentLayerError("mint response carried no key")
        return str(key)

    async def list_api_keys(self, access_token: str) -> list[dict[str, Any]]:
        r = await self._http.get(
            "/v1/user/api-keys", headers={"Authorization": f"Bearer {access_token}"}
        )
        if r.status_code != 200:
            return []
        rows = (r.json() or {}).get("api_keys")
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []

    async def revoke_api_key(self, access_token: str, key_id: str) -> bool:
        """Needs the JWT: revoking with an API key is refused (see ADR 0008)."""
        r = await self._http.delete(
            f"/v1/user/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return r.status_code == 200

    async def agents(self) -> list[dict[str, Any]]:
        data = await self._get("/v1/agents")
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)]
        rows = data.get("agents") if isinstance(data, dict) else None
        return [a for a in rows if isinstance(a, dict)] if isinstance(rows, list) else []

    async def models(self) -> list[dict[str, Any]]:
        rows, _ = await self.models_with_providers()
        return rows

    async def models_with_providers(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """``/v1/models`` also reports per-provider reachability under ``agentlayer``."""
        data = await self._get("/v1/models")
        raw = data.get("data") if isinstance(data, dict) else data
        rows = [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []
        providers = data.get("agentlayer") if isinstance(data, dict) else None
        return rows, providers if isinstance(providers, dict) else {}

    async def default_model(self) -> str:
        rows, providers = await self.models_with_providers()
        return resolve_default_model(rows, providers)

    async def runtime(self, *, model: str = "", conversation_id: str = "") -> dict[str, Any]:
        params = {k: v for k, v in (("model", model), ("conversation_id", conversation_id)) if v}
        data = await self._get("/v1/chat/runtime", **params)
        return data if isinstance(data, dict) else {}

    async def workspaces(self) -> list[dict[str, Any]]:
        data = await self._get("/v1/workspaces")
        rows = data.get("workspaces") if isinstance(data, dict) else None
        return [w for w in rows if isinstance(w, dict)] if isinstance(rows, list) else []

    async def create_workspace(
        self, name: str, *, git_url: str = "", git_branch: str = "main"
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "source": "git" if git_url else "manual",
            "git_branch": git_branch or "main",
        }
        if git_url:
            payload["git_url"] = git_url
        r = await self._http.post("/v1/workspaces", headers=self._headers, json=payload)
        if r.status_code == 400:
            raise AgentLayerError(str((r.json() or {}).get("detail") or "invalid workspace"))
        r.raise_for_status()
        row = (r.json() or {}).get("workspace")
        return row if isinstance(row, dict) else {}

    async def bind_workspace(self, conversation_id: str, workspace_id: str | None) -> bool:
        """Binding is a conversation preference (``pref_workspace_id``); omitted fields on this
        PUT are skipped, so the title and messages survive."""
        r = await self._http.put(
            f"/v1/user/conversations/{conversation_id}",
            headers=self._headers,
            json={"workspace_id": workspace_id},
        )
        return r.status_code == 200

    async def index_workspace(self, workspace_id: str, mode: str = "full") -> dict[str, Any]:
        r = await self._http.post(
            f"/v1/workspaces/{workspace_id}/index",
            headers=self._headers,
            json={"mode": mode},
        )
        if r.status_code == 400:
            raise AgentLayerError(str((r.json() or {}).get("detail") or "indexing refused"))
        if r.status_code == 404:
            raise AgentLayerError("workspace not found or not editable")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}

    async def index_status(self, workspace_id: str) -> dict[str, Any]:
        data = await self._get(f"/v1/workspaces/{workspace_id}/index/status")
        return data if isinstance(data, dict) else {}

    async def conversations(self) -> list[dict[str, Any]]:
        data = await self._get("/v1/user/conversations")
        rows = data.get("conversations") if isinstance(data, dict) else data
        return [c for c in rows if isinstance(c, dict)] if isinstance(rows, list) else []

    async def create_conversation(
        self, title: str, *, agent_id: str = "", workspace_id: str = ""
    ) -> str:
        """Returns the new conversation id — goal/todo tools refuse to run without one."""
        payload: dict[str, Any] = {"title": title, "mode": "agent"}
        if agent_id:
            payload["agent_id"] = agent_id
        if workspace_id:
            payload["workspace_id"] = workspace_id
        r = await self._http.post("/v1/user/conversations", headers=self._headers, json=payload)
        if r.status_code == 401:
            raise AgentLayerError("unauthorised — check the API key")
        r.raise_for_status()
        data = r.json()
        row = data.get("conversation") if isinstance(data, dict) else None
        cid = row.get("id") if isinstance(row, dict) else None
        if not cid:
            raise AgentLayerError("conversation was created but carried no id")
        return str(cid)


class ChatSocket:
    """Thin wrapper: ``send_*`` for control messages, ``events()`` to consume the stream."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._ws: Any = None

    async def connect(self) -> None:
        """Ping right away: a good token answers ``pong``, a bad one gets an error frame + 4401."""
        url = f"{self._s.ws_url}?token={self._s.api_key}"
        try:
            self._ws = await websockets.connect(url, open_timeout=20, max_size=16 * 1024 * 1024)
        except Exception as e:  # noqa: BLE001 — surfaced verbatim in the UI
            raise AgentLayerError(f"cannot reach {self._s.ws_url}: {e}") from e
        try:
            await self.send_ping()
            reply = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=20))
        except Exception as e:  # noqa: BLE001
            await self.close()
            raise AgentLayerError(f"handshake failed: {e}") from e
        if not isinstance(reply, dict) or reply.get("type") != "pong":
            detail = reply.get("detail") if isinstance(reply, dict) else None
            await self.close()
            raise AgentLayerError(str(detail or "unauthorised"))

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise AgentLayerError("not connected")
        await self._ws.send(json.dumps(payload))

    async def send_chat(self, body: dict[str, Any]) -> None:
        await self._send({"type": "chat", "body": body})

    async def send_cancel(self) -> None:
        await self._send({"type": "cancel"})

    async def send_continue(self) -> None:
        await self._send({"type": "continue_step"})

    async def send_permission(self, request_id: str, reply: str) -> None:
        await self._send({"type": "permission_reply", "request_id": request_id, "reply": reply})

    async def send_add_tools(self, names: list[str]) -> None:
        await self._send({"type": "add_tools", "names": names})

    async def send_ping(self) -> None:
        await self._send({"type": "ping"})

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self._ws is None:
            raise AgentLayerError("not connected")
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(msg, dict):
                yield msg


def chat_body(
    settings: Settings,
    prompt: str,
    *,
    conversation_id: str = "",
    workspace_id: str = "",
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """OpenAI-shaped request plus the agent knobs the socket understands."""
    messages = list(history or [])
    messages.append({"role": "user", "content": prompt})
    body: dict[str, Any] = {"messages": messages, "stream": False}
    if settings.model:
        body["model"] = settings.model
    if settings.agent_id:
        body["agent_id"] = settings.agent_id
    if settings.stream:
        body["agent_stream_llm"] = True
    if conversation_id:
        body["conversation_id"] = conversation_id
    # Explicit beats the conversation's pref_workspace_id, so a fresh /bind takes effect
    # on the very next turn without waiting for the preference to round-trip.
    if workspace_id:
        body["workspace_id"] = workspace_id
    # Ask before destructive workspace tools; the TUI can answer on the same socket.
    body["agent_permission_ask"] = True
    return body


async def one_shot(settings: Settings, prompt: str, on_line: Callable[[str], None]) -> str:
    """Non-interactive turn over HTTP for pipes and CI (milestone 5, useful already)."""
    async with httpx.AsyncClient(base_url=settings.base_url, timeout=None) as http:
        r = await http.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json=chat_body(settings, prompt),
        )
        if r.status_code == 401:
            raise AgentLayerError("unauthorised — check the API key")
        r.raise_for_status()
        from .events import answer_from_completion

        text = answer_from_completion(r.json())
        on_line(text)
        return text
