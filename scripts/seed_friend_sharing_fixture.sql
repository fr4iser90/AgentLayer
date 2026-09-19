-- Friend + sharing validation fixture
--
-- Purpose: give ADR 0014's verification plan (docs/adr/0014-*.md §7) real rows
-- to exercise. Every grant below is tagged with the case it exists to test.
--
-- Run:   docker exec -i agent-layer-postgres psql -U agent -d agent \
--            < scripts/seed_friend_sharing_fixture.sql
--
-- Idempotent: safe to re-run. Deterministic UUIDs, upsert on the natural keys.
-- ADR 0014 §6.1 says "audit existing grants before activating an adapter" —
-- this fixture is what makes that audit non-trivial on a dev box.
--
-- Login password for ALL seeded users: Seed#Fixture2026
-- (bcrypt cost 4 — fixture only, do not reuse this hash anywhere real.)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Tenants. Two extra tenants so cross-tenant friendship is exercised, not just
-- same-tenant. ADR 0014 §6.4: friendship is deliberately cross-tenant, so every
-- adapter inherits "a friend can be in another company".
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO tenants (id, name, setup_completed_at)
VALUES
    (2, 'Nord Klinik', NOW()),
    (3, 'West Werk',   NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

SELECT setval('tenants_id_seq', (SELECT MAX(id) FROM tenants));

-- ─────────────────────────────────────────────────────────────────────────────
-- Users.
--   anna  (tenant 2) — the owner; most grants originate here
--   tim   (tenant 2) — same tenant, pending/revoked/expired cases
--   lena  (tenant 3) — the cross-tenant accepted friend; primary grantee
--   bob   (tenant 3) — NOT a friend; the negative control
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO users (id, tenant_id, external_sub, display_name, email, password_hash, role, site_role)
VALUES
    ('a1111111-1111-4111-8111-111111111111', 2, 'seed-anna', 'Anna Nord', 'anna@nord.example',
     '$2b$04$jtgaAVxoIMoQRntKpfm2NeN1uPBSQSgaiHlYP64pmPgiud6MseViC', 'user', 'site_user'),
    ('a2222222-2222-4222-8222-222222222222', 2, 'seed-tim',  'Tim Nord',  'tim@nord.example',
     '$2b$04$jtgaAVxoIMoQRntKpfm2NeN1uPBSQSgaiHlYP64pmPgiud6MseViC', 'user', 'site_user'),
    ('a3333333-3333-4333-8333-333333333333', 3, 'seed-lena', 'Lena West', 'lena@west.example',
     '$2b$04$jtgaAVxoIMoQRntKpfm2NeN1uPBSQSgaiHlYP64pmPgiud6MseViC', 'user', 'site_user'),
    ('a4444444-4444-4444-8444-444444444444', 3, 'seed-bob',  'Bob West',  'bob@west.example',
     '$2b$04$jtgaAVxoIMoQRntKpfm2NeN1uPBSQSgaiHlYP64pmPgiud6MseViC', 'user', 'site_user')
ON CONFLICT (id) DO UPDATE
    SET tenant_id    = EXCLUDED.tenant_id,
        display_name = EXCLUDED.display_name,
        email        = EXCLUDED.email,
        password_hash = EXCLUDED.password_hash;

INSERT INTO tenant_memberships (user_id, tenant_id, membership_role)
VALUES
    ('a1111111-1111-4111-8111-111111111111', 2, 'tenant_owner'),
    ('a2222222-2222-4222-8222-222222222222', 2, 'tenant_member'),
    ('a3333333-3333-4333-8333-333333333333', 3, 'tenant_owner'),
    ('a4444444-4444-4444-8444-444444444444', 3, 'tenant_member')
ON CONFLICT (user_id, tenant_id) DO UPDATE SET membership_role = EXCLUDED.membership_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- Resources to grant against. Grants carry identifiers, so the identifier scheme
-- per type has to be real: dashboard = uuid, collection = slug.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO user_dashboards (id, tenant_id, owner_user_id, kind, title, visibility)
VALUES
    ('b1111111-1111-4111-8111-111111111111', 2,
     'a1111111-1111-4111-8111-111111111111', 'custom', 'Schichtübersicht Nord', 'private'),
    ('b2222222-2222-4222-8222-222222222222', 2,
     'a2222222-2222-4222-8222-222222222222', 'custom', 'Tims Personalkosten',   'private')
ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title;

INSERT INTO user_collections (tenant_id, owner_user_id, slug, title)
VALUES
    (2, 'a1111111-1111-4111-8111-111111111111', 'haustiere',   'Haustiere'),
    (2, 'a1111111-1111-4111-8111-111111111111', 'dienstreisen', 'Dienstreisen')
ON CONFLICT (owner_user_id, slug) DO UPDATE SET title = EXCLUDED.title;

-- ─────────────────────────────────────────────────────────────────────────────
-- Friend requests. Covers all three statuses and both directions, including the
-- shape that the precedence fix in 3c6687c was about: bob DECLINED anna, while
-- anna separately has a PENDING request out to bob. A lookup keyed only on the
-- unordered pair must not let one direction's status mask the other's.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO friend_requests (tenant_id, from_user_id, to_user_id, status, message, responded_at)
VALUES
    -- tim asks anna; still pending (accept-flow case)
    (2, 'a2222222-2222-4222-8222-222222222222',
        'a1111111-1111-4111-8111-111111111111', 'pending',
        'Hi Anna, kollege von der Station 3?', NULL),

    -- anna asks bob; still pending
    (2, 'a1111111-1111-4111-8111-111111111111',
        'a4444444-4444-4444-8444-444444444444', 'pending',
        'Hallo Bob, wegen der West-Werk-Schnittstelle', NULL),

    -- bob asked anna and was declined. Same unordered pair as the row above,
    -- opposite direction, different status.
    (3, 'a4444444-4444-4444-8444-444444444444',
        'a1111111-1111-4111-8111-111111111111', 'declined',
        'Hallo Anna?', NOW() - INTERVAL '3 days'),

    -- lena asked anna, accepted, cross-tenant. This is the primary friendship.
    (3, 'a3333333-3333-4333-8333-333333333333',
        'a1111111-1111-4111-8111-111111111111', 'accepted',
        'Wir hatten telefoniert wg. Kalender-Freigabe', NOW() - INTERVAL '10 days')
ON CONFLICT (from_user_id, to_user_id) DO UPDATE
    SET status = EXCLUDED.status,
        message = EXCLUDED.message,
        responded_at = EXCLUDED.responded_at;

-- Mutual friendship rows for anna <-> lena (friend_request_accept writes both
-- directions; seeded the same way). bob is deliberately absent.
INSERT INTO friends (tenant_id, user_id, friend_user_id, relation)
VALUES
    (2, 'a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333', 'friend'),
    (3, 'a3333333-3333-4333-8333-333333333333',
        'a1111111-1111-4111-8111-111111111111', 'friend')
ON CONFLICT (user_id, friend_user_id) DO UPDATE SET relation = EXCLUDED.relation;

-- ─────────────────────────────────────────────────────────────────────────────
-- The grant matrix.
--
-- Types 1-3 have a reader that enforces the grant. Types 4-7 do NOT (ADR 0014
-- §1.3) — they are seeded on purpose so "grant does nothing" is observable
-- rather than theoretical.
-- ─────────────────────────────────────────────────────────────────────────────

-- [1] POSITIVE CONTROL — cross-tenant, active, policy caps the horizon.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333',
        'google_calendar', 'primary', TRUE, '{"days_ahead": 14}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [2] GRANULAR DASHBOARD — block_ids restrict the layout, edit permission.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333',
        'dashboard', 'b1111111-1111-4111-8111-111111111111', TRUE,
        '{"permission": "edit", "block_ids": ["block-shifts", "block-coverage"]}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [3] COLLECTION — slug identifier, view only.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333',
        'collection', 'haustiere', TRUE, '{"permission": "view"}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [4-7] INERT TYPES — grantable, read by nothing. If an adapter is ever wired
-- for one of these, this row goes live immediately (ADR 0014 §6.1).
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES
    ('a1111111-1111-4111-8111-111111111111', 'a3333333-3333-4333-8333-333333333333', 'github_activity', 'primary', TRUE, '{}'::jsonb),
    ('a1111111-1111-4111-8111-111111111111', 'a3333333-3333-4333-8333-333333333333', 'todoist',         'primary', TRUE, '{}'::jsonb),
    ('a1111111-1111-4111-8111-111111111111', 'a3333333-3333-4333-8333-333333333333', 'notes',           'primary', TRUE, '{}'::jsonb),
    ('a1111111-1111-4111-8111-111111111111', 'a3333333-3333-4333-8333-333333333333', 'roadmap',         'primary', TRUE, '{}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [8] REVOKED — is_allowed stays TRUE, revoked_at kills it via grant_is_active.
-- Tests that readers look at revoked_at and not just is_allowed.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, revoked_at, policy)
VALUES ('a2222222-2222-4222-8222-222222222222',
        'a1111111-1111-4111-8111-111111111111',
        'google_calendar', 'primary', TRUE, NOW() - INTERVAL '2 days', '{}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = EXCLUDED.revoked_at;

-- [9] EXPIRED — policy.expires_at in the past. grant_is_active must deny.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a2222222-2222-4222-8222-222222222222',
        'a1111111-1111-4111-8111-111111111111',
        'dashboard', 'b2222222-2222-4222-8222-222222222222', TRUE,
        jsonb_build_object('permission', 'view', 'expires_at',
                         to_char(NOW() - INTERVAL '1 day', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')))
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [10] GRANT WITHOUT FRIENDSHIP — anna granted to bob, who is NOT her friend
-- (he was declined). Tests whether the grant layer and the friendship layer are
-- independent, and whether that independence is intended.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a4444444-4444-4444-8444-444444444444',
        'google_calendar', 'primary', TRUE, '{"days_ahead": 7}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [11] POLICY IMPRECISION — ADR 0014 §1.9. block_ids is a dashboard concept
-- accepted on a calendar grant because _ALLOWED_POLICY_FIELDS is global. The
-- owner believes they narrowed the share; nothing enforces it. This row is the
-- consent bug made visible.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a2222222-2222-4222-8222-222222222222',
        'google_calendar', 'primary', TRUE,
        '{"days_ahead": 30, "block_ids": ["this-means-nothing-on-a-calendar"]}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [12] LEGACY ALIAS TYPE — resource_type stored as a pre-canonicalization alias
-- of collection. Must still resolve through SHARE_RESOURCE_ALIASES.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333',
        'haustiere', 'dienstreisen', TRUE, '{"permission": "view"}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

-- [13] UNREGISTERED TYPE — nothing declares this. A registry (ADR 0014 option A)
-- must refuse it outright rather than fall back to a generic read.
INSERT INTO share_permissions (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, policy)
VALUES ('a1111111-1111-4111-8111-111111111111',
        'a3333333-3333-4333-8333-333333333333',
        'payroll_export', 'primary', TRUE, '{}'::jsonb)
ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
    DO UPDATE SET is_allowed = TRUE, revoked_at = NULL, policy = EXCLUDED.policy;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Report
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    ou.display_name || ' (' || ot.name || ')'  AS owner,
    gu.display_name || ' (' || gt.name || ')'  AS grantee,
    sp.resource_type,
    sp.resource_identifier,
    CASE
        WHEN sp.revoked_at IS NOT NULL          THEN 'REVOKED'
        WHEN (sp.policy->>'expires_at')::timestamptz < NOW() THEN 'EXPIRED'
        WHEN NOT sp.is_allowed                 THEN 'DENIED'
        ELSE 'ACTIVE'
    END                                       AS state,
    sp.policy::text                           AS policy
FROM share_permissions sp
JOIN users ou ON ou.id = sp.owner_user_id
JOIN users gu ON gu.id = sp.grantee_user_id
JOIN tenants ot ON ot.id = ou.tenant_id
JOIN tenants gt ON gt.id = gu.tenant_id
ORDER BY state DESC, sp.resource_type;

SELECT
    (SELECT COUNT(*) FROM tenants)                              AS tenants,
    (SELECT COUNT(*) FROM users)                               AS users,
    (SELECT COUNT(*) FROM friends)                             AS friend_rows,
    (SELECT COUNT(*) FROM friend_requests WHERE status='pending')  AS req_pending,
    (SELECT COUNT(*) FROM friend_requests WHERE status='accepted') AS req_accepted,
    (SELECT COUNT(*) FROM friend_requests WHERE status='declined') AS req_declined,
    (SELECT COUNT(*) FROM share_permissions)                   AS grants_total,
    (SELECT COUNT(*) FROM share_permissions
      WHERE revoked_at IS NULL AND is_allowed
        AND COALESCE((policy->>'expires_at')::timestamptz, NOW() + INTERVAL '1 year') >= NOW()
    )                                                        AS grants_live;
