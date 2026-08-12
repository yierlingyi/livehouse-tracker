"""
Keyset 分页测试（V4.4 §15.1）。

覆盖：
    1. 同一天多条 start_time 非空。
    2. 同一天多条 start_time IS NULL（sort_start_time 恒为 23:59:59）。
    3. 23:59:58 / 23:59:59 / NULL 同时存在时排序正确。
    4. 分页边界最后一条为 NULL（sort_start_time=23:59:59）。
    5. 分页边界最后一条为 23:59:59。
    6. 同 live_date、同 sort_start_time 下按 id 稳定排序。

验收：无重复、无遗漏、next_token.last_time 非 NULL、ORDER BY 与 keyset 比较字段一致。

每个测试使用独立城市名，保证测试间隔离（不依赖执行顺序）。
"""

from datetime import time

import pytest
from asyncpg import Connection

from backend.api.full import business_today
from backend.services.token_manager import verify_token

pytestmark = pytest.mark.asyncio

# 每个测试独立城市，避免相互干扰
CITY_NONNULL = "KS_NONNULL"
CITY_NULL = "KS_NULL"
CITY_MIX = "KS_MIX"
CITY_EDGE_NULL = "KS_EDGE_NULL"
CITY_EDGE_2359 = "KS_EDGE_2359"
CITY_STABLE = "KS_STABLE"
CITY_DEDUP = "KS_DEDUP"
CITY_TOKEN = "KS_TOKEN"


async def test_same_date_multiple_non_null_start_times(
    db: Connection, insert_live, cleanup_lives, fetch_all_full, client
):
    """同一天多条有 start_time，按 sort_start_time ASC 分页，无重复无遗漏。"""
    city = CITY_NONNULL
    today = business_today()
    ids = []
    times = [
        time(10, 0, 0),
        time(11, 0, 0),
        time(12, 0, 0),
        time(13, 0, 0),
        time(14, 0, 0),
    ]
    try:
        for t in times:
            row = await insert_live(
                city=city, live_date=today, start_time=t, review_status="published"
            )
            ids.append(row["id"])

        rows, _, _ = await fetch_all_full(client, city, page_size=2)

        assert len(rows) == 5, "全部 5 条必须返回"
        got = [(r["id"], r["sort_start_time"]) for r in rows]
        assert [t for _, t in got] == [
            "10:00:00",
            "11:00:00",
            "12:00:00",
            "13:00:00",
            "14:00:00",
        ], "sort_start_time 必须升序"
        assert len({i for i, _ in got}) == 5, "不允许重复 id"
        assert all(r["live_date"] == today.isoformat() for r in rows)
    finally:
        await cleanup_lives(ids)


async def test_same_date_multiple_null_start_times(
    db: Connection, insert_live, cleanup_lives, fetch_all_full, client
):
    """同一天多条 start_time IS NULL：sort_start_time 均为 23:59:59，按 id 稳定排序。"""
    city = CITY_NULL
    today = business_today()
    ids = []
    try:
        for _ in range(5):
            row = await insert_live(
                city=city, live_date=today, start_time=None, review_status="published"
            )
            ids.append(row["id"])

        rows, _, _ = await fetch_all_full(client, city, page_size=2)

        assert len(rows) == 5, "全部 5 条必须返回"
        assert all(r["sort_start_time"] == "23:59:59" for r in rows)
        assert all(r["start_time"] is None for r in rows)
        got_ids = [r["id"] for r in rows]
        assert got_ids == sorted(got_ids), "同 sort_start_time 下必须按 id ASC 稳定排序"
        assert len(set(got_ids)) == 5, "不允许重复 id"
    finally:
        await cleanup_lives(ids)


async def test_235958_235959_null_ordering(
    db: Connection, insert_live, cleanup_lives, fetch_all_full, client
):
    """23:59:58、23:59:59、NULL 同时存在时排序正确（58 < 两个 59 按 id 排）。"""
    city = CITY_MIX
    today = business_today()
    ids = []
    try:
        r58 = await insert_live(
            city=city, live_date=today, start_time=time(23, 59, 58), review_status="published"
        )
        r59 = await insert_live(
            city=city, live_date=today, start_time=time(23, 59, 59), review_status="published"
        )
        rnull = await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        ids = [r58["id"], r59["id"], rnull["id"]]

        rows, _, _ = await fetch_all_full(client, city, page_size=1)

        got = [r["sort_start_time"] for r in rows]
        assert got == ["23:59:58", "23:59:59", "23:59:59"], f"排序错误: {got}"
        # 两个 23:59:59 之间按 id 稳定排序
        assert rows[1]["id"] < rows[2]["id"]
        assert rows[1]["start_time"] == "23:59:59"
        assert rows[2]["start_time"] is None
    finally:
        await cleanup_lives(ids)


async def test_page_boundary_ends_with_null(
    db: Connection, insert_live, cleanup_lives, client
):
    """分页边界最后一条是 NULL（sort_start_time=23:59:59），next_token 引用该行。"""
    city = CITY_EDGE_NULL
    today = business_today()
    ids = []
    try:
        ra = await insert_live(
            city=city, live_date=today, start_time=time(10, 0, 0), review_status="published"
        )
        rb = await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        rc = await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        ids = [ra["id"], rb["id"], rc["id"]]

        # 排序：(10:00, ra), (23:59:59, rb), (23:59:59, rc) → page1=[ra, rb]
        resp1 = await client.get(f"/api/v1/lives/full?city={city}&page_size=2")
        assert resp1.status_code == 200, resp1.text
        body1 = resp1.json()
        assert body1["has_more"] is True
        assert len(body1["data"]) == 2
        last = body1["data"][-1]
        assert last["id"] == rb["id"], "边界最后一条应为 NULL 行"
        assert last["start_time"] is None
        assert last["sort_start_time"] == "23:59:59"

        payload = verify_token(body1["next_token"])
        assert payload["last_id"] == rb["id"]
        assert payload["last_time"] == "23:59:59"
        assert payload["last_date"] == today.isoformat()

        # 第二页应只返回 rc
        resp2 = await client.get(
            f"/api/v1/lives/full?city={city}&page_size=2&page_token={body1['next_token']}"
        )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        assert body2["has_more"] is False
        assert [d["id"] for d in body2["data"]] == [rc["id"]]
    finally:
        await cleanup_lives(ids)


async def test_page_boundary_ends_with_235959(
    db: Connection, insert_live, cleanup_lives, client
):
    """分页边界最后一条是显式 23:59:59（start_time 非空）。"""
    city = CITY_EDGE_2359
    today = business_today()
    ids = []
    try:
        ra = await insert_live(
            city=city, live_date=today, start_time=time(10, 0, 0), review_status="published"
        )
        rb = await insert_live(
            city=city, live_date=today, start_time=time(23, 59, 59), review_status="published"
        )
        rc = await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        ids = [ra["id"], rb["id"], rc["id"]]

        # 排序：(10:00, ra), (23:59:59, rb), (23:59:59, rc) → page1=[ra, rb]
        resp1 = await client.get(f"/api/v1/lives/full?city={city}&page_size=2")
        body1 = resp1.json()
        assert body1["has_more"] is True
        last = body1["data"][-1]
        assert last["id"] == rb["id"], "边界最后一条应为显式 23:59:59 行"
        assert last["start_time"] == "23:59:59"
        assert last["sort_start_time"] == "23:59:59"

        payload = verify_token(body1["next_token"])
        assert payload["last_time"] == "23:59:59"
        assert payload["last_id"] == rb["id"]

        resp2 = await client.get(
            f"/api/v1/lives/full?city={city}&page_size=2&page_token={body1['next_token']}"
        )
        body2 = resp2.json()
        assert body2["has_more"] is False
        assert [d["id"] for d in body2["data"]] == [rc["id"]]
    finally:
        await cleanup_lives(ids)


async def test_same_date_same_time_stable_id_order(
    db: Connection, insert_live, cleanup_lives, fetch_all_full, client
):
    """同 live_date、同 sort_start_time 下按 id 稳定排序（分页跨页后顺序一致）。"""
    city = CITY_STABLE
    today = business_today()
    ids = []
    try:
        for _ in range(6):
            row = await insert_live(
                city=city, live_date=today, start_time=time(20, 0, 0), review_status="published"
            )
            ids.append(row["id"])

        rows, _, _ = await fetch_all_full(client, city, page_size=2)

        got_ids = [r["id"] for r in rows]
        assert len(got_ids) == 6
        assert got_ids == sorted(got_ids), "必须按 id ASC 稳定排序"
        assert all(r["sort_start_time"] == "20:00:00" for r in rows)
    finally:
        await cleanup_lives(ids)


async def test_no_duplicates_across_pages(
    db: Connection, insert_live, cleanup_lives, fetch_all_full, client
):
    """跨页无重复、无遗漏：所有种子 id 恰好出现一次。"""
    city = CITY_DEDUP
    today = business_today()
    ids = []
    times = [None, time(9, 30, 0), time(23, 59, 58), time(23, 59, 59), None, time(15, 0, 0), time(0, 30, 0)]
    try:
        for t in times:
            row = await insert_live(
                city=city, live_date=today, start_time=t, review_status="published"
            )
            ids.append(row["id"])

        rows, _, _ = await fetch_all_full(client, city, page_size=3)

        got_ids = [r["id"] for r in rows]
        assert len(got_ids) == 7
        assert len(set(got_ids)) == 7, "跨页不允许重复"
        assert set(got_ids) == set(ids), "不允许遗漏任何一条"
    finally:
        await cleanup_lives(ids)


async def test_next_token_last_time_not_null(
    db: Connection, insert_live, cleanup_lives, client
):
    """next_token.last_time 永不为 NULL（NULL start_time 映射为 23:59:59）。"""
    city = CITY_TOKEN
    today = business_today()
    ids = []
    try:
        await insert_live(
            city=city, live_date=today, start_time=time(10, 0, 0), review_status="published"
        )
        rb = await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        await insert_live(
            city=city, live_date=today, start_time=None, review_status="published"
        )
        ids = [rb["id"]]

        resp = await client.get(f"/api/v1/lives/full?city={city}&page_size=2")
        body = resp.json()
        assert body["has_more"] is True
        assert body["next_token"] is not None

        payload = verify_token(body["next_token"])
        assert payload["last_time"] is not None, "last_time 必须非 NULL"
        assert payload["last_time"] == "23:59:59"
        # 原始 start_time 为 NULL，但 token 用的是生成列 sort_start_time
        assert payload["last_id"] == rb["id"]
    finally:
        await cleanup_lives(ids)
