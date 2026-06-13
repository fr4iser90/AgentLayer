---
skill_id: secrets_handling
agents: coding, security_auditor
---

## Credentials and API keys (mandatory)

- **Never** edit ``docker/.env``, ``.env``, or similar env files to store user API keys, tokens, or passwords — those writes are **blocked**.
- If a system block lists **configured** secret keys (e.g. ``ssc_api_key``), do **not** ask the user to paste them again unless a tool returns an explicit auth error for that key. Use **`user_secrets_status`** to re-check keys (no values returned).
- When the user pastes a credential in chat and asks to save it, call **`save_user_secret`** with the integration's ``service_key`` (e.g. ``ssc_api_key`` for SimpleSecCheck, ``github_pat`` for GitHub) and the secret value.
- In the **Web UI**, when a secret is missing or a tool reports auth failure, call **`request_user_secret`** (in-chat card) — **not** ``register_secrets`` / curl.
- Use **`register_secrets`** / Settings → Connections only for headless/bridge users who cannot use the Web UI card; prefer **`save_user_secret`** when they pasted the key in chat.
- Operator env vars (``SSC_API_KEY`` in docker) are for humans/ops — not for you to write from a chat turn.
