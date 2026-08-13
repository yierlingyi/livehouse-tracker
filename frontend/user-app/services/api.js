/**
 * API 客户端 — 统一经 common/http.js 的 request(method, path, data) 发出请求
 *
 * - /full /sync（V4.4 §9/§10）供 services/sync_engine.js 使用。
 *   导出签名冻结：fetchFullFirstPage / fetchFullNextPage / fetchSync / getErrorAction / API_BASE。
 *   重构前本模块直接 uni.request；现在改走 common/http.js，mock 模式下自动路由到
 *   shared/mock 夹具（VITE_USE_MOCK=true），真实模式下打 VITE_API_BASE。
 * - 新增公开只读接口（演出详情 / 场地 / 乐队 / CMS，§4.4 / §4.6）供页面调用。
 * - 错误响应遵循 {code, message}；网络失败归一 {code:'NETWORK_ERROR', network:true}
 *   （均由 common/http.js 归一，本模块不再自行 uni.request）。
 */
import { request, API_BASE } from '../common/http.js'

// V4.4 §14 错误码 → 客户端动作
const ERROR_ACTIONS = {
  INVALID_PAGE_TOKEN: 'refetch_full',
  FULL_PAGE_TOKEN_EXPIRED: 'refetch_full',
  SYNC_CURSOR_EXPIRED: 'refetch_full',
  INVALID_CURSOR: 'refetch_full',
  RATE_LIMITED: 'backoff_retry',
  SYNC_INVARIANT_BROKEN: 'stop_and_retry'
}

/**
 * 错误码 → 客户端动作
 * @param {string} code
 * @returns {'refetch_full'|'backoff_retry'|'stop_and_retry'|'unknown'}
 */
export function getErrorAction(code) {
  return ERROR_ACTIONS[code] || 'unknown'
}

/* ---------------- /full /sync（V4.4，sync_engine 依赖，签名勿改） ---------------- */

/**
 * /full 第一页（V4.4 §9）
 * @param {string} city
 * @param {number} [pageSize=500]
 * @returns {Promise<{data:Array, scope:Object, snapshot_cursor:string, has_more:boolean, next_token:string|null}>}
 */
export function fetchFullFirstPage(city, pageSize = 500) {
  return request('GET', '/api/v1/lives/full', { city, page_size: pageSize })
}

/**
 * /full 后续页
 * @param {string} nextToken 签名 keyset token
 * @param {number} [pageSize=500]
 * @returns {Promise<{data:Array, scope:Object, snapshot_cursor:string, has_more:boolean, next_token:string|null}>}
 */
export function fetchFullNextPage(nextToken, pageSize = 500) {
  return request('GET', '/api/v1/lives/full', { page_token: nextToken, page_size: pageSize })
}

/**
 * /sync 增量回放（V4.4 §10）
 * @param {string} city
 * @param {string} scopeStart scope_start_date
 * @param {string} scopeEnd scope_end_date
 * @param {number|string} since 客户端当前 cursor
 * @param {number} [limit=1000]
 * @returns {Promise<{data:Array, deletes:Array<number>, cursor:number, has_more:boolean}>}
 */
export function fetchSync(city, scopeStart, scopeEnd, since, limit = 1000) {
  return request('GET', '/api/v1/lives/sync', {
    city,
    scope_start_date: scopeStart,
    scope_end_date: scopeEnd,
    since,
    limit
  })
}

/* ---------------- 公开只读接口（§4.4 / §4.6） ---------------- */

/** 演出详情（含场地+setlist+海报）→ {live, venue, setlist, poster_image_url} */
export function fetchLiveDetail(id) {
  return request('GET', '/api/v1/lives/' + id)
}

/** 场地列表 → {items:[{id,name,intro,image_url}]} */
export function fetchLivehouses() {
  return request('GET', '/api/v1/livehouses')
}

/** 场地详情 → {id,name,address,phone,intro,image_url,floorplan_url} */
export function fetchLivehouseDetail(id) {
  return request('GET', '/api/v1/livehouses/' + id)
}

/** 乐队列表 → {items:[{id,name,cover_url}]} */
export function fetchBands() {
  return request('GET', '/api/v1/bands')
}

/** 乐队详情 → {id,name,intro,cover_url,members:[{name,role?}]} */
export function fetchBandDetail(id) {
  return request('GET', '/api/v1/bands/' + id)
}

/** 同好群列表 → {items:[{id,city,platform,group_id}]} */
export function fetchCommunityGroups() {
  return request('GET', '/api/v1/cms/groups')
}

/** 赞助 → {thanks_text, qr_image_urls:[2]} */
export function fetchSponsor() {
  return request('GET', '/api/v1/cms/sponsor')
}

/** 项目声明 → {intro, github_url, author, license} */
export function fetchProject() {
  return request('GET', '/api/v1/cms/project')
}

export { API_BASE }
