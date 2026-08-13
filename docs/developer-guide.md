# 乐队演出查看小程序 — 开发者指南

> 面向后端 / 前端开发者和 DevOps / 运维人员。
> 本文档对应 V4.4 生产基线技术方案（下称 V4.4）。
> 后端接口契约见 `backend/contracts/`（`full.openapi.yaml` / `sync.openapi.yaml` / `shared.json`）。

---

## 1. 项目概述

| 项目 | 说明 |
|---|---|
| 项目名称 | 乐队演出查看小程序 |
| 目标 | 高并发 H5 + 微信小程序，本地缓存优先，可验证的最终一致性 |
| 技术栈 | PostgreSQL 16 + FastAPI + asyncpg + Redis 7 + UniApp Vue3 + IndexedDB |
| 架构方式 | 客户端通过 `/full`（全量）+ `/sync`（增量 CDC）实现最终一致性同步 |
| 适用对象 | 普通用户查看已发布演出数据（`review_status='published'` 且落在 Scope 内） |

核心设计一句话概括：

- `/full` 按固定 Scope（默认 90 天）+ 签名 keyset token 分页拉取全量；
- `/sync` 按同一 Scope 从 CDC 日志 `sync_changes` 增量回放（实体折叠 + Scope 投影）；
- 客户端首次 `/full` 写入 `staging_store`，随后 `/sync` catch-up，最后原子切换 `active_store`；
- 一致性真源是 Primary 数据库，Redis 只做缓存 / 限流，不参与一致性判定。

---

## 2. 系统架构

### 2.1 架构图（文字描述）

```mermaid
flowchart LR
    subgraph Client["前端 UniApp Vue3（H5 / 微信小程序）"]
        UI["pages/ 页面（index / city-switch / detail）"]
        SE["services/sync_engine.js 同步引擎"]
        API["services/api.js HTTP 客户端"]
        IDB[("IndexedDB<br/>staging_store / active_store / sync_meta")]
    end

    subgraph Server["FastAPI 后端（backend/）"]
        FULL["api/full.py<br/>GET /api/v1/lives/full"]
        SYNC["api/sync.py<br/>GET /api/v1/lives/sync"]
        CDC["services/cdc_writer.py（业务写路径）"]
        RET["services/retention_cleaner.py（cron）"]
        TOK["services/token_manager.py"]
        CACHE["services/cache.py"]
        RATE["services/rate_limiter.py"]
        MID["middleware/（错误处理 / 请求校验）"]
    end

    subgraph Data["PostgreSQL 16（Primary，/full / /sync 强制读主）"]
        LIVES[("lives")]
        CHANGES[("sync_changes")]
        VER[("sync_version_counter")]
        RETSTATE[("sync_retention_state")]
    end

    REDIS[("Redis 7<br/>缓存 /full 首页 + 限流")]

    UI --> SE
    SE --> API
    SE --> IDB
    API --> FULL
    API --> SYNC
    FULL --> LIVES
    FULL --> VER
    SYNC --> CHANGES
    SYNC --> VER
    SYNC --> RETSTATE
    CDC -. 同一事务写入 .-> CHANGES
    CDC --> VER
    RET -. cron 每日 .-> CHANGES
    RET -. 推进 .-> RETSTATE
    FULL --> CACHE
    CACHE --> REDIS
    RATE --> REDIS
    MID --> FULL
    MID --> SYNC
```

数据流向要点：

1. **写路径**：业务写入 `lives` 必须在同一事务内递增 `sync_version_counter` 并写入 `sync_changes`（`cdc_writer.py`）。`api_role` 对受保护表没有写权限，唯一写路径是后端业务服务。
2. **读路径（客户端同步）**：`/full` 全量 + `/sync` 增量，两者都强制读 Primary。
3. **客户端存储**：`active_store` 是正式缓存（页面只读），`staging_store` 是首次同步的暂存区，`sync_meta` 存 scope / cursor 等元数据。
4. **缓存 / 限流**：Redis 只缓存 `/full` 热点页（`cache.py` 硬校验 key 前缀，杜绝 `/sync` 入缓存），限流走 Redis Lua 原子 token bucket；Redis 不可用时静默降级内存实现。

### 2.2 模块说明

| 路径 | 职责 |
|---|---|
| `database/migrations/V1__schema.sql` | 表结构 + 生成列 + 索引 + 触发器 + CDC 三张表 + 角色 + `safe_update_live_bands` SECURITY DEFINER 函数 |
| `database/migrations/V2__permissions.sql` | 角色级对象权限：`api_role` 只读、`app_definer` 最小权限、`migration_role` 全量 |
| `database/docs/security_review.md` | 权限模型安全评审记录 |
| `backend/main.py` | FastAPI 入口：lifespan 建连接池、注入 token 密钥、挂载中间件与路由 |
| `backend/config.py` | `Settings` 数据类，全部敏感值从环境变量读取 |
| `backend/api/full.py` | `/api/v1/lives/full` 全量同步接口（固定 Scope + 签名 keyset 分页） |
| `backend/api/sync.py` | `/api/v1/lives/sync` 增量同步接口（CDC 回放 + 实体折叠 + Scope 投影） |
| `backend/services/cdc_writer.py` | CDC 写入：`next_version` / `write_sync_change` / `determine_action` / `cdc_transaction` |
| `backend/services/retention_cleaner.py` | 日志清理：单条原子 SQL 删除 + 推进 `retention_floor_version` |
| `backend/services/token_manager.py` | 分页 token 签名（HMAC-SHA256）/ 验签 / 过期校验 |
| `backend/services/cache.py` | Redis 缓存 `/full` 热点页，带 TTL jitter，静默降级 |
| `backend/services/rate_limiter.py` | Token bucket 限流（Redis Lua，内存降级），按 IP+city / user+scope |
| `backend/middleware/error_handler.py` | V4.4 §14 错误码 → 契约 `{code, message}` JSON 映射 |
| `backend/middleware/request_validator.py` | 路由前置防御性参数校验（畸形请求 400，不消耗限流配额） |
| `backend/contracts/` | OpenAPI / JSON Schema 契约（`full` / `sync` / `shared`） |
| `frontend/services/sync_engine.js` | 同步引擎：首次全量 + 增量 + 错误动作分发 |
| `frontend/services/db.js` | IndexedDB 封装：双区模式（staging / active）+ 元数据 + 原子切换 |
| `frontend/services/api.js` | `uni.request` HTTP 客户端，封装 `/full`、`/sync`，错误归一化 |
| `frontend/pages/index.vue` | 演出列表（按日期分组，读 `active_store`） |
| `frontend/pages/city-switch.vue` | 城市选择 + 首次同步进度（`CITIES` 列表在此配置） |
| `frontend/pages/detail.vue` | 演出详情 |
| `frontend/components/SyncStatus.vue` / `ErrorPage.vue` | 同步状态指示 / 错误重试组件 |

---

## 3. 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+ | 后端运行时 |
| PostgreSQL | 16 | 必须为真实数据库（迁移需要超级用户连接） |
| Redis | 7 | 可选，用于 `/full` 热点缓存与限流；不配置则内存降级 |
| Node.js | 18+ | 仅前端 CLI 工具链需要（见 4.3） |
| HBuilderX | 4.x（含 Vue3 / uni-app 编译器） | 前端编译（H5 / 微信小程序） |
| 微信开发者工具 | 最新 | 运行小程序目标 |

Python 依赖（见仓库根目录 `requirements.txt`，`pip install -r requirements.txt` 安装）。

---

## 4. 快速开始（部署教程）

### 4.1 数据库初始化

```bash
# 1. 创建数据库（注意：V1/V2 迁移脚本中数据库名硬编码为 app_db，
#    若改用其他库名，需同步替换 V1__schema.sql / V2__permissions.sql 中的 app_db）
createdb app_db

# 2. 执行迁移（连接角色需要超级用户权限：迁移要 CREATE ROLE、REVOKE ALL ON DATABASE）
psql -d app_db -f database/migrations/V1__schema.sql
psql -d app_db -f database/migrations/V2__permissions.sql
psql -d app_db -f database/migrations/V3__platform.sql
```

迁移产物一览（V1）：

- `public.lives`：演出表，含生成列 `sort_start_time = COALESCE(start_time, '23:59:59')`，部分索引 `idx_lives_full_scope_keyset (city, live_date, sort_start_time, id) WHERE review_status='published'`；
- `public.users` / `public.bands` / `public.live_bands`：依赖表与关系表；
- `public.sync_version_counter`：单行版本计数器（`id=TRUE`，`UPDATE ... RETURNING version`）；
- `public.sync_changes`：CDC 日志（`version` 主键，`action IN ('upsert','delete')`）；
- `public.sync_retention_state`：日志保留状态（`retention_floor_version`）；
- `public.safe_update_live_bands(BIGINT, JSONB)`：SECURITY DEFINER 函数，维护 `live_bands` 与 `lives.band_names` 一致性；
- 三个角色：`api_role` / `migration_role` / `app_definer`（均 NOLOGIN）。

### 4.2 后端部署

```bash
# 1. 安装依赖（仓库根目录执行）
pip install -r requirements.txt

# 2. 配置环境变量（建议写入 .env 或由进程管理器注入）
export DATABASE_URL_PRIMARY="postgresql://user:pass@localhost:5432/app_db"
export DATABASE_URL_REPLICA=""  # 可选；留空则副本读回退 Primary
export TOKEN_SECRET="$(openssl rand -hex 32)"
export REDIS_URL="redis://localhost:6379"  # 可选；不配置则缓存/限流内存降级

# 3. 启动（在仓库根目录执行，backend 为包名）
cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 4. 验证 API（第一页会生成固定 Scope + snapshot_cursor）
curl "http://localhost:8000/api/v1/lives/full?city=Tokyo&page_size=10"
```

启动时后端会自动：

- 在 lifespan 中创建 Primary 连接池（`DATABASE_URL_REPLICA` 存在时额外创建副本池）；
- 注入 `TOKEN_SECRET` 到 `token_manager`；
- 挂载请求校验中间件（外层，先执行）与限流中间件（内层）。

### 4.3 前端部署

仓库当前**不包含 `package.json`**，前端是 HBuilderX 工程（`frontend/manifest.json` 标注 uni-app 编译器 v3），官方推荐用 HBuilderX 编译运行。

```text
# 方式 A（推荐）：HBuilderX
# 1. HBuilderX → 文件 → 导入 → 从本地目录导入，选择 frontend/ 目录
# 2. 运行 → 运行到浏览器（H5）或 运行到小程序模拟器 → 微信开发者工具（mp-weixin）
```

API 地址通过 `frontend/services/api.js` 的 `resolveApiBase()` 解析：

```text
VITE_API_BASE      # Vite CLI 环境变量，优先级最高
VUE_APP_API_BASE   # HBuilderX / 旧版 CLI 环境变量，次之
# 均未配置 → 使用同源（''），H5 由部署侧反向代理 /api 到后端
```

```bash
# 方式 B：自行搭建 uni-app CLI 工具链（可选）
# 用官方模板初始化后，把 services/ pages/ components/ App.vue main.js manifest.json pages.json 拷贝过去，
# 再执行：
npm install
export VITE_API_BASE="https://your-api.example.com"

npm run dev:h5        # H5 开发
npm run dev:mp-weixin # 微信小程序开发
npm run build:h5      # H5 构建
npm run build:mp-weixin
```

---

## 5. API 接口说明

两个接口都要求 `city` 参数（必填，1–50 字符）。响应结构见 `backend/contracts/shared.json`，完整 OpenAPI 见 `backend/contracts/full.openapi.yaml` 与 `sync.openapi.yaml`。

### 5.1 GET `/api/v1/lives/full` — 全量同步

分页拉取指定城市、固定 Scope（默认 90 天）内的已发布演出。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `city` | string | 是 | — | 城市，如 `Tokyo` |
| `page_size` | int | 否 | `500` | 每页条数，上限 `2000` |
| `page_token` | string | 否 | — | 第一页为空；后续页传上一页返回的签名 token |

返回：

```json
{
  "data": [ { "id": 1, "city": "Tokyo", "live_date": "2026-08-12", "start_time": "20:00:00",
              "sort_start_time": "20:00:00", "title": "...", "band_names": ["..."],
              "status": "announced", "updated_at": "..." } ],
  "scope": { "city": "Tokyo", "scope_start_date": "2026-08-12", "scope_end_date": "2026-11-10" },
  "snapshot_cursor": "42",
  "has_more": true,
  "next_token": "eyJ2IjoxLCJjaXR5Ijoi..."
}
```

- 第一页由服务端生成**固定 Scope**：`scope_start_date = business_today()`（业务时区 Asia/Shanghai），`scope_end_date = +90 天`；
- `snapshot_cursor` 在第一页事务内从 `sync_version_counter` 读取，客户端后续 `/sync` 从该水位追平；
- 后续页通过 `next_token`（HMAC-SHA256 签名）恢复固定 Scope 与游标，**禁止动态 `CURRENT_DATE`**（防止跨午夜漂移）；
- token 中 `city` 必须与请求参数一致，否则 400；
- 末页 `has_more=false`、`next_token=null`。

### 5.2 GET `/api/v1/lives/sync` — 增量同步

按固定 Scope 回放 CDC 日志。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `city` | string | 是 | — | 城市 |
| `scope_start_date` | date | 是 | — | 必须与 `/full` 返回的 scope 一致 |
| `scope_end_date` | date | 是 | — | 必须与 `/full` 返回的 scope 一致 |
| `since` | int | 是 | — | 客户端当前 cursor（版本号） |
| `limit` | int | 否 | `1000` | 每批实体数，上限 `5000` |

返回：

```json
{
  "data": [ { "id": 2, "city": "Tokyo", "live_date": "2026-08-13", "start_time": null, "sort_start_time": "23:59:59", "title": "...", "band_names": [], "status": "on_sale", "updated_at": "..." } ],
  "deletes": [ 5, 7 ],
  "cursor": 57,
  "has_more": true
}
```

- 在 `repeatable_read` 事务内读取 retention floor / high_water / 日志 / `lives`，保证批次为一致快照；
- 实体折叠：同一实体在批次内只出现一次（`DISTINCT ON (entity_type, entity_id) ORDER BY version DESC`），只输出最终动作；
- Scope 投影：实体不存在 / 非 `published` / 城市不匹配 / `live_date` 出范围 → 进 `deletes`，否则进 `data`；
- `cursor = max(本批返回的 version)`，仅当批次覆盖到 high_water 时 `has_more=false`；空批次 `cursor == since`、`has_more=false`（客户端已追平，避免无限循环）；
- 同一实体不会同时出现在 `data` 与 `deletes`（违反 → 500 `SYNC_INVARIANT_BROKEN`）。

### 5.3 错误码

错误响应体统一为契约 `Error`：`{"code": "...", "message": "..."}`，由 `middleware/error_handler.py` 映射。

| HTTP | code | 触发场景 | 客户端动作 |
|---|---|---|---|
| 400 | `INVALID_CITY` | city 缺失 / 超长 | 提示参数错误 |
| 400 | `INVALID_PAGE_TOKEN` | token 非法 / 签名不符 / token 城市不一致 | 丢弃分页，重新 `/full` |
| 400 | `INVALID_CURSOR` | `since` 缺失 / 非整数 / 负数；`limit` 越界 | 丢弃本地 cursor，重新 `/full` |
| 409 | `FULL_PAGE_TOKEN_EXPIRED` | 分页 token 过期（默认 30 分钟） | 重新 `/full` |
| 409 | `SYNC_CURSOR_EXPIRED` | `since < retention_floor_version`（cursor 已过保留期） | 清空该 Scope 本地缓存，重新 `/full` |
| 429 | `RATE_LIMITED` | 触发限流配额 | 退避重试（客户端退避 5s） |
| 500 | `SYNC_INVARIANT_BROKEN` | 数据不变量被破坏（如实体同时出现在 data 与 deletes） | 停止写入本地水位，稍后重试 |

补充（中间件兜底，不在 §14 契约 enum 内）：

| HTTP | code | 触发场景 |
|---|---|---|
| 422 | `VALIDATION_ERROR` | FastAPI Query 参数校验失败 |
| 500 | `INTERNAL_ERROR` | 未处理异常（不泄漏内部细节） |
| 500 | `UNKNOWN_ERROR` | 未知 detail 的 HTTPException（保留原状态码） |
| 503 | `PRIMARY_DB_UNAVAILABLE` / `DB_UNAVAILABLE` | 连接池未就绪 |

---

## 6. 同步机制详解

### 6.1 `/full` 全量拉取

- **固定 Scope**：第一页生成 `[business_today(), business_today()+90]`，写入签名 token，后续分页与 `/sync` 必须沿用同一组值；
- **签名 keyset token**：载荷含 `v, city, scope_start_date, scope_end_date, snapshot_cursor, last_date, last_time, last_id, exp`，其中 `last_time` 一律取生成列 `sort_start_time`（`start_time IS NULL` 时恒为 `23:59:59`，保证 token 非 NULL、keyset 稳定）；
- **分页**：基于索引 `(city, live_date, sort_start_time, id)` 做 keyset 比较，禁止 offset；用 `page_size+1` 技巧判断 `has_more`；
- **快照水位**：`snapshot_cursor` 与第一页查询在同一事务内读取。

### 6.2 `/sync` 增量回放

- **CDC 日志**：`sync_changes` 每条记录 `(version, entity_type, entity_id, action)`，version 全局唯一、单调递增（来自 `sync_version_counter`）；
- **实体折叠**：先 `DISTINCT ON` 保留每实体最终动作，再按 `version ASC` 截断（不能先截断再去重，否则会跳过最终版本低于 cursor 的实体，导致永久漏读）；
- **Scope 投影**：对折叠后的每个实体读取 `lives` 当前行，逐条判定 upsert / delete；
- **水位语义**：`cursor = max(返回 version)`，`has_more = cursor < high_water`；客户端循环直到 `has_more=false`。

### 6.3 客户端流程

首次同步（`firstSync`，V4.4 §11.1）：

```text
1. /full 第一页 → 保存 scope + snapshot_cursor（写入 sync_meta）
2. 按 next_token 拉完所有页 → 写入 staging_store
3. /sync catch-up（since=snapshot_cursor，循环到 has_more=false）→ 累积到 staging_store
4. swapStagingToActive 原子切换：单事务 清空 active → 复制 staging → 清空 staging
5. 保存最终 cursor + last_synced_at
```

增量同步（`incrementalSync`，V4.4 §11.2）：

```text
1. 读取本地 scope + cursor
2. 循环 /sync → upsert 写 active_store / delete 按 id 删
3. 每批返回后保存 cursor（即使中途失败，水位已推进，可断点续传）
```

错误处理（`handleSyncError`）：

| 错误码 | 动作 |
|---|---|
| `INVALID_PAGE_TOKEN` / `FULL_PAGE_TOKEN_EXPIRED` / `SYNC_CURSOR_EXPIRED` / `INVALID_CURSOR` | `refetch_full`：`clearAll()` → 重新 `firstSync` |
| `RATE_LIMITED` | `backoff_retry`：退避 5s 后 `incrementalSync` |
| `SYNC_INVARIANT_BROKEN` | `stop_and_retry`：停止写入本地水位，抛出由调用方稍后重试 |
| 网络错误（`NETWORK_ERROR`） | 保留本地缓存，进入离线模式 |

---

## 7. 配置参考

后端全部配置集中在 `backend/config.py`，敏感值只从环境变量读取。`get_settings()` 返回进程内缓存的单例。

| 环境变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `DATABASE_URL_PRIMARY` | 是 | — | Primary 连接串，如 `postgresql://user:pass@localhost:5432/app_db` |
| `DATABASE_URL_REPLICA` | 否 | 空 | Replica 连接串；留空则副本读回退 Primary |
| `TOKEN_SECRET` | 是 | — | HMAC-SHA256 分页 token 签名密钥（`openssl rand -hex 32`） |
| `TOKEN_TTL_MINUTES` | 否 | `30` | 分页 token 有效期（分钟） |
| `DB_POOL_MIN` | 否 | `5` | asyncpg 连接池下限 |
| `DB_POOL_MAX` | 否 | `50` | asyncpg 连接池上限（须 >= `DB_POOL_MIN`） |
| `REDIS_URL` | 否 | 空 | Redis 连接串；不配置则缓存 / 限流走内存降级 |
| `CACHE_TTL_BASE` | 否 | `60` | `/full` 缓存基础 TTL（秒） |
| `CACHE_TTL_JITTER` | 否 | `30` | TTL 随机抖动上限（秒），避免集中失效 |
| `RATE_LIMIT_FULL_PER_MINUTE` | 否 | `30` | `/full` 限流配额（每 IP+city 每分钟） |
| `RATE_LIMIT_SYNC_PER_MINUTE` | 否 | `60` | `/sync` 限流配额（每 user+scope 每分钟） |
| `SCOPE_DEFAULT_DAYS` | 否 | `90` | `/full` 固定 scope 长度（天） |
| `RETENTION_DAYS` | 否 | `30` | CDC 日志保留天数；对应 cursor 有效期（约 30 天） |

前端（`frontend/services/api.js`）：

| 环境变量 | 说明 |
|---|---|
| `VITE_API_BASE` | Vite CLI 环境变量，API 基础地址，优先级最高 |
| `VUE_APP_API_BASE` | HBuilderX / 旧版 CLI 环境变量，API 基础地址 |

---

## 8. 常见问题

**Q: 客户端长时间离线后打开，数据不一致怎么办？**
A: 服务端对 CDC 日志做保留（`RETENTION_DAYS`，默认 30 天）。离线过久导致本地 cursor 低于 `retention_floor_version` 时，`/sync` 返回 409 `SYNC_CURSOR_EXPIRED`。客户端 `handleSyncError` 会自动执行 `clearAll()` + 重新 `/full`，无需人工干预。Cursor 过期不计入攻击，只引导重新全量同步。

**Q: 如何添加新城市？**
A: 后端在 `lives` 表中插入对应 `city` 的已发布数据即可（接口按 `city` 过滤，无需改代码）；前端城市列表在 `frontend/pages/city-switch.vue` 的 `CITIES` 常量中配置（当前为 `['Tokyo','Osaka','Shanghai','Beijing','Guangzhou','Shenzhen']`）。注意 `/full` 与 `/sync` 的 Scope 都是按城市隔离的。

**Q: Redis 挂了影响服务吗？**
A: 不影响核心功能。`cache.py` 缓存失败静默降级（get 返回 None、set 忽略异常）；`rate_limiter.py` 在 Redis 不可用时切换到进程内内存实现。Redis 只做性能优化（热点缓存 + 限流），不参与 `/sync` 或一致性判定。

**Q: 分页 token 过期了怎么办？**
A: `/full` 后续页 token 默认 30 分钟过期，返回 409 `FULL_PAGE_TOKEN_EXPIRED`，客户端重新 `/full` 即可。生产环境可按需调大 `TOKEN_TTL_MINUTES`。

**Q: 为什么 `/full` 返回的 `sort_start_time` 对无开始时间的演出是 `23:59:59`？**
A: 这是数据库生成列 `COALESCE(start_time, TIME '23:59:59')`。它保证 keyset 分页中 `last_time` 永不为 NULL，`NULL` 演出排在当天最后，分页边界稳定不重不漏。

---

## 9. 运维建议

1. **读写分离限制**：`/full` 与 `/sync` 必须走 Primary（V4.4 全局原则 1）。副本（`DATABASE_URL_REPLICA`）只用于非一致性读，不要对同步接口做路由切换。
2. **保留清理任务**：`services/retention_cleaner.py` 的 `clean_expired_logs(conn, retention_days)` 建议用 cron 每天执行一次，推进 `sync_retention_state.retention_floor_version`。任务本身是单条原子 SQL，重复运行幂等。
3. **监控 cursor 过期率**：监控 409 响应比例（`SYNC_CURSOR_EXPIRED` + `FULL_PAGE_TOKEN_EXPIRED`）。比例异常升高说明客户端长期离线或清理过激进，需评估调大 `RETENTION_DAYS`。
4. **热门城市缓存**：为访问量大的城市开启 `REDIS_URL`，`/full` 首页（`cache.py`）自动按 `full:lives:v1:{city}:{scope}:{token_hash}` 缓存并带 TTL jitter。`/sync` 永不缓存。
5. **反向代理与限流**：部署在可信反向代理（Nginx / Caddy）之后，限流依赖 `X-Forwarded-For` / `X-Real-IP` 提取客户端 IP，代理必须正确改写这些头，否则会被绕过或误伤。
6. **密钥管理**：`TOKEN_SECRET` 与数据库口令用 KMS / 密钥管理系统注入环境，禁止硬编码、禁止提交到仓库；`token_manager.set_secret()` 在应用启动时注入。
7. **契约先行**：前后端以 `backend/contracts/` 下的 OpenAPI / JSON Schema 为唯一契约。修改字段必须同步更新契约。
