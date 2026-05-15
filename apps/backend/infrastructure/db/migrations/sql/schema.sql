-- Agent Layer — single baseline schema (one Alembic revision: schema_001).
-- Fresh PostgreSQL only: empty DB, then `alembic upgrade head`.
-- UUID user ids from the start; incremental migrations 0012–0021 were folded into this file.

CREATE TABLE tenants (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, name) VALUES (1, 'default')
ON CONFLICT (id) DO NOTHING;

SELECT setval(
  pg_get_serial_sequence('tenants', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM tenants), 1)
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  external_sub TEXT NOT NULL,
  display_name TEXT,
  email TEXT UNIQUE,
  password_hash TEXT,
  role TEXT NOT NULL DEFAULT 'user',
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  discord_user_id TEXT,
  telegram_user_id TEXT,
  UNIQUE (tenant_id, external_sub)
);

CREATE INDEX idx_users_tenant ON users (tenant_id);
CREATE INDEX idx_users_tenant_sub ON users (tenant_id, external_sub);
CREATE UNIQUE INDEX idx_users_tenant_discord_user ON users (tenant_id, discord_user_id)
  WHERE discord_user_id IS NOT NULL AND btrim(discord_user_id) <> '';
CREATE UNIQUE INDEX idx_users_tenant_telegram_user ON users (tenant_id, telegram_user_id)
  WHERE telegram_user_id IS NOT NULL AND btrim(telegram_user_id) <> '';

CREATE TABLE user_dashboards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'custom',
  title TEXT NOT NULL DEFAULT '',
  ui_layout JSONB NOT NULL DEFAULT '{}'::jsonb,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_dashboards_tenant ON user_dashboards (tenant_id);
CREATE INDEX idx_user_dashboards_owner ON user_dashboards (owner_user_id, created_at DESC);
CREATE INDEX idx_user_dashboards_updated ON user_dashboards (updated_at DESC);

CREATE TABLE dashboard_block_share_grants (
  id BIGSERIAL PRIMARY KEY,
  dashboard_id UUID NOT NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
  viewer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  block_ids TEXT[] NOT NULL DEFAULT '{}',
  permission TEXT NOT NULL DEFAULT 'view',
  created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (dashboard_id, viewer_user_id)
);

CREATE INDEX idx_dashboard_block_shares_dashboard ON dashboard_block_share_grants (dashboard_id);
CREATE INDEX idx_dashboard_block_shares_viewer ON dashboard_block_share_grants (viewer_user_id);

CREATE TABLE tenant_dashboard_installed_template_kinds (
  tenant_id BIGINT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  kinds TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

CREATE TABLE todos (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT todos_status_check CHECK (status IN ('open', 'done', 'cancelled'))
);

CREATE INDEX idx_todos_created_at ON todos (created_at DESC);
CREATE INDEX idx_todos_status ON todos (status);
CREATE INDEX idx_todos_tenant_user_created ON todos (tenant_id, user_id, created_at DESC);
CREATE INDEX idx_todos_user_status ON todos (user_id, status);

CREATE TABLE tool_invocations (
  id BIGSERIAL PRIMARY KEY,
  tool_name TEXT NOT NULL,
  args_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_excerpt TEXT,
  ok BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_tool_invocations_created_at ON tool_invocations (created_at DESC);
CREATE INDEX idx_tool_invocations_tool_name ON tool_invocations (tool_name);
CREATE INDEX idx_tool_inv_user_created ON tool_invocations (user_id, created_at DESC);
CREATE INDEX idx_tool_inv_tenant_user ON tool_invocations (tenant_id, user_id);

CREATE TABLE user_secrets (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  service_key TEXT NOT NULL,
  ciphertext BYTEA NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, service_key)
);

CREATE INDEX idx_user_secrets_user ON user_secrets (user_id);

CREATE TABLE secret_upload_otps (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  otp_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_secret_otps_hash_unused ON secret_upload_otps (otp_hash)
  WHERE used_at IS NULL;

CREATE TABLE user_kb_notes (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  search_tsv tsvector GENERATED ALWAYS AS (
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(body, '')
    )
  ) STORED
);

CREATE INDEX idx_user_kb_notes_tenant_user_created ON user_kb_notes (tenant_id, user_id, created_at DESC);
CREATE INDEX idx_user_kb_notes_tsv ON user_kb_notes USING GIN (search_tsv);

CREATE TABLE user_agent_persona (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  instructions TEXT NOT NULL DEFAULT '',
  inject_into_agent BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_agent_persona_tenant ON user_agent_persona (tenant_id);

CREATE TABLE user_kb_note_shares (
  id BIGSERIAL PRIMARY KEY,
  note_id BIGINT NOT NULL REFERENCES user_kb_notes(id) ON DELETE CASCADE,
  grantee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission TEXT NOT NULL DEFAULT 'read',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT user_kb_note_shares_perm_check CHECK (permission IN ('read')),
  UNIQUE (note_id, grantee_user_id)
);

CREATE INDEX idx_kb_note_shares_grantee ON user_kb_note_shares (grantee_user_id);
CREATE INDEX idx_kb_note_shares_note ON user_kb_note_shares (note_id);

CREATE TABLE user_agent_profile (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

  display_name TEXT NOT NULL DEFAULT '',
  preferred_output_language TEXT NOT NULL DEFAULT '',
  locale TEXT NOT NULL DEFAULT '',
  timezone TEXT NOT NULL DEFAULT '',

  home_location TEXT NOT NULL DEFAULT '',
  work_location TEXT NOT NULL DEFAULT '',
  travel_mode TEXT NOT NULL DEFAULT '',
  travel_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,

  tone TEXT NOT NULL DEFAULT '',
  verbosity TEXT NOT NULL DEFAULT '',
  language_level TEXT NOT NULL DEFAULT '',

  interests JSONB NOT NULL DEFAULT '[]'::jsonb,
  hobbies JSONB NOT NULL DEFAULT '[]'::jsonb,

  job_title TEXT NOT NULL DEFAULT '',
  organization TEXT NOT NULL DEFAULT '',
  industry TEXT NOT NULL DEFAULT '',
  experience_level TEXT NOT NULL DEFAULT '',
  primary_tools JSONB NOT NULL DEFAULT '[]'::jsonb,

  proactive_mode BOOLEAN NOT NULL DEFAULT false,
  interaction_style TEXT NOT NULL DEFAULT '',

  inject_structured_profile BOOLEAN NOT NULL DEFAULT true,
  inject_dynamic_traits BOOLEAN NOT NULL DEFAULT false,
  dynamic_traits JSONB NOT NULL DEFAULT '{}'::jsonb,

  profile_version BIGINT NOT NULL DEFAULT 1,
  profile_hash TEXT NOT NULL DEFAULT '',
  injection_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
  usage_patterns JSONB NOT NULL DEFAULT '{}'::jsonb,

  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_agent_profile_tenant ON user_agent_profile (tenant_id);

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE rag_documents (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  domain TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  source_uri TEXT,
  content_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rag_documents_scope ON rag_documents (tenant_id, user_id, domain);

CREATE TABLE rag_chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(768) NOT NULL,
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_rag_chunks_document ON rag_chunks (document_id);
CREATE INDEX idx_rag_chunks_embedding ON rag_chunks USING hnsw (embedding vector_cosine_ops);

-- --- User memory: structured facts + semantic notes ---

CREATE TABLE user_memory_facts (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json JSONB NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NULL,
  deleted_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX ux_user_memory_facts_global_key
  ON user_memory_facts (tenant_id, user_id, key)
  WHERE dashboard_id IS NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX ux_user_memory_facts_dashboard_key
  ON user_memory_facts (tenant_id, user_id, dashboard_id, key)
  WHERE dashboard_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_user_memory_facts_scope_updated
  ON user_memory_facts (tenant_id, user_id, dashboard_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_user_memory_facts_scope_expires
  ON user_memory_facts (tenant_id, user_id, dashboard_id, expires_at)
  WHERE deleted_at IS NULL;

CREATE TABLE user_memory_notes (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL,
  embedding vector(768) NOT NULL
);

CREATE INDEX idx_user_memory_notes_scope_updated
  ON user_memory_notes (tenant_id, user_id, dashboard_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_user_memory_notes_embedding
  ON user_memory_notes USING hnsw (embedding vector_cosine_ops);

-- Structured memory graph (FMA-style MVP): nodes + edges, activated into prompt as compact bullets.

CREATE TABLE user_memory_graph_nodes (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'event',
  label TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  importance REAL NOT NULL DEFAULT 1.0,
  confidence REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL DEFAULT 'user',
  last_verified TIMESTAMPTZ NULL,
  subject_key TEXT NULL,
  stability TEXT NOT NULL DEFAULT 'normal',
  priority REAL NOT NULL DEFAULT 0,
  embedding vector(768),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_user_memory_graph_nodes_scope_updated
  ON user_memory_graph_nodes (tenant_id, user_id, dashboard_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_user_memory_graph_nodes_subject
  ON user_memory_graph_nodes (tenant_id, user_id, subject_key)
  WHERE deleted_at IS NULL AND subject_key IS NOT NULL;

CREATE INDEX idx_user_memory_graph_nodes_embedding
  ON user_memory_graph_nodes USING hnsw (embedding vector_cosine_ops)
  WHERE deleted_at IS NULL AND embedding IS NOT NULL;

CREATE TABLE user_memory_graph_edges (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  src_node_id BIGINT NOT NULL REFERENCES user_memory_graph_nodes(id) ON DELETE CASCADE,
  dst_node_id BIGINT NOT NULL REFERENCES user_memory_graph_nodes(id) ON DELETE CASCADE,
  rel_type TEXT NOT NULL DEFAULT 'related',
  weight REAL NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_user_memory_graph_edges_no_self CHECK (src_node_id <> dst_node_id),
  CONSTRAINT ux_user_memory_graph_edges_unique UNIQUE (src_node_id, dst_node_id, rel_type)
);

CREATE INDEX idx_user_memory_graph_edges_src
  ON user_memory_graph_edges (tenant_id, user_id, src_node_id);

CREATE INDEX idx_user_memory_graph_edges_dst
  ON user_memory_graph_edges (tenant_id, user_id, dst_node_id);

CREATE TABLE user_memory_graph_activation_log (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID NULL REFERENCES user_dashboards(id) ON DELETE SET NULL,
  node_ids BIGINT[] NOT NULL DEFAULT '{}',
  query_sha256 CHAR(64) NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_graph_activation_user_created
  ON user_memory_graph_activation_log (tenant_id, user_id, created_at DESC);

CREATE TABLE rss_articles (
  id BIGSERIAL PRIMARY KEY,
  article_id TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rss_articles_fetched ON rss_articles (fetched_at DESC);

CREATE TABLE refresh_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  last_used_at TIMESTAMPTZ
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);

CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);

CREATE TABLE workflows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  definition JSONB NOT NULL DEFAULT '{}'::jsonb,
  visibility TEXT NOT NULL DEFAULT 'private',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflows_owner ON workflows(owner_user_id);

CREATE TABLE workflow_permissions (
  workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  can_execute BOOLEAN NOT NULL DEFAULT false,
  can_edit BOOLEAN NOT NULL DEFAULT false,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (workflow_id, user_id)
);

CREATE TABLE admin_claim_otp (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  otp_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  claimed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_admin_claim_otp_pending ON admin_claim_otp (created_at DESC)
  WHERE used_at IS NULL;

CREATE TABLE operator_settings (
  id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  discord_application_id TEXT,
  integration_notes TEXT,
  optional_connection_key TEXT,
  agent_mode TEXT,
  discord_bot_enabled BOOLEAN NOT NULL DEFAULT false,
  discord_bot_token TEXT,
  discord_bot_agent_bearer TEXT,
  discord_trigger_prefix TEXT NOT NULL DEFAULT '!agent ',
  discord_chat_model TEXT,
  telegram_application_id TEXT,
  telegram_bot_enabled BOOLEAN NOT NULL DEFAULT false,
  telegram_bot_token TEXT,
  telegram_bot_agent_bearer TEXT,
  telegram_trigger_prefix TEXT NOT NULL DEFAULT '!agent ',
  telegram_chat_model TEXT,
  dashboard_upload_max_file_mb INTEGER,
  dashboard_upload_allowed_mime TEXT,
  llm_primary_backend TEXT NOT NULL DEFAULT 'ollama',
  llm_smart_routing_enabled BOOLEAN NOT NULL DEFAULT false,
  llm_router_ollama_model TEXT NOT NULL DEFAULT 'nemotron-3-nano:4b',
  llm_router_local_confidence_min DOUBLE PRECISION NOT NULL DEFAULT 0.7,
  llm_router_timeout_sec DOUBLE PRECISION NOT NULL DEFAULT 12,
  llm_route_long_prompt_chars INTEGER NOT NULL DEFAULT 8000,
  llm_route_short_local_max_chars INTEGER NOT NULL DEFAULT 220,
  llm_route_many_code_fences INTEGER NOT NULL DEFAULT 3,
  llm_route_many_messages INTEGER NOT NULL DEFAULT 14,
  memory_graph_enabled BOOLEAN NOT NULL DEFAULT true,
  memory_graph_max_hops INTEGER NOT NULL DEFAULT 2,
  memory_graph_min_score DOUBLE PRECISION NOT NULL DEFAULT 0.03,
  memory_graph_max_bullets INTEGER NOT NULL DEFAULT 14,
  memory_graph_max_prompt_chars INTEGER NOT NULL DEFAULT 3500,
  memory_graph_log_activations BOOLEAN NOT NULL DEFAULT false,
  memory_enabled BOOLEAN NOT NULL DEFAULT true,
  rag_enabled BOOLEAN NOT NULL DEFAULT true,
  rag_ollama_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
  rag_embedding_dim INTEGER NOT NULL DEFAULT 768,
  rag_chunk_size INTEGER NOT NULL DEFAULT 1200,
  rag_chunk_overlap INTEGER NOT NULL DEFAULT 200,
  rag_top_k INTEGER NOT NULL DEFAULT 8,
  rag_embed_timeout_sec DOUBLE PRECISION NOT NULL DEFAULT 120,
  rag_tenant_shared_domains TEXT NOT NULL DEFAULT 'agentlayer_docs',
  docs_root TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO operator_settings (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE operator_external_llm_endpoints (
  id BIGSERIAL PRIMARY KEY,
  sort_order INTEGER NOT NULL DEFAULT 0,
  enabled BOOLEAN NOT NULL DEFAULT true,
  label TEXT NOT NULL DEFAULT '',
  base_url TEXT NOT NULL,
  api_key TEXT NOT NULL,
  model_default TEXT,
  model_vlm TEXT,
  model_agent TEXT,
  model_coding TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_operator_external_llm_endpoints_sort
  ON operator_external_llm_endpoints (sort_order ASC, id ASC);

CREATE TABLE operator_tool_policies (
  package_id TEXT NOT NULL,
  tool_name TEXT NOT NULL DEFAULT '*',
  enabled BOOLEAN NOT NULL DEFAULT true,
  min_role TEXT NOT NULL DEFAULT 'user',
  allowed_tenant_ids INTEGER[],
  execution_context TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (package_id, tool_name),
  CONSTRAINT operator_tool_policies_min_role_check CHECK (min_role IN ('user', 'admin'))
);

CREATE INDEX idx_operator_tool_policies_package ON operator_tool_policies (package_id);

COMMENT ON COLUMN operator_tool_policies.min_role IS
  'Minimum users.role required to list/invoke tools in this package (user = all authenticated users).';
COMMENT ON COLUMN operator_tool_policies.allowed_tenant_ids IS
  'NULL = any tenant; non-empty = only these tenant ids may use the package.';

COMMENT ON COLUMN operator_settings.agent_mode IS
  'sandbox | host; NULL = use AGENT_MODE from environment.';
COMMENT ON COLUMN operator_settings.dashboard_upload_max_file_mb IS
  'Max upload size per file (MB); NULL = use AGENT_DASHBOARD_UPLOAD_MAX_MB.';
COMMENT ON COLUMN operator_settings.dashboard_upload_allowed_mime IS
  'Comma-separated MIME allowlist; NULL = use AGENT_DASHBOARD_UPLOAD_ALLOWED_MIME.';

CREATE TABLE dashboard_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dashboard_id UUID NOT NULL,
  storage_relpath TEXT NOT NULL UNIQUE,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  original_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dashboard_files_owner ON dashboard_files (owner_user_id, created_at DESC);
CREATE INDEX idx_dashboard_files_dashboard ON dashboard_files (dashboard_id);

CREATE TABLE dashboard_members (
  dashboard_id UUID NOT NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'co_owner')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (dashboard_id, user_id)
);

CREATE INDEX idx_dashboard_members_user ON dashboard_members (user_id);

-- Server-side chat threads (first-party UI sync; per user, per tenant).

CREATE TABLE chat_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  dashboard_id UUID REFERENCES user_dashboards(id) ON DELETE SET NULL,
  title TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'chat' CHECK (mode IN ('chat', 'agent')),
  model TEXT NOT NULL DEFAULT '',
  agent_log JSONB NOT NULL DEFAULT '[]'::jsonb,
  shared BOOLEAN NOT NULL DEFAULT false,
  pref_agent_id TEXT,
  pref_workspace_id UUID REFERENCES project_workspaces(id) ON DELETE SET NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_conv_user_updated ON chat_conversations (user_id, updated_at DESC);
CREATE INDEX idx_chat_conv_tenant ON chat_conversations (tenant_id);
CREATE INDEX idx_chat_conv_dashboard ON chat_conversations (dashboard_id);
CREATE UNIQUE INDEX uq_chat_conv_user_dashboard_personal
  ON chat_conversations (user_id, dashboard_id)
  WHERE dashboard_id IS NOT NULL AND shared = false;
CREATE UNIQUE INDEX uq_chat_conv_dashboard_shared
  ON chat_conversations (dashboard_id)
  WHERE dashboard_id IS NOT NULL AND shared = true;

CREATE TABLE chat_messages (
  id BIGSERIAL PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  position INT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, position)
);

CREATE INDEX idx_chat_msg_conv ON chat_messages (conversation_id, position);

-- Bridges (Telegram, Discord, …): rolling conversation per (user, provider, chat/channel, optional thread).

CREATE TABLE IF NOT EXISTS bridge_agent_sessions (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  scope_chat_id BIGINT NOT NULL,
  scope_thread_id BIGINT NOT NULL DEFAULT 0,
  conversation_id UUID NOT NULL UNIQUE REFERENCES chat_conversations(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, provider, scope_chat_id, scope_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_bridge_agent_sessions_conv
  ON bridge_agent_sessions(conversation_id);
