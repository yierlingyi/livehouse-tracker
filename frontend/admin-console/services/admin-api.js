/**
 * Admin Console API 封装（对应 docs/api_contract.md §2/§5/§6/§7）
 *
 * 统一走 common/http.js 的 request()（自动附加管理员 token，mock 模式路由到 shared/mock）。
 * 说明：强制编辑页详情走 Admin 专用 `GET /admin/lives/:id`（任意 review_status 可读，
 * 草稿/下架不再 404），对齐 mock venues.mock.js 的 adminLiveDetail。
 */
import { request } from '../common/http.js'

/* ---------------- 认证 / 管理员账号（§2） ---------------- */

/** 管理员登录 {username,password} → {token,account} */
export function adminLogin(data) {
  return request('POST', '/api/v1/admin/login', data)
}

/** 新增管理员（admin）{username,password} → {account} */
export function createAdminAccount(data) {
  return request('POST', '/api/v1/admin/accounts', data)
}

/* ---------------- 演出与乐队（§6 Admin 管理） ---------------- */

/**
 * 所有 Live（kind=all|normal|coop）→ {items:[{id,title,live_date,kind,review_status,status,band_names}]}
 */
export function listLives(kind) {
  return request('GET', '/api/v1/admin/lives', { kind: kind || 'all' })
}

/** 演出详情（Admin 专用，含 venue/setlist/poster，任意 review_status）→ {live,venue,setlist,poster_image_url} */
export function getLive(id) {
  return request('GET', '/api/v1/admin/lives/' + id)
}

/** 强制编辑 Live（全字段，PATCH /admin/lives/:id）→ {live} */
export function updateLive(id, data) {
  return request('PATCH', '/api/v1/admin/lives/' + id, data)
}

/** 强制下架（POST /admin/lives/:id/offline，status+review_status→draft）→ {live} */
export function offlineLive(id) {
  return request('POST', '/api/v1/admin/lives/' + id + '/offline')
}

/**
 * 乐队账号库 / 审核队列（filter=pending|all）→ {items:[{id,username,band_name,status,created_at}]}
 */
export function listBands(filter) {
  return request('GET', '/api/v1/admin/bands', { filter: filter || 'all' })
}

/** 账号详情 → {account, band} */
export function getBand(id) {
  return request('GET', '/api/v1/admin/bands/' + id)
}

/** 通过/拒绝/改资料 {action:'approve'|'reject',band_name?,intro?} → {account,band} */
export function updateBand(id, data) {
  return request('PATCH', '/api/v1/admin/bands/' + id, data)
}

/** 删除账号 → {ok:true} */
export function deleteBand(id) {
  return request('DELETE', '/api/v1/admin/bands/' + id)
}

/* ---------------- 场地（§5 公开只读 + Admin 写） ---------------- */

/** 场地列表（公开）→ {items:[{id,name,intro,image_url}]} */
export function listVenues() {
  return request('GET', '/api/v1/livehouses')
}

/** 场地详情（公开）→ {id,name,address,phone,intro,image_url,floorplan_url} */
export function getVenue(id) {
  return request('GET', '/api/v1/livehouses/' + id)
}

/** 新增场地（admin）→ {venue} */
export function createVenue(data) {
  return request('POST', '/api/v1/livehouses', data)
}

/** 编辑场地（admin）→ {venue} */
export function updateVenue(id, data) {
  return request('PATCH', '/api/v1/livehouses/' + id, data)
}

/** 删除场地（admin）→ {ok:true} */
export function deleteVenue(id) {
  return request('DELETE', '/api/v1/livehouses/' + id)
}

/* ---------------- CMS 内容管理（§7） ---------------- */

/** 同好群列表（公开）→ {items:[{id,city,platform,group_id}]} */
export function listGroups() {
  return request('GET', '/api/v1/cms/groups')
}

/** 新增同好群 {city,platform,group_id} → {group} */
export function createGroup(data) {
  return request('POST', '/api/v1/cms/groups', data)
}

/** 编辑同好群 → {group} */
export function updateGroup(id, data) {
  return request('PATCH', '/api/v1/cms/groups/' + id, data)
}

/** 删除同好群 → {ok:true} */
export function deleteGroup(id) {
  return request('DELETE', '/api/v1/cms/groups/' + id)
}

/** 赞助（公开）→ {thanks_text,qr_image_urls:[2]} */
export function getSponsor() {
  return request('GET', '/api/v1/cms/sponsor')
}

/** 更新赞助（admin）{thanks_text,qr_image_urls} */
export function updateSponsor(data) {
  return request('PUT', '/api/v1/cms/sponsor', data)
}

/** 项目声明（公开）→ {intro,github_url,author,license} */
export function getProject() {
  return request('GET', '/api/v1/cms/project')
}

/** 更新项目声明（admin）{intro,github_url,author,license} */
export function updateProject(data) {
  return request('PUT', '/api/v1/cms/project', data)
}
