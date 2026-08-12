-- V1__schema.sql — Contract baseline from V4.4 §4-8
-- Agent A completes: permission grants, SECURITY DEFINER ownership, function bodies

-- 4.1 演出表
CREATE TABLE public.lives (
    id                BIGSERIAL PRIMARY KEY,
    livehouse_id      BIGINT NOT NULL,
    live_date         DATE NOT NULL,
    start_time        TIME,
    sort_start_time   TIME GENERATED ALWAYS AS (
        COALESCE(start_time, TIME '23:59:59')
    ) STORED,
    title             VARCHAR(150) NOT NULL,
    ticket_price      VARCHAR(50),
    ticket_url        VARCHAR(255),
    poster_image_url  VARCHAR(255),
    city              VARCHAR(50) NOT NULL,
    band_names        JSONB NOT NULL DEFAULT '[]'::jsonb,
    status            VARCHAR(16) NOT NULL DEFAULT 'announced'
                      CHECK (status IN ('announced','on_sale','completed','cancelled')),
    review_status     VARCHAR(16) NOT NULL DEFAULT 'draft'
                      CHECK (review_status IN ('draft','published','hidden')),
    created_by        BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4.2 索引
CREATE INDEX idx_lives_full_scope_keyset
ON public.lives (city, live_date, sort_start_time, id)
WHERE review_status = 'published';

CREATE INDEX idx_lives_updated_at
ON public.lives (updated_at);

-- 4.3 更新时间触发器 (function body filled by Agent A)
-- Agent A: implement fn_update_timestamp() per §4.3

-- 5.1 版本计数器
CREATE TABLE public.sync_version_counter (
    id       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    version  BIGINT NOT NULL
);
INSERT INTO public.sync_version_counter (id, version) VALUES (TRUE, 0);

-- 5.2 变更日志
CREATE TABLE public.sync_changes (
    version      BIGINT PRIMARY KEY,
    entity_type  VARCHAR(32) NOT NULL CHECK (entity_type IN ('live')),
    entity_id    BIGINT NOT NULL,
    action       VARCHAR(16) NOT NULL CHECK (action IN ('upsert', 'delete')),
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sync_changes_entity_latest
ON public.sync_changes (entity_type, entity_id, version DESC);

CREATE INDEX idx_sync_changes_version
ON public.sync_changes (version);

-- 6 日志保留状态
CREATE TABLE public.sync_retention_state (
    id                       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    retention_floor_version  BIGINT NOT NULL DEFAULT 0,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.sync_retention_state (id, retention_floor_version) VALUES (TRUE, 0);

-- 8.1 演出-乐队关系表
CREATE TABLE public.live_bands (
    live_id     BIGINT NOT NULL REFERENCES public.lives(id) ON DELETE CASCADE,
    band_id     BIGINT NOT NULL,
    sort_order  SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (live_id, band_id)
);

-- Agent A TODO:
-- 1. Add bands table (referenced by live_bands.band_id FK)
-- 2. Add users table (referenced by lives.created_by FK)
-- 3. Implement fn_update_timestamp()
-- 4. Implement safe_update_live_bands() SECURITY DEFINER function (§8.2)
-- 5. Add all permission grants per §7
-- 6. Create roles: api_role, migration_role, app_definer (NOLOGIN)
-- 7. REVOKE CREATE ON SCHEMA public FROM PUBLIC
-- 8. REVOKE ALL ON DATABASE FROM PUBLIC
-- 9. GRANT CREATE ON SCHEMA public TO migration_role
