"""
端到端一致性测试（V4.4 §15.3 验收）。

验证：/full(snapshot_cursor) + /sync(after) == 服务端在 high_water 快照下的
Scope 查询结果。

流程（完整复现客户端首次同步，V4.4 §11.1）：
    1. 提交初始状态（含 sync_changes，版本 <= snapshot_cursor）。
    2. /full 拉全量 → 得到固定 scope + snapshot_cursor，构造本地正式集。
    3. snapshot 之后应用各类变更（新增 / 更新 / hidden / 物理删除 / 移出 scope /
       其他城市移入），全部写 sync_changes（版本 > snapshot_cursor）。
    4. /sync 从 snapshot_cursor 追平（循环到 has_more=false），应用 data/deletes。
    5. 最终本地集 == 服务端 Scope 状态（published + city + 日期区间）。

使用独立城市 + 版本状态快照/恢复，保证测试间隔离。
"""

from datetime import timedelta

import pytest
from asyncpg import Connection

from backend.api.full import business_today

pytestmark = pytest.mark.asyncio

CITY = "E2E_TOKYO"
OTHER_CITY = "E2E_OSAKA"
SCOPE_DAYS = 90


async def test_full_plus_sync_equals_server_state(
    db: Connection,
    insert_live,
    cleanup_lives,
    client,
    seed_change,
    sync_state,
    fetch_all_full,
):
    today = business_today()
    scope_start = today
    scope_end = today + timedelta(days=SCOPE_DAYS)
    start_v, floor = await sync_state.snapshot()
    ids = []

    try:
        # ============ 阶段 1：初始状态（snapshot 之前） ============
        a = await insert_live(
            city=CITY, live_date=today, start_time=None, title="E2E_A", review_status="published"
        )
        b = await insert_live(
            city=CITY, live_date=today + timedelta(days=1), start_time=None, title="E2E_B", review_status="published"
        )
        c = await insert_live(
            city=CITY, live_date=today + timedelta(days=10), start_time=None, title="E2E_C", review_status="published"
        )
        ids = [a["id"], b["id"], c["id"]]
        for lid in ids:
            await seed_change(lid, "upsert")

        # ============ 阶段 2：/full 全量拉取 ============
        rows, scope, snapshot_cursor = await fetch_all_full(client, CITY, page_size=2)
        client_state = {r["id"]: r for r in rows}
        assert set(client_state) == {a["id"], b["id"], c["id"]}, "/full 必须返回全部初始数据"
        assert scope == {
            "city": CITY,
            "scope_start_date": scope_start.isoformat(),
            "scope_end_date": scope_end.isoformat(),
        }

        # ============ 阶段 3：snapshot 之后的变更 ============
        # 3.1 新增 published in-scope 演出
        d = await insert_live(
            city=CITY, live_date=today + timedelta(days=20), start_time=None, title="E2E_D", review_status="published"
        )
        ids.append(d["id"])
        await seed_change(d["id"], "upsert")

        # 3.2 更新现有演出标题
        await db.execute("UPDATE public.lives SET title = $1 WHERE id = $2", "E2E_A_UPDATED", a["id"])
        await seed_change(a["id"], "upsert")

        # 3.3 published -> hidden
        await db.execute("UPDATE public.lives SET review_status = 'hidden' WHERE id = $1", b["id"])
        await seed_change(b["id"], "delete")

        # 3.4 物理删除
        await db.execute("DELETE FROM public.lives WHERE id = $1", c["id"])
        await seed_change(c["id"], "delete")

        # 3.5 移出 scope（city 移到其他城市）
        await db.execute("UPDATE public.lives SET city = $1 WHERE id = $2", OTHER_CITY, a["id"])
        await seed_change(a["id"], "delete")

        # 3.6 其他城市移入当前 scope
        e = await insert_live(
            city=OTHER_CITY, live_date=today + timedelta(days=30), start_time=None, title="E2E_E", review_status="published"
        )
        ids.append(e["id"])
        await seed_change(e["id"], "delete")  # 在其他城市 scope 中是 delete
        await db.execute("UPDATE public.lives SET city = $1 WHERE id = $2", CITY, e["id"])
        await seed_change(e["id"], "upsert")  # 移入后最终 upsert

        # ============ 阶段 4：/sync 从 snapshot_cursor 追平 ============
        cursor = int(snapshot_cursor)
        guard = 0
        while True:
            resp = await client.get(
                f"/api/v1/lives/sync?city={CITY}"
                f"&scope_start_date={scope['scope_start_date']}"
                f"&scope_end_date={scope['scope_end_date']}"
                f"&since={cursor}&limit=3"
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            for row in body["data"]:
                client_state[row["id"]] = row
            for lid in body["deletes"]:
                client_state.pop(lid, None)
            cursor = body["cursor"]
            guard += 1
            assert guard < 50, "sync 循环保护"
            if not body["has_more"]:
                break

        # ============ 阶段 5：与服务端 Scope 状态对比 ============
        expected = await db.fetch(
            """
            SELECT id, title, live_date, city, review_status
            FROM public.lives
            WHERE review_status = 'published'
              AND city = $1
              AND live_date >= $2
              AND live_date <= $3
            """,
            CITY,
            scope_start,
            scope_end,
        )
        expected_map = {r["id"]: r for r in expected}

        assert set(client_state.keys()) == set(expected_map.keys()), (
            f"客户端 id 集 {set(client_state)} != 服务端 id 集 {set(expected_map)}"
        )
        for lid, srow in expected_map.items():
            crow = client_state[lid]
            assert crow["id"] == srow["id"]
            assert crow["title"] == srow["title"], f"id={lid} 标题不一致"
            assert crow["live_date"] == srow["live_date"].isoformat(), f"id={lid} 日期不一致"
            assert crow["city"] == srow["city"]

        # 最终客户端状态只包含移入/新增的 d、e
        assert set(client_state) == {d["id"], e["id"]}, "最终状态应为新增 d 与移入 e"
    finally:
        await sync_state.restore(start_v, floor)
        await cleanup_lives(ids, version_floor=start_v)
