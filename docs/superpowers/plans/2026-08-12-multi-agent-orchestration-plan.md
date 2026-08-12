# Multi-Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Orchestrate 8 AI agents (A-H) across 6 phases to build a production-ready band-live mini-program from the V4.4 specification.

**Architecture:** Supervisor-driven sequential execution. Phase 0 produces shared contract files. Agents A→B→C→D→E→F→G→H execute in dependency order, each consuming upstream contracts/artifacts. Each phase includes a gate review against V4.4 invariants before proceeding. User gives final approval at each gate.

**Tech Stack:** PostgreSQL 16, FastAPI + asyncpg, UniApp Vue3, IndexedDB, Redis 7

---

## Global Constraints

- V4.4 技术实现计划书 is the authoritative baseline — no deviation
- Model: haiku (v4flash) for Agents A/C/E/F/G; sonnet (v4p) for Agents B/D/H
- All sync interfaces (/full, /sync) MUST read Primary only
- sync_version_counter uses `UPDATE...RETURNING version` — no PostgreSQL sequences
- sort_start_time is a GENERATED column: `COALESCE(start_time, TIME '23:59:59')` STORED
- Keyset pagination only: `(live_date, sort_start_time, id) > ($1, $2, $3)` — no offset
- Token must be signed, contain all 8 fields from V4.4 §9.1
- /sync cursor = max(returned version), NOT high_water
- Redis/CDN/Service Worker do NOT participate in consistency decisions
- api_role has no direct write access to live_bands, sync_changes, sync_version_counter
- SECURITY DEFINER functions owned by NOLOGIN app_definer
- No complex animations, no over-abstracted components, no dependencies outside V4.4

---

## File Structure (Target)

```
live/
├── database/
│   ├── migrations/
│   │   ├── V1__schema.sql            # Phase 1 (Agent A)
│   │   └── V2__permissions.sql       # Phase 1 (Agent A)
│   ├── tests/
│   │   └── schema_test.sql           # Phase 1 (Agent A)
│   └── docs/
│       └── security_review.md        # Phase 1 (Agent A)
├── backend/
│   ├── contracts/
│   │   ├── full.openapi.yaml         # Phase 0 (Supervisor)
│   │   ├── sync.openapi.yaml         # Phase 0 (Supervisor)
│   │   └── shared.json               # Phase 0 (Supervisor)
│   ├── main.py                       # Phase 4 (Agent E)
│   ├── config.py                     # Phase 4 (Agent E)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── full.py                   # Phase 3 (Agent C)
│   │   └── sync.py                   # Phase 3 (Agent D)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── token_manager.py          # Phase 3 (Agent C)
│   │   ├── cdc_writer.py             # Phase 2 (Agent B)
│   │   ├── retention_cleaner.py      # Phase 2 (Agent B)
│   │   ├── cache.py                  # Phase 4 (Agent E)
│   │   └── rate_limiter.py           # Phase 4 (Agent E)
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── error_handler.py          # Phase 4 (Agent E)
│   │   └── request_validator.py      # Phase 4 (Agent E)
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py               # Phase 6 (Agent G)
│       ├── test_full.py              # Phase 3+6
│       ├── test_sync.py              # Phase 3+6
│       ├── test_cdc.py               # Phase 2+6
│       ├── test_keyset.py            # Phase 6 (Agent G)
│       ├── test_scope.py             # Phase 6 (Agent G)
│       ├── test_permissions.py       # Phase 6 (Agent G)
│       └── test_performance.py       # Phase 6 (Agent G)
├── frontend/
│   ├── pages/
│   │   ├── index.vue                 # Phase 5 (Agent F)
│   │   ├── detail.vue                # Phase 5 (Agent F)
│   │   └── city-switch.vue           # Phase 5 (Agent F)
│   ├── components/
│   │   ├── LiveCard.vue              # Phase 5 (Agent F)
│   │   ├── SyncStatus.vue            # Phase 5 (Agent F)
│   │   └── ErrorPage.vue             # Phase 5 (Agent F)
│   ├── stores/
│   │   └── sync_store.js             # Phase 5 (Agent F)
│   ├── services/
│   │   ├── api.js                    # Phase 5 (Agent F)
│   │   ├── sync_engine.js            # Phase 5 (Agent F)
│   │   └── db.js                     # Phase 5 (Agent F)
│   └── static/                       # Phase 5 (Agent F)
├── tests/
│   └── integration/
│       └── test_e2e_sync.py           # Phase 6 (Agent G)
└── docs/
    ├── integration_review.md          # Phase 6 (Agent H)
    └── release_checklist.md           # Phase 6 (Agent H)
```

---

## Phase 0: Contract Generation

### Task 0.1: Write SQL Schema Contract

**Files:**
- Create: `database/migrations/V1__schema.sql`

**Produces:** Schema skeleton that Agent A completes with permissions

- [ ] **Step 1: Write the SQL contract file**

Write `database/migrations/V1__schema.sql` from V4.4 §4-8. The file contains the complete DDL without permission grants (those are Phase 1):

```sql
-- V1__schema.sql — Contract baseline from V4.4 §4-8
-- Agent A completes: permission grants, SECURITY DEFINER ownership, function bodies

-- 4.1 演出表
CREATE TABLE public.lives (
    id                BIGSERIAL PRIMARY KEY,
    livehouse_id      BIGINT NOT NULL,
    live_date         DATE NOT NULL,
    start_time        TIME,
    sort_start_time   TIME GENERATED ALWAYS AS (
        COALESCE(start_time, TIME '23:59:59')
    ) STORED,
    title             VARCHAR(150) NOT NULL,
    ticket_price      VARCHAR(50),
    ticket_url        VARCHAR(255),
    poster_image_url  VARCHAR(255),
    city              VARCHAR(50) NOT NULL,
    band_names        JSONB NOT NULL DEFAULT '[]'::jsonb,
    status            VARCHAR(16) NOT NULL DEFAULT 'announced'
                      CHECK (status IN ('announced','on_sale','completed','cancelled')),
    review_status     VARCHAR(16) NOT NULL DEFAULT 'draft'
                      CHECK (review_status IN ('draft','published','hidden')),
    created_by        BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4.2 索引
CREATE INDEX idx_lives_full_scope_keyset
ON public.lives (city, live_date, sort_start_time, id)
WHERE review_status = 'published';

CREATE INDEX idx_lives_updated_at
ON public.lives (updated_at);

-- 4.3 更新时间触发器 (function body filled by Agent A)
-- Agent A: implement fn_update_timestamp() per §4.3

-- 5.1 版本计数器
CREATE TABLE public.sync_version_counter (
    id       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    version  BIGINT NOT NULL
);
INSERT INTO public.sync_version_counter (id, version) VALUES (TRUE, 0);

-- 5.2 变更日志
CREATE TABLE public.sync_changes (
    version      BIGINT PRIMARY KEY,
    entity_type  VARCHAR(32) NOT NULL CHECK (entity_type IN ('live')),
    entity_id    BIGINT NOT NULL,
    action       VARCHAR(16) NOT NULL CHECK (action IN ('upsert', 'delete')),
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sync_changes_entity_latest
ON public.sync_changes (entity_type, entity_id, version DESC);

CREATE INDEX idx_sync_changes_version
ON public.sync_changes (version);

-- 6 日志保留状态
CREATE TABLE public.sync_retention_state (
    id                       BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    retention_floor_version  BIGINT NOT NULL DEFAULT 0,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.sync_retention_state (id, retention_floor_version) VALUES (TRUE, 0);

-- 8.1 演出-乐队关系表
CREATE TABLE public.live_bands (
    live_id     BIGINT NOT NULL REFERENCES public.lives(id) ON DELETE CASCADE,
    band_id     BIGINT NOT NULL,
    sort_order  SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (live_id, band_id)
);

-- Agent A TODO:
-- 1. Add bands table (referenced by live_bands.band_id FK)
-- 2. Add users table (referenced by lives.created_by FK)
-- 3. Implement fn_update_timestamp()
-- 4. Implement safe_update_live_bands() SECURITY DEFINER function (§8.2)
-- 5. Add all permission grants per §7
-- 6. Create roles: api_role, migration_role, app_definer (NOLOGIN)
-- 7. REVOKE CREATE ON SCHEMA public FROM PUBLIC
-- 8. REVOKE ALL ON DATABASE FROM PUBLIC
-- 9. GRANT CREATE ON SCHEMA public TO migration_role
```

- [ ] **Step 2: Verify against V4.4**

Check that every table, column, index, and constraint from V4.4 §4-8 appears in the file.

- [ ] **Step 3: Write the API contracts**

Write `backend/contracts/full.openapi.yaml`:

```yaml
openapi: "3.0.3"
info:
  title: /full API Contract
  version: "1.0.0"
  description: |
    Contract from V4.4 §9. All agents MUST implement against this.
    Deviations are spec violations.

paths:
  /api/v1/lives/full:
    get:
      summary: Full sync — paginated keyset scan
      parameters:
        - name: city
          in: query
          required: true
          schema:
            type: string
            maxLength: 50
        - name: page_size
          in: query
          required: false
          schema:
            type: integer
            default: 500
            minimum: 1
            maximum: 2000
        - name: page_token
          in: query
          required: false
          schema:
            type: string
          description: Signed keyset token from prior page. Omit for first page.
      responses:
        "200":
          description: Page of lives
          content:
            application/json:
              schema:
                type: object
                required: [data, scope, snapshot_cursor, has_more]
                properties:
                  data:
                    type: array
                    items:
                      $ref: "../contracts/shared.json#/definitions/Live"
                  scope:
                    type: object
                    required: [city, scope_start_date, scope_end_date]
                    properties:
                      city: { type: string }
                      scope_start_date: { type: string, format: date }
                      scope_end_date: { type: string, format: date }
                  snapshot_cursor:
                    type: string
                    description: Version at first-page snapshot time
                  has_more:
                    type: boolean
                  next_token:
                    type: string
                    nullable: true
                    description: Signed token for next page. null on last page.
        "400":
          description: INVALID_PAGE_TOKEN — token malformed or city mismatch
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
        "409":
          description: FULL_PAGE_TOKEN_EXPIRED — token TTL exceeded
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
        "429":
          description: RATE_LIMITED
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"

components:
  schemas:
    PageToken:
      type: object
      required: [v, city, scope_start_date, scope_end_date, snapshot_cursor, last_date, last_time, last_id, exp]
      properties:
        v: { type: integer, const: 1 }
        city: { type: string }
        scope_start_date: { type: string, format: date }
        scope_end_date: { type: string, format: date }
        snapshot_cursor: { type: string }
        last_date: { type: string, format: date }
        last_time: { type: string, format: partial-time }
        last_id: { type: integer }
        exp: { type: integer, format: unix-time }
```

- [ ] **Step 4: Write the sync contract**

Write `backend/contracts/sync.openapi.yaml`:

```yaml
openapi: "3.0.3"
info:
  title: /sync API Contract
  version: "1.0.0"
  description: |
    Contract from V4.4 §10. All agents MUST implement against this.

paths:
  /api/v1/lives/sync:
    get:
      summary: Incremental sync — CDC replay
      parameters:
        - name: city
          in: query
          required: true
          schema:
            type: string
            maxLength: 50
        - name: scope_start_date
          in: query
          required: true
          schema:
            type: string
            format: date
        - name: scope_end_date
          in: query
          required: true
          schema:
            type: string
            format: date
        - name: since
          in: query
          required: true
          schema:
            type: integer
            minimum: 0
          description: Client's current cursor (last processed version)
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            default: 1000
            minimum: 1
            maximum: 5000
      responses:
        "200":
          description: Batch of changes
          content:
            application/json:
              schema:
                type: object
                required: [data, deletes, cursor, has_more]
                properties:
                  data:
                    type: array
                    items:
                      $ref: "../contracts/shared.json#/definitions/Live"
                  deletes:
                    type: array
                    items:
                      type: integer
                    description: Entity IDs to remove from client
                  cursor:
                    type: integer
                    description: New cursor — max version in this batch
                  has_more:
                    type: boolean
                    description: true if more changes remain after this batch
        "400":
          description: INVALID_CURSOR — since value malformed
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
        "409":
          description: SYNC_CURSOR_EXPIRED — since below retention floor
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
        "429":
          description: RATE_LIMITED
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
        "500":
          description: SYNC_INVARIANT_BROKEN
          content:
            application/json:
              schema:
                $ref: "../contracts/shared.json#/definitions/Error"
```

- [ ] **Step 5: Write the shared types**

Write `backend/contracts/shared.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "definitions": {
    "Live": {
      "type": "object",
      "required": ["id", "livehouse_id", "live_date", "sort_start_time", "title", "city", "band_names", "status", "updated_at"],
      "properties": {
        "id": { "type": "integer" },
        "livehouse_id": { "type": "integer" },
        "live_date": { "type": "string", "format": "date" },
        "start_time": { "type": "string", "format": "partial-time", "nullable": true },
        "sort_start_time": { "type": "string", "format": "partial-time" },
        "title": { "type": "string", "maxLength": 150 },
        "ticket_price": { "type": "string", "nullable": true },
        "ticket_url": { "type": "string", "nullable": true },
        "poster_image_url": { "type": "string", "nullable": true },
        "city": { "type": "string" },
        "band_names": { "type": "array", "items": { "type": "string" } },
        "status": { "type": "string", "enum": ["announced", "on_sale", "completed", "cancelled"] },
        "updated_at": { "type": "string", "format": "date-time" }
      }
    },
    "Error": {
      "type": "object",
      "required": ["code", "message"],
      "properties": {
        "code": {
          "type": "string",
          "enum": [
            "INVALID_CITY",
            "INVALID_PAGE_TOKEN",
            "INVALID_CURSOR",
            "FULL_PAGE_TOKEN_EXPIRED",
            "SYNC_CURSOR_EXPIRED",
            "RATE_LIMITED",
            "SYNC_INVARIANT_BROKEN"
          ]
        },
        "message": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 6: Create __init__.py files**

```bash
mkdir -p backend/api backend/services backend/middleware backend/tests
touch backend/__init__.py backend/api/__init__.py backend/services/__init__.py backend/middleware/__init__.py backend/tests/__init__.py
```

- [ ] **Step 7: Commit Phase 0**

```bash
git add database/ backend/contracts/ backend/__init__.py backend/api/__init__.py backend/services/__init__.py backend/middleware/__init__.py backend/tests/__init__.py
git commit -m "feat: Phase 0 — contract files from V4.4 baseline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 1: Database Foundation — Agent A

**Model:** `haiku` (v4flash)
**Depends on:** Phase 0 contracts

### Task 1.1: Dispatch Agent A

- [ ] **Step 1: Send Agent A prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "haiku"`:

```
你是一名 PostgreSQL 16 数据库与权限专家。请根据以下要求完成数据库层实现。

## 参考文件

请先阅读以下文件：
1. `技术实现计划书 V4.4 生产基线版.txt` — 完整技术基线
2. `database/migrations/V1__schema.sql` — SQL 契约骨架
3. `backend/contracts/shared.json` — 共享类型定义

## 你的任务

完成 `database/migrations/V1__schema.sql`，填充所有 TODO 标记的部分，并创建以下文件：

### 1. database/migrations/V1__schema.sql（完善）

在现有骨架基础上完成：

a) 创建依赖表：
```sql
CREATE TABLE public.users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.bands (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

b) 添加外键约束：
- live_bands.band_id → bands(id)  （需要在 live_bands 表上 ALTER 或修改原定义）
- lives.created_by → users(id)

c) 实现 fn_update_timestamp()（V4.4 §4.3）：
```sql
CREATE OR REPLACE FUNCTION public.fn_update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_lives_updated_at
BEFORE UPDATE ON public.lives
FOR EACH ROW
EXECUTE FUNCTION public.fn_update_timestamp();
```

d) 实现 safe_update_live_bands()（V4.4 §8.2）：
- 完整实现该函数，包括所有验证逻辑
- 参数校验：p_live_id 有效、p_bands 是数组、长度≤50
- 锁定 lives 行 FOR UPDATE
- 创建临时表去重
- 验证所有 band_id 存在于 bands 表
- DELETE + INSERT ON CONFLICT 更新关系
- 更新 lives.band_names 冗余列
- 使用 SECURITY DEFINER，搜索路径设为 pg_catalog, public, pg_temp

e) 添加权限控制（V4.4 §7）：
- REVOKE CREATE ON SCHEMA public FROM PUBLIC
- REVOKE ALL ON DATABASE app_db FROM PUBLIC （使用当前数据库名）
- GRANT CREATE ON SCHEMA public TO migration_role

### 2. database/migrations/V2__permissions.sql（新建）

创建完整的权限体系：

```sql
-- 创建角色
CREATE ROLE app_definer NOLOGIN;
CREATE ROLE migration_role NOLOGIN;
CREATE ROLE api_role NOLOGIN;

-- Schema 权限
GRANT CREATE ON SCHEMA public TO migration_role;

-- api_role: 只读 lives + bands + live_bands
GRANT SELECT ON public.lives TO api_role;
GRANT SELECT ON public.bands TO api_role;
GRANT SELECT ON public.live_bands TO api_role;

-- api_role: 禁止直接修改受保护表
REVOKE INSERT, UPDATE, DELETE ON public.live_bands FROM api_role;
REVOKE INSERT, UPDATE, DELETE ON public.sync_changes FROM api_role;
REVOKE UPDATE ON public.sync_version_counter FROM api_role;

-- api_role: 可以执行安全函数
GRANT EXECUTE ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) TO api_role;
REVOKE ALL ON FUNCTION public.safe_update_live_bands(BIGINT, JSONB) FROM PUBLIC;

-- app_definer 只授予函数所需的最小表权限
GRANT SELECT, INSERT, UPDATE, DELETE ON public.live_bands TO app_definer;
GRANT SELECT, UPDATE ON public.lives TO app_definer;
GRANT SELECT ON public.bands TO app_definer;

-- 将 SECURITY DEFINER 函数所有权转给 app_definer
ALTER FUNCTION public.safe_update_live_bands(BIGINT, JSONB) OWNER TO app_definer;
ALTER FUNCTION public.fn_update_timestamp() OWNER TO app_definer;

-- migration_role 获得所有表的完整权限用于迁移
GRANT ALL ON ALL TABLES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO migration_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO migration_role;
```

### 3. database/tests/schema_test.sql（新建）

编写验证 SQL 查询：

- 验证 sort_start_time 生成列在 NULL 和 非 NULL start_time 时的行为
- 验证 keyset 索引存在且列顺序正确
- 验证 sync_version_counter 单行约束
- 验证 api_role 无法 INSERT 到 live_bands（应抛出权限错误）
- 验证 api_role 无法 UPDATE sync_version_counter
- 验证 REVIEW CREATE 已从 PUBLIC 撤销
- 验证 app_definer 是 NOLOGIN
- 验证外键约束生效
- EXPLAIN ANALYZE 验证 keyset 查询使用索引扫描

### 4. database/docs/security_review.md（新建）

自我审计报告，包含：
- 角色清单和权限矩阵
- 函数所有权检查结果
- 最小权限原则验证
- SQL 注入风险分析（SECURITY DEFINER 函数）
- 已知限制和改进建议

## 核心原则

- 严格遵守 V4.4，不引入计划书之外的组件
- sort_start_time 是 GENERATED ALWAYS AS STORED，不在查询中重写
- sync_version_counter 使用 UPDATE...RETURNING version
- 所有 SECURITY DEFINER 函数设置 search_path 防止注入
- 不得使用超级用户或数据库 owner 作为函数 owner
```

- [ ] **Step 2: Wait for Agent A to complete**

- [ ] **Step 3: Gate 1 review**

Execute the Gate 1 checklist from the spec. Verify every item:

```
[ ] sort_start_time is GENERATED ALWAYS AS (COALESCE(start_time, TIME '23:59:59')) STORED
[ ] Keyset index columns: (city, live_date, sort_start_time, id) — exact order
[ ] Keyset index has WHERE review_status = 'published'
[ ] sync_version_counter: single-row, BOOLEAN PK, UPDATE...RETURNING version
[ ] sync_changes.version is BIGINT PRIMARY KEY (global unique, no sequence)
[ ] sync_changes has entity fold index: (entity_type, entity_id, version DESC)
[ ] sync_retention_state: BOOLEAN PK, retention_floor_version NOT NULL
[ ] api_role has NO INSERT/UPDATE/DELETE on live_bands
[ ] api_role has NO INSERT/UPDATE/DELETE on sync_changes
[ ] api_role has NO UPDATE on sync_version_counter
[ ] app_definer is NOLOGIN
[ ] SECURITY DEFINER functions owned by app_definer, not superuser
[ ] REVOKE CREATE ON SCHEMA public FROM PUBLIC
[ ] fn_update_timestamp trigger on lives BEFORE UPDATE
[ ] live_bands has ON DELETE CASCADE to lives
[ ] lives query field completeness: 13 fields match contracts/shared.json Live schema
[ ] FK: live_bands.band_id → bands(id), lives.created_by → users(id)
[ ] review_status index: EXPLAIN ANALYZE shows index scan, not seq scan
[ ] Transaction rollback: schema violation leaves no partial sync_changes
[ ] Concurrent writes: two tx updating same live get unique, monotonic versions
```

- [ ] **Step 4: Fix if needed**

If any items fail, re-prompt Agent A with the specific violations and ask for corrections.

- [ ] **Step 5: Present to user for approval**

Show the completed files and gate review results. Ask: "Phase 1 complete. Proceed to Phase 2?"

- [ ] **Step 6: Commit Phase 1**

```bash
git add database/
git commit -m "feat: Phase 1 — database schema, permissions, and security review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 2: CDC Mechanism — Agent B

**Model:** `sonnet` (v4p — CDC is the core consistency primitive)
**Depends on:** Phase 1 (Agent A's schema)

### Task 2.1: Dispatch Agent B

- [ ] **Step 1: Send Agent B prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "sonnet"`:

```
你是一名 CDC（Change Data Capture）与最终一致性同步专家。请根据 V4.4 技术基线实现同步底层机制。

## 参考文件

请先阅读以下文件：
1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §5-6、§10
2. `database/migrations/V1__schema.sql` — Phase 1 完成的 schema
3. `database/migrations/V2__permissions.sql` — 权限配置
4. `backend/contracts/sync.openapi.yaml` — /sync 接口契约

## 你的任务

### 1. backend/services/cdc_writer.py（新建）

实现事务内 sync_changes 写入服务。

核心要求（V4.4 §5.2）：业务修改、版本递增、sync_changes 写入必须在同一事务中。

```python
"""
CDC Writer — 事务内 sync_changes 写入服务

核心约束（V4.4 §5.2）：
- 业务写入 + version 递增 + sync_changes 写入在同一 BEGIN...COMMIT
- Version 来自 UPDATE sync_version_counter...RETURNING version
- 同一事务内同一实体多次修改折叠为最终动作
- 禁止使用 PostgreSQL sequence
"""
from typing import Optional
from asyncpg import Connection


async def next_version(conn: Connection) -> int:
    """原子递增并返回新版本号。必须与业务写入在同一事务中调用。"""
    row = await conn.fetchrow("""
        UPDATE public.sync_version_counter
        SET version = version + 1
        WHERE id = TRUE
        RETURNING version
    """)
    return row["version"]


async def write_sync_change(
    conn: Connection,
    version: int,
    entity_type: str,
    entity_id: int,
    action: str,
) -> None:
    """写入一条同步变更记录。"""
    await conn.execute("""
        INSERT INTO public.sync_changes (version, entity_type, entity_id, action)
        VALUES ($1, $2, $3, $4)
    """, version, entity_type, entity_id, action)


async def determine_action(
    conn: Connection,
    entity_id: int,
    city: Optional[str] = None,
    scope_start_date=None,
    scope_end_date=None,
) -> str:
    """
    计算实体最终对普通用户的动作。

    规则（V4.4 §5.2）：
    - 新增已发布 → upsert
    - 更新（仍可见） → upsert
    - published → hidden → delete
    - hidden → published → upsert
    - city 移出 scope → delete
    - live_date 移出 scope → delete
    - 物理删除 → delete
    """
    row = await conn.fetchrow("""
        SELECT review_status, city, live_date
        FROM public.lives
        WHERE id = $1
    """, entity_id)

    if row is None:
        return "delete"

    if row["review_status"] != "published":
        return "delete"

    # 如果提供了 scope 参数，检查是否在范围内
    if city is not None and row["city"] != city:
        return "delete"

    if scope_start_date and scope_end_date:
        if not (scope_start_date <= row["live_date"] <= scope_end_date):
            return "delete"

    return "upsert"
```

还须实现以下辅助函数：

```python
async def cdc_transaction(
    conn: Connection,
    entity_id: int,
    final_action: str,
    business_write_fn,
) -> int:
    """
    完整的 CDC 事务包装器。

    参数：
        conn: 数据库连接（同一事务）
        entity_id: 被修改的 live ID
        final_action: 'upsert' 或 'delete'
        business_write_fn: 异步函数 (conn) -> None，执行实际业务写入

    返回：
        int: 新分配的版本号

    用法：
        async with pool.acquire() as conn:
            async with conn.transaction():
                version = await cdc_transaction(
                    conn, live_id, 'upsert',
                    lambda c: c.execute("UPDATE lives SET title=$1 WHERE id=$2", title, live_id)
                )
    """
    await business_write_fn(conn)
    version = await next_version(conn)
    await write_sync_change(conn, version, "live", entity_id, final_action)
    return version
```

### 2. backend/services/retention_cleaner.py（新建）

实现定期日志清理任务（V4.4 §6）。

```python
"""
Retention Cleaner — 定期清理过期 CDC 日志

核心约束（V4.4 §6）：
- 不能使用 MIN(version) 判断过期
- 正确语义：retention_floor_version = 已清理的最大 version
- cursor 有效条件：since >= retention_floor_version
- 如果 since < retention_floor_version → 409 SYNC_CURSOR_EXPIRED
"""

from datetime import datetime, timedelta, timezone
from asyncpg import Connection


async def clean_expired_logs(
    conn: Connection,
    retention_days: int = 30,
) -> int:
    """
    清理 retention_days 天前的 sync_changes。

    返回：删除的记录数

    实现（V4.4 §6 参考 SQL）：
    """
    deleted_count = 0

    async with conn.transaction():
        # 先获取要删除的最大 version
        max_version_row = await conn.fetchrow("""
            SELECT MAX(version) AS max_ver
            FROM public.sync_changes
            WHERE changed_at < $1
        """, datetime.now(timezone.utc) - timedelta(days=retention_days))

        if max_version_row["max_ver"] is None:
            return 0

        # 删除过期记录
        result = await conn.execute("""
            DELETE FROM public.sync_changes
            WHERE changed_at < $1
        """, datetime.now(timezone.utc) - timedelta(days=retention_days))

        deleted_count = int(result.split()[-1])

        # 更新 retention floor
        await conn.execute("""
            UPDATE public.sync_retention_state
            SET retention_floor_version = GREATEST(
                retention_floor_version,
                $1
            ),
            updated_at = now()
            WHERE id = TRUE
        """, max_version_row["max_ver"])

    return deleted_count


async def get_retention_floor(conn: Connection) -> int:
    """获取当前保留底线版本号。"""
    row = await conn.fetchrow("""
        SELECT retention_floor_version
        FROM public.sync_retention_state
        WHERE id = TRUE
    """)
    return row["retention_floor_version"]


async def check_cursor_valid(conn: Connection, since: int) -> bool:
    """检查客户端 cursor 是否仍然有效。"""
    floor = await get_retention_floor(conn)
    return since >= floor
```

### 3. backend/tests/test_cdc.py（新建）

编写测试用例验证：

```python
import pytest
from asyncpg import Connection

# 测试 1: 事务原子性
async def test_cdc_transaction_atomic(db: Connection):
    """业务写入和 sync_changes 在同一事务中——回滚后均不可见。"""
    async with db.transaction():
        await db.execute("UPDATE lives SET title = 'test' WHERE id = 1")
        version = await next_version(db)
        await write_sync_change(db, version, 'live', 1, 'upsert')
        raise Exception("forced rollback")

    # 事务回滚后，version 不应存在
    row = await db.fetchrow("SELECT 1 FROM sync_changes WHERE version = $1", version)
    assert row is None

# 测试 2: 版本唯一递增
async def test_version_monotonic(db: Connection):
    """10 个并发事务获得 10 个唯一且递增的版本号。"""
    # (使用 asyncio.gather 并发执行)

# 测试 3: 实体折叠
async def test_entity_folding(db: Connection):
    """同一事务内对同一实体的多次修改只产生一条 sync_changes。"""

# 测试 4: 动作判定 — 各场景
async def test_action_published_to_hidden(db: Connection):
    """published → hidden 返回 delete。"""

async def test_action_hidden_to_published(db: Connection):
    """hidden → published 返回 upsert。"""

async def test_action_city_change(db: Connection):
    """city 从 Tokyo 变为 Osaka。对 Tokyo scope 返回 delete。"""

async def test_action_date_out_of_scope(db: Connection):
    """live_date 移出 scope → delete。"""

async def test_action_physical_delete(db: Connection):
    """实体不存在 → delete。"""

# 测试 5: Retention
async def test_retention_floor_update(db: Connection):
    """清理后 retention_floor_version 正确更新。"""

async def test_cursor_at_floor_valid(db: Connection):
    """since == retention_floor_version 时 cursor 仍有效。"""

async def test_cursor_below_floor_expired(db: Connection):
    """since < retention_floor_version 时返回过期。"""
```

## 核心原则

- 业务写入 + version + sync_changes 永远在同一事务
- Version 来自 UPDATE...RETURNING，禁止使用 sequence
- 确保 retention 清理任务幂等
- cdc_writer 服务不直接暴露给 API 层
```

- [ ] **Step 2: Wait for Agent B to complete**

- [ ] **Step 3: Gate 2 review**

```
[ ] Business write + version increment + sync_changes insert in ONE BEGIN...COMMIT
[ ] Version from UPDATE...RETURNING, not sequence or timestamp
[ ] Entity folding: same (entity_type, entity_id) → single final action per tx
[ ] Action calculation covers all 7 change types from §15.3
[ ] Retention: DELETE...RETURNING version → MAX(deleted) → UPDATE retention_floor
[ ] Retention uses >= retention_floor_version, not MIN(version)
[ ] Retention task is idempotent
[ ] api_role cannot write sync_changes directly (must use cdc_writer)
[ ] Transaction rollback: error after version increment rolls back counter row lock
[ ] Concurrent CDC: 10 concurrent txs → 10 unique versions, no gaps
```

- [ ] **Step 4: Fix if needed**

- [ ] **Step 5: User approval**

"Phase 2 complete — CDC writer, retention cleaner, and tests. Proceed to Phase 3?"

- [ ] **Step 6: Commit Phase 2**

```bash
git add backend/services/cdc_writer.py backend/services/retention_cleaner.py backend/tests/test_cdc.py
git commit -m "feat: Phase 2 — CDC writer, retention cleaner, and integration tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 3: Sync Interfaces — Agent C + Agent D

**Agent C model:** `haiku` (v4flash)
**Agent D model:** `sonnet` (v4p)
**Depends on:** Phase 1 (schema), Phase 2 (CDC — D reads cdc_writer for reference)

### Task 3.1: Dispatch Agent C (/full)

- [ ] **Step 1: Send Agent C prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "haiku"`:

```
你是一名 FastAPI 同步接口专家。请实现 /full 全量同步接口。

## 参考文件

1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §9
2. `backend/contracts/full.openapi.yaml` — API 契约
3. `backend/contracts/shared.json` — Live 类型定义
4. `database/migrations/V1__schema.sql` — 数据库 schema

## 你的任务

### 1. backend/services/token_manager.py（新建）

实现签名 page token 的生成与验证。

```python
"""
Token Manager — 签名 keyset page token（V4.4 §9.1）

Token 载荷（8 个字段）：
{
  "v": 1,
  "city": "Tokyo",
  "scope_start_date": "2026-08-12",
  "scope_end_date": "2026-11-10",
  "snapshot_cursor": "123456",
  "last_date": "2026-09-15",
  "last_time": "23:59:59",
  "last_id": 9988,
  "exp": 1786600000
}

约束：
- last_time 永远使用 sort_start_time，禁止使用原始 start_time
- Token 过期建议 30 分钟
- 校验失败 → 400 INVALID_PAGE_TOKEN
- 过期 → 409 FULL_PAGE_TOKEN_EXPIRED
"""
import hmac
import hashlib
import json
import time
from typing import Optional, Dict, Any


SECRET = None  # 由 config.py 注入


def set_secret(secret: str):
    global SECRET
    SECRET = secret.encode("utf-8")


def sign_token(payload: Dict[str, Any]) -> str:
    """签名 token 载荷并编码为 base64。"""
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(SECRET, payload_bytes, hashlib.sha256).hexdigest()
    token = f"{payload_bytes.decode('utf-8')}.{sig}"
    # base64 encode
    import base64
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def verify_token(token_str: str) -> Dict[str, Any]:
    """验证并解码 token。返回载荷或抛出异常。"""
    import base64
    try:
        decoded = base64.urlsafe_b64decode(token_str.encode("utf-8")).decode("utf-8")
        payload_str, sig = decoded.rsplit(".", 1)
        expected_sig = hmac.new(SECRET, payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("INVALID_PAGE_TOKEN")
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("FULL_PAGE_TOKEN_EXPIRED")
        if payload.get("v") != 1:
            raise ValueError("INVALID_PAGE_TOKEN")
        return payload
    except (ValueError, KeyError) as e:
        if "EXPIRED" in str(e):
            raise
        raise ValueError("INVALID_PAGE_TOKEN")


def build_first_page_token(
    city: str,
    scope_start_date: str,
    scope_end_date: str,
    snapshot_cursor: int,
    last_row: Dict,
    ttl_minutes: int = 30,
) -> str:
    """从首页结果构建下一页 token。last_row 必须包含 live_date, sort_start_time, id。"""
    payload = {
        "v": 1,
        "city": city,
        "scope_start_date": scope_start_date,
        "scope_end_date": scope_end_date,
        "snapshot_cursor": str(snapshot_cursor),
        "last_date": str(last_row["live_date"]),
        "last_time": str(last_row["sort_start_time"]),  # 使用 sort_start_time！
        "last_id": last_row["id"],
        "exp": int(time.time()) + ttl_minutes * 60,
    }
    return sign_token(payload)
```

### 2. backend/api/full.py（新建）

实现 GET /api/v1/lives/full。

```python
"""
GET /api/v1/lives/full — 全量同步接口（V4.4 §9）

核心要求：
- 第一页：固定 scope_start_date/scope_end_date
- 后续页：从签名 token 读取固定 scope
- 分页：signed keyset token，禁止 offset
- 禁止动态 CURRENT_DATE
- 仅读 Primary
"""

from datetime import date, timedelta, timezone
from fastapi import APIRouter, Query, HTTPException, Depends
from asyncpg import Connection

router = APIRouter()

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 2000
BUSINESS_TZ = "Asia/Shanghai"


def business_today() -> date:
    """服务端业务日期，固定时区。"""
    from datetime import datetime
    return (datetime.now(timezone.utc)
            .astimezone(timezone.utc)  # 实际部署中替换为 Asia/Shanghai
            ).date()


@router.get("/api/v1/lives/full")
async def full_sync(
    city: str = Query(..., max_length=50),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    page_token: str = Query(None),
    db: Connection = Depends(get_primary_db),  # 强制 Primary
):
    from backend.services.token_manager import verify_token, build_first_page_token
    from datetime import timedelta

    # 第一页：生成固定 scope
    if page_token is None:
        scope_start_date = business_today()
        scope_end_date = scope_start_date + timedelta(days=90)

        async with db.transaction(isolation="read_committed"):
            snapshot_cursor = await db.fetchval("""
                SELECT version FROM public.sync_version_counter WHERE id = TRUE
            """)

            rows = await db.fetch("""
                SELECT
                    id, livehouse_id, live_date, start_time, sort_start_time,
                    title, ticket_price, ticket_url, poster_image_url,
                    city, band_names, status, updated_at
                FROM public.lives
                WHERE review_status = 'published'
                  AND city = $1
                  AND live_date >= $2
                  AND live_date <= $3
                ORDER BY live_date ASC, sort_start_time ASC, id ASC
                LIMIT $4
            """, city, scope_start_date, scope_end_date, page_size + 1)

    else:
        # 后续页：从 token 读取固定 scope
        try:
            payload = verify_token(page_token)
        except ValueError as e:
            if "EXPIRED" in str(e):
                raise HTTPException(409, detail="FULL_PAGE_TOKEN_EXPIRED")
            raise HTTPException(400, detail="INVALID_PAGE_TOKEN")

        # Token 中的 city 必须与请求参数一致
        if payload["city"] != city:
            raise HTTPException(400, detail="INVALID_PAGE_TOKEN")

        scope_start_date = payload["scope_start_date"]
        scope_end_date = payload["scope_end_date"]
        snapshot_cursor = payload["snapshot_cursor"]
        last_date = payload["last_date"]
        last_time = payload["last_time"]
        last_id = payload["last_id"]

        rows = await db.fetch("""
            SELECT
                id, livehouse_id, live_date, start_time, sort_start_time,
                title, ticket_price, ticket_url, poster_image_url,
                city, band_names, status, updated_at
            FROM public.lives
            WHERE review_status = 'published'
              AND city = $1
              AND live_date >= $2
              AND live_date <= $3
              AND (live_date, sort_start_time, id) > ($4, $5, $6)
            ORDER BY live_date ASC, sort_start_time ASC, id ASC
            LIMIT $7
        """, city, scope_start_date, scope_end_date,
            last_date, last_time, last_id, page_size + 1)

    # 判断是否有更多页
    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    # 构建返回
    data = [dict(r) for r in rows]

    next_token = None
    if has_more:
        last_row = rows[-1]
        next_token = build_first_page_token(
            city=city,
            scope_start_date=str(scope_start_date),
            scope_end_date=str(scope_end_date),
            snapshot_cursor=int(snapshot_cursor),
            last_row=dict(last_row),
        )

    return {
        "data": data,
        "scope": {
            "city": city,
            "scope_start_date": str(scope_start_date),
            "scope_end_date": str(scope_end_date),
        },
        "snapshot_cursor": str(snapshot_cursor),
        "has_more": has_more,
        "next_token": next_token,
    }
```

## 核心原则

- 第一页固定 scope，后续页从 token 读取——禁止 CURRENT_DATE
- last_time 使用 sort_start_time，绝不用 start_time
- ORDER BY 精确匹配 keyset 索引：(live_date, sort_start_time, id) ASC
- Token 必须签名，包含全部 8 个字段
- snapshot_cursor 在第一页事务中读取
```

- [ ] **Step 2: Wait for Agent C, dispatch Agent D**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "sonnet"`:

```
你是一名 CDC 增量同步专家。请实现 /sync 增量同步接口。

## 参考文件

1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §10
2. `backend/contracts/sync.openapi.yaml` — API 契约
3. `backend/contracts/shared.json` — Live 类型定义
4. `database/migrations/V1__schema.sql` — 数据库 schema
5. `backend/services/cdc_writer.py` — CDC 写入（理解版本机制）

## 你的任务

### 1. backend/api/sync.py（新建）

实现 GET /api/v1/lives/sync（V4.4 §10）。

核心要求：
- repeatable_read 事务
- high_water 从 sync_version_counter 读取
- cursor = max(返回的版本的 version)，绝不直接返回 high_water
- has_more = (cursor < high_water) — 只有批次覆盖到 high_water 时才返回 false
- Entity 去重：DISTINCT ON (entity_type, entity_id) ORDER BY version DESC
- Scope 投影：读取当前 lives 行，不满足 scope → delete

```python
"""
GET /api/v1/lives/sync — 增量同步接口（V4.4 §10）

核心约束：
- Primary 读取 + repeatable_read 事务
- high_water 机制 + batch cursor 正确推进
- cursor = max(returned version)，禁止直接返回 high_water
- Scope 投影：超出 scope → delete
- 同一实体不能同时出现在 data 和 deletes
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from asyncpg import Connection
from datetime import date

router = APIRouter()

MAX_SYNC_LIMIT = 5000


@router.get("/api/v1/lives/sync")
async def incremental_sync(
    city: str = Query(..., max_length=50),
    scope_start_date: date = Query(...),
    scope_end_date: date = Query(...),
    since: int = Query(..., ge=0),
    limit: int = Query(1000, ge=1, le=MAX_SYNC_LIMIT),
    db: Connection = Depends(get_primary_db),  # 强制 Primary
):
    # 1. 检查 cursor 是否过期
    retention_floor = await db.fetchval("""
        SELECT retention_floor_version
        FROM public.sync_retention_state
        WHERE id = TRUE
    """)

    if since < retention_floor:
        raise HTTPException(
            status_code=409,
            detail="SYNC_CURSOR_EXPIRED",
        )

    # 2. 强快照读取
    async with db.transaction(isolation="repeatable_read"):
        high_water = await db.fetchval("""
            SELECT version
            FROM public.sync_version_counter
            WHERE id = TRUE
        """)

        # 如果客户端已经是最新
        if since >= high_water:
            return {
                "data": [],
                "deletes": [],
                "cursor": since,
                "has_more": False,
            }

        # 3. 获取折叠后的变更
        changes = await db.fetch("""
            SELECT DISTINCT ON (entity_type, entity_id)
                version,
                entity_type,
                entity_id,
                action
            FROM public.sync_changes
            WHERE version > $1
              AND version <= $2
              AND entity_type = 'live'
            ORDER BY entity_type, entity_id, version DESC
            LIMIT $3
        """, since, high_water, limit)

    # 4. 计算 cursor
    if changes:
        batch_high = max(c["version"] for c in changes)
    else:
        batch_high = since

    has_more = batch_high < high_water
    return_cursor = batch_high

    # 5. 读取当前实体快照
    candidate_ids = [c["entity_id"] for c in changes]
    rows = await db.fetch("""
        SELECT
            id, livehouse_id, live_date, start_time, sort_start_time,
            title, ticket_price, ticket_url, poster_image_url,
            city, band_names, status, updated_at, review_status
        FROM public.lives
        WHERE id = ANY($1)
    """, candidate_ids)

    rows_by_id = {row["id"]: row for row in rows}

    # 6. Scope 投影
    data = []
    deletes_set = set()

    for change in changes:
        row = rows_by_id.get(change["entity_id"])

        # 删除 / 不存在 / hidden
        if change["action"] == "delete" or row is None or row["review_status"] != "published":
            deletes_set.add(change["entity_id"])
            continue

        # 检查 scope
        in_scope = (
            row["city"] == city
            and scope_start_date <= row["live_date"] <= scope_end_date
        )

        if in_scope:
            # 构造 Live 对象（排除内部字段 review_status）
            live_data = {
                "id": row["id"],
                "livehouse_id": row["livehouse_id"],
                "live_date": str(row["live_date"]),
                "start_time": str(row["start_time"]) if row["start_time"] else None,
                "sort_start_time": str(row["sort_start_time"]),
                "title": row["title"],
                "ticket_price": row["ticket_price"],
                "ticket_url": row["ticket_url"],
                "poster_image_url": row["poster_image_url"],
                "city": row["city"],
                "band_names": row["band_names"] if isinstance(row["band_names"], list) else [],
                "status": row["status"],
                "updated_at": row["updated_at"].isoformat(),
            }
            data.append(live_data)
            deletes_set.discard(row["id"])
        else:
            deletes_set.add(change["entity_id"])

    return {
        "data": data,
        "deletes": list(deletes_set),
        "cursor": return_cursor,
        "has_more": has_more,
    }
```

## 核心原则

- cursor = max(返回的版本)，绝不等于 high_water（除非覆盖到 high_water）
- DISTINCT ON 确保同一实体只返回最终动作
- Scope 投影规则：不存在/hidden/城市变化/日期变化 → 全部 delete
- 同一实体不能同时出现在 data 和 deletes
- limit 最大 5000
- since >= retention_floor 才有效
- 空结果时 cursor == since 而非报错
```

### Task 3.2: Gate 3 Review

- [ ] **Step 1: Review Agent C output (/full)**

```
[ ] First page: fixed scope_start_date/scope_end_date generated once
[ ] No CURRENT_DATE in subsequent page queries
[ ] snapshot_cursor read in same transaction as first page query
[ ] Token signed (HMAC or asymmetric), contains all 8 fields from §9.1
[ ] Token last_time uses sort_start_time, never raw start_time
[ ] Keyset pagination: (live_date, sort_start_time, id) > ($1, $2, $3)
[ ] ORDER BY matches keyset index exactly: live_date ASC, sort_start_time ASC, id ASC
[ ] page_size capped at 2000
[ ] Token expiry set, verified; returns 409 on expiry
[ ] Invalid token returns 400
[ ] Reads from Primary only
[ ] /full last page: has_more=false, next_token=null
```

- [ ] **Step 2: Review Agent D output (/sync)**

```
[ ] repeatable_read transaction
[ ] high_water read from sync_version_counter
[ ] cursor = max(returned versions), NOT high_water (unless batch covers high_water)
[ ] has_more = (cursor < high_water)
[ ] since >= retention_floor_version check → 409 on expiry
[ ] Entity dedup: DISTINCT ON (entity_type, entity_id) ORDER BY version DESC
[ ] Scope projection: read current lives row, check 4 conditions
[ ] Upsert → delete conversion when: !exists, hidden, out of city, out of date range
[ ] Same entity never in both data[] and deletes[]
[ ] limit capped at 5000
[ ] Reads from Primary only
[ ] /sync empty result: since == high_water → cursor == since, has_more=false, no error
[ ] /sync return order: entities sorted by version ASC, deletes array is id-only
```

- [ ] **Step 3: Fix if needed**

- [ ] **Step 4: User approval**

"Phase 3 complete — /full with signed keyset tokens and /sync with scope projection. Proceed to Phase 4?"

- [ ] **Step 5: Commit Phase 3**

```bash
git add backend/services/token_manager.py backend/api/full.py backend/api/sync.py
git commit -m "feat: Phase 3 — /full keyset sync and /sync CDC replay interfaces

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 4: Backend Integration — Agent E

**Model:** `haiku` (v4flash)
**Depends on:** Phase 3 (C and D's API modules)

### Task 4.1: Dispatch Agent E

- [ ] **Step 1: Send Agent E prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "haiku"`:

```
你是一名 FastAPI 后端系统架构专家。请整合所有模块为完整的后端服务。

## 参考文件

1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §12-14
2. `backend/api/full.py` — Agent C 的 /full 路由
3. `backend/api/sync.py` — Agent D 的 /sync 路由
4. `backend/services/cdc_writer.py` — Agent B 的 CDC 写入
5. `backend/services/retention_cleaner.py` — Agent B 的日志清理
6. `backend/services/token_manager.py` — Agent C 的 token 管理
7. `backend/contracts/full.openapi.yaml` — API 契约
8. `backend/contracts/sync.openapi.yaml` — API 契约

## 你的任务

### 1. backend/config.py（新建）

```python
"""
应用配置 — KMS/Vault、Redis、数据库连接池（V4.4 §2, §7, §12-13）

核心约束：
- 数据库密码和 token 签名密钥不硬编码
- 支持 Primary/Replica 连接池隔离
"""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    # 数据库
    database_url_primary: str = os.getenv("DATABASE_URL_PRIMARY", "")
    database_url_replica: str = os.getenv("DATABASE_URL_REPLICA", "")
    db_pool_min: int = int(os.getenv("DB_POOL_MIN", "5"))
    db_pool_max: int = int(os.getenv("DB_POOL_MAX", "50"))

    # Token 签名
    token_secret: str = os.getenv("TOKEN_SECRET", "")
    token_ttl_minutes: int = int(os.getenv("TOKEN_TTL_MINUTES", "30"))

    # Redis（仅用于缓存，不参与一致性）
    redis_url: str = os.getenv("REDIS_URL", "")
    cache_ttl_base: int = int(os.getenv("CACHE_TTL_BASE", "60"))
    cache_ttl_jitter: int = int(os.getenv("CACHE_TTL_JITTER", "30"))

    # 限流
    rate_limit_full_per_minute: int = int(os.getenv("RATE_LIMIT_FULL", "30"))
    rate_limit_sync_per_minute: int = int(os.getenv("RATE_LIMIT_SYNC", "60"))

    # 业务
    scope_default_days: int = int(os.getenv("SCOPE_DEFAULT_DAYS", "90"))
    retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))


settings = Settings()
```

### 2. backend/main.py（新建）

FastAPI 应用入口，挂载所有路由。

```python
"""
FastAPI 应用入口

路由挂载：
- /api/v1/lives/full  (Agent C)
- /api/v1/lives/sync  (Agent D)

中间件：
- 错误处理（6 种错误码）
- 限流（token bucket）
- 请求参数校验
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncpg

from backend.config import settings
from backend.api.full import router as full_router
from backend.api.sync import router as sync_router
from backend.middleware.error_handler import register_error_handlers
from backend.middleware.request_validator import RequestValidationMiddleware


# 全局连接池
primary_pool: asyncpg.Pool = None
replica_pool: asyncpg.Pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global primary_pool, replica_pool
    primary_pool = await asyncpg.create_pool(
        settings.database_url_primary,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    if settings.database_url_replica:
        replica_pool = await asyncpg.create_pool(
            settings.database_url_replica,
            min_size=2,
            max_size=settings.db_pool_max,
        )

    # 注入 token secret
    from backend.services.token_manager import set_secret
    set_secret(settings.token_secret)

    yield

    await primary_pool.close()
    if replica_pool:
        await replica_pool.close()


app = FastAPI(title="Band Live API", version="4.4.0", lifespan=lifespan)

# 注册错误处理器
register_error_handlers(app)

# 挂载路由
app.include_router(full_router)
app.include_router(sync_router)


# Primary 数据库依赖 — 供 /full 和 /sync 使用
async def get_primary_db():
    async with primary_pool.acquire() as conn:
        yield conn


# Replica 数据库依赖 — 供其他读取使用
async def get_replica_db():
    if replica_pool:
        async with replica_pool.acquire() as conn:
            yield conn
    else:
        async with primary_pool.acquire() as conn:
            yield conn
```

### 3. backend/middleware/error_handler.py（新建）

映射所有错误码（V4.4 §14）：

```python
"""
错误处理器 — V4.4 §14 全部错误码映射

| HTTP | code                    | 客户端动作 |
|------|-------------------------|-----------|
| 400  | INVALID_CITY            | 提示参数错误 |
| 400  | INVALID_PAGE_TOKEN      | 丢弃分页，重新 /full |
| 400  | INVALID_CURSOR          | 丢弃 cursor，重新 /full |
| 409  | FULL_PAGE_TOKEN_EXPIRED | 重新 /full |
| 409  | SYNC_CURSOR_EXPIRED     | 清空 Scope 缓存，重新 /full |
| 429  | RATE_LIMITED            | 退避重试 |
| 500  | SYNC_INVARIANT_BROKEN   | 停止写入水位，稍后重试 |
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register_error_handlers(app: FastAPI):
    @app.exception_handler(Exception)
    async def generic_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"code": "SYNC_INVARIANT_BROKEN", "message": str(exc)},
        )
```

实现时请将 HTTPException 的 detail 字符串映射到正确的 JSON 错误响应格式。

### 4. backend/middleware/request_validator.py（新建）

请求参数校验中间件：
- city 必填，不超过 50 字符
- page_size 限制 1-2000
- since 为非负整数
- limit 限制 1-5000

### 5. backend/services/cache.py（新建）

Redis 缓存辅助（V4.4 §12）：

```python
"""
Redis 缓存辅助 — 仅用于性能优化，不参与一致性判定（V4.4 §12）

约束：
- 绝不缓存 /sync 响应
- 缓存 key 包含 city + scope + token_hash
- TTL 加 jitter 避免集中失效
- 缓存命中不改变 snapshot_cursor
"""
import hashlib
import random
from typing import Optional
import redis.asyncio as redis

from backend.config import settings


def cache_key_full(city: str, scope_start: str, scope_end: str, token_hash: str) -> str:
    return f"full:lives:v1:{city}:{scope_start}:{scope_end}:{token_hash}"


async def get_cached(key: str) -> Optional[bytes]:
    """获取缓存。失败时静默降级——不影响一致性。"""
    try:
        r = redis.from_url(settings.redis_url)
        return await r.get(key)
    except Exception:
        return None


async def set_cached(key: str, value: str):
    """设置缓存，TTL 含 jitter。"""
    try:
        r = redis.from_url(settings.redis_url)
        ttl = settings.cache_ttl_base + random.randint(0, settings.cache_ttl_jitter)
        await r.setex(key, ttl, value)
    except Exception:
        pass  # 缓存失败不影响业务
```

### 6. backend/services/rate_limiter.py（新建）

Token bucket 限流器：
- /full：按 IP + city 限流（30 req/min）
- /sync：按 user + scope 限流（60 req/min）

## 核心原则

- Redis 缓存绝不参与 /sync 或一致性判定
- 数据库密码和 token 密钥绝不硬编码
- /full 和 /sync 路由强制 Primary 数据库
- 所有 7 种错误码正确映射到 JSON 响应
```

- [ ] **Step 2: Wait for Agent E to complete**

- [ ] **Step 3: Gate 4 review**

```
[ ] /full and /sync routes mounted with Primary DB session dependency
[ ] Redis cache NEVER consulted for /sync responses
[ ] Redis cache TTL includes jitter
[ ] Cache key format: full:lives:v1:{city}:{start}:{end}:{token_hash}
[ ] Error code mapping complete: all 7 codes return correct JSON
[ ] Rate limiter: token bucket per IP+city for /full, per user+scope for /sync
[ ] KMS/Vault: DB password and token signing key not hardcoded
[ ] Request validation: city required, page_size capped, since is positive int
[ ] No sync_changes or sync_version_counter access from API layer directly
[ ] DB connection pool: /full and /sync use Primary pool, other reads use replica
[ ] Pool isolation: no cross-contamination between Primary and replica connections
```

- [ ] **Step 4: Fix if needed**

- [ ] **Step 5: User approval**

"Phase 4 complete — FastAPI app with routing, middleware, caching, rate limiting. Proceed to Phase 5?"

- [ ] **Step 6: Commit Phase 4**

```bash
git add backend/main.py backend/config.py backend/middleware/ backend/services/cache.py backend/services/rate_limiter.py
git commit -m "feat: Phase 4 — backend integration with middleware, caching, and rate limiting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 5: Frontend — Agent F

**Model:** `haiku` (v4flash)
**Depends on:** Phase 4 (complete backend API)

### Task 5.1: Dispatch Agent F

- [ ] **Step 1: Send Agent F prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "haiku"`:

```
你是一名 UniApp Vue3 前端专家。请实现移动端演出查看客户端。

## 参考文件

1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §11、§18
2. `backend/contracts/full.openapi.yaml` — /full API 契约
3. `backend/contracts/sync.openapi.yaml` — /sync API 契约
4. `backend/contracts/shared.json` — Live 等共享类型

## 你的任务

### 1. 项目初始化

创建 UniApp Vue3 项目结构。

### 2. frontend/services/api.js（新建）

HTTP 客户端，封装对 /full 和 /sync 的请求：

```javascript
const BASE = process.env.VUE_APP_API_BASE || ''

// 错误码映射
const ERROR_ACTIONS = {
  INVALID_PAGE_TOKEN: 'refetch_full',
  FULL_PAGE_TOKEN_EXPIRED: 'refetch_full',
  SYNC_CURSOR_EXPIRED: 'refetch_full',
  INVALID_CURSOR: 'refetch_full',
  RATE_LIMITED: 'backoff_retry',
  SYNC_INVARIANT_BROKEN: 'stop_and_retry',
}

export async function fetchFullFirstPage(city, pageSize = 500) {
  const params = new URLSearchParams({ city, page_size: pageSize })
  const res = await fetch(`${BASE}/api/v1/lives/full?${params}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function fetchFullNextPage(nextToken, pageSize = 500) {
  const params = new URLSearchParams({ page_token: nextToken, page_size: pageSize })
  const res = await fetch(`${BASE}/api/v1/lives/full?${params}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function fetchSync(city, scopeStart, scopeEnd, since, limit = 1000) {
  const params = new URLSearchParams({
    city, scope_start_date: scopeStart, scope_end_date: scopeEnd,
    since, limit
  })
  const res = await fetch(`${BASE}/api/v1/lives/sync?${params}`)
  if (!res.ok) throw await res.json()
  return res.json()
}

export function getErrorAction(code) {
  return ERROR_ACTIONS[code] || 'unknown'
}
```

### 3. frontend/services/db.js（新建）

IndexedDB 封装，管理 staging_store 和 active_store：

```javascript
const DB_NAME = 'band_live_cache'
const DB_VERSION = 1

let db = null

export async function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (e) => {
      const db = e.target.result
      // staging store — 用于首次同步期间写入
      if (!db.objectStoreNames.contains('staging_store')) {
        db.createObjectStore('staging_store', { keyPath: 'id' })
      }
      // active store — 正式缓存
      if (!db.objectStoreNames.contains('active_store')) {
        db.createObjectStore('active_store', { keyPath: 'id' })
      }
      // meta store — scope, cursor 等同步元数据
      if (!db.objectStoreNames.contains('sync_meta')) {
        db.createObjectStore('sync_meta', { keyPath: 'key' })
      }
    }
    req.onsuccess = (e) => {
      db = e.target.result
      resolve(db)
    }
    req.onerror = () => reject(req.error)
  })
}

// staging 写入（首次 /full 期间）
export async function writeStaging(lives) {
  const tx = db.transaction('staging_store', 'readwrite')
  const store = tx.objectStore('staging_store')
  for (const live of lives) {
    store.put(live)
  }
  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
}

// 原子切换：清空 active，将 staging 数据复制到 active，清空 staging
export async function swapStagingToActive() {
  const tx = db.transaction(['active_store', 'staging_store', 'sync_meta'], 'readwrite')
  const active = tx.objectStore('active_store')
  const staging = tx.objectStore('staging_store')
  const meta = tx.objectStore('sync_meta')

  // 清空 active
  await new Promise((resolve) => {
    const req = active.clear()
    req.onsuccess = resolve
  })

  // 复制 staging → active
  const stagingData = await new Promise((resolve) => {
    const req = staging.getAll()
    req.onsuccess = () => resolve(req.result)
  })
  for (const live of stagingData) {
    active.put(live)
  }

  // 清空 staging
  staging.clear()

  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
}

// 增量更新
export async function upsertActive(lives) {
  const tx = db.transaction('active_store', 'readwrite')
  const store = tx.objectStore('active_store')
  for (const live of lives) {
    store.put(live)
  }
  return new Promise((resolve) => {
    tx.oncomplete = resolve
  })
}

export async function deleteFromActive(ids) {
  const tx = db.transaction('active_store', 'readwrite')
  const store = tx.objectStore('active_store')
  for (const id of ids) {
    store.delete(id)
  }
  return new Promise((resolve) => {
    tx.oncomplete = resolve
  })
}

// 元数据读写
export async function saveMeta(key, value) {
  const tx = db.transaction('sync_meta', 'readwrite')
  tx.objectStore('sync_meta').put({ key, value })
  return new Promise((resolve) => { tx.oncomplete = resolve })
}

export async function getMeta(key) {
  const tx = db.transaction('sync_meta', 'readonly')
  const req = tx.objectStore('sync_meta').get(key)
  return new Promise((resolve) => { req.onsuccess = () => resolve(req.result?.value ?? null) })
}

// 灾难恢复
export async function clearAll() {
  const tx = db.transaction(['active_store', 'staging_store', 'sync_meta'], 'readwrite')
  tx.objectStore('active_store').clear()
  tx.objectStore('staging_store').clear()
  tx.objectStore('sync_meta').clear()
  return new Promise((resolve) => { tx.oncomplete = resolve })
}
```

### 4. frontend/services/sync_engine.js（新建）

同步引擎，实现 V4.4 §11 定义的完整流程：

```javascript
import { fetchFullFirstPage, fetchFullNextPage, fetchSync, getErrorAction } from './api.js'
import { openDB, writeStaging, swapStagingToActive, upsertActive, deleteFromActive, saveMeta, getMeta, clearAll } from './db.js'

// 首次同步（V4.4 §11.1）
export async function firstSync(city) {
  // 1. /full 第一页
  const firstPage = await fetchFullFirstPage(city)
  const { scope, snapshot_cursor } = firstPage

  // 2. 保存 scope 和 snapshot_cursor
  await saveMeta('scope', scope)
  await saveMeta('cursor', snapshot_cursor)

  // 3. 按 next_token 拉完所有页
  await writeStaging(firstPage.data)
  let nextToken = firstPage.next_token
  while (nextToken) {
    const page = await fetchFullNextPage(nextToken)
    await writeStaging(page.data)
    nextToken = page.next_token
  }

  // 4-6. /sync catch-up
  let cursor = snapshot_cursor
  let hasMore = true
  while (hasMore) {
    const batch = await fetchSync(
      scope.city, scope.scope_start_date, scope.scope_end_date, cursor
    )
    if (batch.data.length) await upsertActive(batch.data)  // upsert 进 staging 的数据
    if (batch.deletes.length) await deleteFromActive(batch.deletes)
    cursor = batch.cursor
    hasMore = batch.has_more
  }

  // 7. 原子替换
  await swapStagingToActive()

  // 8. 保存最终 cursor
  await saveMeta('cursor', cursor)
  await saveMeta('last_synced_at', Date.now())

  return { scope, cursor }
}

// 增量同步（V4.4 §11.2）
export async function incrementalSync() {
  const scope = await getMeta('scope')
  const cursor = await getMeta('cursor')

  if (!scope || cursor == null) {
    throw new Error('NO_SYNC_STATE')
  }

  let since = cursor
  let hasMore = true

  while (hasMore) {
    const batch = await fetchSync(
      scope.city, scope.scope_start_date, scope.scope_end_date, since
    )
    if (batch.data.length) await upsertActive(batch.data)
    if (batch.deletes.length) await deleteFromActive(batch.deletes)

    since = batch.cursor
    hasMore = batch.has_more
  }

  await saveMeta('cursor', since)
  await saveMeta('last_synced_at', Date.now())

  return { cursor: since }
}

// 错误处理：决定是否需要重新 /full
export async function handleSyncError(error) {
  const action = getErrorAction(error.code)
  if (action === 'refetch_full') {
    await clearAll()
    const scope = await getMeta('scope')
    const city = scope?.city || 'Tokyo'
    return firstSync(city)
  }
  if (action === 'backoff_retry') {
    await new Promise(r => setTimeout(r, 5000))
    return incrementalSync()
  }
  throw error
}
```

### 5. 页面实现

实现 5 个页面（V4.4 §18），每个页面应包含完整代码：

**frontend/pages/index.vue** — 首页演出列表：
- 按日期分组显示演出
- 每项显示：日期、演出标题、场地名、乐队名列表、开始时间
- 下拉刷新触发增量同步
- 显示同步状态（"上次同步：X 分钟前"）
- 顶部城市名称，点击可切换

**frontend/pages/city-switch.vue** — 城市切换：
- 城市列表/搜索
- 选择后触发首次全量同步
- 同步期间显示进度

**frontend/pages/detail.vue** — 演出详情：
- 海报图（加载失败显示占位）
- 完整信息展示
- 票价、购票链接
- 乐队阵容

**frontend/components/SyncStatus.vue** — 同步状态指示器
**frontend/components/ErrorPage.vue** — 错误/异常提示

## UI 原则（V4.4 §18）

- 移动端优先布局
- 普通用户无需学习即可使用
- 图片加载失败有默认占位
- 网络异常时展示本地缓存数据
- 首次加载显示同步进度
- 禁止复杂动画
- 保持统一字体、间距、颜色

## 核心原则

- 首次同步使用 staging_store → active_store 双区模式
- cursor 每次 /sync 后保存
- 城市切换 / cursor 过期 / token 过期 → 全部重新 /full
- 离线时展示 active_store 缓存数据
- IndexedDB 损坏时自动清理重建
```

- [ ] **Step 2: Wait for Agent F to complete**

- [ ] **Step 3: Gate 5 review**

```
[ ] First sync: /full page 1 → save scope → pull all pages → /sync catch-up → swap
[ ] staging_store during full pull, active_store after swap
[ ] Cursor saved to IndexedDB after each /sync completion
[ ] Scope change (city switch) triggers full re-sync
[ ] SYNC_CURSOR_EXPIRED (409) triggers full re-sync
[ ] FULL_PAGE_TOKEN_EXPIRED (409) triggers fresh /full from page 1
[ ] RATE_LIMITED (429) triggers backoff retry
[ ] Offline: shows cached active_store data with "last synced" indicator
[ ] No complex animations or abstracted component hierarchies
[ ] Image load failure shows placeholder
[ ] Loading state shows sync progress (pages pulled / total)
[ ] IndexedDB schema versioned: migration path on upgrade
[ ] Disaster recovery: corrupted IndexedDB → delete and re-/full
[ ] Long offline: >30 days → cursor expired → /full recovery → consistent state
```

- [ ] **Step 4: Fix if needed**

- [ ] **Step 5: User approval**

"Phase 5 complete — UniApp Vue3 client with IndexedDB, sync engine, and 5 pages. Proceed to Phase 6?"

- [ ] **Step 6: Commit Phase 5**

```bash
git add frontend/
git commit -m "feat: Phase 5 — UniApp Vue3 client with sync engine and IndexedDB cache

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 6: Test & Review — Agent G + Agent H

**Agent G model:** `haiku` (v4flash)
**Agent H model:** `sonnet` (v4p)
**Depends on:** All prior phases

### Task 6.1: Dispatch Agent G (Testing)

- [ ] **Step 1: Send Agent G prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "haiku"`:

```
你是一名测试工程专家。请建立完整测试体系，覆盖 V4.4 §15 全部场景。

## 参考文件

请阅读以下所有文件（测试需要了解完整系统）：
1. `技术实现计划书 V4.4 生产基线版.txt` — 特别关注 §15 测试清单
2. `database/migrations/V1__schema.sql` — 数据库 schema
3. `database/migrations/V2__permissions.sql` — 权限配置
4. `backend/api/full.py` — /full 接口
5. `backend/api/sync.py` — /sync 接口
6. `backend/services/cdc_writer.py` — CDC 写入
7. `backend/services/retention_cleaner.py` — 日志清理
8. `backend/services/token_manager.py` — Token 管理
9. `backend/contracts/full.openapi.yaml` — API 契约
10. `backend/contracts/sync.openapi.yaml` — API 契约

## 你的任务

创建以下测试文件，每个文件包含完整的、可运行的测试代码：

### 1. backend/tests/conftest.py

pytest 配置和 fixtures：
- 测试数据库连接（使用测试专用 PostgreSQL）
- 表创建/清理 fixture
- 测试数据播种 fixture（至少包含多城市、多日期、各种 review_status、start_time NULL 和非 NULL）
- asyncpg Connection fixture
- FastAPI TestClient fixture

### 2. backend/tests/test_keyset.py

Keyset 分页测试（V4.4 §15.1）：
- test_same_date_multiple_non_null_start_times — 同一天多条有 start_time
- test_same_date_multiple_null_start_times — 同一天多条 start_time IS NULL
- test_null_sort_start_time_ordering — 23:59:58、23:59:59、NULL 同时存在，排序正确
- test_page_boundary_ends_with_null — 分页边界最后一条是 NULL
- test_page_boundary_ends_with_235959 — 分页边界最后一条是 23:59:59
- test_same_date_same_time_stable_id_order — 同日期同时刻按 id 稳定排序
- test_no_duplicates_across_pages — 分页无重复无遗漏
- test_next_token_last_time_not_null — next_token.last_time 非 NULL

### 3. backend/tests/test_scope.py

固定 Scope 测试（V4.4 §15.2）：
- test_full_first_page_at_midnight — 首页在 23:59:59 发起
- test_full_next_page_next_day — 后续页在次日 00:00:01 发起仍用固定 scope
- test_sync_uses_same_scope — /sync 使用与 /full 相同的 scope
- test_no_date_drift — CURRENT_DATE 改变不导致数据跳过或重复

### 4. backend/tests/test_cdc.py

CDC 测试（V4.4 §15.3），全覆盖 13 种场景：
- test_insert_in_scope — 新增 Scope 内演出
- test_update_in_scope — 更新 Scope 内演出
- test_delete_in_scope — 删除 Scope 内演出
- test_published_to_hidden — published → hidden → delete
- test_hidden_to_published — hidden → published → upsert
- test_city_move_out — city 从 Scope 移出 → delete
- test_city_move_in — city 从其他城市移入 → upsert
- test_date_move_out — live_date 移出 Scope → delete
- test_date_move_in — live_date 移入 Scope → upsert
- test_start_time_null_to_non_null — start_time 改为 NULL 后 sort_start_time 正确
- test_start_time_non_null_to_null — start_time 改为非空后 sort_start_time 正确
- test_sort_key_moved_before_paginated — 排序键移到已分页区域之前
- test_sort_key_moved_after_paginated — 排序键移到尚未分页区域之后

### 5. backend/tests/test_sync.py

Sync 分批测试（V4.4 §15.4）：
- test_limit_less_than_changes — limit 小于变更数时分批正确
- test_cursor_is_batch_max_not_high_water — cursor 是本批最大 version 而非 high_water
- test_has_more_loop_until_complete — 客户端循环到 has_more=false 后数据完整
- test_same_entity_folded_to_final_action — 同一实体多次变更只输出最终动作
- test_entity_not_in_both_data_and_deletes — 同一实体不会同时出现在 data 和 deletes
- test_sync_empty_result_when_up_to_date — since == high_water 时返回空结果无错误
- test_sync_return_order_by_version_asc — 返回按 version ASC 排序

### 6. backend/tests/test_permissions.py

权限测试（V4.4 §15.6）：
- test_api_role_cannot_insert_live_bands — api_role 不能直接写 live_bands
- test_api_role_cannot_insert_sync_changes — api_role 不能直接写 sync_changes
- test_public_cannot_create_in_schema — PUBLIC 不能在 public schema 创建对象
- test_security_definer_owner_is_nologin — SECURITY DEFINER 函数 owner 是 NOLOGIN
- test_safe_update_bands_rejects_invalid_json — safe_update_live_bands 拒绝非法 JSON
- test_safe_update_bands_rejects_unknown_band — safe_update_live_bands 拒绝未知 band_id
- test_safe_update_bands_rejects_too_many — safe_update_live_bands 拒绝超长数组

### 7. backend/tests/test_performance.py

性能测试：
- test_hot_city_first_full_page — 热门城市首次 /full 响应时间
- test_consecutive_sync — 连续 /sync 响应时间
- test_concurrent_full_requests — 并发 /full 请求不降级

### 8. backend/tests/test_retention.py

Retention 测试（V4.4 §15.5）：
- test_since_at_floor_valid — since == retention_floor_version 仍有效
- test_since_below_floor_expired — since < retention_floor_version 返回 409
- test_no_logs_still_returns_high_water — 无日志时仍返回当前 high_water
- test_cleanup_updates_floor — 清理任务更新 floor

### 9. tests/integration/test_e2e_sync.py

端到端一致性测试：
- test_full_plus_sync_equals_server_state — full(snapshot_cursor) + sync(after) == 服务端 Scope 状态

### 10. 验收清单

生成验收清单，逐项对应 V4.4 §16 的 12 条标准。

## 核心原则

- 每个测试独立运行，不依赖执行顺序
- 使用真实的 PostgreSQL 测试数据库，不使用 mock
- 覆盖所有边界条件，特别是 NULL 和 23:59:59
- 测试命名清晰，失败时能从名称判断问题
```

### Task 6.2: Dispatch Agent H (Review)

- [ ] **Step 1: Send Agent H prompt**

Use `Agent` tool with `subagent_type: "general-purpose"`, `model: "sonnet"`:

```
你是一名系统集成审查专家。请对整个项目进行最终架构审查。

## 参考文件

请阅读项目中所有文件，特别关注：
1. `技术实现计划书 V4.4 生产基线版.txt` — 技术基线
2. 所有 `backend/`、`database/`、`frontend/`、`tests/` 下的文件
3. `docs/superpowers/specs/2026-08-12-multi-agent-orchestration-design.md` — 编排设计

## 你的任务

### 1. 一致性审查

验证最终一致性前提（V4.4 §1）：
```
full(snapshot_cursor) + sync(after snapshot_cursor) = 服务端最终 Scope 状态
```

检查：
- /full 和 /sync 是否都读取 Primary？
- 所有会影响客户端可见数据的写入是否在同一事务中写入 sync_changes？
- /full 首页 scope 是否固定，后续分页和 /sync 是否沿用同一 Scope？
- 客户端完成 /full 后是否立即执行 /sync?since=snapshot_cursor？
- Cursor 过期判定是否使用 retention_floor_version？

### 2. 安全审查

检查：
- 权限绕过：api_role 是否有任何路径可以直接写受保护表？
- Token 伪造：page_token 签名是否可被伪造或重放？
- SQL 注入：SECURITY DEFINER 函数是否设置了 search_path？
- 函数提权：SECURITY DEFINER 函数 owner 是否为 NOLOGIN app_definer？

### 3. 性能审查

检查：
- 索引命中：/full 和 /sync 的关键查询是否都命中了正确的索引？
- 热点城市：热门城市的 /full 首页是否有缓存策略？
- /sync 压力：/sync 的 limit 和分批设计是否合理？
- Redis 策略：Redis 是否参与了任何一致性判定？

### 4. 产出

生成 `docs/integration_review.md`：
- 集成问题列表（逐条列出每个发现的问题）
- P0（阻塞上线）/ P1（上线前修复）/ P2（后续优化）风险分类
- 最终发布建议（go / no-go / conditional-go）

生成 `docs/release_checklist.md`：
- V4.4 §16 全部 12 条验收标准的逐条检查结果
```

### Task 6.3: Gate 6 Review

- [ ] **Step 1: Review Agent G output**

```
[ ] Keyset NULL tests: same-date NULL times, 23:59:58/59/NULL ordering, id tiebreak
[ ] Scope midnight test: page 1 at 23:59:59, page 2 at 00:00:01, same scope
[ ] CDC: all 13 scenarios from §15.3 covered
[ ] Sync batching: limit < total changes, cursor advances correctly, no entity in both arrays
[ ] Retention: since==floor valid, since<floor returns 409, cleanup updates floor
[ ] Permissions: api_role blocked from direct writes, SECURITY DEFINER ownership verified
[ ] Final consistency proof: full(snapshot_cursor) + sync(after) == server Scope state
```

- [ ] **Step 2: Review Agent H output**

```
[ ] All P0 items are real blockers, with specific file/line references
[ ] P1 items have clear fix descriptions
[ ] P2 items are genuinely optional
[ ] Release recommendation is clear (go/no-go/conditional)
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/ -v
```

- [ ] **Step 4: Fix any failures**

- [ ] **Step 5: User approval**

"Phase 6 complete — test suite and integration review. Project ready. Final approval?"

- [ ] **Step 6: Final commit**

```bash
git add tests/ docs/integration_review.md docs/release_checklist.md
git commit -m "feat: Phase 6 — test suite, integration review, and release checklist

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Execution Order Summary

```
Phase 0: Contracts    (Supervisor)     ─> Commit
Phase 1: Agent A      (haiku)         ─> Gate 1 ─> User ✓ ─> Commit
Phase 2: Agent B      (sonnet)        ─> Gate 2 ─> User ✓ ─> Commit
Phase 3: Agent C      (haiku)         ─> Agent D (sonnet) ─> Gate 3 ─> User ✓ ─> Commit
Phase 4: Agent E      (haiku)         ─> Gate 4 ─> User ✓ ─> Commit
Phase 5: Agent F      (haiku)         ─> Gate 5 ─> User ✓ ─> Commit
Phase 6: Agent G      (haiku)         ─> Agent H (sonnet) ─> Gate 6 ─> User ✓ ─> Commit
```

Each phase gate includes:
1. Supervisor preliminary review (checklist verification)
2. Fix cycle if needed (re-prompt agent)
3. Present to user for final approval
4. Commit before next phase
