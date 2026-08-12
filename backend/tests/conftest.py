"""
pytest 全局配置与 fixtures（V4.4 §15 测试体系）。

依赖（见 pytest.ini）：
    - pytest-asyncio（asyncio_mode=auto，loop scope=session）
    - asyncpg
    - httpx（ASGITransport 驱动 FastAPI app）
    - 真实 PostgreSQL 测试库，通过 TEST_DATABASE_URL 连接（回退 DATABASE_URL_PRIMARY）。

关键设计决策：
    1. 每个测试独立运行，不依赖执行顺序：函数级 seeding + finally 清理。
    2. 全部异步：app 的 primary_pool 由本 conftest 在 pytest session loop 创建，
       ASGITransport 在同一 loop 内驱动请求，避免 asyncpg 跨 loop 问题。
    3. schema 一次性重建（DROP SCHEMA public CASCADE 后应用 V1/V2），并做两处
       安全调整：
         a) 角色幂等创建（DO $$ IF NOT EXISTS）；
         b) 跳过 `REVOKE ALL ON DATABASE ... FROM PUBLIC`——该语句会撤销 PUBLIC
            的 CONNECT，可能锁死非 superuser 的后续测试连接；§15.6 权限验收
            只依赖 表/schema/函数 级 ACL，不受影响。
    4. TEST_DATABASE_URL 连接角色应为 superuser（SET ROLE api_role、
       DROP SCHEMA public CASCADE 需要相应权限）。

本 conftest 不覆盖已有 backend/tests/test_cdc.py 与 database/tests/schema_test.sql。
"""

import json
import os
import re
from pathlib import Path

import asyncpg
import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_DIR = BACKEND_DIR.parent
MIGRATIONS_DIR = REPO_DIR / "database" / "migrations"


# ============================================================
# 环境准备（在导入任何 backend 模块之前设置，保证 get_settings() 读取到测试值）
# ============================================================
def _env_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL_PRIMARY", "")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set to a real PostgreSQL test database. "
            "The connection role should be a superuser (needed for SET ROLE api_role "
            "and DROP SCHEMA public CASCADE)."
        )
    return url


_TEST_DB_URL = _env_db_url()

os.environ["DATABASE_URL_PRIMARY"] = _TEST_DB_URL
os.environ.setdefault("DATABASE_URL_REPLICA", "")
os.environ.setdefault("TOKEN_SECRET", "test-token-secret-for-pytest")
# 压测/并发测试需要高频请求；把限流配额调到非常大，避免 429 干扰。
os.environ.setdefault("RATE_LIMIT_FULL_PER_MINUTE", "1000000")
os.environ.setdefault("RATE_LIMIT_SYNC_PER_MINUTE", "1000000")
os.environ.setdefault("REDIS_URL", "")


# ============================================================
# 迁移应用
# ============================================================
def _db_name_from_url(url: str) -> str:
    from urllib.parse import unquote, urlsplit

    path = urlsplit(url).path
    return unquote(path.strip("/")) or "postgres"


def _sanitize_sql(sql: str, db_name: str) -> str:
    """为测试环境安全化迁移脚本。"""
    # V1/V2 中的 DATABASE 名称占位符替换为真实测试库名。
    sql = sql.replace("app_db", db_name)
    # 角色已在 _apply_schema 中幂等创建；去掉 V1 的 CREATE ROLE 语句，避免重复。
    sql = re.sub(r"CREATE ROLE (app_definer|migration_role|api_role) NOLOGIN;", "", sql)
    # 跳过 DB 级 REVOKE ALL ON DATABASE ... FROM PUBLIC（防锁死测试连接）。
    sql = re.sub(r"REVOKE ALL ON DATABASE \S+ FROM PUBLIC;", "", sql)
    return sql


async def _apply_schema(db_url: str) -> None:
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        await conn.execute(
            """
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'api_role') THEN
                    CREATE ROLE api_role NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'migration_role') THEN
                    CREATE ROLE migration_role NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_definer') THEN
                    CREATE ROLE app_definer NOLOGIN;
                END IF;
            END $$;
            """
        )
        db_name = _db_name_from_url(db_url)
        v1 = _sanitize_sql(
            (MIGRATIONS_DIR / "V1__schema.sql").read_text(encoding="utf-8"), db_name
        )
        await conn.execute(v1)
        v2 = _sanitize_sql(
            (MIGRATIONS_DIR / "V2__permissions.sql").read_text(encoding="utf-8"), db_name
        )
        await conn.execute(v2)
    finally:
        await conn.close()


# ============================================================
# 核心 fixtures
# ============================================================
@pytest_asyncio.fixture(scope="session")
async def db_url() -> str:
    return _TEST_DB_URL


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema(db_url):
    """一次性重建 schema 并应用 V1/V2 迁移。"""
    await _apply_schema(db_url)
    yield


@pytest_asyncio.fixture(scope="session")
async def pool(db_url, _schema) -> asyncpg.Pool:
    """session 级 asyncpg 连接池（供 db fixture 与并发测试使用）。"""
    p = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    yield p
    await p.close()


@pytest_asyncio.fixture
async def db(pool) -> asyncpg.Connection:
    """函数级 asyncpg.Connection（pool-backed，get_pool() 可用）。"""
    async with pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture(scope="session")
async def app(db_url, _schema):
    """FastAPI app：primary_pool 指向测试库，ASGITransport 在同一 loop 驱动。"""
    import backend.main as main
    from backend.services.token_manager import set_secret

    main.primary_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=20)
    main.replica_pool = None
    set_secret(os.getenv("TOKEN_SECRET") or "test-token-secret-for-pytest")

    # 预热连接，避免性能测试的首个请求承担建连开销。
    async with main.primary_pool.acquire() as conn:
        await conn.fetchval("SELECT 1")

    yield main.app

    await main.primary_pool.close()
    main.primary_pool = None


@pytest_asyncio.fixture(scope="session")
async def client(app):
    """httpx AsyncClient 通过 ASGITransport 驱动真实 FastAPI app（含中间件/错误处理）。"""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


# ============================================================
# 数据操作 helpers（以 fixture 形式暴露，绑定 db）
# ============================================================
@pytest_asyncio.fixture
async def insert_live(db):
    """插入一条 lives 行，返回 {id, sort_start_time}。"""

    async def _insert(
        *,
        live_date,
        city="Tokyo",
        start_time=None,
        title="TEST_LIVE",
        review_status="published",
        status="announced",
        livehouse_id=1,
        band_names=None,
        ticket_price=None,
        ticket_url=None,
        poster_image_url=None,
    ):
        if band_names is None:
            band_names = []
        return dict(
            await db.fetchrow(
                """
                INSERT INTO public.lives
                    (livehouse_id, live_date, start_time, title, ticket_price,
                     ticket_url, poster_image_url, city, band_names, status,
                     review_status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                RETURNING id, sort_start_time
                """,
                livehouse_id,
                live_date,
                start_time,
                title,
                ticket_price,
                ticket_url,
                poster_image_url,
                city,
                band_names,
                status,
                review_status,
            )
        )

    return _insert


@pytest_asyncio.fixture
async def cleanup_lives(db):
    """删除测试 lives 及其产生的 sync_changes（按 entity_id）。"""

    async def _cleanup(ids, version_floor=None):
        ids = [i for i in ids if i is not None]
        if not ids:
            return
        await db.execute(
            "DELETE FROM public.sync_changes "
            "WHERE entity_type = 'live' AND entity_id = ANY($1::bigint[])",
            ids,
        )
        if version_floor is not None:
            await db.execute("DELETE FROM public.sync_changes WHERE version > $1", version_floor)
        await db.execute(
            "DELETE FROM public.lives WHERE id = ANY($1::bigint[])", ids
        )

    return _cleanup


@pytest_asyncio.fixture
async def seed_change(db):
    """在事务内递增版本并写入一条 sync_changes，返回版本号。"""

    async def _seed(live_id: int, action: str = "upsert") -> int:
        from backend.services.cdc_writer import next_version, write_sync_change

        async with db.transaction():
            version = await next_version(db)
            await write_sync_change(db, version, "live", live_id, action)
        return version

    return _seed


@pytest_asyncio.fixture
async def sync_state(db):
    """快照 / 恢复同步状态（版本计数器 + retention floor），保证测试间隔离。"""

    class _SyncState:
        async def snapshot(self):
            version = await db.fetchval(
                "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
            )
            floor = await db.fetchval(
                "SELECT retention_floor_version FROM public.sync_retention_state WHERE id = TRUE"
            )
            return version, floor

        async def restore(self, version, floor):
            await db.execute(
                "UPDATE public.sync_version_counter SET version = $1 WHERE id = TRUE",
                version,
            )
            await db.execute(
                "UPDATE public.sync_retention_state SET retention_floor_version = $1, updated_at = now() WHERE id = TRUE",
                floor,
            )

    return _SyncState()


@pytest_asyncio.fixture
async def seed_base_data(db, insert_live, cleanup_lives):
    """V4.4 §15 通用测试数据：多城市（Tokyo/Osaka）、多日期（today/+30/+60）、
    多 review_status（published/hidden/draft）、start_time NULL/非 NULL、
    23:59:58 / 23:59:59 边界。返回 {key: id} 映射，测试结束时自动清理。"""
    from backend.api.full import business_today
    from datetime import time, timedelta

    today = business_today()
    ids = {}

    async def _mk(key, **kw):
        row = await insert_live(**kw)
        ids[key] = row["id"]

    await _mk("tokyo_pub_today", city="Tokyo", live_date=today, start_time=time(20, 0), review_status="published")
    await _mk("tokyo_pub_plus30_null", city="Tokyo", live_date=today + timedelta(days=30), start_time=None, review_status="published")
    await _mk("tokyo_pub_plus60_235958", city="Tokyo", live_date=today + timedelta(days=60), start_time=time(23, 59, 58), review_status="published")
    await _mk("tokyo_pub_plus1_235959", city="Tokyo", live_date=today + timedelta(days=1), start_time=time(23, 59, 59), review_status="published")
    await _mk("tokyo_hidden_today", city="Tokyo", live_date=today, review_status="hidden")
    await _mk("tokyo_draft_plus30", city="Tokyo", live_date=today + timedelta(days=30), review_status="draft")
    await _mk("osaka_pub_today", city="Osaka", live_date=today, start_time=time(19, 0), review_status="published")
    await _mk("osaka_pub_plus30_null", city="Osaka", live_date=today + timedelta(days=30), start_time=None, review_status="published")

    yield ids

    await cleanup_lives(list(ids.values()))


@pytest_asyncio.fixture
async def fetch_all_full(client):
    """拉取 /full 全部分页，返回 (rows, scope, snapshot_cursor)。"""

    async def _fetch(city: str, page_size: int = 2):
        rows = []
        scope = None
        snapshot_cursor = None
        next_token = None
        while True:
            url = f"/api/v1/lives/full?city={city}&page_size={page_size}"
            if next_token:
                url += f"&page_token={next_token}"
            resp = await client.get(url)
            assert resp.status_code == 200, f"/full failed: {resp.status_code} {resp.text}"
            body = resp.json()
            if scope is None:
                scope = body["scope"]
                snapshot_cursor = body["snapshot_cursor"]
            rows.extend(body["data"])
            if not body["has_more"]:
                break
            next_token = body["next_token"]
            assert next_token, "has_more=true but next_token is null"
        return rows, scope, snapshot_cursor

    return _fetch
