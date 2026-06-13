---
skill_id: coding_fix_from_artifact
agents: coding
when_delegate_mode: fix_from_artifact
---

## **fix_from_artifact** (this run)

- Edit **only** paths from ``[Referenced artifacts]`` — enforcement blocks other files.
- When ``branch: …`` is in requirements: checkout, commit, and push **that** branch only.
- After edits: ``git_read`` log + re-read each changed file before claiming success.
