-- Shared user_dashboards table. Idempotent (safe if referenced from multiple bundles).

CREATE TABLE IF NOT EXISTS user_dashboards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'custom',
  title TEXT NOT NULL DEFAULT '',
  ui_layout JSONB NOT NULL DEFAULT '{"version":1,"blocks":[]}'::jsonb,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_dashboards_owner
  ON user_dashboards (owner_user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_dashboards_tenant
  ON user_dashboards (tenant_id);

