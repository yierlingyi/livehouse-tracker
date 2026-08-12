# 系统集成审查报告

> 审查对象：乐队演出查看小程序全项目（backend / database / frontend / tests）
> 审查基线：`技术实现计划书 V4.4 生产基线版.txt`（§1-§17）
> 编排设计：`docs/superpowers/specs/2026-08-12-multi-agent-orchestration-design.md`
> 审查日期：2026-08-12
> 审查性质：最终架构审查（Agent H 角色）

---

## 一、结论摘要

核心一致性不变量 **full(snapshot_cursor) + sync(after snapshot_cursor) = 服务端最终 Scope 状态** 在代码层面成立，且被端到端测试覆盖。安全姿态整体良好（Token 签名、SECURITY DEFINER 固定 search_path、NOLOGIN 专用 owner、无硬编码密钥）。性能路径的索引设计正确。

未发现必须阻塞上线的 **P0** 问题。但存在 **1 项 P1 级一致性风险（跨 Scope 移动的 action 语义）** 与若干 P1 级部署/运维缺口（生产写路径未交付、LOGIN 角色与数据库名未定义、限流可被伪造头绕过、热门城市压测不充分）。

**最终发布建议：conditional-go（条件放行）**——满足 §五 所列 4 项 P1 前置条件后即可上线。

---

## 二、一致性审查（V4.4 §1 最终一致性前提）

### 逐前提核对

| # | 前提 | 结论 | 证据 |
|---|---|---|---|
| 1 | `/full` 与 `/sync` 全部读取 Primary | ✅ 通过 | `backend/api/full.py:90-99`、`backend/api/sync.py:116-125` 的 `get_primary_db` 均从 `backend.main.primary_pool` 获取连接；`backend/main.py:94-99` 明确 Primary-only |
| 2 | 所有影响客户端可见数据的写入与 sync_changes 同事务 | ⚠️ 部分通过 | `backend/services/cdc_writer.py:150-153` 的 `cdc_transaction` 保证同事务；但**生产环境没有任何调用方**（见问题 #P1-1），且 `safe_update_live_bands` 不写 sync_changes（V1:151-246），只能靠调用方约定 |
| 3 | `/full` 第一页固定 Scope，后续分页与 `/sync` 沿用 | ✅ 通过 | `full.py:208-233` 第一页用 `business_today()` 生成一次；token 携带 scope；`full.py:250-255` 后续页从 token 恢复，无 `CURRENT_DATE`；`test_scope.py` 覆盖午夜漂移 |
| 4 | 客户端完成 `/full` 后立即 `/sync?since=snapshot_cursor` | ✅ 通过 | `frontend/services/sync_engine.js:75-99`：拉完所有 /full 页后，以 `snapshot_cursor` 起始循环 /sync 直到 `has_more=false` |
| 5 | cursor 过期用 `retention_floor_version` 判定 | ✅ 通过 | `backend/api/sync.py:267-271` 在 repeatable_read 事务内读 floor 并比较；`retention_cleaner.py` 单语句 `DELETE→MAX(version)→UPDATE floor` |
| 6 | `sort_start_time` 生成列正确使用 | ✅ 通过 | V1:17-19 生成列 `COALESCE(start_time, '23:59:59') STORED`；`full.py` ORDER BY 直接引用 `sort_start_time`，token `last_time` 取生成列（`token_manager.py:217`）；查询未重写 COALESCE |
| 7 | Token 签名且含全部必需字段 | ✅ 通过 | `token_manager.py:101-181` HMAC-SHA256 + `hmac.compare_digest`；载荷含 v + 8 字段；`verify_token` 先验签后解析、校验类型与 exp |
| 8 | `/sync` cursor 推进正确（max returned vs high_water） | ✅ 通过 | `sync.py:283-291`：`batch_high = max(返回 version)`，`has_more = batch_high < high_water`；空批次 `cursor=since`。`test_sync.py` 全面覆盖 |

### 一致性核心算法复核

- **/full keyset**：`(live_date, sort_start_time, id) > (...)` 与 ORDER BY 精确匹配部分索引 `idx_lives_full_scope_keyset`（V1:38-40）。`page_size+1` 判 has_more 正确。
- **/sync 去重**：内层 `DISTINCT ON (entity_type, entity_id) ... ORDER BY entity_id, version DESC`，外层 `ORDER BY version ASC LIMIT`（`sync.py:78-94`）。此两层结构避免了「按 entity_id 截断导致 cursor 越过未返回变更」的漏读，符合 V4.4 §15.4 验收。手工推演（同实体多版本、limit 截断、跨批折叠）均无遗漏/重复。
- **强快照**：`repeatable_read` 内同时读取 floor / high_water / sync_changes / lives，避免与 retention 清理并发时读到不完整批次。

### 一致性审查发现的关键风险

见问题 **#P1-1**（跨 Scope 移动的 action 语义）。这是唯一能破坏最终一致性不变量、且当前测试未覆盖的真实场景。

---

## 三、安全审查

| 检查项 | 结论 | 证据 |
|---|---|---|
| api_role 直接写受保护表 | ✅ 无直接路径 | V2:47-49 REVOKE；`test_permissions.py` 验证 api_role 无法 INSERT live_bands / sync_changes、无法 UPDATE sync_version_counter |
| api_role 间接写路径 | ⚠️ `safe_update_live_bands` 已授予 EXECUTE（V1:249-250），属合规安全路径，但**不写 sync_changes**（见问题 #P1-2） | V1:151-246 |
| Token 伪造 | ✅ 不可伪造 | HMAC-SHA256，密钥由 env 注入（`main.py:59`）；`verify_token` 先验签后解析，常数时间比较 |
| Token 重放 | ✅ 只读分页，风险可接受 | 30 分钟 TTL（`token_manager.py:219`）；重放仅能重读同一页，无写操作 |
| SQL 注入（SECURITY DEFINER） | ✅ search_path 固定 | `fn_update_timestamp`（V1:51）与 `safe_update_live_bands`（V1:164）均 `SET search_path = pg_catalog, public, pg_temp` |
| 函数提权 owner | ✅ NOLOGIN `app_definer` | V2:81-82 `ALTER FUNCTION ... OWNER TO app_definer`；`test_permissions.py:94-120` 验证 NOLOGIN |
| 密钥硬编码 | ✅ 无 | `config.py:88-104` 全部来自 env；仓库 grep 未发现硬编码 token_secret / database_url |

### 安全审查发现的风险

- **#P1-4**：限流依赖客户端可控的 `X-User-Id` 与 `X-Forwarded-For`，可被伪造绕过。
- **#P1-3**：所有角色 NOLOGIN，未交付后端应用 LOGIN 角色；若实际连接角色是超管/owner，则 api_role 的 ACL 防线形同虚设。

---

## 四、性能审查

| 检查项 | 结论 | 证据 |
|---|---|---|
| /full keyset 索引命中 | ✅ | `schema_test.sql` #9 用 EXPLAIN ANALYZE 验证命中 `idx_lives_full_scope_keyset`；查询列序与索引精确一致 |
| /sync 索引 | ⚠️ | `idx_sync_changes_version`（version）支持范围扫描；内层 DISTINCT ON 在 `(since, high_water]` 全区间去重后再 LIMIT，写放大时成本随区间长度线性增长（见 #P2-2） |
| 热门城市 /full 首页缓存 | ❌ 未生效 | `backend/services/cache.py` 已实现完整缓存层（含 key 前缀硬校验、TTL jitter），但 **full.py 未调用** `get_cached_full/set_cached_full`，等于未接入（见 #P1-5） |
| /sync 限流与分批 | ✅ | limit 默认 1000 / 最大 5000（`sync.py:41`）；分批 cursor 语义正确 |
| Redis 参与一致性判定 | ✅ 不参与 | `cache.py:1-6` 硬校验仅允许 `full:lives:v1:` 前缀，`/sync` 永不入缓存；`main.py:22` 声明 Redis 只做性能优化 |

---

## 五、集成问题清单

### P0（阻塞上线）

无。

### P1（上线前必须修复/确认）

**#P1-1 跨 Scope 移动的 action 语义可破坏目标城市一致性**
- 位置：`backend/api/sync.py:228-247`（`_project_scope`）、`backend/services/cdc_writer.py:72-118`（`determine_action`）
- 描述：`sync_changes` 是**全局单条**记录，只存一个 action。`_project_scope` 中 `in_scope` 要求 `action == "upsert"` 才可能进 data；`action == "delete"` 时直接判 delete，**不复查当前行**。若生产写路径在「演出从 Tokyo 移入 Osaka」时按旧城市 scope 计算 `determine_action(..., city='Tokyo')` 得到 `delete` 并落库，则 Osaka 客户端 /sync 会收到 delete 并移除该演出——即使它在 Osaka scope 内已 published。这与 V4.4 §15.3「city 从其他城市移入当前 Scope」的验收相冲突。
- 当前 E2E 测试（`tests/integration/test_e2e_sync.py:96-103`）对移入场景手动记录的是 `upsert`，因此测试通过，未暴露此风险。
- 修复要求（择一）：
  1. **约定并强制**：写路径对任何「仍为 published 的行」一律记录 `upsert`（无论 city/date 是否在目标 scope），`delete` 仅用于 hidden/draft/物理删除；并新增一条测试：对「已 published、但 sync_changes action=delete」的行，验证目标 scope 投影。
  2. **改 `_project_scope`**：即使 action=delete，只要行存在且当前满足 Scope（published + city + 日期），仍输出 upsert（更贴近 V4.4 §10.3「/sync 输出必须按 Scope 转换」的意图，但偏离 §10.3 参考伪码）。
- 建议：采用方案 2（更健壮），并在写路径文档与测试中固化方案 1 的约束。

**#P1-2 生产写路径未交付，CDC 同事务写入无强制手段**
- 位置：`backend/services/cdc_writer.py`、`backend/api/`（无任何写端点）、`database/docs/security_review.md:83`
- 描述：`cdc_writer` 与 `safe_update_live_bands` 在仓库中**只有测试引用**。生产上创建/更新演出没有任何已交付的入口。若运营人员用 psql/管理工具直写 `lives`，或未来新增的管理端点忘记调用 `cdc_transaction`，则一致性前提 #2 被绕过且无审计可查。V4.4 §1 明确要求「必须通过权限和审计禁止绕过」。
- 修复要求：上线前交付（或书面固化）生产写路径——所有写 `lives`/`live_bands` 的后端服务必须在同一事务内 `next_version + write_sync_change`；建议在 CI 增加一条「对受保护表的 DML 必须伴随 sync_changes」的规则测试或启用 pgAudit 审计。

**#P1-3 数据库名 `app_db` 硬编码 + 无应用 LOGIN 角色**
- 位置：`database/migrations/V1__schema.sql:147`（`REVOKE ALL ON DATABASE app_db FROM PUBLIC`）、V1:138-140（三角色均 NOLOGIN）、`database/docs/security_review.md:80-81`
- 描述：(a) 实际库名若非 `app_db`，V1 迁移会失败；(b) 后端连接角色未定义——若用超管/owner 连接，api_role 的只读防线失效。
- 修复要求：迁移脚本参数化库名；部署文档明确创建 LOGIN 角色并授予 api_role 权限与 `GRANT CONNECT ON DATABASE`，且该角色对 `lives/bands/live_bands` 仅 SELECT。

**#P1-4 限流可被伪造头绕过**
- 位置：`backend/main.py:121-148`、`backend/services/rate_limiter.py:73-91`
- 描述：/sync 按 `X-User-Id`（缺省 IP）限流，攻击者可任意旋转该头绕过配额；`client_ip` 无条件信任 `X-Forwarded-For` 首值，可伪造 IP 绕过 /full 限流。虽然读取接口无数据完整性风险，但构成对 /full、/sync 的 DoS 缺口。
- 修复要求：部署在可信反向代理后，仅信任代理注入的 XFF；/sync 限流键建议绑定不可伪造的用户身份（登录态）或改用签名参数。

**#P1-5 热门城市 /full 首页缓存未接入**
- 位置：`backend/api/full.py`（无缓存调用）、`backend/services/cache.py`（已实现但闲置）
- 描述：V4.4 §12 允许缓存 /full 首页/热点页以缓解高并发；`cache.py` 完整实现了 key 前缀硬校验与 TTL jitter，但 full.py 从未调用。当前热门城市首页每次请求都直查 Primary。
- 修复要求：在 `full.py` 第一页路径接入 `get_cached_full/set_cached_full`（key 含 city+scope+token_hash，TTL 60-90s）。注意缓存命中必须原样返回固定 Scope 与 snapshot_cursor，且 TTL 不得超过 retention 安全窗口（否则客户端 /sync?since=旧 cursor 会 409 触发重新 /full，仍安全但增加回源）。

**#P1-6 压测不满足 V4.4 §16 验收第 12 条**
- 位置：`backend/tests/test_performance.py`
- 描述：仅播种 200 行、断言 /full<500ms、/sync<200ms，且单机测试库无真实并发负载，未覆盖「热门城市真实数据量 + 连续 /sync 高峰」。
- 修复要求：上线前用接近生产的数据量（如 1 万+ 行/城市）与并发客户端做一次基准，确认 keyset 分页与 DISTINCT ON 在真实规模下达标。

### P2（后续优化）

**#P2-1 前端未实现 Service Worker**
- 位置：`frontend/`（无 sw.js / service-worker 注册）
- V4.4 技术栈与编排设计 §七均列明 Service Worker；当前离线能力仅靠 IndexedDB 缓存，弱网首屏/静态资源离线未覆盖。V4.4 §2 全局原则 9 明确 SW 不参与一致性判定，故为性能增强项。

**#P2-2 /sync DISTINCT ON 扫描成本随版本区间线性增长**
- 位置：`backend/api/sync.py:78-94`
- 描述：内层须对 `(since, high_water]` 内全部变更去重后才 LIMIT；写放大场景（如热门城市高频更新）下，即使 limit 很小，每批也要扫全区间。当前规模可接受，后续可考虑按 entity 折叠的增量索引或对高 version 段做增量物化。

**#P2-3 /sync 未校验 scope_start <= scope_end，且 scope 宽度客户端可控**
- 位置：`backend/api/sync.py:253-258`
- 描述：客户端可传任意宽日期区间拉取全部 published 数据（公开数据，无保密风险），也可用超大区间放大扫描。建议服务端校验 `scope_end - scope_start <= 90 天` 且 `scope_start = 服务端业务日`（或至少合法化宽度上限）。

**#P2-4 计划书文件结构与实际有出入**
- 位置：`docs/superpowers/specs/.../design.md:201,284`（列了 `stores/sync_store.js`、`test_full.py`）
- 实际同步逻辑放在 `frontend/services/sync_engine.js`，/full 测试分散在 `test_scope.py`/`test_keyset.py`。非缺陷，仅文档与实现未对齐，建议更新设计文档。

**#P2-5 其他小项**
- `business_today()` 在无 IANA tzdata 时回退 UTC（`full.py:102-112`），跨午夜窗口可能偏差一天——生产部署需确保 tzdata 可用。
- `safe_update_live_bands` 的 `sort_order` 未做纯数字过滤，非数字输入会抛 PG 22007 而非业务错误（`database/docs/security_review.md:82`）。
- 城市列表在前端硬编码（`city-switch.vue:46`），后端新增城市需同步发版。

---

## 六、最终发布建议

### 判定：CONDITIONAL-GO（条件放行）

核心一致性不变量正确实现且测试充分，安全基线达标，索引设计正确，未发现 P0。满足以下 **P1 前置条件**后即可上线：

1. **#P1-1** 明确并固化跨 Scope 移动的 action 语义（建议采用 `_project_scope` 复查当前行 + 写路径约定「published 即 upsert」），并补一条针对性测试。
2. **#P1-2 / #P1-3** 交付生产写路径（必须走 cdc_transaction 同事务）并定义应用 LOGIN 角色与真实库名，完成部署安全校验。
3. **#P1-4** 收敛限流键的可伪造性（可信代理 + 绑定真实身份）。
4. **#P1-5 / #P1-6** 接入热门城市 /full 缓存并用接近生产的数据量完成压测。

P2 项可在上线后迭代，不影响发布。

---

## 七、审查覆盖文件清单

- `技术实现计划书 V4.4 生产基线版.txt`
- `docs/superpowers/specs/2026-08-12-multi-agent-orchestration-design.md`
- `database/migrations/V1__schema.sql`、`V2__permissions.sql`、`database/docs/security_review.md`、`database/tests/schema_test.sql`
- `backend/main.py`、`config.py`、`api/full.py`、`api/sync.py`、`services/*`（token_manager/cdc_writer/retention_cleaner/cache/rate_limiter）、`middleware/*`、`contracts/*`
- `backend/tests/*`、`tests/integration/test_e2e_sync.py`
- `frontend/**`（pages/components/services）
