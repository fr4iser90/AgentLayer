# IDOR / Auth test matrix

Manual and automated checks for **authentication**, **authorization**, and **cross-user isolation**
in AgentLayer. Complements static scanners (Bandit, CodeQL, Semgrep) — those do not prove
AuthZ correctness.

## How to run automated checks

Requires a **running** Agent Layer instance (default `http://127.0.0.1:8088`).

**Config split:** `.env` = server/runtime (DB, JWT, …). **E2E credentials belong in `.env.e2e` only** (gitignored; copy from `.env.e2e.example`). Tests load `.env` first, then `.env.e2e` for keys not already set — admin login can fall back to `AGENT_INITIAL_ADMIN_*` from `.env` when `AGENT_E2E_EMAIL` is unset.

```bash
cp .env.e2e.example .env.e2e
# edit .env.e2e — set AGENT_E2E_EMAIL_B / AGENT_E2E_PASSWORD_B (and optional admin overrides)

./scripts/run-e2e-journeys.sh
# or only IDOR matrix:
PYTHONPATH=. python3 -m pytest tests/e2e/test_auth_idor_matrix.py -m e2e -v
```

### What these tests do (and what they do **not** do)

**Purpose:** prove User B **cannot** read User A's private resources (conversations,
dashboards, tasks, workspaces, secret keys). Each test **deliberately** has User B
call `GET` on User A's resource ID — that is the security probe (simulated attacker),
not a chat prompt and not LLM usage.

**Pass criteria:** User A GET → **200**; User B GET → **401 / 403 / 404**.  
**Fail (IDOR bug):** User B GET → **200** with User A's data.

**Not tested here:** LLM replies, model quality, agent tool rounds.  
**Live LLM agent tests:** `tests/e2e/test_secrets_cross_user_isolation.py`, `tests/e2e/test_journey_agent_smoke.py` (require configured provider on server).

Conversation probes use **`messages: []`** — empty DB row, no fake chat text.

Stale sandboxes: `python3 scripts/e2e_cleanup.py`.

### User secrets (cross-user + live LLM)

| Test file | What it checks |
|-----------|----------------|
| `test_user_b_cannot_list_admin_secret_keys` | User B `GET /v1/user/secrets` — no admin keys |
| `test_secrets_cross_user_isolation.py` | API + `user_secrets_status` tool + **live LLM** prompt-injection (User B) |

E2E requires a **live LLM** in `GET /v1/models` (`LLM_PROVIDER_*` or Admin LLM endpoints). No mock/stub mode.

Policy reference: `GET /auth/policy` and `apps/backend/api/optional_http_access.py`.

## Actors

| Actor | Description |
|-------|-------------|
| **Anon** | No `Authorization` header |
| **User A** | Authenticated user (tests use admin account for resource creation) |
| **User B** | Second tenant user (`role=user`, same `tenant_id=1` in default E2E setup) |
| **Admin** | `role=admin` — required for `/v1/admin/*` |

## Matrix

Legend: **401** = unauthenticated, **403** = authenticated but forbidden, **404** = not found
(often used instead of 403 to avoid resource enumeration), **200** = allowed,
**200+body** = HTTP 200 but JSON `ok: false` / error in body (tool policy).

### Middleware classes

| Route pattern | Anon | User B | Notes |
|---------------|------|--------|-------|
| `/health`, `/auth/login`, `/auth/setup-status`, SPA shells (`/app/*`, `/login`) | 200 | 200 | Fully public |
| `POST /v1/user/secrets/register-with-otp` | 200* | 200* | *OTP + rate limit + HTTPS/loopback |
| `GET /v1/dashboards/shared/{token}` | 200* | 200* | *Valid share token; optional password |
| `POST /v1/chat/completions`, `POST /tools/run`, WS `/ws/v1/chat` | 401 | 401 without token | Handler: `resolve_chat_identity` |
| `GET /v1/tools`, `GET /v1/capabilities` | 200 | 200 | Anonymous catalog (tenant 1, role user) |
| `GET /openapi.json`, `/openapi/*` | 200 | 200 | API surface disclosure by design |
| All other `/v1/*` | 401 | 401 without token | Global middleware JWT/API key |

### Admin escalation

| Route | User B expected | Enforcement |
|-------|-----------------|-------------|
| `GET /v1/admin/operator-settings` | 403 | `require_admin()` |
| `PATCH /v1/admin/operator-settings` | 403 | `require_admin()` |
| `GET /v1/admin/users` | 403 | `require_admin()` |
| `POST /v1/admin/users` | 403 | `require_admin()` |
| `POST /v1/admin/rag/ingest` | 403 | `require_admin()` |
| `PUT /v1/admin/tool-policies` | 403 | `require_admin()` |

Users **cannot** self-promote via `POST /auth/setup` after the first admin exists (409).

### Cross-user IDOR (User A resource → User B)

| Resource | User B read | User B write | Enforcement |
|----------|-------------|--------------|-------------|
| `GET /v1/dashboards/{id}` (private) | 404 | 404 on PATCH | `dashboard_get(user.id, …)` |
| `GET /v1/tasks/{id}` | 404 | 404 on PATCH | `user_may_access_task_row` |
| `GET /v1/user/conversations/{id}` | 404 | 404 on PUT/DELETE | `conversation_get(user.id, …)` |
| `GET /v1/user/persona` | 200 (own empty/different) | N/A | Per-user row; B must not see A's text |
| `GET /v1/user/memory/facts` | 200 (own keys only) | N/A | Identity-scoped memory service |
| `GET /v1/user/secrets` | 200 (own keys only) | N/A | `resolve_chat_identity` + `user_id`; E2E: `test_user_b_cannot_list_admin_secret_keys` |
| `GET /v1/workspaces/{id}` | 404 | 404 on mutating routes | `owner_user_id` in SQL; E2E: `test_user_b_cannot_read_admin_workspace` |
| Dashboard block render (no share) | 403 or 404 | — | E2E: `test_dashboard_nested_ref` |

### Shared access (positive — must succeed)

| Resource | User B / Anon expected | Enforcement |
|----------|------------------------|-------------|
| `GET /v1/dashboards/{id}` after **member** invite (`viewer`) | 200 | E2E: `test_user_b_can_read_dashboard_when_member_viewer` |
| Member **`viewer`** PATCH / DELETE | 404 | E2E: `test_viewer_member_cannot_patch_dashboard` |
| Member **`editor`** PATCH title | 200 | E2E: `test_editor_member_can_patch_dashboard_title` |
| Member **`editor`** DELETE dashboard | 404 (owner only) | E2E: `test_editor_member_cannot_delete_dashboard` |
| Block-share **`view`** PATCH layout | 404 | E2E: `test_block_share_view_cannot_patch_layout` |
| Block-share **`edit`** PATCH allowed block | 200 | E2E: `test_block_share_edit_can_patch_allowed_block` |
| `GET /v1/dashboards/shared/{token}` (no password) | 200 anon | E2E: `test_anon_public_dashboard_share_without_password` |
| Invalid / expired share token | 404 | token length + DB lookup |
| Granular **block-share** (subset of layout) | 200 partial data | `dashboard_block_share_grants`; E2E: `test_dashboard_nested_ref` |

### Tool / agent RBAC

| Action | User B expected | Enforcement |
|--------|-----------------|-------------|
| Chat as `coding` agent | Blocked in planner | `user_may_invoke_agent` → general only |
| `POST /tools/run` admin-only tool | 200 + `ok: false` in JSON | `caller_fulfills_effective_policy` |
| `GET /v1/tools` | No admin-only tools in list | `filter_chat_tool_specs` |

### Intentionally public / deferred

These are **not** IDOR bugs when documented:

- Tool catalog without Bearer (metadata only; execute still needs auth).
- OpenAPI spec (deployment may restrict at reverse proxy).
- Media stream `GET …/stream?token=` (handler validates token).

## Manual pentest checklist (not in CI)

- [ ] Brute-force / rate limit: `/auth/login`, `/auth/setup`, OTP register
- [ ] Refresh cookie: `HttpOnly`, `Secure`, `SameSite` behind HTTPS
- [ ] WebSocket: invalid/expired token on `/ws/v1/chat`
- [ ] Share token guessing on `/v1/dashboards/shared/{token}`
- [ ] Host header / SSRF on media stream URLs (allowlist in `media_policy`)
- [ ] Second tenant (`tenant_id=2`) isolation if multi-tenant is enabled
- [ ] API key revocation (`api_keys` table) after delete

## Related tests in repo

| File | Coverage |
|------|----------|
| `tests/e2e/test_auth_idor_matrix.py` | This matrix (automated) |
| `tests/e2e/test_dashboard_nested_ref.py` | Dashboard block ACL |
| `tests/unit/test_agent_access.py` | Agent allowlist unit tests |
| `tests/unit/test_auth_setup.py` | First-admin bootstrap |
| `tests/unit/test_media_stream_route_auth.py` | Stream route middleware bypass shape |
| SimpleSecCheck (`security_scan_*` tools) | SAST only |

## External DAST (optional)

Not bundled: OWASP ZAP, Burp Suite, `nuclei`, `ffuf` against a staging instance.
Run only on environments you own.
