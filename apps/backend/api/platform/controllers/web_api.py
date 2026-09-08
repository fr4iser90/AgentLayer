from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def _refuse_web_ui_or_none(path: str) -> None:
    from apps.backend.application.platform.use_cases.client_surface_policy import refuse_web_ui_path

    detail = refuse_web_ui_path(path)
    if detail:
        raise HTTPException(status_code=403, detail=detail)


def register_web_routes(app: FastAPI) -> None:

    # Legacy control UI (optional): repo ``interfaces/web/static`` if present.
    _repo_root = Path(__file__).resolve().parents[5]
    _control_dir = _repo_root / "interfaces" / "web" / "static"
    _control_login_html = _control_dir / "login.html"
    _js_dir = _control_dir / "js"
    if _js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=str(_js_dir)), name="public_js")

    _agent_ui_dir = _repo_root / "apps" / "frontend" / "dist"
    _agent_index = _agent_ui_dir / "index.html"
    if _agent_index.is_file():

        @app.get("/coding-agent")
        async def redirect_legacy_coding_agent(request: Request):
            """Legacy deep links: Coding UI removed; Chat is the only project surface."""
            _refuse_web_ui_or_none("/app/chat")
            q = request.url.query
            target = "/app/chat" + (f"?{q}" if q else "")
            return RedirectResponse(url=target, status_code=302)

        @app.get("/app")
        async def agent_ui_spa_root():
            """``/app`` without trailing slash: same shell as ``/app/`` (hard refresh must not 405)."""
            from apps.backend.application.platform.use_cases.client_surface_policy import web_ui_enabled

            if not web_ui_enabled():
                return RedirectResponse(url="/app/login", status_code=302)
            return FileResponse(_agent_index)

        @app.get("/app/chat")
        @app.get("/app/coding-agent")
        @app.get("/app/dashboard")
        @app.get("/app/dashboard/shared")
        @app.get("/app/docs")
        @app.get("/app/login")
        @app.get("/app/setup")
        @app.get("/app/legal/{rest:path}")
        @app.get("/app/schedules")
        @app.get("/app/tasks")
        @app.get("/app/settings")
        @app.get("/app/settings/profile")
        @app.get("/app/settings/voice")
        @app.get("/app/settings/connections")
        @app.get("/app/settings/notifications")
        @app.get("/app/settings/tools")
        @app.get("/app/settings/agent")
        @app.get("/app/settings/delegate")
        @app.get("/app/settings/friends")
        @app.get("/app/settings/shares")
        @app.get("/app/studio")
        @app.get("/app/org/knowledge")
        @app.get("/app/org/setup")
        @app.get("/app/org/team")
        @app.get("/app/admin")
        @app.get("/app/admin/interfaces")
        @app.get("/app/admin/interfaces/bridges")
        @app.get("/app/admin/interfaces/llm")
        @app.get("/app/admin/interfaces/providers")
        @app.get("/app/admin/interfaces/model-policies")
        @app.get("/app/admin/interfaces/routing")
        @app.get("/app/admin/interfaces/memory")
        @app.get("/app/admin/interfaces/voice")
        @app.get("/app/admin/interfaces/automation")
        @app.get("/app/admin/interfaces/platform")
        @app.get("/app/admin/interfaces/{rest:path}")
        @app.get("/app/admin/tools")
        @app.get("/app/admin/agents")
        @app.get("/app/admin/benchmarks")
        @app.get("/app/admin/agent-config")
        @app.get("/app/admin/run-traces")
        @app.get("/app/admin/users")
        @app.get("/app/admin/scheduled-jobs")
        @app.get("/app/admin/schedules")
        @app.get("/app/admin/workflows")
        @app.get("/app/admin/agent-config/{rest:path}")
        async def agent_ui_spa_shell(request: Request):
            """Serve SPA index for client-side routes (must register before mount /app)."""
            _refuse_web_ui_or_none(request.url.path)
            return FileResponse(_agent_index)

        app.mount(
            "/app",
            StaticFiles(directory=str(_agent_ui_dir), html=True),
            name="agent_ui",
        )

    @app.get("/")
    def root(request: Request):
        """JSON index for API clients; top-level browser navigations go to the SPA (see /auth/policy for JSON)."""
        accept = (request.headers.get("accept") or "").lower()
        sec_dest = (request.headers.get("sec-fetch-dest") or "").lower()
        first = accept.split(",")[0].strip() if accept else ""
        wants_html = sec_dest == "document" or (
            "text/html" in accept and not first.startswith("application/json")
        )
        if wants_html and _agent_index.is_file():
            from apps.backend.application.platform.use_cases.client_surface_policy import web_ui_enabled

            target = "/app/" if web_ui_enabled() else "/app/login"
            return RedirectResponse(url=target, status_code=302)

        out: dict[str, object] = {
            "service": "agent-layer",
            "first_party_ui": "/app/",
            "login": "/login",
            "hint": "OpenAI API under /v1/ (e.g. POST /v1/chat/completions); WebSocket /ws/v1/chat; GET /health; GET /v1/tools",
        }
        if _agent_index.is_file():
            out["operator_admin_ui"] = "/app/admin"
        try:
            from apps.backend.application.platform.use_cases.client_surface_policy import public_policy

            out["client_surface"] = public_policy()
        except Exception:
            pass
        return out


    @app.get("/favicon.ico")
    def favicon():
        """Empty favicon so GET does not fall through to POST /{tool_name} (would return 405)."""
        return Response(status_code=204)


    @app.get("/login")
    def login_page():
        """Browser login: legacy ``interfaces/web/static/login.html`` if present, else SPA."""
        if _control_login_html.is_file():
            return FileResponse(_control_login_html)
        if _agent_index.is_file():
            return RedirectResponse(url="/app/login", status_code=307)
        raise HTTPException(status_code=404, detail="login UI not shipped")


    @app.get("/chat")
    def browser_chat_entry():
        """Short URL → SPA (public: loading the shell must not require JWT)."""
        _refuse_web_ui_or_none("/app/chat")
        return RedirectResponse(url="/app/chat", status_code=307)


    @app.get("/dashboard")
    def browser_dashboard_entry():
        """Short URL → first-party app home (`/app/`)."""
        from apps.backend.application.platform.use_cases.client_surface_policy import web_ui_enabled

        if not web_ui_enabled():
            return RedirectResponse(url="/app/login", status_code=307)
        return RedirectResponse(url="/app/", status_code=307)
