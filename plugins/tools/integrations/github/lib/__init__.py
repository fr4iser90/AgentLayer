"""GitHub integration helpers — colocated with github tools, not backend domain."""

from plugins.tools.integrations.github.lib.auth import (
    USER_SECRET_KEY,
    askpass_extra_env,
    cleanup_askpass_paths,
    git_auth_failure_reason,
    git_command_needs_github_pat,
    github_pat_for_current_user,
    github_pat_for_user_id,
    no_github_pat_payload,
    parse_github_pat,
    redact_secrets,
)
from plugins.tools.integrations.github.lib.repos import list_user_repos

__all__ = [
    "USER_SECRET_KEY",
    "askpass_extra_env",
    "cleanup_askpass_paths",
    "git_auth_failure_reason",
    "git_command_needs_github_pat",
    "github_pat_for_current_user",
    "github_pat_for_user_id",
    "list_user_repos",
    "no_github_pat_payload",
    "parse_github_pat",
    "redact_secrets",
]
