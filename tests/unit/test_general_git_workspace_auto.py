"""General chat auto-workspace from Git URL in user message."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.domain.agent import _try_auto_create_workspace_from_git_url


def test_auto_create_for_general_admin_with_git_url() -> None:
    uid = uuid.uuid4()
    ws_id = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.role = "admin"
    created_ws = {
        "id": str(ws_id),
        "name": "agentlayer-abc",
        "path": "/data/ws",
        "git_url": "https://github.com/fr4iser90/AgentLayer",
    }

    with patch(
        "apps.backend.domain.agent._is_elevated_admin",
        return_value=True,
    ):
        with patch(
            "apps.backend.domain.workspace.workspace_common.find_owned_git_workspace",
            return_value=None,
        ):
            with patch(
                "apps.backend.infrastructure.workspace_service.create_project_workspace_for_user",
                return_value={"id": str(ws_id)},
            ) as create_mock:
                with patch(
                    "apps.backend.infrastructure.workspace_service.ensure_workspace",
                    return_value=created_ws,
                ):
                    with patch(
                        "apps.backend.infrastructure.workspace_service.slug_from_git_url",
                        return_value="agentlayer",
                    ):
                        out = _try_auto_create_workspace_from_git_url(
                            agent_id="general",
                            user_id=uid,
                            user_obj=user,
                            last_user_text=(
                                "Scan https://github.com/fr4iser90/AgentLayer with SimpleSecCheck"
                            ),
                            embedded_subagent=False,
                        )

    assert out == created_ws
    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs.get("git_url") == (
        "https://github.com/fr4iser90/AgentLayer"
    )


def test_auto_create_reuses_owned_git_workspace_without_creating() -> None:
    uid = uuid.uuid4()
    ws_id = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.role = "admin"
    existing = {
        "id": str(ws_id),
        "owner_user_id": str(uid),
        "name": "AgentLayer-deadbeef",
        "git_url": "https://github.com/fr4iser90/AgentLayer.git",
    }
    bound = {**existing, "path": "/data/ws"}

    with patch(
        "apps.backend.domain.agent._is_elevated_admin",
        return_value=True,
    ):
        with patch(
            "apps.backend.domain.workspace.workspace_common.find_owned_git_workspace",
            return_value=existing,
        ) as find_mock:
            with patch(
                "apps.backend.infrastructure.workspace_service.create_project_workspace_for_user",
            ) as create_mock:
                with patch(
                    "apps.backend.infrastructure.workspace_service.ensure_workspace",
                    return_value=bound,
                ) as ensure_mock:
                    out = _try_auto_create_workspace_from_git_url(
                        agent_id="general",
                        user_id=uid,
                        user_obj=user,
                        last_user_text="https://github.com/fr4iser90/AgentLayer",
                        embedded_subagent=False,
                    )

    assert out == bound
    find_mock.assert_called_once_with(user, git_url="https://github.com/fr4iser90/AgentLayer")
    create_mock.assert_not_called()
    ensure_mock.assert_called_once_with(str(ws_id), user)


def test_auto_create_skipped_when_prompt_defers_to_workspace_create_tool() -> None:
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.role = "admin"

    with patch(
        "apps.backend.domain.agent._is_elevated_admin",
        return_value=True,
    ):
        with patch(
            "apps.backend.domain.workspace.workspace_common.find_owned_git_workspace",
        ) as find_mock:
            with patch(
                "apps.backend.infrastructure.workspace_service.create_project_workspace_for_user",
            ) as create_mock:
                out = _try_auto_create_workspace_from_git_url(
                    agent_id="general",
                    user_id=uid,
                    user_obj=user,
                    last_user_text=(
                        'Use workspace.create with source=git, git_url="https://github.com/octocat/Hello-World.git", '
                        'git_branch="master", name exactly "bench-test-git", and bind=true.'
                    ),
                    embedded_subagent=False,
                )

    assert out is None
    find_mock.assert_not_called()
    create_mock.assert_not_called()


def test_user_defers_git_workspace_to_tool() -> None:
    from apps.backend.domain.agent import _user_defers_git_workspace_to_tool

    assert _user_defers_git_workspace_to_tool(
        'Use workspace.create with source=git, git_url="https://github.com/x/y.git"'
    )
    assert not _user_defers_git_workspace_to_tool("clone https://github.com/x/y.git please")


def test_auto_create_skipped_for_embedded_subagent() -> None:
    out = _try_auto_create_workspace_from_git_url(
        agent_id="general",
        user_id=uuid.uuid4(),
        user_obj=MagicMock(),
        last_user_text="https://github.com/fr4iser90/AgentLayer",
        embedded_subagent=True,
    )
    assert out is None
