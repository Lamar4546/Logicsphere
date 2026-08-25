-- LogiSphere AI v2.0 — Thin Slice Schema
-- Scope: Command Center + Shipment Delay Workflow (SRS §10.2)
-- Entities drawn from SRS §12.1; only what this slice needs is included.
-- Extend incrementally as later slices (inventory, procurement, documents) are built.

-- ============================================================
-- 1. ORGANIZATION & USERS  (SRS §8.1)
-- ============================================================

create table organizations (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    industry        text,
    country         text,
    logistics_profile jsonb default '{}',   -- freight modes, regions, default carriers, etc.
    created_at      timestamptz not null default now()
);

create type user_role as enum (
    'admin',
    'ops_manager',
    'supply_chain_user',
    'viewer'
);

create table app_users (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    email           text not null unique,
    -- Password identity is owned by Supabase Auth; this legacy column remains
    -- nullable only for compatibility with older installations.
    password_hash   text,
    full_name       text not null,
    role            user_role not null default 'viewer',
    created_at      timestamptz not null default now()
);

create index idx_app_users_org on app_users(organization_id);

-- ============================================================
-- 2. CARRIERS & SHIPMENTS  (SRS §8.3, §12.1)
-- ============================================================

create table carriers (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    name            text not null,
    mode            text,   -- 'ocean' | 'air' | 'road' | 'rail'
    created_at      timestamptz not null default now()
);

create type shipment_status as enum (
    'planned',
    'in_transit',
    'at_risk',
    'delayed',
    'delivered',
    'exception'
);

create table shipments (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id) on delete cascade,
    reference_number    text not null,
    carrier_id          uuid references carriers(id),
    origin              text,
    destination         text,
    mode                text,
    status              shipment_status not null default 'planned',
    eta_original        timestamptz,
    eta_current         timestamptz,
    departed_at         timestamptz,
    last_event_at       timestamptz,
    last_event_description text,
    raw_source_payload  jsonb,              -- provenance: original integration payload
    source_system       text,               -- SRS §12.2 data provenance
    synced_at           timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index idx_shipments_org_status on shipments(organization_id, status);

-- ============================================================
-- 3. RISK / ALERTS  (SRS §8.11, §12.1)
-- ============================================================

create type risk_severity as enum ('low', 'medium', 'high', 'critical');
create type risk_status as enum ('open', 'acknowledged', 'resolved');

create table risk_alerts (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    entity_type     text not null,      -- 'shipment' | 'inventory' | 'supplier' | ... (slice: 'shipment' only)
    entity_id       uuid not null,
    risk_type       text not null,      -- e.g. 'delay'
    severity        risk_severity not null,
    status          risk_status not null default 'open',
    description     text not null,
    detected_by     text not null,      -- agent name, e.g. 'risk_agent'
    detected_at     timestamptz not null default now(),
    created_at      timestamptz not null default now()
);

create index idx_risk_alerts_org_status on risk_alerts(organization_id, status);
create index idx_risk_alerts_entity on risk_alerts(entity_type, entity_id);

-- ============================================================
-- 4. AI RECOMMENDATIONS  (SRS §8.12, §14.2)
-- ============================================================

create type recommendation_status as enum (
    'pending_approval',
    'approved',
    'edited',
    'rejected',
    'deferred'
);

create table ai_recommendations (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id) on delete cascade,
    entity_type         text not null,
    entity_id           uuid not null,
    risk_alert_id       uuid references risk_alerts(id),
    generated_by        text not null,          -- e.g. 'central_ai_logistics_manager'
    summary             text not null,          -- business-language explanation (NFR-021)
    recommended_action  text not null,
    facts               jsonb default '[]',     -- SRS §14.2: facts vs predictions vs recommendations
    predictions         jsonb default '[]',
    confidence          numeric,                -- 0.0 - 1.0, nullable if not applicable
    status              recommendation_status not null default 'pending_approval',
    reviewed_by         uuid references app_users(id),
    reviewed_at         timestamptz,
    review_notes        text,
    created_at          timestamptz not null default now()
);

create index idx_recommendations_org_status on ai_recommendations(organization_id, status);

-- ============================================================
-- 5. COMMUNICATIONS  (SRS §8.9 — draft only in this slice)
-- ============================================================

create type communication_status as enum ('draft', 'approved', 'sent', 'rejected');

create table communications (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id) on delete cascade,
    related_entity_type text not null,
    related_entity_id   uuid not null,
    recommendation_id   uuid references ai_recommendations(id),
    channel             text not null default 'email',
    recipient           text,
    subject             text,
    body                text not null,
    status              communication_status not null default 'draft',
    approved_by         uuid references app_users(id),
    approved_at         timestamptz,
    created_at          timestamptz not null default now()
);

-- ============================================================
-- 6. WORKFLOWS & TASKS  (SRS §8.13)
-- ============================================================

create type workflow_status as enum ('pending', 'running', 'completed', 'failed');

create table workflows (
    id                  uuid primary key default gen_random_uuid(),
    organization_id     uuid not null references organizations(id) on delete cascade,
    workflow_type       text not null,          -- e.g. 'shipment_delay'
    entity_type         text not null,
    entity_id           uuid not null,
    recommendation_id   uuid references ai_recommendations(id),
    status              workflow_status not null default 'pending',
    steps_log           jsonb default '[]',     -- ordered log of steps executed, for audit
    started_at          timestamptz,
    completed_at        timestamptz,
    created_at          timestamptz not null default now()
);

create table tasks (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    assigned_to     uuid references app_users(id),
    title           text not null,
    description     text,
    related_entity_type text,
    related_entity_id   uuid,
    is_done         boolean not null default false,
    created_at      timestamptz not null default now()
);

-- ============================================================
-- 7. AUDIT  (SRS §13.1 NFR-006, §14.2)
-- ============================================================

create table audit_events (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    actor_type      text not null,      -- 'user' | 'agent' | 'system'
    actor_id        text,               -- user id or agent name
    event_type      text not null,      -- 'recommendation_created' | 'recommendation_approved' | 'workflow_executed' | ...
    entity_type     text,
    entity_id       uuid,
    detail          jsonb default '{}',
    created_at      timestamptz not null default now()
);

create index idx_audit_events_org on audit_events(organization_id, created_at desc);

-- ============================================================
-- 8. AGENT RUNS  (SRS §12.1 — observability into agent execution)
-- ============================================================

create table agent_runs (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    agent_name      text not null,      -- 'transportation_agent' | 'risk_agent' | 'communication_agent' | 'central_ai_logistics_manager'
    entity_type     text,
    entity_id       uuid,
    input_summary   jsonb,
    output_summary  jsonb,
    output_kind     text,               -- 'observation' | 'prediction' | 'recommendation' | 'action' (SRS §7.1)
    status          text not null default 'success',  -- 'success' | 'failed'
    error_message   text,
    started_at      timestamptz not null default now(),
    completed_at    timestamptz
);

create index idx_agent_runs_org on agent_runs(organization_id, started_at desc);

-- ============================================================
-- Row Level Security (tenant isolation — NFR-003)
-- ============================================================

alter table organizations enable row level security;
alter table app_users enable row level security;
alter table shipments enable row level security;
alter table risk_alerts enable row level security;
alter table ai_recommendations enable row level security;
alter table communications enable row level security;
alter table workflows enable row level security;
alter table tasks enable row level security;
alter table audit_events enable row level security;
alter table agent_runs enable row level security;

-- Policy pattern: a user may only see rows in their own organization.
-- Backend uses the service-role key for agent writes; these policies
-- protect any direct client-side Supabase access.

create or replace function current_org_id() returns uuid as $$
    select organization_id from app_users where id = auth.uid();
$$ language sql stable;

create policy org_isolation_app_users on app_users
    for select using (organization_id = current_org_id());
create policy org_isolation_shipments on shipments
    for all using (organization_id = current_org_id());
create policy org_isolation_risk_alerts on risk_alerts
    for all using (organization_id = current_org_id());
create policy org_isolation_ai_recommendations on ai_recommendations
    for all using (organization_id = current_org_id());
create policy org_isolation_communications on communications
    for all using (organization_id = current_org_id());
create policy org_isolation_workflows on workflows
    for all using (organization_id = current_org_id());
create policy org_isolation_tasks on tasks
    for all using (organization_id = current_org_id());
create policy org_isolation_audit_events on audit_events
    for select using (organization_id = current_org_id());
create policy org_isolation_agent_runs on agent_runs
    for select using (organization_id = current_org_id());
