# Generic friend share grants

Unified permission layer for sharing resources with confirmed friends — one management tool, policy JSON on grants, resource catalog (not hardcoded in UI).

## Architecture

```
share_permissions (DB)
  owner_user_id, grantee_user_id
  resource_type, resource_identifier   ← any id you choose (google_calendar, my_notes, …)
  is_allowed, revoked_at
  policy JSONB  →  { "days_ahead": 7, "expires_at": "2026-06-11T00:00:00Z" }

API  /v1/shares/set | /check | /outgoing | /incoming | /friend/{id} | /catalog

Agent  friends.shares  (action: list | grant | revoke | check)
Read adapters  friends.calendar, …  →  check grant + apply policy at fetch time
```

Dashboard sharing (members, block grants, public tokens) stays separate; can be linked in catalog later as `dashboard` resource type.

## Policy fields (per resource)

| Field | Used by | Meaning |
|-------|---------|---------|
| `days_ahead` | `google_calendar` | Max calendar horizon the grantee may request |
| `expires_at` | all | ISO-8601 UTC; grant inactive after this time |

## Agent examples

- *"Teile Max meinen Kalender für 7 Tage"* → `shares` action `grant`, `resource_type: google_calendar`, `policy: { days_ahead: 7 }`
- *"Wer hat Zugriff auf meinen Kalender?"* → `shares` action `list`
- *"Zeig mir Lisas Termine"* → `friends.calendar` (checks grant + policy)

## Files

| Area | Path |
|------|------|
| Type normalization | `apps/backend/domain/shares/catalog.py` |
| Policy helpers | `apps/backend/domain/shares/policy.py` |
| DB | `apps/backend/infrastructure/db/share_permissions_db.py` |
| API | `apps/backend/api/shares_api.py` |
| Tool | `plugins/tools/integrations/friends/shares.py` |
| UI | `apps/frontend/src/pages/settings/SharesSettings.tsx` |
