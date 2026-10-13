"""API for the agent submission staging + review queue (P7a).

- Any authenticated user may submit a proposed agent draft (``POST``), and read
  their own / admin previews.
- Site admins list pending drafts and approve/reject them; on approve the draft
  is promoted into ``plugins/agents`` and the live registry reloaded.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.application.agent_runtime.use_cases.agent_submission_services import (
    assess_submission,
    preview_submission,
    list_submissions,
    review_submission as review_submission_use,
    submit_agent_submission,
)
from apps.backend.application.identity.use_cases.request_auth import (
    get_current_user,
    require_site_admin,
)

router = APIRouter(prefix="/v1", tags=["agents-submissions"])


class AgentSubmissionBody(BaseModel):
    agent: dict[str, Any] = Field(default_factory=dict, description="Proposed agent definition.")
    agent_id: str | None = Field(default=None, max_length=128, description="Proposed slug; inferred when absent.")
    system_prompt: str | None = Field(default=None, max_length=100000)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class AgentReviewBody(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    review_notes: str | None = Field(default=None, max_length=4000)


@router.post("/agents/submissions", status_code=201)
async def create_submission(request: Request, body: AgentSubmissionBody) -> dict[str, Any]:
    """Submit a proposed agent draft for review (any authenticated user)."""
    user = await get_current_user(request)
    agent = body.agent
    if not isinstance(agent, dict) or not agent:
        raise HTTPException(status_code=400, detail="agent must be a non-empty object")
    agent_id = (body.agent_id or str(agent.get("id") or "").strip()
                or str(agent.get("name") or "").strip())
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id (or agent.id/agent.name) is required")
    try:
        return submit_agent_submission(
            author_id=str(user.id),
            agent_id=agent_id,
            agent_yaml=agent,
            title=body.title,
            description=body.description or agent.get("description"),
            system_prompt=body.system_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agents/submissions/assess")
async def assess_submission_endpoint(request: Request, body: AgentSubmissionBody) -> dict[str, Any]:
    """Heuristic pre-filter for a proposed draft (any authenticated user).

    No submission is written — submitters can sanity-check risk and unknown
    tools before the draft enters the review queue.
    """
    user = await get_current_user(request)
    agent = body.agent
    if not isinstance(agent, dict) or not agent:
        raise HTTPException(status_code=400, detail="agent must be a non-empty object")
    agent_id = (body.agent_id or str(agent.get("id") or "").strip()
                or str(agent.get("name") or "").strip())
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id (or agent.id/agent.name) is required")
    try:
        return assess_submission(
            author_id=str(user.id),
            agent_id=agent_id,
            agent_yaml=agent,
            title=body.title,
            description=body.description or agent.get("description"),
            system_prompt=body.system_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents/submissions/{submission_id}")
async def get_submission_preview(request: Request, submission_id: str) -> dict[str, Any]:
    """Preview a draft: the author or a site admin."""
    user = await get_current_user(request)
    data = preview_submission(submission_id)
    if data is None:
        raise HTTPException(status_code=404, detail="submission not found")
    if str(data.get("author_id")) != str(user.id):
        await require_site_admin(request)
    return data


@router.get("/admin/agents/submissions")
async def admin_list_submissions(
    request: Request,
    status: str | None = Query(None, description="pending | approved | rejected"),
    agent_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List submissions (site admin)."""
    await require_site_admin(request)
    return {"submissions": list_submissions(status=status, agent_id=agent_id, limit=limit)}


@router.post("/admin/agents/submissions/{submission_id}/review")
async def review_submission(request: Request, submission_id: str, body: AgentReviewBody) -> dict[str, Any]:
    """Approve/reject a draft (site admin). Approve promotes the agent."""
    user = await require_site_admin(request)
    try:
        return review_submission_use(
            submission_id=submission_id,
            decision=body.decision,
            reviewed_by=str(user.id),
            review_notes=body.review_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
