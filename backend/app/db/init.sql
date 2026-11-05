-- =====================================================================
-- 骑手招聘 Agent 化信息收集平台 — 数据库骨架（契约 v1）
-- 幂等脚本：容器首次启动与 API 启动时都会执行，可重复运行。
-- 仅含合成/脱敏数据，不含任何真实个人信息。
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- 员工（RBAC + 城市/站点数据域）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    salt          text NOT NULL,
    display_name  text NOT NULL,
    role          text NOT NULL CHECK (role IN ('admin', 'city_manager', 'station_operator', 'viewer')),
    city          text NOT NULL,                       -- '*' = 全城市
    station_ids   uuid[] NOT NULL DEFAULT '{}',
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 站点：open_quota 是预约名额，扣减必须走条件 UPDATE（库级原子）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    city       text NOT NULL,
    area       text NOT NULL,
    lat        double precision NOT NULL,
    lng        double precision NOT NULL,
    open_quota integer NOT NULL DEFAULT 0 CHECK (open_quota >= 0),
    address    text,
    distance_km double precision NOT NULL DEFAULT 0,
    manager_virtual_no text,
    manager_display_no text,
    slot_capacity integer NOT NULL DEFAULT 3,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name)
);

-- 兼容旧库（幂等 ALTER）
ALTER TABLE stations ADD COLUMN IF NOT EXISTS address text;
ALTER TABLE stations ADD COLUMN IF NOT EXISTS distance_km double precision NOT NULL DEFAULT 0;
ALTER TABLE stations ADD COLUMN IF NOT EXISTS manager_virtual_no text;
ALTER TABLE stations ADD COLUMN IF NOT EXISTS manager_display_no text;
ALTER TABLE stations ADD COLUMN IF NOT EXISTS slot_capacity integer NOT NULL DEFAULT 3;

-- ---------------------------------------------------------------------
-- 保险箱：token（确定性 HMAC）-> 密文；明文只以密文形式落库
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vault_tokens (
    token      text PRIMARY KEY,
    pii_type   text NOT NULL CHECK (pii_type IN ('phone', 'id_card', 'name', 'address')),
    ciphertext text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 候选人（契约实体；name_token / phone_token 为保险箱令牌）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name_token       text,
    phone_token      text UNIQUE,
    birth_ym         text CHECK (birth_ym IS NULL OR birth_ym ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    area_text        text,
    job_type         text CHECK (job_type IN ('fulltime', 'parttime', 'undecided')),
    has_ebike        boolean,
    start_text       text,
    experience_text  text,
    health_cert      text CHECK (health_cert IN ('none', 'holding', 'processing', 'unknown')),
    source_channel   text NOT NULL DEFAULT 'manual',
    station_id       uuid REFERENCES stations (id) ON DELETE SET NULL,
    city             text NOT NULL DEFAULT '上海',
    status           text NOT NULL DEFAULT 'new'
                     CHECK (status IN ('new', 'collecting', 'complete', 'booked', 'interviewed', 'hired', 'rejected', 'handoff')),
    profile_complete boolean NOT NULL DEFAULT false,
    is_minor         boolean NOT NULL DEFAULT false,
    consent_version  text,
    consent_at       timestamptz,
    retention_until  timestamptz,                       -- NULL = 永久保留（已入职/已交接）
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_candidates_city_status ON candidates (city, status);
CREATE INDEX IF NOT EXISTS idx_candidates_station ON candidates (station_id);
CREATE INDEX IF NOT EXISTS idx_candidates_retention ON candidates (retention_until) WHERE retention_until IS NOT NULL;

-- 兼容旧库：H5 允许先「告知同意」建空档，姓名/手机号随后由对话补齐
ALTER TABLE candidates ALTER COLUMN name_token DROP NOT NULL;
ALTER TABLE candidates ALTER COLUMN phone_token DROP NOT NULL;

-- ---------------------------------------------------------------------
-- 预约（同一候选人同一时刻只允许一个有效预约）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    station_id   uuid NOT NULL REFERENCES stations (id) ON DELETE RESTRICT,
    slot_start   timestamptz NOT NULL,
    status       text NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'cancelled', 'done', 'no_show')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_active_candidate
    ON bookings (candidate_id) WHERE status = 'booked';
CREATE INDEX IF NOT EXISTS idx_bookings_station_slot ON bookings (station_id, slot_start);

-- ---------------------------------------------------------------------
-- 事件 outbox（事务内写事件 + 去重键；后台投递 Webhook）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      text NOT NULL,
    aggregate_type  text NOT NULL,
    aggregate_id    uuid NOT NULL,
    payload         jsonb NOT NULL,
    dedupe_key      text NOT NULL UNIQUE,
    attempts        integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox_events (next_attempt_at) WHERE delivered_at IS NULL;

-- ---------------------------------------------------------------------
-- Webhook 投递记录（(event_id, endpoint) 去重 => 重复投递幂等）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     uuid NOT NULL REFERENCES outbox_events (id) ON DELETE CASCADE,
    endpoint     text NOT NULL,
    dedupe_key   text NOT NULL UNIQUE,
    status       text NOT NULL DEFAULT 'delivered' CHECK (status IN ('delivered', 'failed', 'duplicate')),
    http_status  integer,
    attempts     integer NOT NULL DEFAULT 0,
    last_error   text,
    delivered_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 只追加哈希链审计（UPDATE / DELETE 被触发器拒绝）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id         bigserial PRIMARY KEY,
    actor      text NOT NULL,
    action     text NOT NULL,
    resource   text NOT NULL,
    payload    text NOT NULL DEFAULT '{}',  -- 规范化 JSON 文本（哈希链参与哈希，故用精确字节）
    prev_hash  text NOT NULL,
    hash       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % denied', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;
CREATE TRIGGER trg_audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

-- 旧库迁移：payload 需要精确字节参与哈希，jsonb 会被重排/加空格导致链校验失败。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_log' AND column_name = 'payload' AND data_type = 'jsonb'
    ) THEN
        ALTER TABLE audit_log ALTER COLUMN payload TYPE text USING payload::text;
        RAISE NOTICE 'audit_log.payload migrated from jsonb to text; old rows keep historical bytes';
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 政策知识库（pgvector + 关键词混合检索；回答必须带出处）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_docs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_name    text NOT NULL,
    doc_version text NOT NULL,
    section     text NOT NULL,
    chunk       text NOT NULL,
    effective_date text,
    disclaimer  text,
    embedding   vector(384),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_name, doc_version, section)
);

ALTER TABLE policy_docs ADD COLUMN IF NOT EXISTS effective_date text;
ALTER TABLE policy_docs ADD COLUMN IF NOT EXISTS disclaimer text;

CREATE INDEX IF NOT EXISTS idx_policy_docs_embedding ON policy_docs USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------
-- Agent 会话与消息（消息原文保留 30 天）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_sessions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id  uuid REFERENCES candidates (id) ON DELETE CASCADE,
    stage         text NOT NULL DEFAULT 'collecting',
    context       jsonb NOT NULL DEFAULT '{}'::jsonb,
    client_replies jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'handoff', 'terminated_minor')),
    llm_mode      text NOT NULL DEFAULT 'mock',
    first_user_at timestamptz,
    first_reply_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS client_replies jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS agent_messages (
    id              bigserial PRIMARY KEY,
    session_id      uuid NOT NULL REFERENCES agent_sessions (id) ON DELETE CASCADE,
    role            text NOT NULL CHECK (role IN ('user', 'assistant')),
    text_redacted   text NOT NULL,
    raw_text        text,
    llm_payload     jsonb,
    client_message_id text,
    latency_ms      integer,
    redacted_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS client_message_id text;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_messages_client_id
    ON agent_messages (session_id, client_message_id) WHERE client_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages (session_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_retention ON agent_messages (created_at) WHERE raw_text IS NOT NULL;

-- ---------------------------------------------------------------------
-- 合成脱敏样本库（≥200 条，供脱敏召回跑分与演示；纯合成）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS synthetic_samples (
    id         bigserial PRIMARY KEY,
    raw_text   text NOT NULL,
    expected   jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 保留期执行记录
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retention_runs (
    id                 bigserial PRIMARY KEY,
    as_of              timestamptz NOT NULL,
    deleted_candidates integer NOT NULL DEFAULT 0,
    redacted_messages  integer NOT NULL DEFAULT 0,
    run_at             timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- KPI 单点定义（7 个指标的唯一口径；API 只许 SELECT 此视图）
-- 1 进线数 2 AI 接待率 3 报名完整率 4 AI 首响均值 5 AI 首响 P95
-- 6 预约到面率 7 转人工率 8 入职数
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW kpi_summary AS
WITH
leads AS (
    SELECT count(*)::double precision AS leads_in FROM candidates
),
reception AS (
    SELECT
        count(DISTINCT s.candidate_id)::double precision AS ai_received,
        coalesce(avg(extract(epoch FROM (s.first_reply_at - s.first_user_at)) * 1000.0), 0)::double precision
            AS first_response_avg_ms,
        coalesce(percentile_cont(0.95) WITHIN GROUP (
            ORDER BY extract(epoch FROM (s.first_reply_at - s.first_user_at)) * 1000.0
        ), 0)::double precision AS first_response_p95_ms,
        count(DISTINCT s.candidate_id) FILTER (WHERE s.status = 'handoff')::double precision AS handoff_candidates
    FROM agent_sessions s
    WHERE s.first_user_at IS NOT NULL AND s.first_reply_at IS NOT NULL
),
complete_rate AS (
    SELECT count(*) FILTER (WHERE profile_complete)::double precision AS profile_complete_count
    FROM candidates
),
booking_stat AS (
    SELECT
        count(*) FILTER (WHERE status = 'done')::double precision AS arrived,
        count(*) FILTER (WHERE status IN ('done', 'no_show'))::double precision AS finished
    FROM bookings
),
hired AS (
    SELECT count(*) FILTER (WHERE status = 'hired')::double precision AS hired_count FROM candidates
)
SELECT
    leads.leads_in,
    CASE WHEN leads.leads_in = 0 THEN 0 ELSE reception.ai_received / leads.leads_in END AS ai_reception_rate,
    CASE WHEN leads.leads_in = 0 THEN 0 ELSE complete_rate.profile_complete_count / leads.leads_in END AS profile_complete_rate,
    reception.first_response_avg_ms AS ai_first_response_avg_ms,
    reception.first_response_p95_ms AS ai_first_response_p95_ms,
    CASE WHEN booking_stat.finished = 0 THEN 0 ELSE booking_stat.arrived / booking_stat.finished END AS booking_show_rate,
    CASE WHEN leads.leads_in = 0 THEN 0 ELSE reception.handoff_candidates / leads.leads_in END AS handoff_rate,
    hired.hired_count AS hired_count
FROM leads, reception, complete_rate, booking_stat, hired;
