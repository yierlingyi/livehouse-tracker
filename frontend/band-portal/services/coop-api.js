/**
 * 拼盘（Co-op）API 封装（契约 §4.3 + §4.1 账号校验 + §4.4 场地只读）
 *
 * - 全部接口走 common/http.js 的 request（mock 模式自动路由到 shared/mock）
 * - 登录态由 http.js 自动附加 Authorization；当前账号经 storage.getAccount()
 * - 状态机：invited → agreed / rejected / exit_requested → removed
 *
 * 说明（invite_id 解析）：
 * 列表接口（GET /coop/events、GET /coop/events/invites）不返回 invite_id，
 * 因此在执行「仅本人」的动作时（accept/reject/songs/revoke/exit-request）允许
 * 不传 invite_id —— 内部通过 GET /coop/events/{id} 详情解析当前账号的 invite_id；
 * approve-exit 需要目标账号的 invite_id，可传 username 让内部解析。
 */
import { request } from '../common/http.js'
import { getAccount } from '../common/storage.js'

/** 过滤并规整曲目数组 → [{song_title}]，剔除空行 */
export function cleanSongs(songs) {
  return (songs || [])
    .map((s) => {
      const title = (s && typeof s === 'object' ? s.song_title : s) || ''
      return String(title).trim()
    })
    .filter(Boolean)
    .map((song_title) => ({ song_title }))
}

/** 深拷贝曲目数组（保留 band_id 占位） */
export function cloneSongs(songs) {
  return (songs || []).map((s) => ({
    song_title: (s && s.song_title) || '',
    band_id: (s && s.band_id) != null ? s.band_id : null
  }))
}

/** 判断两份曲目内容是否一致（仅比较歌名） */
export function sameSongs(a, b) {
  a = a || []
  b = b || []
  if (a.length !== b.length) return false
  return a.every((s, i) => String((s && s.song_title) || '') === String((b[i] && b[i].song_title) || ''))
}

/** 当前登录账号 username（可能为空串） */
export function currentUsername() {
  const account = getAccount()
  return (account && account.username) || ''
}

/* ---------------- 基础 CRUD ---------------- */

/** 创建拼盘（可存草稿；action: 'save_draft' | 'publish'） */
export function createEvent(payload) {
  return request('POST', '/api/v1/coop/events', payload)
}

/** 我关联的所有拼盘 + 实时状态 */
export function listEvents() {
  return request('GET', '/api/v1/coop/events')
}

/** 拼盘详情（含 participants + invite_id + 聚合计数） */
export function getEventDetail(eventId) {
  return request('GET', '/api/v1/coop/events/' + eventId)
}

/** 发起方编辑 / 存草稿 */
export function patchEvent(eventId, payload) {
  return request('PATCH', '/api/v1/coop/events/' + eventId, payload)
}

/** 发起方删草稿 */
export function deleteEvent(eventId) {
  return request('DELETE', '/api/v1/coop/events/' + eventId)
}

/** 追加邀请（发起方） */
export function addInvite(eventId, username, songs) {
  return request('POST', '/api/v1/coop/events/' + eventId + '/invites', {
    username,
    songs: cleanSongs(songs)
  })
}

/** 我收到的邀请 */
export function listInvites() {
  return request('GET', '/api/v1/coop/events/invites')
}

/* ---------------- 状态动作（invite_id 可省略，内部自动解析当前账号） ---------------- */

async function resolveMyInviteId(eventId) {
  const username = currentUsername()
  if (!username) return null
  return resolveInviteId(eventId, username)
}

/** 从详情 participants 解析指定账号的 invite_id */
export async function resolveInviteId(eventId, username) {
  if (!eventId || !username) return null
  const detail = await getEventDetail(eventId)
  const p = (detail && (detail.participants || []).find((x) => x.username === username)) || null
  return p ? p.invite_id : null
}

/** 同意（可带曲目） */
export async function acceptInvite(eventId, inviteId, songs) {
  const id = inviteId || (await resolveMyInviteId(eventId))
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  const payload = songs == null ? {} : { songs: cleanSongs(songs) }
  return request('POST', `/api/v1/coop/events/${eventId}/invites/${id}/accept`, payload)
}

/** 拒绝 */
export async function rejectInvite(eventId, inviteId) {
  const id = inviteId || (await resolveMyInviteId(eventId))
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  return request('POST', `/api/v1/coop/events/${eventId}/invites/${id}/reject`)
}

/** 改本队曲目（仅本人） */
export async function updateSongs(eventId, inviteId, songs) {
  const id = inviteId || (await resolveMyInviteId(eventId))
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  return request('PATCH', `/api/v1/coop/events/${eventId}/invites/${id}/songs`, { songs: cleanSongs(songs) })
}

/** 撤销同意（→ invited） */
export async function revokeAgree(eventId, inviteId) {
  const id = inviteId || (await resolveMyInviteId(eventId))
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  return request('POST', `/api/v1/coop/events/${eventId}/invites/${id}/revoke`)
}

/** 申请退出（→ exit_requested） */
export async function exitRequest(eventId, inviteId) {
  const id = inviteId || (await resolveMyInviteId(eventId))
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  return request('POST', `/api/v1/coop/events/${eventId}/invites/${id}/exit-request`)
}

/** 发起方审批退出（→ removed）；inviteId 省略时按 username 解析目标邀请 */
export async function approveExit(eventId, inviteId, username) {
  let id = inviteId
  if (id == null) {
    id = username ? await resolveInviteId(eventId, username) : await resolveMyInviteId(eventId)
  }
  if (id == null) throw { code: 'INVITE_NOT_FOUND', message: '未找到对应邀请', statusCode: 404 }
  return request('POST', `/api/v1/coop/events/${eventId}/invites/${id}/approve-exit`)
}

/** 发起方下架拼盘 */
export function offlineEvent(eventId) {
  return request('POST', `/api/v1/coop/events/${eventId}/offline`)
}

/* ---------------- 配套只读 ---------------- */

/** 拼盘邀请实时校验账号（仅 active 乐队） */
export function accountExists(username) {
  return request('GET', '/api/v1/accounts/' + encodeURIComponent(String(username || '').trim()) + '/exists')
}

/** 场地列表（创建拼盘下拉用，公开只读） */
export function listLivehouses() {
  return request('GET', '/api/v1/livehouses')
}

export default {
  cleanSongs,
  cloneSongs,
  sameSongs,
  currentUsername,
  createEvent,
  listEvents,
  getEventDetail,
  patchEvent,
  deleteEvent,
  addInvite,
  listInvites,
  resolveInviteId,
  acceptInvite,
  rejectInvite,
  updateSongs,
  revokeAgree,
  exitRequest,
  approveExit,
  offlineEvent,
  accountExists,
  listLivehouses
}
