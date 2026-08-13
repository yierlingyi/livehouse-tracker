\encoding UTF8
SET client_encoding = 'UTF8';

-- V3__platform.sql — 三端平台扩展（认证/乐队资料与 Live 管理/拼盘/场地/CMS/上传）
-- Applied AFTER V1__schema.sql + V2__permissions.sql.
--
-- 设计约束（frontend_refactor_plan §七 + docs/api_contract.md §0）：
--   * 新增实体一律不进 CDC 同步（不触碰 sync_changes / /full /sync），走普通 REST。
--   * lives 仅新增展示字段 kind（poster_image_url / ticket_url 已在 V1 存在），
--     不得改动 /full /sync 的 SELECT 列与过滤逻辑（仍按 review_status='published'）。
--   * 下架/强制下架 = status + review_status → 'draft'，/sync Scope 投影自动以 delete 下发。
--   * api_role 保持表级只读；所有写操作走 SECURITY DEFINER 函数（owner=app_definer，固定 search_path）。
--   * 函数幂等、参数化，不信任客户端、不拼接 SQL。
--
-- 注意：V1 的 lives.status CHECK 不允许 'draft'，此处 DROP 后以同名重建（含 'draft'）。
-- 该改动只放宽 status 枚举，不影响 /full /sync 的 review_status='published' 过滤。

-- ============================================================
-- 角色（幂等，沿用 V2 范式）
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_definer') THEN
        EXECUTE 'CREATE ROLE app_definer NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'migration_role') THEN
        EXECUTE 'CREATE ROLE migration_role NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'api_role') THEN
        EXECUTE 'CREATE ROLE api_role NOLOGIN';
    END IF;
END
$$;

-- ============================================================
-- 0.5 Schema USAGE（关键缺口修复）
--     测试库经 DROP/CREATE SCHEMA public 后，PUBLIC 对 public schema 无 USAGE，
--     api_role 无法 SELECT、SECURITY DEFINER 函数（含 V1 safe_update_live_bands）
--     以 app_definer 身份也无法访问任何表。此处显式授予 USAGE，不改动 /full /sync 语义。
-- ============================================================
GRANT USAGE ON SCHEMA public TO api_role;
GRANT USAGE ON SCHEMA public TO app_definer;
GRANT USAGE ON SCHEMA public TO migration_role;

-- ============================================================
-- 1. 乐队账号（Band Portal / Admin Console 共用）
--    id 与 users.id 对齐（safe_register_band 同时写 users，供 lives.created_by FK）
-- ============================================================
CREATE TABLE IF NOT EXISTS public.band_accounts (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    band_name     VARCHAR(150) NOT NULL,
    intro         TEXT,
    qq_bind       VARCHAR(50),
    cover_url     VARCHAR(255),
    members       JSONB NOT NULL DEFAULT '[]'::jsonb,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','active','rejected','disabled')),
    role          VARCHAR(16) NOT NULL DEFAULT 'band'
                  CHECK (role IN ('band','admin')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_band_accounts_updated_at ON public.band_accounts;
CREATE TRIGGER trg_band_accounts_updated_at
BEFORE UPDATE ON public.band_accounts
FOR EACH ROW EXECUTE FUNCTION public.fn_update_timestamp();

-- ============================================================
-- 2. 场地（公开只读 + Admin 写）
--    city 用于确定场地所在城市（乐队建 Live 时继承，决定 /full /sync 城市归属）
-- ============================================================
CREATE TABLE IF NOT EXISTS public.livehouses (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(150) NOT NULL,
    city          VARCHAR(50) NOT NULL DEFAULT 'Tokyo',
    address       VARCHAR(255),
    phone         VARCHAR(50),
    image_url     VARCHAR(255),
    intro         TEXT,
    floorplan_url VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 3. lives 增列（幂等）——仅新增展示字段，不改动 /full /sync 投影
-- ============================================================
ALTER TABLE public.lives
    ADD COLUMN IF NOT EXISTS poster_image_url TEXT;

ALTER TABLE public.lives
    ADD COLUMN IF NOT EXISTS ticket_url TEXT;

ALTER TABLE public.lives
    ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'normal'
    CHECK (kind IN ('normal','coop'));

-- status 枚举放宽：加入 'draft'（下架/草稿状态）。同名重建，保持约束名稳定。
ALTER TABLE public.lives DROP CONSTRAINT IF EXISTS lives_status_check;
ALTER TABLE public.lives
    ADD CONSTRAINT lives_status_check
    CHECK (status IN ('draft','announced','on_sale','completed','cancelled'));

-- ============================================================
-- 4. Live 曲目表（live 详情 setlist；拼盘各队曲目也归入此表）
-- ============================================================
CREATE TABLE IF NOT EXISTS public.live_setlist (
    live_id     BIGINT NOT NULL REFERENCES public.lives(id) ON DELETE CASCADE,
    position    INT NOT NULL,
    song_title  VARCHAR(255) NOT NULL,
    band_id     BIGINT,
    PRIMARY KEY (live_id, position)
);

-- ============================================================
-- 5. 拼盘（Co-op）
-- ============================================================
CREATE TABLE IF NOT EXISTS public.coop_events (
    id                    BIGSERIAL PRIMARY KEY,
    live_id               BIGINT NOT NULL REFERENCES public.lives(id) ON DELETE CASCADE,
    initiator_account_id  BIGINT NOT NULL REFERENCES public.band_accounts(id) ON DELETE CASCADE,
    status                VARCHAR(16) NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft','published','offline')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.coop_invites (
    id              BIGSERIAL PRIMARY KEY,
    event_id        BIGINT NOT NULL REFERENCES public.coop_events(id) ON DELETE CASCADE,
    band_account_id BIGINT NOT NULL REFERENCES public.band_accounts(id) ON DELETE CASCADE,
    invite_status   VARCHAR(16) NOT NULL DEFAULT 'invited'
                    CHECK (invite_status IN ('invited','agreed','rejected','exit_requested','removed')),
    songs           JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, band_account_id)
);

DROP TRIGGER IF EXISTS trg_coop_invites_updated_at ON public.coop_invites;
CREATE TRIGGER trg_coop_invites_updated_at
BEFORE UPDATE ON public.coop_invites
FOR EACH ROW EXECUTE FUNCTION public.fn_update_timestamp();

-- ============================================================
-- 6. CMS（同好群 / 赞助 / 项目声明）
-- ============================================================
CREATE TABLE IF NOT EXISTS public.community_groups (
    id         BIGSERIAL PRIMARY KEY,
    city       VARCHAR(50) NOT NULL,
    platform   VARCHAR(10) NOT NULL CHECK (platform IN ('wechat','qq')),
    group_id   VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.sponsor_content (
    id            INT PRIMARY KEY DEFAULT 1,
    thanks_text   TEXT,
    qr_image_urls JSONB NOT NULL DEFAULT '[]'::jsonb
);
INSERT INTO public.sponsor_content (id, thanks_text, qr_image_urls)
VALUES (1, '', '[]'::jsonb)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.project_declaration (
    id         INT PRIMARY KEY DEFAULT 1,
    intro      TEXT,
    github_url TEXT,
    author     TEXT,
    license    TEXT
);
INSERT INTO public.project_declaration (id, intro, github_url, author, license)
VALUES (1, '', '', '', '')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 7. api_role 表级只读授权（新增表；api_role 绝无 INSERT/UPDATE/DELETE）
-- ============================================================
GRANT SELECT ON public.band_accounts       TO api_role;
GRANT SELECT ON public.livehouses          TO api_role;
GRANT SELECT ON public.lives               TO api_role;
GRANT SELECT ON public.live_setlist        TO api_role;
GRANT SELECT ON public.community_groups    TO api_role;
GRANT SELECT ON public.sponsor_content     TO api_role;
GRANT SELECT ON public.project_declaration TO api_role;
GRANT SELECT ON public.coop_events         TO api_role;
GRANT SELECT ON public.coop_invites        TO api_role;

REVOKE INSERT, UPDATE, DELETE ON public.band_accounts       FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.livehouses          FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.lives               FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.live_setlist        FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.community_groups    FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.sponsor_content     FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.project_declaration FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.coop_events         FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.coop_invites        FROM api_role;

-- ============================================================
-- 8. app_definer 最小写权限（SECURITY DEFINER 函数执行所需）
-- ============================================================
GRANT USAGE, SELECT, UPDATE ON SEQUENCE public.users_id_seq TO app_definer;
-- setval()（safe_register_band 同步 band_accounts_id_seq 与 users_id_seq）需要 UPDATE 权限
GRANT USAGE, SELECT, UPDATE ON SEQUENCE public.band_accounts_id_seq TO app_definer;
GRANT USAGE, SELECT ON SEQUENCE public.lives_id_seq TO app_definer;
GRANT USAGE, SELECT ON SEQUENCE public.livehouses_id_seq TO app_definer;
GRANT USAGE, SELECT ON SEQUENCE public.community_groups_id_seq TO app_definer;
GRANT USAGE, SELECT ON SEQUENCE public.coop_events_id_seq TO app_definer;
GRANT USAGE, SELECT ON SEQUENCE public.coop_invites_id_seq TO app_definer;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.band_accounts       TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.livehouses          TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.lives               TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.live_setlist        TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.community_groups    TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sponsor_content     TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.project_declaration TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coop_events         TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.coop_invites        TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.users TO app_definer;

-- CDC 写（safe_cdc_write_live 内部）：app_definer 需要写 sync_changes / 版本计数器。
-- UPDATE ... WHERE id=TRUE RETURNING version 需要读取 id/version 列 → SELECT 一并授予。
GRANT INSERT ON public.sync_changes TO app_definer;
GRANT SELECT, UPDATE ON public.sync_version_counter TO app_definer;

-- ============================================================
-- 9. 安全函数
-- ============================================================

-- 9.0 内部 CDC helper（不授予 api_role —— 只能被上层 SECURITY DEFINER 函数调用）
CREATE OR REPLACE FUNCTION public.safe_cdc_write_live(
    p_live_id BIGINT,
    p_action TEXT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_version BIGINT;
BEGIN
    IF p_action NOT IN ('upsert','delete') THEN
        RAISE EXCEPTION 'INVALID_ACTION';
    END IF;
    UPDATE public.sync_version_counter
    SET version = version + 1
    WHERE id = TRUE
    RETURNING version INTO v_version;
    INSERT INTO public.sync_changes (version, entity_type, entity_id, action)
    VALUES (v_version, 'live', p_live_id, p_action);
END;
$$;

REVOKE ALL ON FUNCTION public.safe_cdc_write_live(BIGINT, TEXT) FROM PUBLIC;

-- 9.1 乐队注册（→ status=pending；同时写 users 供 lives.created_by FK）
CREATE OR REPLACE FUNCTION public.safe_register_band(
    p_username TEXT,
    p_password_hash TEXT,
    p_band_name TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_username IS NULL OR length(trim(p_username)) = 0 THEN
        RAISE EXCEPTION 'INVALID_USERNAME';
    END IF;
    IF p_password_hash IS NULL OR length(p_password_hash) = 0 THEN
        RAISE EXCEPTION 'INVALID_PASSWORD';
    END IF;
    IF p_band_name IS NULL OR length(trim(p_band_name)) = 0 THEN
        RAISE EXCEPTION 'INVALID_BAND_NAME';
    END IF;
    IF EXISTS (SELECT 1 FROM public.band_accounts WHERE username = p_username) THEN
        RAISE EXCEPTION 'USERNAME_TAKEN';
    END IF;
    IF EXISTS (SELECT 1 FROM public.users WHERE username = p_username) THEN
        RAISE EXCEPTION 'USERNAME_TAKEN';
    END IF;

    INSERT INTO public.users (username) VALUES (p_username) RETURNING id INTO v_id;
    INSERT INTO public.band_accounts (id, username, password_hash, band_name, status, role)
    VALUES (v_id, p_username, p_password_hash, p_band_name, 'pending', 'band');

    -- 保证 band_accounts_id_seq 不会与已用的显式 id 冲突（管理员账号经 DEFAULT 取号）
    PERFORM setval('public.band_accounts_id_seq',
                   GREATEST(v_id, (SELECT last_value FROM public.band_accounts_id_seq)));

    RETURN v_id;
END;
$$;

-- 9.2 新增管理员（role=admin, status=active；无公开注册）
CREATE OR REPLACE FUNCTION public.safe_create_admin(
    p_username TEXT,
    p_password_hash TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_username IS NULL OR length(trim(p_username)) = 0 THEN
        RAISE EXCEPTION 'INVALID_USERNAME';
    END IF;
    IF p_password_hash IS NULL OR length(p_password_hash) = 0 THEN
        RAISE EXCEPTION 'INVALID_PASSWORD';
    END IF;
    IF EXISTS (SELECT 1 FROM public.band_accounts WHERE username = p_username) THEN
        RAISE EXCEPTION 'USERNAME_TAKEN';
    END IF;
    IF EXISTS (SELECT 1 FROM public.users WHERE username = p_username) THEN
        RAISE EXCEPTION 'USERNAME_TAKEN';
    END IF;

    -- 与 safe_register_band 一致：先插 users 取号，再插 band_accounts（同 id 对齐）。
    -- 修复：原实现先插 band_accounts 拿 nextval，在 users 表已有数据（app_db 非空）时
    -- 会因序列错位撞 users 主键。users 先取号保证 id 一定不冲突。
    INSERT INTO public.users (username) VALUES (p_username) RETURNING id INTO v_id;
    INSERT INTO public.band_accounts (id, username, password_hash, band_name, status, role)
    VALUES (v_id, p_username, p_password_hash, p_username, 'active', 'admin');
    -- 对齐 band_accounts_id_seq，后续乐队注册不会撞主键
    PERFORM setval('public.band_accounts_id_seq',
                   GREATEST(v_id, (SELECT last_value FROM public.band_accounts_id_seq)));

    RETURN v_id;
END;
$$;

-- 9.3 更新乐队资料（NULL 字段 = 不修改）
CREATE OR REPLACE FUNCTION public.safe_update_band_profile(
    p_account_id BIGINT,
    p_band_name TEXT,
    p_intro TEXT,
    p_qq_bind TEXT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.band_accounts WHERE id = p_account_id) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.band_accounts
    SET band_name = CASE
            WHEN p_band_name IS NOT NULL AND length(trim(p_band_name)) > 0 THEN trim(p_band_name)
            ELSE band_name END,
        intro     = CASE WHEN p_intro IS NOT NULL THEN p_intro ELSE intro END,
        qq_bind   = CASE WHEN p_qq_bind IS NOT NULL THEN p_qq_bind ELSE qq_bind END
    WHERE id = p_account_id;
END;
$$;

-- 9.3b 更新乐队资料扩展字段（成员 / 封面；NULL 字段 = 不修改）
CREATE OR REPLACE FUNCTION public.safe_update_band_profile_extra(
    p_account_id BIGINT,
    p_cover_url TEXT,
    p_members JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.band_accounts WHERE id = p_account_id) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.band_accounts
    SET cover_url = CASE WHEN p_cover_url IS NOT NULL THEN p_cover_url ELSE cover_url END,
        members   = CASE
            WHEN p_members IS NOT NULL AND jsonb_typeof(p_members) = 'array'
            THEN p_members ELSE members END
    WHERE id = p_account_id;
END;
$$;

-- 9.4 管理员审批 / 改资料（action: active / rejected / disabled / pending）
CREATE OR REPLACE FUNCTION public.safe_admin_band_status(
    p_account_id BIGINT,
    p_status TEXT,
    p_band_name TEXT,
    p_intro TEXT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF p_status IS NULL OR p_status NOT IN ('active','rejected','disabled','pending') THEN
        RAISE EXCEPTION 'INVALID_STATUS';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.band_accounts WHERE id = p_account_id AND role = 'band'
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.band_accounts
    SET status    = p_status,
        band_name = CASE
            WHEN p_band_name IS NOT NULL AND length(trim(p_band_name)) > 0 THEN trim(p_band_name)
            ELSE band_name END,
        intro     = CASE WHEN p_intro IS NOT NULL THEN p_intro ELSE intro END
    WHERE id = p_account_id;
END;
$$;

-- 9.5 管理员删除乐队账号（级联清理拼盘关系；保留 users 桩行以防 lives 引用）
CREATE OR REPLACE FUNCTION public.safe_admin_delete_band(
    p_account_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.band_accounts WHERE id = p_account_id AND role = 'band'
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    DELETE FROM public.band_accounts WHERE id = p_account_id;
    DELETE FROM public.users
    WHERE id = p_account_id
      AND NOT EXISTS (SELECT 1 FROM public.lives WHERE created_by = p_account_id);
END;
$$;

-- ============================================================
-- 10. Live 写函数（均写 CDC，保证 /full /sync 联动）
-- ============================================================

-- 10.1 乐队创建 Live（band_names 传展示用乐队名数组；setlist 为曲目表）
CREATE OR REPLACE FUNCTION public.safe_create_live(
    p_account_id BIGINT,
    p_livehouse_id BIGINT,
    p_live_date DATE,
    p_start_time TIME,
    p_title TEXT,
    p_ticket_price TEXT,
    p_ticket_url TEXT,
    p_poster_image_url TEXT,
    p_city TEXT,
    p_status TEXT,
    p_review_status TEXT,
    p_kind TEXT,
    p_band_names JSONB,
    p_setlist JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_live_id BIGINT;
    v_pos INT;
    v_item JSONB;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.band_accounts WHERE id = p_account_id AND role = 'band'
    ) THEN
        RAISE EXCEPTION 'FORBIDDEN';
    END IF;
    IF p_title IS NULL OR length(trim(p_title)) = 0 THEN
        RAISE EXCEPTION 'INVALID_TITLE';
    END IF;
    IF p_live_date IS NULL THEN RAISE EXCEPTION 'INVALID_LIVE_DATE'; END IF;
    IF p_livehouse_id IS NULL OR p_livehouse_id <= 0 THEN RAISE EXCEPTION 'INVALID_LIVEHOUSE'; END IF;
    IF p_city IS NULL THEN p_city := ''; END IF;
    IF p_kind IS NULL OR p_kind NOT IN ('normal','coop') THEN p_kind := 'normal'; END IF;
    IF p_status IS NULL OR p_status NOT IN ('draft','announced','on_sale','completed','cancelled') THEN
        p_status := 'draft';
    END IF;
    IF p_review_status IS NULL OR p_review_status NOT IN ('draft','published','hidden') THEN
        p_review_status := 'draft';
    END IF;
    IF p_band_names IS NULL OR jsonb_typeof(p_band_names) <> 'array' THEN
        p_band_names := '[]'::jsonb;
    END IF;

    INSERT INTO public.lives
        (livehouse_id, live_date, start_time, title, ticket_price, ticket_url,
         poster_image_url, city, band_names, status, review_status, created_by, kind)
    VALUES
        (p_livehouse_id, p_live_date, p_start_time, trim(p_title), p_ticket_price,
         p_ticket_url, p_poster_image_url, trim(p_city), p_band_names, p_status,
         p_review_status, p_account_id, p_kind)
    RETURNING id INTO v_live_id;

    IF p_setlist IS NOT NULL AND jsonb_typeof(p_setlist) = 'array' THEN
        v_pos := 0;
        FOR v_item IN SELECT value FROM jsonb_array_elements(p_setlist) LOOP
            v_pos := v_pos + 1;
            INSERT INTO public.live_setlist (live_id, position, song_title, band_id)
            VALUES (v_live_id, v_pos,
                    COALESCE(v_item->>'song_title', ''),
                    CASE WHEN v_item->>'band_id' ~ '^[0-9]+$'
                         THEN (v_item->>'band_id')::BIGINT ELSE NULL END);
        END LOOP;
    END IF;

    PERFORM public.safe_cdc_write_live(
        v_live_id,
        CASE WHEN p_review_status = 'published' THEN 'upsert' ELSE 'delete' END
    );

    RETURN v_live_id;
END;
$$;

-- 10.2 乐队编辑 Live（必须本人；编辑已发布内容由 Python 层置回 draft）
CREATE OR REPLACE FUNCTION public.safe_update_live(
    p_account_id BIGINT,
    p_live_id BIGINT,
    p_livehouse_id BIGINT,
    p_live_date DATE,
    p_start_time TIME,
    p_title TEXT,
    p_ticket_price TEXT,
    p_ticket_url TEXT,
    p_poster_image_url TEXT,
    p_city TEXT,
    p_status TEXT,
    p_review_status TEXT,
    p_kind TEXT,
    p_band_names JSONB,
    p_setlist JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_pos INT;
    v_item JSONB;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.lives WHERE id = p_live_id AND created_by = p_account_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    IF p_title IS NULL OR length(trim(p_title)) = 0 THEN
        RAISE EXCEPTION 'INVALID_TITLE';
    END IF;
    IF p_live_date IS NULL THEN RAISE EXCEPTION 'INVALID_LIVE_DATE'; END IF;
    IF p_city IS NULL THEN p_city := ''; END IF;
    IF p_kind IS NULL OR p_kind NOT IN ('normal','coop') THEN p_kind := 'normal'; END IF;
    IF p_status IS NULL OR p_status NOT IN ('draft','announced','on_sale','completed','cancelled') THEN
        p_status := 'draft';
    END IF;
    IF p_review_status IS NULL OR p_review_status NOT IN ('draft','published','hidden') THEN
        p_review_status := 'draft';
    END IF;
    IF p_band_names IS NULL OR jsonb_typeof(p_band_names) <> 'array' THEN
        p_band_names := '[]'::jsonb;
    END IF;

    UPDATE public.lives SET
        livehouse_id    = p_livehouse_id,
        live_date       = p_live_date,
        start_time      = p_start_time,
        title           = trim(p_title),
        ticket_price    = p_ticket_price,
        ticket_url      = p_ticket_url,
        poster_image_url = p_poster_image_url,
        city            = trim(p_city),
        status          = p_status,
        review_status   = p_review_status,
        kind            = p_kind,
        band_names      = p_band_names
    WHERE id = p_live_id;

    DELETE FROM public.live_setlist WHERE live_id = p_live_id;
    IF p_setlist IS NOT NULL AND jsonb_typeof(p_setlist) = 'array' THEN
        v_pos := 0;
        FOR v_item IN SELECT value FROM jsonb_array_elements(p_setlist) LOOP
            v_pos := v_pos + 1;
            INSERT INTO public.live_setlist (live_id, position, song_title, band_id)
            VALUES (p_live_id, v_pos,
                    COALESCE(v_item->>'song_title', ''),
                    CASE WHEN v_item->>'band_id' ~ '^[0-9]+$'
                         THEN (v_item->>'band_id')::BIGINT ELSE NULL END);
        END LOOP;
    END IF;

    PERFORM public.safe_cdc_write_live(
        p_live_id,
        CASE WHEN p_review_status = 'published' THEN 'upsert' ELSE 'delete' END
    );
END;
$$;

-- 10.3 乐队发布（→ published 直接上线）
CREATE OR REPLACE FUNCTION public.safe_publish_live(
    p_account_id BIGINT,
    p_live_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.lives WHERE id = p_live_id AND created_by = p_account_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.lives SET review_status = 'published', status = 'announced'
    WHERE id = p_live_id;
    PERFORM public.safe_cdc_write_live(p_live_id, 'upsert');
END;
$$;

-- 10.4 乐队下架（status + review_status → draft，用户端即时隐藏）
CREATE OR REPLACE FUNCTION public.safe_offline_live(
    p_account_id BIGINT,
    p_live_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.lives WHERE id = p_live_id AND created_by = p_account_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.lives SET review_status = 'draft', status = 'draft'
    WHERE id = p_live_id;
    PERFORM public.safe_cdc_write_live(p_live_id, 'delete');
END;
$$;

-- 10.5 管理员强制下架（无归属校验）
CREATE OR REPLACE FUNCTION public.safe_admin_offline_live(
    p_live_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.lives WHERE id = p_live_id) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.lives SET review_status = 'draft', status = 'draft'
    WHERE id = p_live_id;
    PERFORM public.safe_cdc_write_live(p_live_id, 'delete');
END;
$$;

-- 10.6 乐队删除草稿（物理删除；级联 live_setlist / coop 关系）
CREATE OR REPLACE FUNCTION public.safe_delete_live(
    p_account_id BIGINT,
    p_live_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.lives WHERE id = p_live_id AND created_by = p_account_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    PERFORM public.safe_cdc_write_live(p_live_id, 'delete');
    DELETE FROM public.lives WHERE id = p_live_id;
END;
$$;

-- 10.7 管理员强制编辑（全字段；p_bands 为 live_bands 阵容，可选）
CREATE OR REPLACE FUNCTION public.safe_admin_update_live(
    p_live_id BIGINT,
    p_livehouse_id BIGINT,
    p_live_date DATE,
    p_start_time TIME,
    p_title TEXT,
    p_ticket_price TEXT,
    p_ticket_url TEXT,
    p_poster_image_url TEXT,
    p_city TEXT,
    p_status TEXT,
    p_review_status TEXT,
    p_kind TEXT,
    p_band_names JSONB,
    p_setlist JSONB,
    p_bands JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_pos INT;
    v_item JSONB;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.lives WHERE id = p_live_id) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    IF p_kind IS NULL OR p_kind NOT IN ('normal','coop') THEN p_kind := 'normal'; END IF;
    IF p_status IS NULL OR p_status NOT IN ('draft','announced','on_sale','completed','cancelled') THEN
        p_status := 'draft';
    END IF;
    IF p_review_status IS NULL OR p_review_status NOT IN ('draft','published','hidden') THEN
        p_review_status := 'draft';
    END IF;
    IF p_band_names IS NULL OR jsonb_typeof(p_band_names) <> 'array' THEN
        p_band_names := '[]'::jsonb;
    END IF;

    UPDATE public.lives SET
        livehouse_id    = p_livehouse_id,
        live_date       = p_live_date,
        start_time      = p_start_time,
        title           = COALESCE(NULLIF(trim(p_title), ''), title),
        ticket_price    = p_ticket_price,
        ticket_url      = p_ticket_url,
        poster_image_url = p_poster_image_url,
        city            = COALESCE(NULLIF(trim(p_city), ''), city),
        status          = p_status,
        review_status   = p_review_status,
        kind            = p_kind,
        band_names      = p_band_names
    WHERE id = p_live_id;

    DELETE FROM public.live_setlist WHERE live_id = p_live_id;
    IF p_setlist IS NOT NULL AND jsonb_typeof(p_setlist) = 'array' THEN
        v_pos := 0;
        FOR v_item IN SELECT value FROM jsonb_array_elements(p_setlist) LOOP
            v_pos := v_pos + 1;
            INSERT INTO public.live_setlist (live_id, position, song_title, band_id)
            VALUES (p_live_id, v_pos,
                    COALESCE(v_item->>'song_title', ''),
                    CASE WHEN v_item->>'band_id' ~ '^[0-9]+$'
                         THEN (v_item->>'band_id')::BIGINT ELSE NULL END);
        END LOOP;
    END IF;

    IF p_bands IS NOT NULL AND jsonb_typeof(p_bands) = 'array' THEN
        PERFORM public.safe_update_live_bands(p_live_id, p_bands);
    END IF;

    PERFORM public.safe_cdc_write_live(
        p_live_id,
        CASE WHEN p_review_status = 'published' THEN 'upsert' ELSE 'delete' END
    );
END;
$$;

-- ============================================================
-- 11. 场地写函数
-- ============================================================
CREATE OR REPLACE FUNCTION public.safe_livehouse_upsert(
    p_id BIGINT,
    p_name TEXT,
    p_city TEXT,
    p_address TEXT,
    p_phone TEXT,
    p_image_url TEXT,
    p_intro TEXT,
    p_floorplan_url TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_name IS NULL OR length(trim(p_name)) = 0 THEN
        RAISE EXCEPTION 'INVALID_VENUE_NAME';
    END IF;
    IF p_city IS NULL OR length(trim(p_city)) = 0 THEN p_city := 'Tokyo'; END IF;

    IF p_id IS NOT NULL AND p_id > 0 THEN
        UPDATE public.livehouses SET
            name          = trim(p_name),
            city          = trim(p_city),
            address       = p_address,
            phone         = p_phone,
            image_url     = p_image_url,
            intro         = p_intro,
            floorplan_url = p_floorplan_url
        WHERE id = p_id;
        IF FOUND THEN
            RETURN p_id;
        END IF;
    END IF;

    INSERT INTO public.livehouses
        (name, city, address, phone, image_url, intro, floorplan_url)
    VALUES
        (trim(p_name), trim(p_city), p_address, p_phone, p_image_url, p_intro, p_floorplan_url)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.safe_livehouse_delete(
    p_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    DELETE FROM public.livehouses WHERE id = p_id;
END;
$$;

-- ============================================================
-- 12. 拼盘写函数
-- ============================================================

-- 12.0 内部：把 invites 数组（[{username,songs}]）写入 coop_invites
--      p_replace_invited=true 时先清理未响应的 invited 邀请（发起方编辑用）
CREATE OR REPLACE FUNCTION public.safe_coop_fill_invites(
    p_event_id BIGINT,
    p_invites JSONB,
    p_replace_invited BOOLEAN
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_invite JSONB;
    v_account BIGINT;
    v_username TEXT;
    v_songs JSONB;
    v_accounts BIGINT[] := '{}';
BEGIN
    IF p_invites IS NULL OR jsonb_typeof(p_invites) <> 'array' THEN
        RETURN;
    END IF;

    -- 先删除未响应的旧邀请（若需要替换）
    IF p_replace_invited THEN
        DELETE FROM public.coop_invites
        WHERE event_id = p_event_id AND invite_status = 'invited';
    END IF;

    FOR v_invite IN SELECT value FROM jsonb_array_elements(p_invites) LOOP
        v_username := v_invite->>'username';
        SELECT id INTO v_account FROM public.band_accounts
        WHERE username = v_username AND role = 'band';
        IF v_account IS NULL THEN
            RAISE EXCEPTION 'USER_NOT_FOUND';
        END IF;
        IF v_account = (SELECT initiator_account_id FROM public.coop_events WHERE id = p_event_id) THEN
            RAISE EXCEPTION 'CANNOT_INVITE_SELF';
        END IF;
        v_songs := COALESCE(v_invite->'songs', '[]'::jsonb);
        IF jsonb_typeof(v_songs) <> 'array' THEN v_songs := '[]'::jsonb; END IF;
        v_accounts := v_accounts || v_account;

        -- 仅更新仍为 invited 的行；已响应的不覆盖（发起方无权改对方曲目）
        INSERT INTO public.coop_invites (event_id, band_account_id, invite_status, songs)
        VALUES (p_event_id, v_account, 'invited', v_songs)
        ON CONFLICT (event_id, band_account_id)
        DO UPDATE SET songs = EXCLUDED.songs, updated_at = now()
        WHERE public.coop_invites.invite_status = 'invited';
    END LOOP;

    -- 清理：已不再出现在邀请清单中的未响应邀请
    DELETE FROM public.coop_invites
    WHERE event_id = p_event_id
      AND invite_status = 'invited'
      AND band_account_id <> ALL(v_accounts);
END;
$$;

-- 12.1 创建拼盘（建 Live kind=coop + event + 发起方 agreed 邀请 + 受邀乐队 invited 邀请）
CREATE OR REPLACE FUNCTION public.safe_coop_create_event(
    p_initiator_id BIGINT,
    p_livehouse_id BIGINT,
    p_live_date DATE,
    p_start_time TIME,
    p_title TEXT,
    p_ticket_price TEXT,
    p_poster_image_url TEXT,
    p_city TEXT,
    p_action TEXT,
    p_own_songs JSONB,
    p_invites JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_live_id BIGINT;
    v_event_id BIGINT;
    v_status TEXT;
    v_review TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.band_accounts WHERE id = p_initiator_id AND role = 'band'
    ) THEN
        RAISE EXCEPTION 'FORBIDDEN';
    END IF;
    IF p_title IS NULL OR length(trim(p_title)) = 0 THEN
        RAISE EXCEPTION 'INVALID_TITLE';
    END IF;
    IF p_live_date IS NULL THEN RAISE EXCEPTION 'INVALID_LIVE_DATE'; END IF;
    IF p_livehouse_id IS NULL OR p_livehouse_id <= 0 THEN RAISE EXCEPTION 'INVALID_LIVEHOUSE'; END IF;
    IF p_city IS NULL THEN p_city := ''; END IF;

    IF p_action = 'publish' THEN v_status := 'published'; v_review := 'published';
    ELSE v_status := 'draft'; v_review := 'draft'; END IF;

    v_live_id := public.safe_create_live(
        p_initiator_id, p_livehouse_id, p_live_date, p_start_time, p_title,
        p_ticket_price, NULL, p_poster_image_url, p_city,
        CASE WHEN v_review = 'published' THEN 'announced' ELSE 'draft' END,
        v_review, 'coop', '[]'::jsonb, p_own_songs
    );

    INSERT INTO public.coop_events (live_id, initiator_account_id, status)
    VALUES (v_live_id, p_initiator_id, v_status)
    RETURNING id INTO v_event_id;

    INSERT INTO public.coop_invites (event_id, band_account_id, invite_status, songs)
    VALUES (v_event_id, p_initiator_id, 'agreed', COALESCE(p_own_songs, '[]'::jsonb));

    PERFORM public.safe_coop_fill_invites(v_event_id, p_invites, false);

    RETURN v_event_id;
END;
$$;

-- 12.2 发起方编辑拼盘（更新 Live 字段 + 本队曲目 + 未响应邀请替换）
CREATE OR REPLACE FUNCTION public.safe_coop_update_event(
    p_initiator_id BIGINT,
    p_event_id BIGINT,
    p_livehouse_id BIGINT,
    p_live_date DATE,
    p_start_time TIME,
    p_title TEXT,
    p_ticket_price TEXT,
    p_poster_image_url TEXT,
    p_city TEXT,
    p_action TEXT,
    p_own_songs JSONB,
    p_invites JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_live_id BIGINT;
    v_status TEXT;
    v_review TEXT;
    v_pos INT;
    v_item JSONB;
BEGIN
    SELECT live_id INTO v_live_id
    FROM public.coop_events
    WHERE id = p_event_id AND initiator_account_id = p_initiator_id;
    IF v_live_id IS NULL THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;

    IF p_action = 'publish' THEN v_status := 'published'; v_review := 'published';
    ELSE v_status := 'draft'; v_review := 'draft'; END IF;
    IF p_city IS NULL THEN p_city := ''; END IF;

    UPDATE public.lives SET
        livehouse_id = p_livehouse_id,
        live_date    = p_live_date,
        start_time   = p_start_time,
        title        = trim(p_title),
        ticket_price = p_ticket_price,
        poster_image_url = p_poster_image_url,
        city         = trim(p_city),
        status       = CASE WHEN v_review = 'published' THEN 'announced' ELSE 'draft' END,
        review_status = v_review
    WHERE id = v_live_id;

    -- 本队曲目即 setlist
    DELETE FROM public.live_setlist WHERE live_id = v_live_id;
    IF p_own_songs IS NOT NULL AND jsonb_typeof(p_own_songs) = 'array' THEN
        v_pos := 0;
        FOR v_item IN SELECT value FROM jsonb_array_elements(p_own_songs) LOOP
            v_pos := v_pos + 1;
            INSERT INTO public.live_setlist (live_id, position, song_title, band_id)
            VALUES (v_live_id, v_pos, COALESCE(v_item->>'song_title', ''), NULL);
        END LOOP;
    END IF;

    -- 更新发起方自己的邀请曲目
    UPDATE public.coop_invites SET songs = COALESCE(p_own_songs, '[]'::jsonb)
    WHERE event_id = p_event_id AND band_account_id = p_initiator_id;

    PERFORM public.safe_coop_fill_invites(p_event_id, p_invites, true);

    PERFORM public.safe_cdc_write_live(
        v_live_id,
        CASE WHEN v_review = 'published' THEN 'upsert' ELSE 'delete' END
    );
END;
$$;

-- 12.3 追加邀请
CREATE OR REPLACE FUNCTION public.safe_coop_add_invite(
    p_event_id BIGINT,
    p_initiator_id BIGINT,
    p_username TEXT,
    p_songs JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_account BIGINT;
    v_invite_id BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.coop_events
        WHERE id = p_event_id AND initiator_account_id = p_initiator_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    SELECT id INTO v_account FROM public.band_accounts
    WHERE username = p_username AND role = 'band';
    IF v_account IS NULL THEN RAISE EXCEPTION 'USER_NOT_FOUND'; END IF;
    IF v_account = p_initiator_id THEN RAISE EXCEPTION 'CANNOT_INVITE_SELF'; END IF;
    IF p_songs IS NULL OR jsonb_typeof(p_songs) <> 'array' THEN p_songs := '[]'::jsonb; END IF;

    INSERT INTO public.coop_invites (event_id, band_account_id, invite_status, songs)
    VALUES (p_event_id, v_account, 'invited', p_songs)
    ON CONFLICT (event_id, band_account_id)
    DO UPDATE SET invite_status = 'invited', songs = EXCLUDED.songs, updated_at = now()
    RETURNING id INTO v_invite_id;
    RETURN v_invite_id;
END;
$$;

-- 12.4 同意（可带曲目）
CREATE OR REPLACE FUNCTION public.safe_coop_accept_invite(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_band_account_id BIGINT,
    p_songs JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    UPDATE public.coop_invites
    SET invite_status = 'agreed',
        songs = CASE WHEN p_songs IS NOT NULL AND jsonb_typeof(p_songs) = 'array'
                     THEN p_songs ELSE songs END
    WHERE id = p_invite_id AND event_id = p_event_id AND band_account_id = p_band_account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.5 拒绝
CREATE OR REPLACE FUNCTION public.safe_coop_reject_invite(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_band_account_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    UPDATE public.coop_invites SET invite_status = 'rejected'
    WHERE id = p_invite_id AND event_id = p_event_id AND band_account_id = p_band_account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.6 改本队曲目（仅本人，非发起方）
CREATE OR REPLACE FUNCTION public.safe_coop_update_songs(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_band_account_id BIGINT,
    p_songs JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF p_songs IS NULL OR jsonb_typeof(p_songs) <> 'array' THEN p_songs := '[]'::jsonb; END IF;
    UPDATE public.coop_invites SET songs = p_songs
    WHERE id = p_invite_id AND event_id = p_event_id AND band_account_id = p_band_account_id
      AND band_account_id <> (SELECT initiator_account_id FROM public.coop_events WHERE id = p_event_id);
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.7 撤销同意（agreed → invited）
CREATE OR REPLACE FUNCTION public.safe_coop_revoke(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_band_account_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    UPDATE public.coop_invites SET invite_status = 'invited'
    WHERE id = p_invite_id AND event_id = p_event_id AND band_account_id = p_band_account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.8 申请退出（agreed → exit_requested）
CREATE OR REPLACE FUNCTION public.safe_coop_exit_request(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_band_account_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    UPDATE public.coop_invites SET invite_status = 'exit_requested'
    WHERE id = p_invite_id AND event_id = p_event_id AND band_account_id = p_band_account_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.9 发起方审批退出（exit_requested → removed）
CREATE OR REPLACE FUNCTION public.safe_coop_approve_exit(
    p_event_id BIGINT,
    p_invite_id BIGINT,
    p_initiator_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.coop_events
        WHERE id = p_event_id AND initiator_account_id = p_initiator_id
    ) THEN
        RAISE EXCEPTION 'NOT_FOUND';
    END IF;
    UPDATE public.coop_invites SET invite_status = 'removed'
    WHERE id = p_invite_id AND event_id = p_event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
END;
$$;

-- 12.10 发起方下架拼盘（event → offline；live → draft；CDC delete）
CREATE OR REPLACE FUNCTION public.safe_coop_offline_event(
    p_event_id BIGINT,
    p_initiator_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_live_id BIGINT;
BEGIN
    SELECT live_id INTO v_live_id
    FROM public.coop_events
    WHERE id = p_event_id AND initiator_account_id = p_initiator_id;
    IF v_live_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;

    UPDATE public.coop_events SET status = 'offline' WHERE id = p_event_id;
    UPDATE public.lives SET review_status = 'draft', status = 'draft' WHERE id = v_live_id;
    PERFORM public.safe_cdc_write_live(v_live_id, 'delete');
END;
$$;

-- 12.11 发起方删除拼盘草稿（物理删除 Live → 级联 event/invites）
CREATE OR REPLACE FUNCTION public.safe_coop_delete_event(
    p_event_id BIGINT,
    p_initiator_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_live_id BIGINT;
    v_status TEXT;
BEGIN
    SELECT live_id, status INTO v_live_id, v_status
    FROM public.coop_events
    WHERE id = p_event_id AND initiator_account_id = p_initiator_id;
    IF v_live_id IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
    IF v_status <> 'draft' THEN RAISE EXCEPTION 'FORBIDDEN'; END IF;

    PERFORM public.safe_cdc_write_live(v_live_id, 'delete');
    DELETE FROM public.lives WHERE id = v_live_id;
END;
$$;

-- ============================================================
-- 13. CMS 写函数
-- ============================================================
CREATE OR REPLACE FUNCTION public.safe_cms_upsert_group(
    p_id BIGINT,
    p_city TEXT,
    p_platform TEXT,
    p_group_id TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_city IS NULL OR length(trim(p_city)) = 0 THEN RAISE EXCEPTION 'INVALID_CITY'; END IF;
    IF p_platform NOT IN ('wechat','qq') THEN RAISE EXCEPTION 'INVALID_PLATFORM'; END IF;
    IF p_group_id IS NULL OR length(trim(p_group_id)) = 0 THEN RAISE EXCEPTION 'INVALID_GROUP_ID'; END IF;

    IF p_id IS NOT NULL AND p_id > 0 THEN
        UPDATE public.community_groups
        SET city = trim(p_city), platform = p_platform, group_id = trim(p_group_id)
        WHERE id = p_id;
        IF FOUND THEN RETURN p_id; END IF;
    END IF;

    INSERT INTO public.community_groups (city, platform, group_id)
    VALUES (trim(p_city), p_platform, trim(p_group_id))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.safe_cms_delete_group(
    p_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    DELETE FROM public.community_groups WHERE id = p_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.safe_cms_upsert_sponsor(
    p_thanks_text TEXT,
    p_qr_image_urls JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF p_qr_image_urls IS NULL OR jsonb_typeof(p_qr_image_urls) <> 'array' THEN
        p_qr_image_urls := '[]'::jsonb;
    END IF;
    INSERT INTO public.sponsor_content (id, thanks_text, qr_image_urls)
    VALUES (1, p_thanks_text, p_qr_image_urls)
    ON CONFLICT (id) DO UPDATE SET
        thanks_text = EXCLUDED.thanks_text,
        qr_image_urls = EXCLUDED.qr_image_urls;
END;
$$;

CREATE OR REPLACE FUNCTION public.safe_cms_upsert_project(
    p_intro TEXT,
    p_github_url TEXT,
    p_author TEXT,
    p_license TEXT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.project_declaration (id, intro, github_url, author, license)
    VALUES (1, p_intro, p_github_url, p_author, p_license)
    ON CONFLICT (id) DO UPDATE SET
        intro = EXCLUDED.intro,
        github_url = EXCLUDED.github_url,
        author = EXCLUDED.author,
        license = EXCLUDED.license;
END;
$$;

-- ============================================================
-- 14. 函数授权
--    公开可调用的写函数 GRANT EXECUTE 给 api_role；内部 helper 仅 app_definer。
-- ============================================================
REVOKE ALL ON FUNCTION
    public.safe_register_band(TEXT, TEXT, TEXT),
    public.safe_create_admin(TEXT, TEXT),
    public.safe_update_band_profile(BIGINT, TEXT, TEXT, TEXT),
    public.safe_update_band_profile_extra(BIGINT, TEXT, JSONB),
    public.safe_admin_band_status(BIGINT, TEXT, TEXT, TEXT),
    public.safe_admin_delete_band(BIGINT),
    public.safe_create_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_update_live(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_publish_live(BIGINT, BIGINT),
    public.safe_offline_live(BIGINT, BIGINT),
    public.safe_admin_offline_live(BIGINT),
    public.safe_delete_live(BIGINT, BIGINT),
    public.safe_admin_update_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB, JSONB),
    public.safe_livehouse_upsert(BIGINT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT),
    public.safe_livehouse_delete(BIGINT),
    public.safe_coop_create_event(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_coop_update_event(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_coop_add_invite(BIGINT, BIGINT, TEXT, JSONB),
    public.safe_coop_accept_invite(BIGINT, BIGINT, BIGINT, JSONB),
    public.safe_coop_reject_invite(BIGINT, BIGINT, BIGINT),
    public.safe_coop_update_songs(BIGINT, BIGINT, BIGINT, JSONB),
    public.safe_coop_revoke(BIGINT, BIGINT, BIGINT),
    public.safe_coop_exit_request(BIGINT, BIGINT, BIGINT),
    public.safe_coop_approve_exit(BIGINT, BIGINT, BIGINT),
    public.safe_coop_offline_event(BIGINT, BIGINT),
    public.safe_coop_delete_event(BIGINT, BIGINT),
    public.safe_cms_upsert_group(BIGINT, TEXT, TEXT, TEXT),
    public.safe_cms_delete_group(BIGINT),
    public.safe_cms_upsert_sponsor(TEXT, JSONB),
    public.safe_cms_upsert_project(TEXT, TEXT, TEXT, TEXT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    public.safe_register_band(TEXT, TEXT, TEXT),
    public.safe_create_admin(TEXT, TEXT),
    public.safe_update_band_profile(BIGINT, TEXT, TEXT, TEXT),
    public.safe_update_band_profile_extra(BIGINT, TEXT, JSONB),
    public.safe_admin_band_status(BIGINT, TEXT, TEXT, TEXT),
    public.safe_admin_delete_band(BIGINT),
    public.safe_create_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_update_live(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_publish_live(BIGINT, BIGINT),
    public.safe_offline_live(BIGINT, BIGINT),
    public.safe_admin_offline_live(BIGINT),
    public.safe_delete_live(BIGINT, BIGINT),
    public.safe_admin_update_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB, JSONB),
    public.safe_livehouse_upsert(BIGINT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT),
    public.safe_livehouse_delete(BIGINT),
    public.safe_coop_create_event(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_coop_update_event(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB),
    public.safe_coop_add_invite(BIGINT, BIGINT, TEXT, JSONB),
    public.safe_coop_accept_invite(BIGINT, BIGINT, BIGINT, JSONB),
    public.safe_coop_reject_invite(BIGINT, BIGINT, BIGINT),
    public.safe_coop_update_songs(BIGINT, BIGINT, BIGINT, JSONB),
    public.safe_coop_revoke(BIGINT, BIGINT, BIGINT),
    public.safe_coop_exit_request(BIGINT, BIGINT, BIGINT),
    public.safe_coop_approve_exit(BIGINT, BIGINT, BIGINT),
    public.safe_coop_offline_event(BIGINT, BIGINT),
    public.safe_coop_delete_event(BIGINT, BIGINT),
    public.safe_cms_upsert_group(BIGINT, TEXT, TEXT, TEXT),
    public.safe_cms_delete_group(BIGINT),
    public.safe_cms_upsert_sponsor(TEXT, JSONB),
    public.safe_cms_upsert_project(TEXT, TEXT, TEXT, TEXT)
TO api_role;

-- safe_coop_fill_invites 只被 app_definer 所有函数内部调用，不授予 api_role。
REVOKE ALL ON FUNCTION public.safe_coop_fill_invites(BIGINT, JSONB, BOOLEAN) FROM PUBLIC;

-- ============================================================
-- 15. 迁移角色获得新表完整权限（迁移可在应用后继续维护）
--     注意：必须放在 ALTER ... OWNER 之前。所有权转给 app_definer 后，
--     非超级用户的迁移连接会失去对这些函数的 GRANT OPTION，
--     届时 GRANT ALL ON ALL FUNCTIONS 将失败。
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO migration_role;

-- ============================================================
-- 16. 将 SECURITY DEFINER 函数所有权转给 app_definer（幂等）
-- ============================================================
DO $$
DECLARE
    funcs TEXT[] := ARRAY[
        'safe_cdc_write_live(BIGINT, TEXT)',
        'safe_register_band(TEXT, TEXT, TEXT)',
        'safe_create_admin(TEXT, TEXT)',
        'safe_update_band_profile(BIGINT, TEXT, TEXT, TEXT)',
        'safe_update_band_profile_extra(BIGINT, TEXT, JSONB)',
        'safe_admin_band_status(BIGINT, TEXT, TEXT, TEXT)',
        'safe_admin_delete_band(BIGINT)',
        'safe_create_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB)',
        'safe_update_live(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB)',
        'safe_publish_live(BIGINT, BIGINT)',
        'safe_offline_live(BIGINT, BIGINT)',
        'safe_admin_offline_live(BIGINT)',
        'safe_delete_live(BIGINT, BIGINT)',
        'safe_admin_update_live(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB, JSONB)',
        'safe_livehouse_upsert(BIGINT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)',
        'safe_livehouse_delete(BIGINT)',
        'safe_coop_create_event(BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB)',
        'safe_coop_update_event(BIGINT, BIGINT, BIGINT, DATE, TIME, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB, JSONB)',
        'safe_coop_fill_invites(BIGINT, JSONB, BOOLEAN)',
        'safe_coop_add_invite(BIGINT, BIGINT, TEXT, JSONB)',
        'safe_coop_accept_invite(BIGINT, BIGINT, BIGINT, JSONB)',
        'safe_coop_reject_invite(BIGINT, BIGINT, BIGINT)',
        'safe_coop_update_songs(BIGINT, BIGINT, BIGINT, JSONB)',
        'safe_coop_revoke(BIGINT, BIGINT, BIGINT)',
        'safe_coop_exit_request(BIGINT, BIGINT, BIGINT)',
        'safe_coop_approve_exit(BIGINT, BIGINT, BIGINT)',
        'safe_coop_offline_event(BIGINT, BIGINT)',
        'safe_coop_delete_event(BIGINT, BIGINT)',
        'safe_cms_upsert_group(BIGINT, TEXT, TEXT, TEXT)',
        'safe_cms_delete_group(BIGINT)',
        'safe_cms_upsert_sponsor(TEXT, JSONB)',
        'safe_cms_upsert_project(TEXT, TEXT, TEXT, TEXT)'
    ];
    f TEXT;
BEGIN
    FOREACH f IN ARRAY funcs LOOP
        IF to_regprocedure('public.' || f) IS NOT NULL THEN
            EXECUTE 'ALTER FUNCTION public.' || f || ' OWNER TO app_definer';
        END IF;
    END LOOP;
END
$$;

-- ============================================================
-- 17. 序列自愈（幂等）：把每个 public.<table>_id_seq 对齐到对应表 MAX(id)。
--     防止：显式 id 种子数据（V1/V3 测试数据）之后序列错位，导致 nextval
--     撞主键（app_db 非空场景曾复现 lives_pkey / users_pkey 冲突）。
-- ============================================================
DO $$
DECLARE
    r  record;
    tbl text;
    mx  bigint;
BEGIN
    FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' LOOP
        tbl := regexp_replace(r.sequencename, '_id_seq$', '');
        IF to_regclass('public.' || tbl) IS NOT NULL THEN
            EXECUTE format('SELECT COALESCE(MAX(id), 1) FROM public.%I', tbl) INTO mx;
            EXECUTE format('SELECT setval(%L, GREATEST(%s, 1), true)',
                           'public.' || r.sequencename, mx);
        END IF;
    END LOOP;
END
$$;
