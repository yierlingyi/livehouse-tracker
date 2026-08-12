-- V1__schema.sql — Contract baseline from V4.4 §4-8
-- Completed by Agent A: dependency tables (users/bands), FK backfill,
-- fn_update_timestamp() trigger, safe_update_live_bands() SECURITY DEFINER
-- function, roles, and schema-level permission grants per V4.4 §7.
--
-- NOTE: the database name used in REVOKE ALL ON DATABASE is taken from
-- V4.4 §7.1 (app_db). Adjust it to the real database name if different.

-- ============================================================
-- 4.1 演出表
-- ============================================================
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
-- Keyset 索引：city + live_date + sort_start_time + id，部分索引限定 published。
-- 查询不得改写 COALESCE(start_time,...)，必须使用生成列 sort_start_time。
CREATE INDEX idx_lives_full_scope_keyset
ON public.lives (city, live_date, sort_start_time, id)
WHERE review_status = 'published';

CREATE INDEX idx_lives_updated_at
ON public.lives (updated_at);

-- ============================================================
-- 4.3 更新时间触发器
-- ============================================================
CREATE OR REPLACE FUNCTION public.fn_update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_lives_updated_at
BEFORE UPDATE ON public.lives
FOR EACH ROW
EXECUTE FUNCTION public.fn_update_timestamp();

-- ============================================================
-- 依赖表（lives.created_by -> users.id，live_bands.band_id -> bands.id）
-- ============================================================
CREATE TABLE public.users (
    id          BIGSERIAL PRIMARY KEY,
    username    VARCHAR(100) NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.bands (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 补建外键：lives.created_by -> users(id)（V4.4 §4.1）
ALTER TABLE public.lives
    ADD CONSTRAINT fk_lives_created_by
    FOREIGN KEY (created_by) REFERENCES public.users(id);

-- ============================================================
-- 5.1 版本计数器（单行原子递增，UPDATE ... RETURNING version）
-- ============================================================
CREATE TABLE public.sync_version_counter (
    id       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    version  BIGINT NOT NULL
);
INSERT INTO public.sync_version_counter (id, version) VALUES (TRUE, 0);

-- ============================================================
-- 5.2 变更日志 (CDC)
-- ============================================================
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

-- ============================================================
-- 6 日志保留状态（retention_floor_version 过期判定）
-- ============================================================
CREATE TABLE public.sync_retention_state (
    id                       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    retention_floor_version  BIGINT NOT NULL DEFAULT 0,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.sync_retention_state (id, retention_floor_version) VALUES (TRUE, 0);

-- ============================================================
-- 8.1 演出-乐队关系表
-- ============================================================
CREATE TABLE public.live_bands (
    live_id     BIGINT NOT NULL REFERENCES public.lives(id) ON DELETE CASCADE,
    band_id     BIGINT NOT NULL,
    sort_order  SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (live_id, band_id)
);

-- 补建外键：live_bands.band_id -> bands(id)（V4.4 §8.1）
ALTER TABLE public.live_bands
    ADD CONSTRAINT fk_live_bands_band
    FOREIGN KEY (band_id) REFERENCES public.bands(id);

-- ============================================================
-- 角色（V4.4 §7.2/§7.3）
-- ============================================================
CREATE ROLE api_role NOLOGIN;
CREATE ROLE migration_role NOLOGIN;
CREATE ROLE app_definer NOLOGIN;

-- ============================================================
-- 7.1 Schema 权限
-- 只允许迁移角色在 public schema 创建对象，普通用户仅 USAGE（PG15+ 默认）。
-- ============================================================
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE app_db FROM PUBLIC;
GRANT CREATE ON SCHEMA public TO migration_role;

-- ============================================================
-- 8.2 safe_update_live_bands (SECURITY DEFINER)
--
-- 职责：维护 live_bands 关系表与 lives.band_names 冗余列的一致性。
-- 调用方所在业务事务仍必须自行写入 sync_changes（V4.4 §8.2 说明）。
-- 安全：SECURITY DEFINER + 固定 search_path，参数强校验，禁止注入。
-- ============================================================
CREATE OR REPLACE FUNCTION public.safe_update_live_bands(
    p_live_id BIGINT,
    p_bands JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_band_count INT;
BEGIN
    -- 参数校验：live_id 必须为正整数
    IF p_live_id IS NULL OR p_live_id <= 0 THEN
        RAISE EXCEPTION 'INVALID_LIVE_ID';
    END IF;

    -- 参数校验：p_bands 必须是 JSON 数组
    IF p_bands IS NULL OR jsonb_typeof(p_bands) <> 'array' THEN
        RAISE EXCEPTION 'INVALID_BANDS';
    END IF;

    SELECT jsonb_array_length(p_bands) INTO v_band_count;

    -- 参数校验：最多 50 个乐队
    IF v_band_count > 50 THEN
        RAISE EXCEPTION 'TOO_MANY_BANDS';
    END IF;

    -- 锁定 lives 行，防止并发修改同一演出的乐队阵容
    PERFORM 1
    FROM public.lives
    WHERE id = p_live_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'LIVE_NOT_FOUND';
    END IF;

    -- 去重（DISTINCT ON band_id），band_id 必须为纯数字，防止非法类型转换
    CREATE TEMP TABLE tmp_live_bands ON COMMIT DROP AS
    SELECT
        DISTINCT ON ((item->>'band_id')::BIGINT)
        (item->>'band_id')::BIGINT AS band_id,
        COALESCE((item->>'sort_order')::SMALLINT, 0) AS sort_order
    FROM jsonb_array_elements(p_bands) AS item
    WHERE item ? 'band_id'
      AND (item->>'band_id') ~ '^[0-9]+$'
    ORDER BY (item->>'band_id')::BIGINT, COALESCE((item->>'sort_order')::SMALLINT, 0);

    -- 校验所有 band_id 必须存在于 bands 表
    IF EXISTS (
        SELECT 1
        FROM tmp_live_bands t
        LEFT JOIN public.bands b ON b.id = t.band_id
        WHERE b.id IS NULL
    ) THEN
        RAISE EXCEPTION 'UNKNOWN_BAND_ID';
    END IF;

    -- 删除集合外已存在的关系
    DELETE FROM public.live_bands lb
    WHERE lb.live_id = p_live_id
      AND NOT EXISTS (
          SELECT 1
          FROM tmp_live_bands t
          WHERE t.band_id = lb.band_id
      );

    -- 写入 / 更新关系（PK 冲突则刷新 sort_order）
    INSERT INTO public.live_bands (live_id, band_id, sort_order)
    SELECT p_live_id, band_id, sort_order
    FROM tmp_live_bands
    ON CONFLICT (live_id, band_id)
    DO UPDATE SET sort_order = EXCLUDED.sort_order;

    -- 刷新 lives.band_names 冗余列（触发 trg_lives_updated_at 同步 updated_at）
    UPDATE public.lives
    SET band_names = (
        SELECT COALESCE(
            jsonb_agg(b.name ORDER BY lb.sort_order, lb.band_id),
            '[]'::jsonb
        )
        FROM public.live_bands lb
        JOIN public.bands b ON b.id = lb.band_id
        WHERE lb.live_id = p_live_id
    )
    WHERE id = p_live_id;
END;
$$;

-- 仅 api_role 可执行；PUBLIC 一律拒绝
REVOKE ALL ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) TO api_role;
