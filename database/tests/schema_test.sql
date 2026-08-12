-- schema_test.sql — Verification queries for V1/V2 schema (V4.4 §15.6 + §16 acceptance)
--
-- Requirements:
--   * V1__schema.sql and V2__permissions.sql must already be applied.
--   * Run against a scratch/test database (e.g. psql -d app_db -f schema_test.sql).
--   * For the operational SET ROLE checks (tests 4/5) run as superuser, or as a
--     role that is a member of api_role. The ACL-only assertions work for any role.
--
-- Expected outcome: every check prints a "PASS" (or "SKIP") NOTICE; a failing
-- assertion raises an EXCEPTION and stops the script (ON_ERROR_STOP).

\set ON_ERROR_STOP 1

-- ============================================================
-- 0. Fixtures (cleanup + seed; uses high, distinctive IDs)
-- ============================================================
DO $$
BEGIN
    -- clean leftovers from a previous run (FK-safe order)
    DELETE FROM public.live_bands
    WHERE live_id IN (SELECT id FROM public.lives WHERE title LIKE 'TEST_%');
    DELETE FROM public.lives WHERE title LIKE 'TEST_%';
    DELETE FROM public.bands WHERE name LIKE 'TEST_%';
    DELETE FROM public.users WHERE username LIKE 'test_%';

    INSERT INTO public.users (id, username) VALUES (900001, 'test_user');

    INSERT INTO public.bands (id, name) VALUES (900001, 'TEST_BAND_A');
    INSERT INTO public.bands (id, name) VALUES (900002, 'TEST_BAND_B');

    -- known start_time
    INSERT INTO public.lives (id, livehouse_id, live_date, start_time, title, city, status, review_status)
    VALUES (900001, 1, CURRENT_DATE, TIME '20:00:00', 'TEST_KnownStart', 'Tokyo', 'announced', 'published');

    -- NULL start_time
    INSERT INTO public.lives (id, livehouse_id, live_date, start_time, title, city, status, review_status)
    VALUES (900002, 1, CURRENT_DATE, NULL, 'TEST_NullStart', 'Tokyo', 'announced', 'published');

    -- row for ON DELETE CASCADE check
    INSERT INTO public.lives (id, livehouse_id, live_date, start_time, title, city, status, review_status)
    VALUES (900003, 1, CURRENT_DATE, TIME '19:00:00', 'TEST_Cascade', 'Tokyo', 'announced', 'published');

    INSERT INTO public.live_bands (live_id, band_id, sort_order) VALUES (900001, 900001, 0);

    -- Bulk published Tokyo rows (ids 910001..910200) so the EXPLAIN ANALYZE
    -- in test 9 has real statistics and deterministically picks the keyset index.
    INSERT INTO public.lives (id, livehouse_id, live_date, start_time, title, city, status, review_status)
    SELECT
        910000 + g,
        1,
        CURRENT_DATE + (g % 90),
        TIME '10:00:00' + ((g % 500) * interval '1 minute'),
        'TEST_Bulk_' || g,
        'Tokyo',
        'announced',
        'published'
    FROM generate_series(1, 200) AS g;

    -- keep sequences ahead of the explicit fixture IDs
    PERFORM setval(pg_get_serial_sequence('public.lives','id'),
                   GREATEST((SELECT COALESCE(MAX(id),1) FROM public.lives), 910200));
    PERFORM setval(pg_get_serial_sequence('public.users','id'),
                   GREATEST((SELECT COALESCE(MAX(id),1) FROM public.users), 900001));
    PERFORM setval(pg_get_serial_sequence('public.bands','id'),
                   GREATEST((SELECT COALESCE(MAX(id),1) FROM public.bands), 900002));

    ANALYZE public.lives;
    ANALYZE public.live_bands;
END
$$;

-- ============================================================
-- 1. sort_start_time 生成列：NULL -> 23:59:59，非 NULL -> 原值
-- ============================================================
DO $$
DECLARE
    v_sort TIME;
BEGIN
    SELECT sort_start_time INTO v_sort FROM public.lives WHERE id = 900001;
    IF v_sort IS DISTINCT FROM TIME '20:00:00' THEN
        RAISE EXCEPTION 'FAIL: non-NULL start_time -> sort_start_time = %, expected 20:00:00', v_sort;
    END IF;

    SELECT sort_start_time INTO v_sort FROM public.lives WHERE id = 900002;
    IF v_sort IS DISTINCT FROM TIME '23:59:59' THEN
        RAISE EXCEPTION 'FAIL: NULL start_time -> sort_start_time = %, expected 23:59:59', v_sort;
    END IF;

    RAISE NOTICE 'PASS: sort_start_time maps NULL -> 23:59:59 and keeps a known TIME';
END
$$;

-- ============================================================
-- 2. Keyset 索引存在且列顺序正确 (city, live_date, sort_start_time, id)
-- ============================================================
DO $$
DECLARE
    v_indexdef TEXT;
BEGIN
    SELECT indexdef INTO v_indexdef
    FROM pg_catalog.pg_indexes
    WHERE schemaname = 'public' AND indexname = 'idx_lives_full_scope_keyset';

    IF v_indexdef IS NULL THEN
        RAISE EXCEPTION 'FAIL: idx_lives_full_scope_keyset not found';
    END IF;

    IF position('(city, live_date, sort_start_time, id)' IN v_indexdef) = 0 THEN
        RAISE EXCEPTION 'FAIL: keyset index column order is wrong: %', v_indexdef;
    END IF;

    IF position('review_status' IN v_indexdef) = 0 THEN
        RAISE EXCEPTION 'FAIL: keyset index is not partial on review_status: %', v_indexdef;
    END IF;

    RAISE NOTICE 'PASS: keyset index columns/order correct: %', v_indexdef;
END
$$;

-- ============================================================
-- 3. sync_version_counter 单行约束 (id BOOLEAN PRIMARY KEY + CHECK)
-- ============================================================
DO $$
DECLARE
    v_cnt INT;
BEGIN
    SELECT count(*) INTO v_cnt FROM public.sync_version_counter;
    IF v_cnt <> 1 THEN
        RAISE EXCEPTION 'FAIL: sync_version_counter must have exactly 1 row, found %', v_cnt;
    END IF;

    BEGIN
        INSERT INTO public.sync_version_counter (id, version) VALUES (TRUE, 1);
        RAISE EXCEPTION 'FAIL: second row with id=TRUE was accepted';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'PASS: duplicate id=TRUE rejected (unique_violation)';
    END;

    BEGIN
        INSERT INTO public.sync_version_counter (id, version) VALUES (FALSE, 1);
        RAISE EXCEPTION 'FAIL: row with id=FALSE was accepted';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'PASS: id=FALSE rejected (check_violation)';
    END;
END
$$;

-- ============================================================
-- 4. api_role 不能 INSERT 到 live_bands（应抛出权限错误）
-- ============================================================
DO $$
BEGIN
    IF has_table_privilege('api_role', 'public.live_bands', 'INSERT') THEN
        RAISE EXCEPTION 'FAIL: api_role must NOT have INSERT on live_bands';
    END IF;
    RAISE NOTICE 'PASS(ACL): api_role has no INSERT on live_bands';

    BEGIN
        SET ROLE api_role;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'SKIP: cannot SET ROLE api_role (not superuser/member); ACL check passed';
        RETURN;
    END;

    BEGIN
        INSERT INTO public.live_bands (live_id, band_id) VALUES (900001, 900001);
        RESET ROLE;
        RAISE EXCEPTION 'FAIL: api_role INSERT into live_bands was allowed';
    EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'PASS: api_role INSERT into live_bands raised insufficient_privilege';
    END;
END
$$;

-- ============================================================
-- 5. api_role 不能 UPDATE sync_version_counter
-- ============================================================
DO $$
BEGIN
    IF has_table_privilege('api_role', 'public.sync_version_counter', 'UPDATE') THEN
        RAISE EXCEPTION 'FAIL: api_role must NOT have UPDATE on sync_version_counter';
    END IF;
    RAISE NOTICE 'PASS(ACL): api_role has no UPDATE on sync_version_counter';

    BEGIN
        SET ROLE api_role;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'SKIP: cannot SET ROLE api_role (not superuser/member); ACL check passed';
        RETURN;
    END;

    BEGIN
        UPDATE public.sync_version_counter SET version = version + 1 WHERE id = TRUE;
        RESET ROLE;
        RAISE EXCEPTION 'FAIL: api_role UPDATE on sync_version_counter was allowed';
    EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'PASS: api_role UPDATE on sync_version_counter raised insufficient_privilege';
    END;
END
$$;

-- ============================================================
-- 6. REVOKE CREATE 已从 PUBLIC 撤销（public schema）
-- ============================================================
DO $$
DECLARE
    v_public_create BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace n
        CROSS JOIN LATERAL aclexplode(n.nspacl) acl
        WHERE n.nspname = 'public'
          AND acl.grantee = 0                -- grantee 0 == PUBLIC
          AND acl.privilege_type = 'CREATE'
    ) INTO v_public_create;

    IF v_public_create THEN
        RAISE EXCEPTION 'FAIL: PUBLIC still holds CREATE on schema public';
    END IF;
    RAISE NOTICE 'PASS: CREATE on schema public revoked from PUBLIC';
END
$$;

-- ============================================================
-- 7. app_definer 是 NOLOGIN
-- ============================================================
DO $$
DECLARE
    v_login BOOLEAN;
BEGIN
    SELECT rolcanlogin INTO v_login FROM pg_catalog.pg_roles WHERE rolname = 'app_definer';
    IF v_login IS NULL THEN
        RAISE EXCEPTION 'FAIL: role app_definer does not exist';
    END IF;
    IF v_login THEN
        RAISE EXCEPTION 'FAIL: app_definer must be NOLOGIN';
    END IF;
    RAISE NOTICE 'PASS: app_definer is NOLOGIN';
END
$$;

-- ============================================================
-- 8. 外键约束生效
-- ============================================================
DO $$
BEGIN
    -- live_bands.band_id -> bands(id)
    BEGIN
        INSERT INTO public.live_bands (live_id, band_id) VALUES (900001, 999999);
        RAISE EXCEPTION 'FAIL: FK allowed unknown band_id in live_bands';
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE NOTICE 'PASS: live_bands FK band_id enforced';
    END;

    -- lives.created_by -> users(id)
    BEGIN
        UPDATE public.lives SET created_by = 999999 WHERE id = 900001;
        RAISE EXCEPTION 'FAIL: FK allowed unknown created_by in lives';
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE NOTICE 'PASS: lives.created_by FK enforced';
    END;

    -- ON DELETE CASCADE from lives -> live_bands
    BEGIN
        INSERT INTO public.live_bands (live_id, band_id, sort_order) VALUES (900003, 900002, 0);
        DELETE FROM public.lives WHERE id = 900003;
        IF EXISTS (SELECT 1 FROM public.live_bands WHERE live_id = 900003) THEN
            RAISE EXCEPTION 'FAIL: ON DELETE CASCADE left orphan live_bands rows';
        END IF;
        RAISE NOTICE 'PASS: ON DELETE CASCADE from lives works';
    END;
END
$$;

-- ============================================================
-- 9. EXPLAIN ANALYZE：keyset 查询使用 idx_lives_full_scope_keyset
-- ============================================================
DO $$
DECLARE
    v_line  TEXT;
    v_plan  TEXT := '';
    v_used  BOOLEAN := FALSE;
BEGIN
    FOR v_line IN
        EXECUTE 'EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
                 SELECT id
                 FROM public.lives
                 WHERE review_status = ''published''
                   AND city = ''Tokyo''
                   AND live_date >= ''2026-08-12''
                   AND live_date <= ''2026-11-10''
                   AND (live_date, sort_start_time, id) > (''2026-09-15'', ''23:59:59'', 9988)
                 ORDER BY live_date, sort_start_time, id
                 LIMIT 10'
    LOOP
        v_plan := v_plan || v_line || E'\n';
        IF v_line LIKE '%idx_lives_full_scope_keyset%' THEN
            v_used := TRUE;
        END IF;
    END LOOP;

    IF NOT v_used THEN
        RAISE EXCEPTION 'FAIL: keyset query did not use idx_lives_full_scope_keyset. Plan:%', v_plan;
    END IF;
    RAISE NOTICE 'PASS: keyset query uses idx_lives_full_scope_keyset. Plan:%', v_plan;
END
$$;

-- ============================================================
-- 10. Cleanup fixtures
-- ============================================================
DO $$
BEGIN
    DELETE FROM public.live_bands
    WHERE live_id IN (SELECT id FROM public.lives WHERE title LIKE 'TEST_%');
    DELETE FROM public.lives WHERE title LIKE 'TEST_%';
    DELETE FROM public.bands WHERE name LIKE 'TEST_%';
    DELETE FROM public.users WHERE username LIKE 'test_%';
END
$$;

\echo 'schema_test.sql: all checks complete'
