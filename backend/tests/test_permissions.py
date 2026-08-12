"""
权限测试（V4.4 §15.6）。

覆盖：
    1. api_role 不能直接写 live_bands。
    2. api_role 不能直接写 sync_changes。
    3. PUBLIC 不能在 public schema 创建对象。
    4. SECURITY DEFINER 函数 owner 是 NOLOGIN（且归 app_definer）。
    5. safe_update_live_bands 对非法 JSON / 未知 band_id / 过长数组会拒绝。

说明：
    - 需要 TEST_DATABASE_URL 连接角色为 superuser（才能 SET ROLE api_role）。
    - 使用真实数据库 ACL，不 mock；每次 SET ROLE 后必须 RESET ROLE。
"""

from datetime import date

import asyncpg
import pytest
from asyncpg import Connection

pytestmark = pytest.mark.asyncio


async def _role_has_privilege(db: Connection, role: str, table: str, priv: str) -> bool:
    return await db.fetchval(
        "SELECT has_table_privilege($1, $2, $3)", role, table, priv
    )


async def test_api_role_cannot_insert_live_bands(
    db: Connection, insert_live, cleanup_lives
):
    """api_role 不能 INSERT live_bands（V2 REVOKE INSERT）。"""
    assert not await _role_has_privilege(db, "api_role", "public.live_bands", "INSERT")

    row = await insert_live(city="PERM", live_date=date.today(), review_status="published")
    try:
        await db.execute("SET ROLE api_role")
        try:
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await db.execute(
                    "INSERT INTO public.live_bands (live_id, band_id) VALUES ($1, $2)",
                    row["id"],
                    1,
                )
        finally:
            await db.execute("RESET ROLE")
    finally:
        await cleanup_lives([row["id"]])


async def test_api_role_cannot_insert_sync_changes(db: Connection):
    """api_role 不能 INSERT sync_changes（V2 REVOKE INSERT）。"""
    assert not await _role_has_privilege(db, "api_role", "public.sync_changes", "INSERT")

    await db.execute("SET ROLE api_role")
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await db.execute(
                "INSERT INTO public.sync_changes "
                "(version, entity_type, entity_id, action) VALUES (1, 'live', 1, 'upsert')"
            )
    finally:
        await db.execute("RESET ROLE")


async def test_public_cannot_create_in_schema(db: Connection):
    """PUBLIC 不能在 public schema 创建对象。"""
    # ACL 检查：PUBLIC（grantee=0）不再拥有 public schema 的 CREATE
    public_has_create = await db.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_namespace n
            CROSS JOIN LATERAL aclexplode(n.nspacl) acl
            WHERE n.nspname = 'public'
              AND acl.grantee = 0
              AND acl.privilege_type = 'CREATE'
        )
        """
    )
    assert public_has_create is False, "PUBLIC 不应拥有 public schema 的 CREATE"

    # 操作检查：非迁移角色（api_role）无法建表
    await db.execute("SET ROLE api_role")
    try:
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await db.execute("CREATE TABLE public.perm_probe (id int)")
    finally:
        await db.execute("RESET ROLE")


async def test_security_definer_owner_is_nologin(db: Connection):
    """SECURITY DEFINER 函数 owner 必须是 NOLOGIN，且 safe_update_live_bands 归 app_definer。"""
    rows = await db.fetch(
        """
        SELECT p.proname, r.rolname AS owner, r.rolcanlogin
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
        WHERE n.nspname = 'public' AND p.prosecdef
        """
    )
    assert rows, "public schema 下应至少有一个 SECURITY DEFINER 函数"
    for row in rows:
        assert row["rolcanlogin"] is False, (
            f"SECURITY DEFINER 函数 {row['proname']} 的 owner {row['owner']} 必须 NOLOGIN"
        )

    owner = await db.fetchval(
        """
        SELECT r.rolname
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
        WHERE n.nspname = 'public' AND p.proname = 'safe_update_live_bands'
        """
    )
    assert owner == "app_definer", "safe_update_live_bands 必须归 app_definer"


async def test_safe_update_live_bands_rejects_invalid_json(
    db: Connection, insert_live, cleanup_lives
):
    """safe_update_live_bands 拒绝非法 JSON（非数组或 NULL）。"""
    row = await insert_live(city="PERM", live_date=date.today(), review_status="published")
    try:
        # 非数组 JSONB
        with pytest.raises(asyncpg.exceptions.PostgresError, match="INVALID_BANDS"):
            await db.fetchval(
                "SELECT public.safe_update_live_bands($1, $2)",
                row["id"],
                {"a": 1},
            )
        # NULL
        with pytest.raises(asyncpg.exceptions.PostgresError, match="INVALID_BANDS"):
            await db.fetchval(
                "SELECT public.safe_update_live_bands($1, NULL::jsonb)", row["id"]
            )
    finally:
        await cleanup_lives([row["id"]])


async def test_safe_update_live_bands_rejects_unknown_band(
    db: Connection, insert_live, cleanup_lives
):
    """safe_update_live_bands 拒绝未知 band_id。"""
    row = await insert_live(city="PERM", live_date=date.today(), review_status="published")
    try:
        bands = [{"band_id": 9_999_999, "sort_order": 0}]
        with pytest.raises(asyncpg.exceptions.PostgresError, match="UNKNOWN_BAND_ID"):
            await db.fetchval(
                "SELECT public.safe_update_live_bands($1, $2)", row["id"], bands
            )
    finally:
        await cleanup_lives([row["id"]])


async def test_safe_update_live_bands_rejects_too_many(db: Connection):
    """safe_update_live_bands 拒绝超过 50 个乐队的数组。"""
    bands = [{"band_id": i, "sort_order": i} for i in range(1, 52)]
    with pytest.raises(asyncpg.exceptions.PostgresError, match="TOO_MANY_BANDS"):
        await db.fetchval(
            "SELECT public.safe_update_live_bands($1, $2)", 9_000_000, bands
        )
