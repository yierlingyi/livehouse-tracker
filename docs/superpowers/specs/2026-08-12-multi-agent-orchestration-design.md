# Multi-Agent Orchestration Design — 乐队演出查看小程序

> 版本：1.0  
> 日期：2026-08-12  
> 基线：技术实现计划书 V4.4 生产基线版  
> 目标：8 个 AI Agent 协作完成可生产部署的项目

---

## 一、设计决策汇总

| 决策 | 选择 |
|------|------|
| 编排方式 | 顺序 Supervisor 驱动（Approach 1） |
| 契约机制 | Phase 0 预生成共享契约文件 |
| 模型分配 | haiku=v4flash（Agent A/C/E/F/G），sonnet=v4p（Agent B/D/H） |
| 节奏 | 6 阶段门控，每阶段 Supervisor 初步评审 → 用户最终审批 |
| 文件结构 | 单仓库，清晰模块边界 |
| 审查 | 6 道门，~80 项检查清单 |

---

## 二、契约层（Phase 0）

在任何 Agent 编写代码之前，Supervisor 从 V4.4 提取以下共享契约文件：

### 2.1 SQL Schema Contract (`database/migrations/V1__schema.sql`)

从 V4.4 §4-8 提取，包含：
- `lives` 表（含 `sort_start_time` 生成列）
- `live_bands` 表
- `sync_version_counter`（单行，`UPDATE...RETURNING version`）
- `sync_changes`（全局唯一 version，实体折叠索引）
- `sync_retention_state`（floor-based 过期判定）
- 所有索引，包括 keyset 索引 `(city, live_date, sort_start_time, id)`
- `updated_at` 触发器
- Agent A 待填充：权限授予、函数所有权、SECURITY DEFINER 包装

### 2.2 API Contracts (`backend/contracts/`)

**full.openapi.yaml** — `GET /api/v1/lives/full`:
- 请求：`city`（必填）、`page_size`（默认 500，最大 2000）、`page_token`（可选）
- 响应：`{data, scope{city, scope_start_date, scope_end_date}, snapshot_cursor, has_more, next_token}`
- Token 载荷 schema（签名，包含 §9.1 全部 8 个字段）
- 错误响应：400、409、429

**sync.openapi.yaml** — `GET /api/v1/lives/sync`:
- 请求：`city`、`scope_start_date`、`scope_end_date`、`since`（cursor）、`limit`（最大 5000）
- 响应：`{data, deletes, cursor, has_more}`
- 错误响应：400、409、429、500

### 2.3 Shared Types (`backend/contracts/shared.json`)

跨模块引用的 JSON Schema：
- `Live` 对象（§9.2 中 SELECT 列表的全部 13 个字段）
- `Scope` 对象
- `SyncChange` 对象
- 错误信封

---

## 三、阶段计划与执行顺序

### Phase 0：契约生成（Supervisor，无 Agent）

Supervisor 直接从 V4.4 编写三个契约文件。耗时约 2 分钟。

### Phase 1：数据库基础 — Agent A

**模型：** haiku（v4flash — 机械式 DDL，低风险）

**输入：** SQL schema contract + V4.4 §4-8

**产出：**
- `database/migrations/V1__schema.sql`（完成权限授予、SECURITY DEFINER 所有权、函数包装）
- `database/migrations/V2__permissions.sql`（角色创建、权限授予）
- `database/tests/schema_test.sql`（验证查询）
- `database/docs/security_review.md`（自我审计）

**门禁 1 检查清单：**
- [ ] `sort_start_time` 为 `GENERATED ALWAYS AS (COALESCE(start_time, TIME '23:59:59')) STORED`
- [ ] Keyset 索引列顺序：`(city, live_date, sort_start_time, id)` — 与 ORDER BY 完全一致
- [ ] Keyset 索引含 `WHERE review_status = 'published'`
- [ ] `sync_version_counter`：单行、BOOLEAN PK、`UPDATE...RETURNING version`
- [ ] `sync_changes.version` 为 BIGINT PRIMARY KEY（全局唯一，非 sequence）
- [ ] `sync_changes` 含实体折叠索引：`(entity_type, entity_id, version DESC)`
- [ ] `sync_retention_state`：BOOLEAN PK、`retention_floor_version NOT NULL`
- [ ] `api_role` 对 `live_bands` 无 INSERT/UPDATE/DELETE
- [ ] `api_role` 对 `sync_changes` 无 INSERT/UPDATE/DELETE
- [ ] `api_role` 对 `sync_version_counter` 无 UPDATE
- [ ] `app_definer` 为 NOLOGIN
- [ ] SECURITY DEFINER 函数归属于 `app_definer`，非 superuser
- [ ] `REVOKE CREATE ON SCHEMA public FROM PUBLIC`
- [ ] `fn_update_timestamp` 触发器位于 lives BEFORE UPDATE
- [ ] `live_bands` 有 `ON DELETE CASCADE` 到 lives
- [ ] lives 查询字段完整性：/full 和 /sync 返回的 13 个字段均在 schema 中存在且有正确类型
- [ ] FK：`live_bands.band_id → bands(id)`，`lives.created_by → users(id)` — 均被强制执行
- [ ] `review_status` 索引：`EXPLAIN ANALYZE` 显示对 `idx_lives_full_scope_keyset` 进行索引扫描，非 seq scan
- [ ] 事务回滚：schema 违规不留部分 `sync_changes`
- [ ] 并发写入：两个事务更新同一条 live → 各自获得唯一且单调递增的 version

### Phase 2：CDC 机制 — Agent B

**模型：** sonnet（DSv4p — CDC 是核心一致性原语）

**输入：** Agent A 的最终 schema + V4.4 §5-6

**产出：**
- `backend/services/cdc_writer.py`（事务内 sync_changes 写入）
- `backend/services/retention_cleaner.py`（定期日志清理）
- `backend/tests/cdc_integration_test.py`

**门禁 2 检查清单：**
- [ ] 业务写入 + version 递增 + sync_changes 插入在同一 BEGIN...COMMIT 中
- [ ] Version 来自 `UPDATE...RETURNING`，非 sequence 或时间戳
- [ ] 实体折叠：同一事务内同一 (entity_type, entity_id) → 单个最终动作
- [ ] 动作计算覆盖 §15.3 全部 7 种变更类型
- [ ] Retention：`DELETE...RETURNING version → MAX(deleted) → UPDATE retention_floor`
- [ ] Retention 使用 `>= retention_floor_version` 判定有效性，非 `MIN(version)`
- [ ] Retention 任务幂等（并发运行安全）
- [ ] `api_role` 无法直接写 `sync_changes`（使用 cdc_writer 服务）
- [ ] 事务回滚：version 递增之后的任何错误回滚计数器行锁
- [ ] 并发 CDC 写入：10 个并发事务 → 10 个唯一 version，应用视角无间隙

### Phase 3：同步接口 — Agent C + Agent D

**Agent C（/full）：** 模型 haiku（v4flash）
- 输入：OpenAPI contract + Agent A 的 schema
- 产出：`backend/api/full.py`、`backend/services/token_manager.py`、tests

**Agent D（/sync）：** 模型 sonnet（DSv4p — scope 投影逻辑细腻）
- 输入：OpenAPI contract + Agent A 的 schema
- 产出：`backend/api/sync.py`、tests

顺序执行（Approach 1）：C 完成后 D 再开始。

**门禁 3 检查清单（/full）：**
- [ ] 首页：固定 scope_start_date/scope_end_date 一次性生成
- [ ] 后续页查询不使用 CURRENT_DATE
- [ ] snapshot_cursor 与首页查询在同一事务中读取
- [ ] Token 签名（HMAC 或非对称），包含 §9.1 全部 8 个字段
- [ ] Token last_time 使用 sort_start_time，不使用原始 start_time
- [ ] Keyset 分页：`(live_date, sort_start_time, id) > ($1, $2, $3)`
- [ ] ORDER BY 与 keyset 索引精确匹配：`live_date ASC, sort_start_time ASC, id ASC`
- [ ] page_size 上限 2000
- [ ] Token 设有过期时间并验证；过期返回 409
- [ ] 无效 token 返回 400
- [ ] 仅读 Primary
- [ ] /full 末页：has_more=false，next_token=null

**门禁 3 检查清单（/sync）：**
- [ ] repeatable_read 事务
- [ ] high_water 从 sync_version_counter 读取
- [ ] cursor = max(返回的 version)，非 high_water（除非批次覆盖 high_water）
- [ ] has_more = (cursor < high_water)
- [ ] since >= retention_floor_version 检查 → 过期返回 409
- [ ] 实体去重：`DISTINCT ON (entity_type, entity_id) ORDER BY version DESC`
- [ ] Scope 投影：读取当前 lives 行，检查 4 个条件
- [ ] Upsert → delete 转换当：!exists、hidden、城市不匹配、日期超出范围
- [ ] 同一实体不同时出现在 data[] 和 deletes[] 中
- [ ] limit 上限 5000
- [ ] 仅读 Primary
- [ ] /sync 空结果：since == high_water → cursor == since，has_more=false，无错误
- [ ] /sync 返回顺序：实体按 version ASC 排序（回放顺序），deletes 数组仅含 id

### Phase 4：后端集成 — Agent E

**模型：** haiku（v4flash — 集成接线，低风险）

**输入：** C 和 D 的实际 API 模块 + V4.4 §12-14

**产出：**
- `backend/main.py`（FastAPI 应用，挂载路由）
- `backend/middleware/`（限流、错误处理、请求验证）
- `backend/config.py`（KMS/Vault、Redis、数据库连接池）
- `backend/services/cache.py`（Redis 辅助，不参与同步）
- `backend/services/rate_limiter.py`（token bucket）

**门禁 4 检查清单：**
- [ ] /full 和 /sync 路由挂载时使用 Primary 数据库会话依赖
- [ ] Redis 缓存绝不参与 /sync 响应
- [ ] Redis 缓存 TTL 含 jitter
- [ ] 缓存 key 格式：`full:lives:v1:{city}:{start}:{end}:{token_hash}`
- [ ] 错误码映射完整：全部 7 个 code 返回正确 JSON
- [ ] 限流器：/full 按 IP+city token bucket，/sync 按 user+scope
- [ ] KMS/Vault：数据库密码和 token 签名密钥不硬编码
- [ ] 请求验证：city 必填，page_size 有上限，since 为正整数
- [ ] API 层不直接访问 sync_changes 或 sync_version_counter
- [ ] 数据库连接池：/full 和 /sync 使用 Primary 池，其他读取使用 replica 池（如已配置）
- [ ] 连接池隔离：Primary 和 replica 连接无交叉污染

### Phase 5：前端 — Agent F

**模型：** haiku（v4flash — 直观移动端 UI）

**输入：** OpenAPI contracts + V4.4 §11、§18

**产出：**
- UniApp Vue3 项目结构
- 5 个页面（列表、城市切换、详情、同步状态、错误）
- `stores/sync_store.js`（staging/active 双区、cursor 管理）
- `services/sync_engine.js`（full → sync catch-up → 原子切换）
- `services/db.js`（IndexedDB 封装）
- `services/api.js`（HTTP 客户端）

**门禁 5 检查清单：**
- [ ] 首次同步：/full 第 1 页 → 保存 scope → 拉完所有页 → /sync catch-up → 切换
- [ ] /full 拉取期间使用 staging_store，切换后使用 active_store
- [ ] 每次 /sync 完成后 cursor 保存至 IndexedDB
- [ ] Scope 变更（城市切换）触发完全重新同步
- [ ] SYNC_CURSOR_EXPIRED（409）触发完全重新同步
- [ ] FULL_PAGE_TOKEN_EXPIRED（409）触发从第 1 页重新 /full
- [ ] RATE_LIMITED（429）触发退避重试
- [ ] 离线：显示已缓存的 active_store 数据并附"上次同步"指示
- [ ] 无复杂动画或过度抽象的组件层级
- [ ] 图片加载失败显示占位图
- [ ] 加载状态显示同步进度（已拉取页数 / 总页数）
- [ ] IndexedDB schema 版本化：store 结构变更时有迁移路径，升级不丢失数据
- [ ] 灾难恢复：IndexedDB 损坏 → 删除并自动重新 /full
- [ ] 长时间离线：>30 天离线 → cursor 过期 → /full 恢复 → 用户看到一致状态

### Phase 6：测试与审查 — Agent G + Agent H

**Agent G（测试）：** 模型 haiku（v4flash）
- 产出：pytest 测试套件、SQL 测试、性能测试、验收清单

**Agent H（审查）：** 模型 sonnet（DSv4p）
- 产出：集成审查报告，含 P0/P1/P2 风险、发布建议

顺序执行：G 先完成，H 审查全部内容包括 G 的测试覆盖率。

**门禁 6 检查清单：**
- [ ] Keyset NULL 测试：同日期 NULL 时间、23:59:58/59/NULL 排序、id 作为 tiebreak
- [ ] Scope 午夜测试：23:59:59 第 1 页、00:00:01 第 2 页、相同 scope
- [ ] CDC：§15.3 全部 13 种场景全覆盖
- [ ] Sync 分批：limit < 总变更数、cursor 正确推进、无实体同时出现在两个数组中
- [ ] Retention：since==floor 有效、since<floor 返回 409、cleanup 更新 floor
- [ ] 权限：api_role 被阻止直接写入、SECURITY DEFINER 所有权已验证
- [ ] 最终一致性证明：full(snapshot_cursor) + sync(after) == 服务端 Scope 状态
- [ ] Agent H 报告：P0/P1/P2 风险已分类，发布建议已陈述
- [ ] 部署安全：数据库凭证不在仓库中、token 签名密钥来自 env、HTTPS 强制（P2 建议，非必须）

---

## 四、项目文件结构

```
live/
├── .claude/                          # 已存在，不修改
├── database/
│   ├── migrations/
│   │   ├── V1__schema.sql            # Agent A
│   │   └── V2__permissions.sql       # Agent A
│   ├── tests/
│   │   └── schema_test.sql           # Agent A
│   └── docs/
│       └── security_review.md        # Agent A
│
├── backend/
│   ├── contracts/                    # Phase 0（Supervisor）
│   │   ├── full.openapi.yaml
│   │   ├── sync.openapi.yaml
│   │   └── shared.json
│   ├── main.py                       # Agent E
│   ├── config.py                     # Agent E
│   ├── api/
│   │   ├── __init__.py
│   │   ├── full.py                   # Agent C
│   │   └── sync.py                   # Agent D
│   ├── services/
│   │   ├── __init__.py
│   │   ├── token_manager.py          # Agent C
│   │   ├── cdc_writer.py             # Agent B
│   │   ├── retention_cleaner.py      # Agent B
│   │   ├── cache.py                  # Agent E
│   │   └── rate_limiter.py           # Agent E
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── error_handler.py          # Agent E
│   │   └── request_validator.py      # Agent E
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py               # Agent G
│       ├── test_full.py              # Agent C + G
│       ├── test_sync.py              # Agent D + G
│       ├── test_cdc.py               # Agent B + G
│       ├── test_keyset.py            # Agent G
│       ├── test_scope.py             # Agent G
│       ├── test_permissions.py       # Agent G
│       └── test_performance.py       # Agent G
│
├── frontend/
│   ├── pages/
│   │   ├── index.vue                 # Agent F
│   │   ├── detail.vue                # Agent F
│   │   └── city-switch.vue           # Agent F
│   ├── components/
│   │   ├── LiveCard.vue              # Agent F
│   │   ├── SyncStatus.vue            # Agent F
│   │   └── ErrorPage.vue             # Agent F
│   ├── stores/
│   │   └── sync_store.js             # Agent F
│   ├── services/
│   │   ├── api.js                    # Agent F
│   │   ├── sync_engine.js            # Agent F
│   │   └── db.js                     # Agent F
│   └── static/                       # Agent F
│
├── tests/
│   └── integration/
│       └── test_e2e_sync.py           # Agent G
│
├── docs/
│   ├── superpowers/
│   │   └── specs/
│   │       └── 2026-08-12-multi-agent-orchestration-design.md  # 本文档
│   ├── integration_review.md          # Agent H
│   └── release_checklist.md           # Agent H
│
└── 技术实现计划书 V4.4 生产基线版.txt   # 已存在，只读参考
```

**模块边界规则：**
- `backend/api/full.py` — Agent C 写入，Agent E 读取（挂载路由）
- `backend/api/sync.py` — Agent D 写入，Agent E 读取
- `backend/services/cdc_writer.py` — Agent B 写入，C 和 D 不触碰
- `backend/tests/` — Agent C、D、B 各自播种测试；Agent G 填补空白
- 任何 Agent 不得在未经明确交接的情况下触碰其他 Agent 的主文件

---

## 五、失败处理

### 5.1 Agent 失败模式

| 场景 | 恢复方式 |
|------|----------|
| Agent 产出违反 V4.4 不变量 | 门禁审查捕获 → 以具体违规内容重新提示 Agent → Agent 修复并重新提交 |
| Agent 产出不完整（缺少必需文件） | 门禁审查按清单检查产出物 → 以缺失文件重新提示 |
| Agent 超时或报错 | 以相同提示和契约输入重新生成。所有 Agent 对相同输入具有确定性 |
| Agent 引入 V4.4 之外的依赖 | 门禁审查标记 → 进入下一阶段前移除 |

### 5.2 阶段内回滚

若 Agent 产出未通过门禁审查，修复始终为：
1. 以原始提示 + 具体违规项重新提示同一 Agent
2. Agent 产出修正后内容
3. 对修正内容重新执行门禁检查清单

无需回滚状态——每个阶段的产出为独立文件，下游 Agent 尚未消费。

### 5.3 V4.4 高频违规项（每道门禁均复查）

1. **查询中重写 sort_start_time** 而非使用生成列 — Agent C
2. **Offset 分页** 或 /full 中使用 `CURRENT_DATE` — Agent C
3. **cursor = high_water** 而非 /sync 中 `max(returned version)` — Agent D
4. **PostgreSQL sequence** 而非 CDC 中 `UPDATE...RETURNING` — Agent B
5. **Redis 参与同步一致性判定** — Agent E
6. **API 直接写入受保护表** — Agent A

---

## 六、不在范围内的内容

- **生产部署** — 我们交付可部署的项目，而非已部署的项目
- **真实数据迁移** — schema 为全新构建。从现有系统迁移不在范围内
- **OSS/CDN 配置** — Agent E 产出配置模板，实际 bucket/域名设置为运维操作

---

## 七、最终交付目标

```
backend/    — FastAPI 后端，含 /full、/sync、CDC、限流
database/   — PostgreSQL 16 schema，含权限、索引、函数
frontend/   — UniApp Vue3 客户端，含 IndexedDB、Service Worker
tests/      — pytest + SQL 测试，覆盖全部 §15 场景
docs/       — 集成审查、发布检查清单、安全审查
```

验收标准（来自 V4.4 §16）：
1. 所有同步接口强制走 Primary
2. /full Token 已签名且包含固定 Scope
3. /sync 校验并使用 Scope
4. sort_start_time 生成列已落库并被索引使用
5. sync_version_counter 使用单行原子递增
6. sync_changes.version 全局唯一
7. cursor 过期使用 retention_floor_version 判定
8. 客户端首次同步使用 staging store
9. /sync 分批 cursor 不越过未返回变更
10. 权限测试通过
11. 午夜、NULL、Scope 移入移出、分页排序移动测试通过
12. 压测覆盖热门城市首次 /full 与连续 /sync
