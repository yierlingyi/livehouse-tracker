\encoding UTF8
SET client_encoding = 'UTF8';

-- V4__cities.sql — 运行时城市表（三端城市选择改为从此表读取）
-- Applied AFTER V1__schema.sql + V2__permissions.sql + V3__platform.sql.
--
-- 设计约束（与 V3 一致）：
--   * 城市表独立于 CDC / /full /sync，走普通 REST：
--       GET    /api/v1/cities            城市列表（公开，无鉴权）
--       POST   /api/v1/admin/cities      新增城市（admin）
--       DELETE /api/v1/admin/cities/{id} 删除城市（admin）
--   * api_role 保持表级只读；写操作走 SECURITY DEFINER 函数（owner=app_definer，
--     固定 search_path），不信任客户端、不拼接 SQL。
--   * 幂等：表 IF NOT EXISTS、种子 ON CONFLICT (name) DO NOTHING、
--     函数 CREATE OR REPLACE、授权/所有权重放安全。

-- ============================================================
-- 1. 城市表
-- ============================================================
CREATE TABLE IF NOT EXISTS public.cities (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 2. 种子（幂等）：回填 livehouses/lives/community_groups 的 DISTINCT 非空 city，
--    并确保 '青岛' 一定存在。当前库城市已全部归一为 '青岛'，故种子结果即 ['青岛']。
-- ============================================================
INSERT INTO public.cities (name)
SELECT DISTINCT trim(city) FROM public.livehouses
WHERE city IS NOT NULL AND length(trim(city)) > 0
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.cities (name)
SELECT DISTINCT trim(city) FROM public.lives
WHERE city IS NOT NULL AND length(trim(city)) > 0
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.cities (name)
SELECT DISTINCT trim(city) FROM public.community_groups
WHERE city IS NOT NULL AND length(trim(city)) > 0
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.cities (name) VALUES ('青岛')
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 3. 权限：api_role 表级只读；app_definer 最小写权限
-- ============================================================
GRANT SELECT ON public.cities TO api_role;
REVOKE INSERT, UPDATE, DELETE ON public.cities FROM api_role;

GRANT USAGE, SELECT ON SEQUENCE public.cities_id_seq TO app_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cities TO app_definer;

-- ============================================================
-- 4. 写函数（SECURITY DEFINER，仿 V3 §13 safe_cms_upsert_group）
-- ============================================================
CREATE OR REPLACE FUNCTION public.safe_cities_upsert(
    p_name VARCHAR
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
        RAISE EXCEPTION 'INVALID_CITY';
    END IF;
    -- 原子判重：INSERT ... ON CONFLICT DO NOTHING 并发安全，冲突时 v_id 保持 NULL
    INSERT INTO public.cities (name) VALUES (trim(p_name))
    ON CONFLICT (name) DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'CITY_TAKEN';
    END IF;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.safe_cities_delete(
    p_id BIGINT
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.cities WHERE id = p_id) THEN
        RAISE EXCEPTION 'CITY_NOT_FOUND';
    END IF;
    DELETE FROM public.cities WHERE id = p_id;
END;
$$;

-- ============================================================
-- 5. 函数授权（仿 V3 §14）
-- ============================================================
REVOKE ALL ON FUNCTION
    public.safe_cities_upsert(VARCHAR),
    public.safe_cities_delete(BIGINT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    public.safe_cities_upsert(VARCHAR),
    public.safe_cities_delete(BIGINT)
TO api_role;

-- ============================================================
-- 6. 迁移角色获得新表完整权限（应用后仍可继续维护）
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO migration_role;

-- ============================================================
-- 7. SECURITY DEFINER 函数所有权转给 app_definer（幂等）
-- ============================================================
DO $$
DECLARE
    funcs TEXT[] := ARRAY[
        'safe_cities_upsert(VARCHAR)',
        'safe_cities_delete(BIGINT)'
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
-- 8. 序列自愈（幂等）：cities_id_seq 对齐到 MAX(id)
-- ============================================================
SELECT setval('public.cities_id_seq',
              GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.cities), 1),
              true);
