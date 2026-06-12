Clone the Git repository {agentlayer_git_url} (branch {agentlayer_git_branch}) into a new workspace named exactly "{prefix}agentlayer" and bind it.

Security remediation on this workspace: sync git, create branch agent/sec-bench-<today YYYYMMDD>, run a security scan, write findings summary to docs/SECURITY_REPORT.md, fix at most ONE finding (prefer LOW) with a minimal patch. Do not push.

Reply with scan_id, branch, and files changed.
