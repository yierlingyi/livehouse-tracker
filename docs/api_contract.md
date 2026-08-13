# API 契约（冻结版）

> 状态：已冻结。依据三端重构复审决策（2026-08-13）。
> 本文件是 **User App / Band Portal / Admin Console / backend-apis** 四方唯一的接口契约。
> 三端前端以 `VITE_USE_MOCK=true` 的 mock 层自洽开发；backend-apis 按本文实现后，
> 三端 `VITE_USE_MOCK=false` + `VITE_API_BASE` 一键切换联调。
> Mock 层实现位于 `frontend/shared/mock/`，与下表一一对应。

## 0.5 契约勘误（2026-08-13）

以下表项与实现（mock + 后端一致、前端按此读取）不符，以本勘误为准：

| 位置 | 原表述 | 修正 |
|---|---|---|
| §4.3 `POST /coop/events` | `{event}` | 返回**裸 event 对象**（含 `id`），不包裹 |
| §5 `POST /livehouses` / `PATCH /livehouses/{id}` | `{venue}` | 返回**裸 venue 对象** |
| §7 `POST /cms/groups` / `PATCH /cms/groups/{id}` | `{group}` | 返回**裸 group 对象** |
| §4.3 `GET /coop/events/invites` | 列表项无 `id` | **设计如此**：invite_id 经 `GET /coop/events/{id}` 详情 `participants[].invite_id` 解析；accept/reject/songs/revoke/exit-request/approve-exit 均允许省略 invite_id（前端 `coop-api.js` 内部兜底解析） |

> 其余接口（`/band/lives` → `{live}`、`/admin/lives` → `{live}`、invite 动作 → `{invite}` 等）保持包裹，与实现一致。

## 0. 全局约定

- 基础路径：`/api/v1`
- 错误统一：`{code, message}`（HTTP 状态码 4xx/5xx；鉴权失败 401、无权限 403、不存在 404）
- 鉴权：`Authorization: Bearer <token>`（白名单接口与公开 GET 除外）
- 可复用现有接口（不改动 V4.4 一致性模型）：`GET /lives/full`、`GET /lives/sync`（仅 User App 演出列表）。
- 新增实体**一律不进 CDC 同步**（不触碰 sync_changes / /full /sync），走普通 REST。
- 本契约不包含 `Submitted` 状态；Live 发布状态仅 `draft` / `published` 两级。

## 1. 已批准决策（契约内化）

| 决策项 | 结论 |
|---|---|
| 后端范围 | 本轮前后端并行实现；前端 mock 先行不阻塞。 |
| Live 发布流程 | **提交即发布（直接 Published）**，无 Submitted 态。生命周期：Draft → Published；下架/强制下架 = Published → Draft。 |
| Pending 登录 | **禁止登录，仅提示**。登录返回 status='pending' → 前端提示「账号审核中」。 |
| 下架语义 | `offline` / 强制下架将 Live 同时置 `status='draft'` 且 `review_status='draft'` → `/sync` Scope 投影自动以 `delete` 下发 → 用户端即时隐藏。 |
| 编辑已发布内容 | 编辑已发布 Live 后回 draft（需重新发布）。 |
| 拼盘实时性 | 不做 WebSocket，管理页 5s 轮询。 |

## 2. 认证与账号（§4.1）

| method | 路径 | 用途 | 请求 | 响应关键字段 |
|---|---|---|---|---|
| POST | `/auth/register` | 乐队注册 | `{username,password,band_name}` | `{account}`(status=pending) |
| POST | `/auth/login` | 乐队登录 | `{username,password}` | `{token, account:{id,username,band_name,role:'band',status}}` |
| POST | `/auth/logout` | 注销 | — | `{ok:true}` |
| GET | `/auth/me` | 当前账号 | — | `{account}` |
| POST | `/admin/login` | 管理员登录 | `{username,password}` | `{token, account:{id,username,role:'admin'}}` |
| GET | `/accounts/{username}/exists` | 拼盘邀请实时校验 | — | `{exists:bool}` |
| POST | `/admin/accounts` | 新增管理员（admin） | `{username,password}` | `{account}` |

登录时按 status 分支：`active` 放行；`pending` 拒绝并提示「账号审核中」；`rejected/disabled` 拒绝并显示原因。

## 3. 乐队资料与 Live — Band Portal（§4.2）

| method | 路径 | 用途 | 请求 | 响应关键字段 |
|---|---|---|---|---|
| GET | `/band/me` | 我的资料/设置 | — | `{account, band:{id,name,qq_bind?}, lives:{draft,published}}` |
| PATCH | `/band/me` | 更新资料/QQ 绑定 | `{band_name?,qq_bind?}` | `{account,band}` |
| POST | `/band/lives` | 创建 Live | `{title,livehouse_id,live_date,start_time,ticket_price,ticket_url,poster_image_url,setlist:[{song_title,band_id?}],action:'save_draft'\|'publish'}` | `{live}` |
| GET | `/band/lives` | 我的 Live（status 过滤） | `?status=draft\|published` | `{items:[...]}` |
| GET | `/band/lives/{id}` | 我的 Live 详情（含 setlist） | — | `{live,setlist}` |
| PATCH | `/band/lives/{id}` | 编辑（已发布内容 → 回 draft） | 同 POST | `{live}` |
| DELETE | `/band/lives/{id}` | 删除草稿 | — | `{ok:true}` |
| POST | `/band/lives/{id}/publish` | **发布（→ published 直接上线）** | — | `{live}` |
| POST | `/band/lives/{id}/offline` | 下架（status+review_status→draft） | — | `{live}` |

## 4. 拼盘 Co-op（§4.3）

状态枚举：`invited → agreed / rejected / exit_requested → removed`

| method | 路径 | 用途 | 请求 | 响应关键字段 |
|---|---|---|---|---|
| POST | `/coop/events` | 创建拼盘（可存草稿） | `{title,livehouse_id,live_date,start_time,ticket_price,poster_image_url,own_songs:[...],invites:[{username,songs:[...]}],action}` | `{event}` |
| GET | `/coop/events` | 我关联的所有拼盘+实时状态 | — | `{items:[{id,title,live_date,status,invites:[{band_name,username,invite_status,songs,is_me,is_initiator}]}]}` |
| GET | `/coop/events/{id}` | 拼盘详情 | — | `{event,participants,agreed_count,total_count,rejected_count,exit_requested_count}` |
| PATCH | `/coop/events/{id}` | 发起方编辑/存草稿 | 同 POST | `{event}` |
| DELETE | `/coop/events/{id}` | 发起方删草稿 | — | `{ok:true}` |
| POST | `/coop/events/{id}/invites` | 追加邀请（发起方） | `{username,songs}` | `{event}` |
| GET | `/coop/events/invites` | 我收到的邀请 | — | `{items:[{event_id,initiator_band,title,live_date,venue_address,assigned_songs,invite_status}]}` |
| POST | `/coop/events/{id}/invites/{invite_id}/accept` | 同意（可带曲目） | `{songs?}` | `{invite}` |
| POST | `/coop/events/{id}/invites/{invite_id}/reject` | 拒绝 | — | `{invite}` |
| PATCH | `/coop/events/{id}/invites/{invite_id}/songs` | 改本队曲目（仅本人，非发起方） | `{songs}` | `{invite}` |
| POST | `/coop/events/{id}/invites/{invite_id}/revoke` | 撤销同意 | — | `{invite}`(→invited) |
| POST | `/coop/events/{id}/invites/{invite_id}/exit-request` | 申请退出 | — | `{invite}`(exit_requested) |
| POST | `/coop/events/{id}/invites/{invite_id}/approve-exit` | 发起方审批退出 | — | `{invite}`(removed) |
| POST | `/coop/events/{id}/offline` | 发起方下架拼盘 | — | `{event}` |

## 5. 场地 / 乐队 — 公开只读 + Admin 写（§4.4）

| method | 路径 | 用途 | 响应关键字段 |
|---|---|---|---|
| GET | `/livehouses` | 场地列表（公开） | `{items:[{id,name,intro,image_url}]}` |
| GET | `/livehouses/{id}` | 场地详情（公开） | `{id,name,address,phone,intro,image_url,floorplan_url}` |
| POST | `/livehouses` | 新增场地（admin） | `{name,address,phone,image_url,intro,floorplan_url?}` → `{venue}` |
| PATCH | `/livehouses/{id}` | 编辑场地（admin） | 同上 → `{venue}` |
| DELETE | `/livehouses/{id}` | 删除场地（admin） | → `{ok:true}` |
| GET | `/bands` | 乐队列表（公开，**无地址/电话**） | `{items:[{id,name,cover_url}]}` |
| GET | `/bands/{id}` | 乐队详情（公开，**不展示地址电话**） | `{id,name,intro,cover_url,members:[{name,role?}]}` |
| GET | `/lives/{id}` | 演出详情（公开，含场地信息+setlist+海报） | `{live,venue,setlist,poster_image_url}` |

> 乐队资料为独立实体（后端建议 `band_profiles` / `band_accounts`），**不复用/不重名**现有 `bands` 表（live_bands 关联表）。

## 6. Admin 管理（§4.5）

| method | 路径 | 用途 | 响应关键字段 |
|---|---|---|---|
| GET | `/admin/lives` | 所有 Live（all/normal/coop 过滤） | `{items:[{id,title,live_date,kind,review_status,status,band_names}]}` |
| PATCH | `/admin/lives/{id}` | 强制编辑（全字段含 setlist/阵容） | `{live}` |
| POST | `/admin/lives/{id}/offline` | 强制下架（status+review_status→draft） | `{live}` |
| GET | `/admin/bands` | 乐队列表（`?filter=pending\|all`） | `{items:[{id,username,band_name,status,created_at}]}` |
| GET | `/admin/bands/{id}` | 账号详情 | `{account,band}` |
| PATCH | `/admin/bands/{id}` | 通过/拒绝/改资料 | `{action:'approve'\|'reject',band_name?,intro?}` → `{account,band}` |
| DELETE | `/admin/bands/{id}` | 删除账号 | `{ok:true}` |

## 7. CMS（§4.6）

| method | 路径 | 用途 | 响应关键字段 |
|---|---|---|---|
| GET | `/cms/groups` | 同好群列表（公开） | `{items:[{id,city,platform:'wechat'\|'qq',group_id}]}` |
| POST | `/cms/groups` | 新增（admin） | `{city,platform,group_id}` → `{group}` |
| PATCH | `/cms/groups/{id}` | 编辑（admin） | 同上 → `{group}` |
| DELETE | `/cms/groups/{id}` | 删除（admin） | `{ok:true}` |
| GET | `/cms/sponsor` | 赞助（公开） | `{thanks_text,qr_image_urls:[2]}` |
| PUT | `/cms/sponsor` | 更新（admin） | `{thanks_text,qr_image_urls}` |
| GET | `/cms/project` | 项目声明（公开） | `{intro,github_url,author,license}` |
| PUT | `/cms/project` | 更新（admin） | 同上 |

## 8. 文件上传（§4.7）

| method | 路径 | 用途 | 请求 | 响应 |
|---|---|---|---|---|
| POST | `/upload` | multipart 上传 | `form-data file` | `{url}` |

> Mock 模式返回 `static/` 本地占位 URL；真实模式需存储前缀（`VITE_IMAGE_BASE`），远端 URL 由前端 `image @error` 兜底。

## 9. Mock / 联调切换

- 各端 `.env`：`VITE_USE_MOCK=true`（默认开发）、`VITE_API_BASE=http://127.0.0.1:8000`
- `frontend/shared/http.js`：`VITE_USE_MOCK==='true'` 时路由到 `frontend/shared/mock/index.js`，否则 `uni.request` 打真实 API。
- 后端就绪后：`VITE_USE_MOCK=false` 即切换真实 API；`/full /sync` 原有测试需回归全绿。
