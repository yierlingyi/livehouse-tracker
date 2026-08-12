-- V2__permissions.sql — Role-level object permissions (V4.4 §7-8)
-- Applied AFTER V1__schema.sql.
--
-- The three roles (app_definer / migration_role / api_role) are already created
-- in V1__schema.sql, so the role-creation block below is idempotent: it is a
-- no-op where the roles exist and creates them only in a fresh environment.
--
-- Two additions beyond the V4.4 excerpt are required for correctness and are
-- documented in database/docs/security_review.md:
--   * GRANT TEMPORARY ON DATABASE app_db TO app_definer — V1 §7.1 revokes TEMP
--     (and CONNECT/CREATE) from PUBLIC, and safe_update_live_bands() creates a
--     temp table; the SECURITY DEFINER function runs as app_definer, so that
--     role must retain TEMP on the database.

-- ============================================================
-- 创建角色 (idempotent)
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
-- Schema 权限
-- ============================================================
GRANT CREATE ON SCHEMA public TO migration_role;

-- ============================================================
-- api_role: 只读 lives + bands + live_bands
-- ============================================================
GRANT SELECT ON public.lives TO api_role;
GRANT SELECT ON public.bands TO api_role;
GRANT SELECT ON public.live_bands TO api_role;

-- ============================================================
-- api_role: 禁止直接修改受保护表
-- ============================================================
REVOKE INSERT, UPDATE, DELETE ON public.live_bands FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.sync_changes FROM api_role;
REVOKE UPDATE ON public.sync_version_counter FROM api_role;

-- ============================================================
-- api_role: 可以执行安全函数
-- ============================================================
GRANT EXECUTE ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) TO api_role;
REVOKE ALL ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) FROM PUBLIC;

-- ============================================================
-- app_definer 只授予函数所需的最小表权限
-- ============================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON public.live_bands TO app_definer;
GRANT SELECT, UPDATE ON public.lives TO app_definer;
GRANT SELECT ON public.bands TO app_definer;

-- safe_update_live_bands() 内 CREATE TEMP TABLE 需要数据库 TEMP 权限
-- （V1 的 REVOKE ALL ON DATABASE ... FROM PUBLIC 已撤销 PUBLIC 的 TEMP）
GRANT TEMPORARY ON DATABASE app_db TO app_definer;

-- ============================================================
-- migration_role 获得所有表的完整权限用于迁移
-- 注意：必须放在 ALTER ... OWNER 之前。所有权转给 app_definer 后，
-- 非超级用户的迁移连接会失去对这些函数的 GRANT OPTION，
-- 届时 GRANT ALL ON ALL FUNCTIONS 将失败。
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO migration_role;

-- ============================================================
-- 将 SECURITY DEFINER 函数所有权转给 app_definer
-- ============================================================
ALTER FUNCTION public.safe_update_live_bands(BIGINT, JSONB) OWNER TO app_definer;
ALTER FUNCTION public.fn_update_timestamp() OWNER TO app_definer;
