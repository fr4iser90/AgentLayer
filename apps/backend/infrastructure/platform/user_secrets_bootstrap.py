"""System-prompt snippets: which user secret keys exist (never values)."""

from __future__ import annotations

import uuid

from apps.backend.infrastructure.platform.config import config


def build_user_secrets_bootstrap_snippet(user_id: uuid.UUID | None) -> str:
    """
    Tell the model which ``service_key`` slots are already stored for this user.
    Values are never included.
    """
    if user_id is None:
        return ""
    if not (config.SECRETS_MASTER_KEY or "").strip():
        return (
            "## User secrets\n\n"
            "Server-side secret storage is not configured (``AGENT_SECRETS_MASTER_KEY``). "
            "Integration tools may fall back to operator env vars only."
        )
    try:
        from apps.backend.infrastructure.db import db

        keys = sorted(db.user_secret_list_service_keys(user_id))
    except Exception:
        return ""

    if not keys:
        return (
            "## User secrets (Settings → Connections)\n\n"
            "No per-user secrets are stored yet. If a tool needs a credential, use "
            "**``request_user_secret``** (in-chat card) or **``save_user_secret``** when they pasted "
            "a key in chat, or Settings → Connections — do not write keys into ``.env`` files."
        )

    listed = ", ".join(f"``{k}``" for k in keys)
    hints: list[str] = []
    if "ssc_api_key" in keys:
        hints.append(
            "**SimpleSecCheck:** ``ssc_api_key`` is already stored — do **not** ask the user to paste "
            "the SSC API key. For scans, bind a project workspace then ``delegate`` with "
            "``agent_id: security_auditor``."
        )
    if "github_pat" in keys:
        hints.append(
            "**GitHub:** ``github_pat`` is stored — git push/clone in coding tools use it server-side; "
            "do not ask the user to paste a PAT unless a tool returns ``no_token`` / auth failure."
        )

    extra = ("\n".join(f"- {h}" for h in hints)) if hints else ""
    block = (
        "## User secrets (configured keys only — values are never shown)\n\n"
        f"Stored for this signed-in user: {listed}.\n"
        "- Do **not** ask the user to re-paste credentials for keys listed above unless a tool "
        "returns an explicit auth error for that ``service_key``.\n"
        "- Use **``user_secrets_status``** if you need to re-check which keys exist."
    )
    if extra:
        block += "\n\n" + extra
    return block


def build_workspace_bound_snippet(workspace: dict) -> str:
    """Short hint for general chat when a project workspace is active."""
    if not isinstance(workspace, dict):
        return ""
    wid = workspace.get("id")
    name = workspace.get("name") or workspace.get("slug") or "project"
    git_url = workspace.get("git_url") or ""
    path = workspace.get("path") or ""
    lines = [
        "## Active project workspace",
        f"Bound workspace: **{name}** (id: ``{wid}``).",
    ]
    if git_url:
        lines.append(f"Git: ``{git_url}`` (branch: ``{workspace.get('git_branch') or 'main'}``).")
    if path:
        lines.append(f"Container path: ``{path}``.")
    lines.append(
        "``delegate`` (``security_auditor``, ``coding``, ``coding_plan``) and ``coding_*`` "
        "read tools use this workspace — call ``create`` / ``bind`` first if the "
        "user asked about a **different** repository."
    )
    return "\n".join(lines)
