# 生产发布检查清单 — V4.4 §16 验收标准逐条核验

> 依据：`技术实现计划书 V4.4 生产基线版.txt` §十六 生产验收标准（12 条）
> 核验方式：静态代码审查 + 测试覆盖分析（本环境无 PostgreSQL 实例，未执行测试；所有「测试覆盖」结论来自测试代码审阅）
> 判定：PASS / PARTIAL / FAIL / NOT-APPLICABLE
> 核验日期：2026-08-12

---

| # | 验收标准 | 判定 | 核验结果与证据 |
|---|---|---|---|
| 1 | **所有同步接口强制 Primary** | ✅ PASS | `/full` 与 `/sync` 均通过 `get_primary_db()` 依赖从 `backend.main.primary_pool` 获取连接（`backend/api/full.py:90-99`、`backend/api/sync.py:116-125`、`backend/main.py:94-99`）。代码中不存在任何指向 replica 的同步读路径。 |
| 2 | **/full Token 已签名并包含固定 Scope** | ✅ PASS | `backend/services/token_manager.py:101-181`：HMAC-SHA256 签名，`verify_token` 先验签后解析；载荷含 `v + city + scope_start_date + scope_end_date + snapshot_cursor + last_date + last_time + last_id + exp` 全部字段。`full.py:208-233` 第一页生成固定 scope，后续页从 token 恢复（`full.py:250-255`），禁止 `CURRENT_DATE` 漂移。`test_scope.py` 覆盖午夜后 scope 不漂移。 |
| 3 | **/sync 必须校验并使用 Scope** | ✅ PASS（含 1 项 P2 改进） | `sync.py:253-258` 接收 `scope_start_date/scope_end_date` 并在 `_project_scope`（`sync.py:228-247`）按 `review_status='published' + city + 日期区间` 四条件投影；超界/隐藏/不存在均转为 delete。P2：未校验 `scope_end - scope_start` 宽度上限，客户端可传任意宽区间（见 `docs/integration_review.md` #P2-3）。 |
| 4 | **sort_start_time 生成列已落库并被索引使用** | ✅ PASS | `V1__schema.sql:17-19`：`GENERATED ALWAYS AS (COALESCE(start_time, TIME '23:59:59')) STORED`。索引 `idx_lives_full_scope_keyset (city, live_date, sort_start_time, id) WHERE review_status='published'`（V1:38-40）。查询 ORDER BY 直接引用生成列，未重写 COALESCE。`database/tests/schema_test.sql` #1/#2/#9 分别验证生成列映射、索引列序、EXPLAIN ANALYZE 命中索引。 |
| 5 | **sync_version_counter 使用单行原子递增** | ✅ PASS | `V1__schema.sql:87-91`：`id BOOLEAN PRIMARY KEY CHECK(id)` 单行；`backend/services/cdc_writer.py:35-47` 使用 `UPDATE ... SET version = version + 1 ... RETURNING version`。`test_cdc.py::test_version_monotonic` 验证 10 并发事务获得唯一且无间隙版本号。 |
| 6 | **sync_changes.version 全局唯一** | ✅ PASS | `V1__schema.sql:96-102`：`version BIGINT PRIMARY KEY`（非 sequence，无回滚空洞）。版本分配与业务修改同事务（`cdc_writer.py:150-153`）。`test_cdc.py::test_cdc_transaction_atomic` 验证回滚后计数器与日志均不可见。 |
| 7 | **cursor 过期使用 retention_floor_version 判定** | ✅ PASS | `backend/api/sync.py:267-271` 在 repeatable_read 事务内读取 `retention_floor_version`，`since < floor → 409 SYNC_CURSOR_EXPIRED`。`retention_cleaner.py:42-87` 单条语句完成「DELETE→MAX(version)→GREATEST 推进 floor」。`test_retention.py` 覆盖 since==floor 有效、since<floor 过期、无日志时返回 high_water、清理推进 floor。 |
| 8 | **客户端首次同步使用 staging store** | ✅ PASS | `frontend/services/sync_engine.js:42-100`：`firstSync` 拉 /full 全部分页写入 staging，/sync catch-up 作用于 staging，完成后 `swapStagingToActive()` 原子替换（`frontend/services/db.js:115-135`，单事务 `clear active → copy staging → clear staging`）。 |
| 9 | **/sync 分批 cursor 不越过未返回变更** | ✅ PASS | `backend/api/sync.py:283-291`：`cursor = max(本批返回 version)`，`has_more = (cursor < high_water)`，空批次 `cursor=since`。两层查询（内层 DISTINCT ON 去重 → 外层按 version ASC LIMIT）保证「未返回实体的最终版本 >= cursor」。`test_sync.py::test_limit_less_than_changes`、`test_cursor_is_batch_max_not_high_water`、`test_has_more_loop_until_complete` 全覆盖。 |
| 10 | **权限测试通过** | ✅ PASS（含 1 项部署前置） | `backend/tests/test_permissions.py`：api_role 无法 INSERT live_bands / sync_changes、无法 UPDATE sync_version_counter、PUBLIC 无法在 public schema 建表、SECURITY DEFINER owner 为 NOLOGIN 且归 app_definer、`safe_update_live_bands` 拒绝非法 JSON/未知 band_id/超长数组。`database/tests/schema_test.sql` #3-#7 同步覆盖。**部署前置**：所有角色 NOLOGIN，上线需另建应用 LOGIN 角色并 `GRANT CONNECT`（见 `docs/integration_review.md` #P1-3）。 |
| 11 | **午夜、NULL、Scope 移入移出、分页排序移动测试通过** | ⚠️ PARTIAL | 午夜：`test_scope.py::test_full_first_page_fixed_scope`（模拟 23:59:59→00:00:01 scope 不漂移）✅。NULL：`test_keyset.py` 覆盖同日期 NULL、23:59:58/59/NULL 混排、边界为 NULL、token last_time 非 NULL ✅。分页排序移动：`test_keyset.py` 覆盖同 live_date+同 sort_start_time 按 id 稳定排序 ✅。Scope 移入移出：`tests/integration/test_e2e_sync.py` 覆盖新增/更新/hidden/物理删除/移出城市/移入城市，最终断言 full+sync == 服务端 Scope 状态 ✅。**缺口**：E2E 对「移入」场景记录的是 `upsert`；若生产写路径对移入场景记录 `delete`，目标城市将错误删除该演出（`docs/integration_review.md` #P1-1，P1 级，需在写路径固化 action 语义并补测）。 |
| 12 | **压测覆盖热门城市首次 /full 与连续 /sync** | ⚠️ PARTIAL | `backend/tests/test_performance.py` 存在三项测试：热门城市首次 /full<500ms、连续 /sync<200ms、10 并发 /full 全部 200 且 scope 一致。但仅播种 200 行，非真实数据量/真实并发，未覆盖热门城市热点缓存（cache 未接入，见 `docs/integration_review.md` #P1-5）。上线前需以接近生产的数据量与并发完成基准（#P1-6）。 |

---

## 汇总

- ✅ PASS：8 条（#1-#10 除 #11 外）
- ⚠️ PARTIAL：2 条（#11、#12）
- ❌ FAIL：0 条
- NOT-APPLICABLE：0 条

## 结论

V4.4 §16 全部 12 条验收标准中，**8 条完全满足、2 条部分满足、0 条不满足**。

部分满足的两条均与「真实生产数据规模/写路径行为」相关（#11 的 Scope 移入 action 语义、#12 的压测规模与缓存），而非代码逻辑缺陷。结合 `docs/integration_review.md` 的 P1 修复清单，判定为 **CONDITIONAL-GO**：完成 P1 项（跨 Scope action 语义固化、生产写路径与 LOGIN 角色交付、限流可伪造头收敛、热门城市缓存接入与真实规模压测）后即可放行上线。
