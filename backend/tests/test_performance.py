"""
性能测试（V4.4 §16 验收第 12 条）。

覆盖：
    - 热门城市首次 /full 响应时间 < 500ms。
    - 连续 /sync 响应时间 < 200ms。
    - 并发 /full 请求不降级（全部 200，scope 一致）。

说明：
    - 阈值可经环境变量覆盖：PERF_FULL_MS、PERF_SYNC_MS。
    - 测试库连接池在 conftest 的 app fixture 已预热，避免首个请求承担建连开销。
    - 并发测试使用 asyncio.gather + 同一 httpx.AsyncClient（ASGITransport）。
"""

import asyncio
import os
import time
from datetime import timedelta

import pytest
from asyncpg import Connection

from backend.api.full import business_today

pytestmark = pytest.mark.asyncio

FULL_LIMIT_MS = int(os.getenv("PERF_FULL_MS", "500"))
SYNC_LIMIT_MS = int(os.getenv("PERF_SYNC_MS", "200"))


async def _seed_published_batch(db, insert_live, city, count):
    """在 scope 内播种 count 条 published 演出，返回 id 列表。"""
    today = business_today()
    ids = []
    for i in range(count):
        row = await insert_live(
            city=city,
            live_date=today + timedelta(days=i % 90),
            start_time=None,
            review_status="published",
            title=f"PERF_{i}",
        )
        ids.append(row["id"])
    return ids


async def test_hot_city_first_full_page(
    db: Connection, insert_live, cleanup_lives, client
):
    """热门城市首次 /full 响应时间 < 500ms。"""
    city = "PERF_FULL"
    ids = await _seed_published_batch(db, insert_live, city, 200)
    try:
        t0 = time.perf_counter()
        resp = await client.get(f"/api/v1/lives/full?city={city}&page_size=500")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["data"]) == 200
        assert body["has_more"] is False
        assert elapsed_ms < FULL_LIMIT_MS, (
            f"热门城市首次 /full 耗时 {elapsed_ms:.1f}ms，超过 {FULL_LIMIT_MS}ms"
        )
    finally:
        await cleanup_lives(ids)


async def test_consecutive_sync(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """连续 /sync 响应时间 < 200ms。"""
    city = "PERF_SYNC"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        for _ in range(3):
            row = await insert_live(city=city, live_date=today, review_status="published")
            ids.append(row["id"])
            await seed_change(row["id"], "upsert")

        scope_end = (today + timedelta(days=90)).isoformat()
        elapsed = []
        cursor = start_v
        for _ in range(3):
            t0 = time.perf_counter()
            resp = await client.get(
                f"/api/v1/lives/sync?city={city}"
                f"&scope_start_date={today.isoformat()}"
                f"&scope_end_date={scope_end}"
                f"&since={cursor}&limit=10"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert resp.status_code == 200, resp.text
            cursor = resp.json()["cursor"]
            elapsed.append(elapsed_ms)

        assert max(elapsed) < SYNC_LIMIT_MS, (
            f"连续 /sync 最大耗时 {max(elapsed):.1f}ms，超过 {SYNC_LIMIT_MS}ms"
        )
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_concurrent_full_requests(
    db: Connection, insert_live, cleanup_lives, client
):
    """并发 /full 请求不降级：全部 200、数据一致、scope 一致。"""
    city = "PERF_CONCURRENT"
    ids = await _seed_published_batch(db, insert_live, city, 50)
    try:
        async def _one():
            resp = await client.get(f"/api/v1/lives/full?city={city}&page_size=100")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert len(body["data"]) == 50
            return body

        results = await asyncio.gather(*(_one() for _ in range(10)))

        assert len(results) == 10
        scopes = {(r["scope"]["scope_start_date"], r["scope"]["scope_end_date"]) for r in results}
        assert len(scopes) == 1, "并发请求必须返回同一固定 scope"
        for r in results:
            assert r["has_more"] is False
            assert r["snapshot_cursor"] is not None
    finally:
        await cleanup_lives(ids)
