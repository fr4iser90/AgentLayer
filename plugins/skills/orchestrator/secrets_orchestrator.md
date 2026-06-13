---
skill_id: secrets_orchestrator
agents: general
---

## Credentials (orchestrator)

- **Never** ask users to paste keys into ``.env`` / docker env files — those writes are blocked for agents.
- Use **`user_secrets_status`** to see which integration keys exist (names only, no values).
- If **[User secrets]** lists a key (e.g. ``ssc_api_key``, ``github_pat``), do **not** ask the user to paste it again — **delegate** to the right specialist (`security_auditor`, `coding`, …).
- You cannot call **`save_user_secret`** or **`request_user_secret`** — for missing credentials, point the user to **Settings → Connections** or delegate to an agent that can handle auth.
