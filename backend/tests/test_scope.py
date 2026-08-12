"""
固定 Scope 测试（V4.4 §15.2）。

覆盖：
    - /full 第一页 scope 固定为 [business_today(), business_today()+90d]。
    - 后续分页使用与首页相同的固定 scope，即使 business_today 跨午夜变化，
      也不得漂移（不因 CURRENT_DATE 改变导致前一天数据被跳过或重复）。
    - /sync 使用与 /full 相同的 scope（超出 scope 的变更投影为 delete）。
"""

from datetime import timedelta

import pytest
from asyncpg import Connection

from backend.api.full import business_today
from backend.services.cdc_writer import next_version, write_sync_change
from backend.services.token_manager import verify_token

pytestmark = pytest.mark.asyncio

CITY = "SCOPE_TOKYO"
CITY2 = "SCOPE_TOKYO2"
CITY_SYNC = "SCOPE_SYNC"
SCOPE_DAYS = 90


async def test_full_first_page_fixed_scope(
    db: Connection, insert_live, cleanup_lives, client, monkeypatch
):
    """第一页生成固定 scope；模拟午夜后第一页 scope 不随 business_today 漂移。"""
    today = business_today()
    ids = []
    try:
        # 3 条 in-scope：today / today+45 / today+90（边界）
        for delta in (0, 45, SCOPE_DAYS):
            row = await insert_live(
                city=CITY,
                live_date=today + timedelta(days=delta),
                start_time=None,
                review_status="published",
            )
            ids.append(row["id"])

        # 模拟午夜：第一页在 D 日 23:59:59 发起，第二页在 D+1 日 00:00:01 发起。
        real = business_today
        calls = {"n": 0}

        def fake_business_today():
            calls["n"] += 1
            if calls["n"] == 1:
                return real()  # 第一页：D 日
            return real() + timedelta(days=1)  # 后续：D+1 日

        monkeypatch.setattr("backend.api.full.business_today", fake_business_today)

        resp1 = await client.get(f"/api/v1/lives/full?city={CITY}&page_size=2")
        assert resp1.status_code == 200, resp1.text
        body1 = resp1.json()
        scope1 = body1["scope"]
        assert scope1["scope_start_date"] == today.isoformat()
        assert scope1["scope_end_date"] == (today + timedelta(days=SCOPE_DAYS)).isoformat()
        assert body1["has_more"] is True

        resp2 = await client.get(
            f"/api/v1/lives/full?city={CITY}&page_size=2&page_token={body1['next_token']}"
        )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()

        # 关键断言：即使 business_today 已推进一天，scope 必须保持第一页固定值
        assert body2["scope"] == scope1, "后续分页 scope 不得漂移"
        assert body2["scope"]["scope_start_date"] != (real() + timedelta(days=1)).isoformat()
        # 数据无重复：两页合起来正好 3 条
        all_ids = [d["id"] for d in body1["data"] + body2["data"]]
        assert len(all_ids) == 3
        assert len(set(all_ids)) == 3
    finally:
        await cleanup_lives(ids)


async def test_full_next_page_same_scope(
    db: Connection, insert_live, cleanup_lives, client
):
    """后续页 scope 与首页完全一致，且 token 载荷中的 scope 字段一致。"""
    today = business_today()
    ids = []
    try:
        for delta in (0, 30, 60, SCOPE_DAYS):
            row = await insert_live(
                city=CITY2,
                live_date=today + timedelta(days=delta),
                start_time=None,
                review_status="published",
            )
            ids.append(row["id"])

        resp1 = await client.get(f"/api/v1/lives/full?city={CITY2}&page_size=2")
        body1 = resp1.json()
        scope1 = body1["scope"]
        assert body1["has_more"] is True

        resp2 = await client.get(
            f"/api/v1/lives/full?city={CITY2}&page_size=2&page_token={body1['next_token']}"
        )
        body2 = resp2.json()
        assert body2["scope"] == scope1

        payload = verify_token(body1["next_token"])
        assert payload["city"] == CITY2
        assert payload["scope_start_date"] == scope1["scope_start_date"]
        assert payload["scope_end_date"] == scope1["scope_end_date"]

        resp3 = await client.get(
            f"/api/v1/lives/full?city={CITY2}&page_size=2&page_token={body2['next_token']}"
        )
        body3 = resp3.json()
        assert body3["scope"] == scope1
        assert body3["has_more"] is False
    finally:
        await cleanup_lives(ids)


async def test_full_returns_only_published_in_scope(
    db: Connection, client, seed_base_data
):
    """seed_base_data 播种验证：/full 只返回 published 且落在 Scope 内的 Tokyo 行。"""
    # seed_base_data 覆盖：Tokyo/Osaka、today/+30/+60、published/hidden/draft、
    # NULL 与 23:59:58/23:59:59 边界。
    resp = await client.get(f"/api/v1/lives/full?city=Tokyo&page_size=100")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    got_ids = {d["id"] for d in body["data"]}

    # 只有 published 的 Tokyo 行
    assert got_ids == {
        seed_base_data["tokyo_pub_today"],
        seed_base_data["tokyo_pub_plus30_null"],
        seed_base_data["tokyo_pub_plus60_235958"],
        seed_base_data["tokyo_pub_plus1_235959"],
    }, "hidden/draft/Osaka 不得出现在 Tokyo published 结果中"

    # published 的 Tokyo 行必须包含边界 sort_start_time
    by_id = {d["id"]: d for d in body["data"]}
    null_row = by_id[seed_base_data["tokyo_pub_plus30_null"]]
    assert null_row["start_time"] is None
    assert null_row["sort_start_time"] == "23:59:59"
    edge_row = by_id[seed_base_data["tokyo_pub_plus60_235958"]]
    assert edge_row["sort_start_time"] == "23:59:58"


async def test_sync_uses_same_scope(
    db: Connection, insert_live, cleanup_lives, client, sync_state
):
    """/sync 使用与 /full 相同的 scope：超界变更投影为 delete，界内为 data。"""
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        # 界内演出
        in_row = await insert_live(
            city=CITY_SYNC, live_date=today, review_status="published"
        )
        # 界外演出（today+91 > scope_end = today+90）
        out_row = await insert_live(
            city=CITY_SYNC, live_date=today + timedelta(days=SCOPE_DAYS + 1), review_status="published"
        )
        ids = [in_row["id"], out_row["id"]]

        # 先 /full 拿固定 scope
        resp_full = await client.get(f"/api/v1/lives/full?city={CITY_SYNC}&page_size=50")
        assert resp_full.status_code == 200, resp_full.text
        body_full = resp_full.json()
        scope = body_full["scope"]
        snapshot_cursor = int(body_full["snapshot_cursor"])
        # /full 只返回界内数据
        assert [d["id"] for d in body_full["data"]] == [in_row["id"]]

        # snapshot 之后写入两行的 sync_changes
        async with db.transaction():
            v_in = await next_version(db)
            await write_sync_change(db, v_in, "live", in_row["id"], "upsert")
            v_out = await next_version(db)
            await write_sync_change(db, v_out, "live", out_row["id"], "upsert")

        # /sync 使用 /full 的同一 scope
        resp_sync = await client.get(
            f"/api/v1/lives/sync?city={CITY_SYNC}"
            f"&scope_start_date={scope['scope_start_date']}"
            f"&scope_end_date={scope['scope_end_date']}"
            f"&since={snapshot_cursor}"
        )
        assert resp_sync.status_code == 200, resp_sync.text
        body_sync = resp_sync.json()
        data_ids = [d["id"] for d in body_sync["data"]]
        assert in_row["id"] in data_ids, "界内演出必须返回 data"
        assert out_row["id"] in body_sync["deletes"], "超出 scope_end 的演出必须投影为 delete"
        assert in_row["id"] not in body_sync["deletes"]
    finally:
        await cleanup_lives(ids, version_floor=start_v)
        await sync_state.restore(start_v, floor)
