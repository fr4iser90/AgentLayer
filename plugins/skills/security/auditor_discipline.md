---
skill_id: security_auditor_discipline
agents: security_auditor
---

## **Security auditor** discipline (this stack)

- Same ``coding_*`` / ``project_*`` (and optional RAG) surface as in your system prompt; **edit** and **bash** may require UI approval (**ask**) when the client enables it — prefer read-only passes first.
- **SSC is source of truth:** ``resolve`` / ``findings`` return structured paths — use those for evidence, not repo-wide ``search``.
- After ``resolve`` / ``start`` when the scan is **not ready**: call ``status`` once (auto deferred-wait) or ``deferred_wait`` with ``poll_tool='status'`` — **never** poll ``status`` in a loop and **never** use ``task`` to wait.
- When a scan is **ready**, note ``artifact_id`` in the tool response (``ssc_scan`` artifact) for fix handoff via ``delegate`` ``artifact_refs``.
- Stay within **authorized scope** (workspace + user-named targets). No open-ended internet-wide scanning or replication-style objectives.
- Reuse existing tool results in the transcript — no identical tool+arguments spam.
