"""Runtime placeholders for scenario prompt templates."""

from __future__ import annotations

import os
from typing import Callable

from tests.benchmarks.agent.fixtures import agentlayer_bench_git_url
from tests.e2e.support.helpers import git_clone_url


def hello_git_url() -> str:
    return (os.environ.get("AGENT_BENCH_GIT_URL") or git_clone_url()).strip()


def hello_git_branch() -> str:
    return (os.environ.get("AGENT_BENCH_GIT_BRANCH") or "master").strip() or "master"


def agentlayer_git_branch() -> str:
    return (os.environ.get("AGENT_BENCH_AGENTLAYER_GIT_BRANCH") or "main").strip() or "main"


ENV_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "hello_git_url": hello_git_url,
    "hello_git_branch": hello_git_branch,
    "agentlayer_git_url": agentlayer_bench_git_url,
    "agentlayer_git_branch": agentlayer_git_branch,
}


def resolve_env_placeholders(text: str) -> str:
    out = text
    for key, fn in ENV_PLACEHOLDERS.items():
        out = out.replace("{" + key + "}", fn())
    return out
