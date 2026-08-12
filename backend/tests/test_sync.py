"""
/sync 分批测试（V4.4 §15.4）。

覆盖：
    1. limit 小于变更数时分批正确。
    2. 返回 cursor 为本批最大 version，而不是 high_water。
    3. 客户端循环到 has_more=false 后数据完整。
    4. 同一实体多次变更只输出最终动作。
    5. 同一实体不会同时出现在 data 与 deletes。
    6. since == high_water 时返回空结果无错误。
    7. 返回按 version ASC 排序。

每个测试使用独立城市 + 版本状态快照/恢复，保证测试间隔离。
"""

from datetime import timedelta

import pytest
from asyncpg import Connection

from backend.api.full import business_today

pytestmark = pytest.mark.asyncio

SCOPE_DAYS = 90


def _scope(city: str, today) -> str:
    return (
        f"/api/v1/lives/sync?city={city}"
        f"&scope_start_date={today.isoformat()}"
        f"&scope_end_date={(today + timedelta(days=SCOPE_DAYS)).isoformat()}"
    )


async def test_limit_less_than_changes(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """limit 小于变更数时分批正确，循环到 has_more=false 后数据完整。"""
    city = "SYNC_LIMIT"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        for _ in range(5):
            row = await insert_live(city=city, live_date=today, review_status="published")
            ids.append(row["id"])
            await seed_change(row["id"], "upsert")

        data_ids = []
        cursor = start_v
        pages = 0
        while True:
            resp = await client.get(f"{_scope(city, today)}&since={cursor}&limit=2")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            data_ids.extend(d["id"] for d in body["data"])
            cursor = body["cursor"]
            pages += 1
            if not body["has_more"]:
                break
            assert pages < 10, "分批循环保护"

        assert pages == 3, "5 条变更、limit=2 应产生 3 批（2+2+1）"
        assert sorted(data_ids) == sorted(ids), "分批后必须无遗漏"
        assert len(set(data_ids)) == 5, "分批后必须无重复"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_cursor_is_batch_max_not_high_water(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """cursor 是本批最大 version，而非 high_water。"""
    city = "SYNC_CURSOR"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        for _ in range(5):
            row = await insert_live(city=city, live_date=today, review_status="published")
            ids.append(row["id"])
            await seed_change(row["id"], "upsert")

        high_water = await db.fetchval(
            "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
        )

        resp = await client.get(f"{_scope(city, today)}&since={start_v}&limit=2")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["cursor"] == start_v + 2, "cursor 必须是本批最大 version"
        assert body["cursor"] < high_water, "cursor 不得越过 high_water"
        assert body["has_more"] is True
        assert len(body["data"]) == 2
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_has_more_loop_until_complete(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """客户端循环到 has_more=false 后数据完整。"""
    city = "SYNC_LOOP"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        for _ in range(7):
            row = await insert_live(city=city, live_date=today, review_status="published")
            ids.append(row["id"])
            await seed_change(row["id"], "upsert")

        high_water = await db.fetchval(
            "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
        )

        data_ids = []
        cursor = start_v
        while True:
            resp = await client.get(f"{_scope(city, today)}&since={cursor}&limit=3")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            data_ids.extend(d["id"] for d in body["data"])
            cursor = body["cursor"]
            if not body["has_more"]:
                break

        assert cursor == high_water, "循环结束后 cursor 必须到达 high_water"
        assert sorted(data_ids) == sorted(ids), "数据必须完整"
        assert len(set(data_ids)) == 7, "不允许重复"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_same_entity_folded_to_final_action(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """同一实体多次变更只输出最终动作。"""
    city = "SYNC_FOLD"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        row = await insert_live(city=city, live_date=today, review_status="published")
        ids.append(row["id"])
        # 三次变更：upsert -> delete -> upsert（最终动作 upsert）
        await seed_change(row["id"], "upsert")
        await seed_change(row["id"], "delete")
        await seed_change(row["id"], "upsert")

        resp = await client.get(f"{_scope(city, today)}&since={start_v}&limit=10")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert [d["id"] for d in body["data"]] == [row["id"]], "最终动作必须是 upsert"
        assert body["deletes"] == []
        assert len(body["data"]) + len(body["deletes"]) == 1, "同一实体只能输出一次"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_entity_not_in_both_data_and_deletes(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """同一实体不会同时出现在 data 与 deletes。"""
    city = "SYNC_EXCL"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        # live_a：published in-scope，最终 upsert
        a = await insert_live(city=city, live_date=today, review_status="published")
        # live_b：物理删除，最终 delete
        b = await insert_live(city=city, live_date=today, review_status="published")
        ids = [a["id"], b["id"]]

        await seed_change(a["id"], "upsert")
        await seed_change(b["id"], "upsert")
        await db.execute("DELETE FROM public.lives WHERE id = $1", b["id"])
        await seed_change(b["id"], "delete")

        resp = await client.get(f"{_scope(city, today)}&since={start_v}&limit=10")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        data_ids = {d["id"] for d in body["data"]}
        delete_ids = set(body["deletes"])
        assert a["id"] in data_ids and a["id"] not in delete_ids
        assert b["id"] in delete_ids and b["id"] not in data_ids
        assert not (data_ids & delete_ids), "data 与 deletes 必须互斥"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)


async def test_sync_empty_result_when_up_to_date(client, sync_state):
    """since == high_water 时返回空结果，无错误。"""
    city = "SYNC_EMPTY"
    today = business_today()
    start_v, _ = await sync_state.snapshot()

    resp = await client.get(f"{_scope(city, today)}&since={start_v}&limit=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] == []
    assert body["deletes"] == []
    assert body["cursor"] == start_v, "空批次 cursor 应保持 since"
    assert body["has_more"] is False


async def test_sync_return_order_by_version_asc(
    db: Connection, insert_live, cleanup_lives, client, seed_change, sync_state
):
    """返回按 version ASC 排序（回放顺序）。"""
    city = "SYNC_ORDER"
    today = business_today()
    start_v, floor = await sync_state.snapshot()
    ids = []
    try:
        a = await insert_live(city=city, live_date=today, review_status="published", title="ORDER_A")
        b = await insert_live(city=city, live_date=today, review_status="published", title="ORDER_B")
        c = await insert_live(city=city, live_date=today, review_status="published", title="ORDER_C")
        ids = [a["id"], b["id"], c["id"]]

        # 按 B、C、A 顺序写入；version 分配为 B<C<A
        v_b = await seed_change(b["id"], "upsert")
        v_c = await seed_change(c["id"], "upsert")
        v_a = await seed_change(a["id"], "upsert")
        assert v_b < v_c < v_a

        resp = await client.get(f"{_scope(city, today)}&since={start_v}&limit=10")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        got = [d["title"] for d in body["data"]]
        # 输出必须按 version ASC（与写入顺序无关）：B、C、A
        assert got == ["ORDER_B", "ORDER_C", "ORDER_A"], f"必须按 version ASC: {got}"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)
