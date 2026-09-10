---
skill_id: secrets_orchestrator
agents: general
---

## Credentials (orchestrator)

- **Never** ask users to paste keys into ``.env`` / docker env files — those writes are blocked for agents.
- Use **`user_secrets_status`** to see which integration keys exist (names only, no values).
- If the user **pasted** a credential in chat and asked to save it, call **`save_user_secret`** yourself.
  Derive ``service_key`` by lowercasing the env/var name (``FOO_BAR`` → ``foo_bar``), or use a
  catalog key when an integration declares one. Never invent fixed product-specific key names.
  Never echo the secret value back.
- If a secret is missing and the user should type it in the Web UI, call **`request_user_secret`**.
- Optional: **`secrets_help`** / **`register_secrets`** for headless OTP flows.
- For CLI env vars after a workspace is **bound**: **`save_user_secret`** ``scope=workspace``
  **auto-creates** ``env_bindings`` (``FOO_BAR`` ← ``foo_bar``) so Coding/`bash` injects at
  runtime — no separate ``env_bindings`` call and **never** a repo ``.env`` file.
  Use ``env_bindings`` only to list/override. Catalog keys (``github_pat``, …) stay ``scope=global``
  and are not auto-bound unless ``env_name`` is passed.
  Then **delegate** to `coding` for fetch/build.
- If **[User secrets]** already lists a key (e.g. ``ssc_api_key``, ``github_pat``), do **not** ask
  the user to paste it again — **delegate** to the right specialist (`security_auditor`, `coding`, …).
- Settings → Connections remains an alternative for catalog integrations; do not use it as an excuse
  to refuse `save_user_secret` when the user already pasted values in chat.
