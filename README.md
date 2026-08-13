# 乐队演出平台（Band Live）

三端分离的乐队演出查看与管理平台：普通用户看演出，乐队发布演出、发起拼盘，管理员审核与运营。

## 架构概览

三个前端工程各自独立，但共享 `前端/shared` 单一数据源（组件 / API 封装 / mock / 主题），由 `前端/scripts/sync-shared.js` 同步到各端的 `common/` 目录。

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   user-app    │   │  band-portal  │   │ admin-console │
│  普通用户端   │   │    乐队端     │   │   管理员端    │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       └────────  前端/shared（同步到各端 common/）────────┘
                              │ HTTP（REST + /full /sync 增量同步）
                     ┌────────▼────────┐
                     │   FastAPI 后端   │
                     └────────┬────────┘
                              │ asyncpg
                     ┌────────▼────────┐
                     │   PostgreSQL    │
                     └─────────────────┘
```

## 目录结构

```
live/
├── backend/                 # FastAPI 后端
│   ├── main.py              # 应用入口（uvicorn backend.main:app）
│   ├── config.py            # 环境变量配置（敏感值只从环境读取，零硬编码）
│   ├── api/                 # 路由（auth/band/bands/lives/admin/livehouse/coop/cms/upload...）
│   ├── services/            # 业务与安全（passwords/token_manager/cache...）
│   └── middleware/          # 错误归一、限流、CORS
├── database/migrations/     # PostgreSQL 迁移（V1 → V2 → V3）
├── 前端/
│   ├── shared/              # 三端共享单一数据源
│   ├── user-app/            # 普通用户端（演出 / 场地 / 乐队 / 设置）
│   ├── band-portal/         # 乐队端（Live 管理 / 拼盘 / 资料）
│   ├── admin-console/       # 管理员端（审核 / 场地 / CMS / 系统）
│   └── scripts/sync-shared.js
├── docs/
│   ├── api_contract.md      # API 契约
│   ├── developer-guide.md   # 后端开发指南
│   └── 部署指南.md          # Linux 部署（git clone 后完整步骤）
├── requirements.txt         # 后端 Python 依赖
└── .env.example             # 环境变量模板
```

## 技术栈

- 前端：uni-app + Vue 3（HBuilderX，Vite 编译器）
- 后端：Python + FastAPI + asyncpg
- 数据库：PostgreSQL
- 认证：PBKDF2-HMAC-SHA256 口令哈希 + HMAC-SHA256 签名 Token

## 快速开始

### 1. 数据库

建库（生产用 `app_db`），按顺序应用迁移：

```bash
psql -d app_db -f database/migrations/V1__schema.sql
psql -d app_db -f database/migrations/V2__permissions.sql
psql -d app_db -f database/migrations/V3__platform.sql
```

### 2. 后端

```bash
pip install -r requirements.txt
# 配置环境变量（见下方「环境变量」，至少 DATABASE_URL_PRIMARY 与 TOKEN_SECRET）
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

初始化管理员：调用 V3 迁移提供的 `safe_create_admin(username, password_hash)`（见「预设账户」）。

### 3. 前端

用 HBuilderX 分别打开 `前端/user-app`、`前端/band-portal`、`前端/admin-console`，运行到浏览器或微信开发者工具。

修改 `前端/shared` 后运行 `node 前端/scripts/sync-shared.js` 同步到三端。

## 环境变量

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `DATABASE_URL_PRIMARY` | ✅ | — | 主库连接串，如 `postgresql://postgres@127.0.0.1:5432/app_db` |
| `DATABASE_URL_REPLICA` | | 空 | 从库连接串（空则回退主库） |
| `TOKEN_SECRET` | ✅ | — | HMAC-SHA256 签名密钥 |
| `TOKEN_TTL_MINUTES` | | 30 | 分页 token 有效期 |
| `DB_POOL_MIN` / `DB_POOL_MAX` | | 5 / 50 | 连接池上下限 |
| `REDIS_URL` | | 空 | 缓存 / 限流（空则内存降级） |
| `CACHE_TTL_BASE` / `CACHE_TTL_JITTER` | | 60 / 30 | 缓存 TTL 及其抖动 |
| `RATE_LIMIT_FULL_PER_MINUTE` | | 30 | `/full` 限流配额 |
| `RATE_LIMIT_SYNC_PER_MINUTE` | | 60 | `/sync` 限流配额 |
| `SCOPE_DEFAULT_DAYS` | | 90 | `/full` 固定 scope 长度 |
| `RETENTION_DAYS` | | 30 | CDC 变更日志保留天数 |
| `UPLOAD_DIR` | | `uploads` | 上传落盘目录 |
| `UPLOAD_URL_PREFIX` | | `/static/uploads` | 上传 URL 前缀 |

## 预设账户

| 端 | 账号 | 密码 | 说明 |
|---|---|---|---|
| 管理员端 | `admin` | `admin123` | 由 V3 `safe_create_admin` 创建；**部署后请更换为强密码** |
| 乐队端 | — | — | 无公开预设；注册 → 管理员审核 → 登录 |

> 乐队账号注册后为 `pending`，管理员在「乐队审核」通过后即可登录；`rejected` 无法登录。

## 城市数据模型

- **场地（livehouses）**：含 `city` 列，严格按城市归属。
- **演出（lives）**：含 `city` 列，创建时从场地继承；`/full`、`/sync` 均按 `city` 过滤，keyset 索引 `(city, live_date, sort_start_time, id)`。不同城市的演出互不混排。
- **乐队（band_accounts）**：无 `city` 列，为全局实体（一支乐队可跨城演出）；乐队在某城市出现，是因为它在该城有已发布演出。

## 安全

- 口令：PBKDF2-HMAC-SHA256（120,000 次迭代 + 16 字节随机盐，`salt$hash` hex 存储，`hmac.compare_digest` 防时序侧信道），明文不落库。
- 会话：HMAC-SHA256 签名 Token（24 小时短时），登录后 `Authorization: Bearer`。
- 权限：数据库 `api_role` 表级只读 + 写操作走 `SECURITY DEFINER` 函数（固定 `search_path`、参数化、防注入）。
- 限流：按 `IP + city` / `user + scope`。
- 敏感值只从环境变量读取，代码零硬编码。

## 图片 / 图床

图片地址以 URL 字符串存库。前端 `resolveImageUrl` 对 `http(s)://` 绝对地址与 `data:` 原样透传，只对根相对路径拼 `API_BASE`。因此**天然支持图床 / CDN**：把 `image_url` / `poster_image_url` 存成 OSS / COS / 七牛等绝对 URL 即可，前端无需改动。默认本地上传走 `/static/uploads/`（由 `UPLOAD_DIR` / `UPLOAD_URL_PREFIX` 配置）。

## 微信 / QQ 小程序预留

- 三端 `manifest.json` 均已含 `mp-weixin` 配置块，HBuilderX 可直接「发行 → 小程序-微信」。
- 代码全用 uni-app 跨端 API（`uni.request` / `navigateTo` / `switchTab`），无 H5 专属依赖。
- 社群表 `community_groups.platform` 已预留 `wechat` / `qq` 枚举。
- QQ 小程序：在 `manifest.json` 补 `mp-qq` 块并填 appid 即可，业务代码无需改动。

## 文档

- `docs/api_contract.md` — API 契约（含契约勘误）。
- `docs/developer-guide.md` — 后端开发指南。
- `docs/部署指南.md` — Linux 部署（`git clone` 后完整步骤）。
