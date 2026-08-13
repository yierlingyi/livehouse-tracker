/**
 * 乐队资料与 Live 服务（Band Portal）
 * 封装 §4.2 /api/v1/band/* 与公开场地 GET /api/v1/livehouses（经 common/http.js）
 */
import { request } from '../common/http.js'

/* ---------------- 我的资料 / 设置 ---------------- */

/** GET /api/v1/band/me → {account, band:{id,name,qq_bind}, lives:{draft,published}} */
export function getBandMe() {
  return request('GET', '/api/v1/band/me')
}

/** PATCH /api/v1/band/me → {account, band} */
export function patchBandMe(data) {
  return request('PATCH', '/api/v1/band/me', data)
}

/* ---------------- 我的 Live ---------------- */

/**
 * 创建 Live
 * @param {{title, livehouse_id, live_date, start_time, ticket_price, ticket_url, poster_image_url, setlist, action:'save_draft'|'publish'}} data
 * @returns {Promise<{live:Object}>}
 */
export function createLive(data) {
  return request('POST', '/api/v1/band/lives', data)
}

/**
 * 我的 Live 列表
 * @param {'draft'|'published'|''} status 留空返回全部
 * @returns {Promise<{items:Array}>}
 */
export function getBandLives(status) {
  return request('GET', '/api/v1/band/lives', { status: status || '' })
}

/** GET /api/v1/band/lives/:id → {live, setlist} */
export function getLive(id) {
  return request('GET', '/api/v1/band/lives/' + id)
}

/** PATCH /api/v1/band/lives/:id（编辑已发布内容 → 回 draft） */
export function updateLive(id, data) {
  return request('PATCH', '/api/v1/band/lives/' + id, data)
}

/** DELETE /api/v1/band/lives/:id → {ok:true} */
export function deleteLive(id) {
  return request('DELETE', '/api/v1/band/lives/' + id)
}

/** POST /api/v1/band/lives/:id/publish → {live} */
export function publishLive(id) {
  return request('POST', '/api/v1/band/lives/' + id + '/publish')
}

/** POST /api/v1/band/lives/:id/offline → {live} */
export function offlineLive(id) {
  return request('POST', '/api/v1/band/lives/' + id + '/offline')
}

/* ---------------- 场地（公开只读） ---------------- */

/** GET /api/v1/livehouses → {items:[{id,name,intro,image_url}]} */
export function getLivehouses() {
  return request('GET', '/api/v1/livehouses')
}
