/**
 * 拼盘 Co-op Mock（§4.3）
 *
 * 演示数据：预置拼盘已随测试账号清理移除；业务拼盘由运行时
 * POST /api/v1/coop/events 创建，状态机不变。
 *
 * 状态机：invited → agreed / rejected / exit_requested → removed
 */
import { delay, requireLogin, getAccountByUsername } from './_state.js'
import { LIVES, bumpLiveVersion, markLivePublished } from './lives.mock.js'
import { LIVEHOUSES } from './livehouse.mock.js'

let nextEventId = 100
let nextInviteId = 1000
// 拼盘在 LIVES 中的 id 独立段（5001+），避免与 lives.mock.js 预置 1xx/2xx/3xx 冲突
let nextCoopLiveId = 5000

function makeParticipant(username, status, songs, is_initiator) {
  const account = getAccountByUsername(username) || { band_name: username }
  nextInviteId += 1
  return {
    invite_id: nextInviteId,
    username,
    band_name: account.band_name || username,
    invite_status: status,
    songs: songs || [],
    is_initiator: !!is_initiator
  }
}

function makeEvent(o) {
  nextEventId = Math.max(nextEventId, o.id)
  return {
    id: o.id,
    live_id: o.live_id || null,
    title: o.title,
    livehouse_id: o.livehouse_id,
    venue_name: o.venue_name || 'Live Garage 涩谷',
    venue_address: o.venue_address || '東京都渋谷区宇田川町13-8',
    live_date: o.live_date,
    start_time: o.start_time,
    ticket_price: o.ticket_price,
    poster_image_url: o.poster_image_url || '/static/mock-cover.svg',
    initiator_username: o.initiator_username,
    status: o.status || 'draft',
    participants: o.participants
  }
}

export const COOP_EVENTS = []

function computeCounts(event) {
  const ps = event.participants || []
  let total = ps.length
  let agreed = 0
  let rejected = 0
  let exit_requested = 0
  for (const p of ps) {
    if (p.invite_status === 'agreed') agreed += 1
    else if (p.invite_status === 'rejected') rejected += 1
    else if (p.invite_status === 'exit_requested') exit_requested += 1
  }
  return { total_count: total, agreed_count: agreed, rejected_count: rejected, exit_requested_count: exit_requested }
}

function findEvent(id) {
  const event = COOP_EVENTS.find((e) => e.id === id)
  if (!event) throw { code: 'NOT_FOUND', message: '拼盘不存在', statusCode: 404 }
  return event
}

function findParticipant(event, username) {
  return (event.participants || []).find((p) => p.username === username) || null
}

function publicEvent(event) {
  return {
    id: event.id,
    live_id: event.live_id || null,
    title: event.title,
    live_date: event.live_date,
    status: event.status,
    initiator_band: getAccountByUsername(event.initiator_username)?.band_name || event.initiator_username,
    livehouse_id: event.livehouse_id,
    venue_name: event.venue_name,
    venue_address: event.venue_address,
    start_time: event.start_time,
    ticket_price: event.ticket_price,
    poster_image_url: event.poster_image_url
  }
}

/** 拼盘已同意乐队的阵容名单（投影到 LIVES.band_names） */
function liveBandNames(event) {
  return (event.participants || [])
    .filter((p) => p.invite_status === 'agreed')
    .map((p) => getAccountByUsername(p.username)?.band_name || p.username)
}

/** 拼盘已同意乐队的曲目合集（投影到 LIVES.setlist） */
function liveSetlist(event) {
  const out = []
  for (const p of event.participants || []) {
    if (p.invite_status !== 'agreed') continue
    for (const s of p.songs || []) {
      if (s && String(s.song_title || '').trim()) {
        out.push({ song_title: String(s.song_title).trim(), band_id: null })
      }
    }
  }
  return out
}

/**
 * 把拼盘事件同步为一个 kind='coop' 的 LIVES 条目（id 独立自 5001）。
 * 发布态 → review_status='published' 进 /full；草稿/下架 → 'draft'，从 /full 隐藏，
 * /sync 据此产出 delete。本函数不推进 VERSION，由调用方在真实数据变更时负责。
 */
function ensureCoopLive(event) {
  if (!event.live_id) {
    nextCoopLiveId += 1
    event.live_id = nextCoopLiveId
  }
  const published = event.status === 'published'
  const venue = LIVEHOUSES.find((v) => v.id === Number(event.livehouse_id)) || null
  let live = LIVES.find((l) => l.id === event.live_id)
  if (!live) {
    live = {
      id: event.live_id,
      owner: event.initiator_username,
      livehouse_id: event.livehouse_id || null,
      live_date: event.live_date || '',
      start_time: event.start_time || '',
      sort_start_time: event.start_time || '',
      title: event.title || '',
      ticket_price: Number(event.ticket_price) || 0,
      ticket_url: 'https://example.com/tickets/' + event.live_id,
      poster_image_url: event.poster_image_url || '/static/mock-cover.svg',
      city: venue ? venue.city : 'Tokyo',
      band_names: liveBandNames(event),
      status: published ? 'announced' : 'draft',
      kind: 'coop',
      review_status: published ? 'published' : 'draft',
      updated_at: new Date().toISOString(),
      venue: venue ? { id: venue.id, name: venue.name, address: venue.address, phone: venue.phone } : null,
      setlist: liveSetlist(event)
    }
    LIVES.push(live)
  } else {
    if (event.title != null) live.title = event.title
    if (event.live_date != null) live.live_date = event.live_date
    if (event.start_time != null) { live.start_time = event.start_time; live.sort_start_time = event.start_time }
    if (event.ticket_price != null) live.ticket_price = Number(event.ticket_price) || 0
    if (event.livehouse_id != null) {
      live.livehouse_id = event.livehouse_id
      if (venue) {
        live.city = venue.city
        live.venue = { id: venue.id, name: venue.name, address: venue.address, phone: venue.phone }
      }
    }
    if (event.poster_image_url) live.poster_image_url = event.poster_image_url
    live.band_names = liveBandNames(event)
    live.setlist = liveSetlist(event)
    live.status = published ? 'announced' : 'draft'
    live.review_status = published ? 'published' : 'draft'
    live.updated_at = new Date().toISOString()
  }
  if (published) markLivePublished(live)
  return live
}

// 种子拼盘与 LIVES 联动（均为草稿态，不进 /full、不产生 delete）
COOP_EVENTS.forEach(ensureCoopLive)

export default {
  /* ---------------- 创建拼盘（可存草稿 / 直接发布） ---------------- */
  'POST /api/v1/coop/events': async ({ data, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const body = data || {}
    if (!body.title) throw { code: 'VALIDATION_ERROR', message: '请填写拼盘名称' }
    const action = body.action === 'publish' ? 'publish' : 'save_draft'
    if (action === 'publish') {
      if (!body.livehouse_id) throw { code: 'VALIDATION_ERROR', message: '请选择场地' }
      if (!body.live_date) throw { code: 'VALIDATION_ERROR', message: '请选择演出日期' }
      if (!body.start_time) throw { code: 'VALIDATION_ERROR', message: '请选择演出时间' }
    }
    const participants = [makeParticipant(username, 'agreed', body.own_songs || [], true)]
    // create 同时落地受邀乐队（后端 safe_coop_create_event 亦处理 invites）
    if (Array.isArray(body.invites)) {
      for (const inv of body.invites) {
        const target = String((inv && inv.username) || '').trim()
        const account = getAccountByUsername(target)
        if (!account || account.role !== 'band' || account.status !== 'active') {
          throw { code: 'NOT_FOUND', message: '乐队账号不存在：' + target, statusCode: 404 }
        }
        participants.push(makeParticipant(target, 'invited', (inv && inv.songs) || [], false))
      }
    }
    const event = makeEvent({
      id: nextEventId + 1,
      title: String(body.title),
      livehouse_id: body.livehouse_id || 1,
      live_date: body.live_date || '',
      start_time: body.start_time || '20:00',
      ticket_price: body.ticket_price || 0,
      poster_image_url: body.poster_image_url || '/static/mock-cover.svg',
      initiator_username: username,
      status: action === 'publish' ? 'published' : 'draft',
      participants
    })
    COOP_EVENTS.push(event)
    ensureCoopLive(event)
    bumpLiveVersion()
    return publicEvent(event)
  },

  /* ---------------- 我关联的拼盘 + 实时状态 ---------------- */
  'GET /api/v1/coop/events': async ({ headers }) => {
    await delay()
    const username = requireLogin(headers)
    const items = COOP_EVENTS
      .filter((e) => (e.participants || []).some((p) => p.username === username))
      .map((e) => ({
        id: e.id,
        title: e.title,
        live_date: e.live_date,
        status: e.status,
        invites: (e.participants || []).map((p) => ({
          band_name: p.band_name,
          username: p.username,
          invite_status: p.invite_status,
          songs: p.songs || [],
          is_me: p.username === username,
          is_initiator: p.is_initiator
        }))
      }))
    return { items }
  },

  /* ---------------- 我收到的邀请（字面路由，必须先于 :id 注册，避免被 :id 吞掉） ---------------- */
  'GET /api/v1/coop/events/invites': async ({ headers }) => {
    await delay()
    const username = requireLogin(headers)
    const items = []
    for (const e of COOP_EVENTS) {
      const me = findParticipant(e, username)
      if (!me || me.is_initiator) continue
      if (me.invite_status !== 'invited' && me.invite_status !== 'agreed') continue
      items.push({
        event_id: e.id,
        initiator_band: getAccountByUsername(e.initiator_username)?.band_name || e.initiator_username,
        title: e.title,
        live_date: e.live_date,
        venue_address: e.venue_address,
        assigned_songs: me.songs || [],
        invite_status: me.invite_status
      })
    }
    return { items }
  },

  /* ---------------- 拼盘详情 ---------------- */
  'GET /api/v1/coop/events/:id': async ({ params, headers }) => {
    await delay()
    requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    return Object.assign(publicEvent(event), {
      participants: (event.participants || []).map((p) => ({ ...p })),
      ...computeCounts(event)
    })
  },

  /* ---------------- 发起方编辑 / 存草稿 / 发布 ---------------- */
  'PATCH /api/v1/coop/events/:id': async ({ params, data, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    if (event.initiator_username !== username) throw { code: 'FORBIDDEN', message: '仅发起方可编辑', statusCode: 403 }
    const body = data || {}
    if (body.title != null) event.title = String(body.title)
    if (body.live_date != null) event.live_date = body.live_date
    if (body.livehouse_id != null) event.livehouse_id = body.livehouse_id
    if (body.start_time != null) event.start_time = body.start_time
    if (body.ticket_price != null) event.ticket_price = body.ticket_price
    if (body.poster_image_url != null) event.poster_image_url = body.poster_image_url
    if (body.action === 'publish') event.status = 'published'
    ensureCoopLive(event)
    bumpLiveVersion()
    return publicEvent(event)
  },

  /* ---------------- 发起方删草稿 ---------------- */
  'DELETE /api/v1/coop/events/:id': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    if (event.initiator_username !== username) throw { code: 'FORBIDDEN', message: '仅发起方可删除', statusCode: 403 }
    const idx = COOP_EVENTS.findIndex((e) => e.id === event.id)
    COOP_EVENTS.splice(idx, 1)
    if (event.live_id) {
      const li = LIVES.findIndex((l) => l.id === event.live_id)
      if (li !== -1) LIVES.splice(li, 1)
    }
    bumpLiveVersion()
    return { ok: true }
  },

  /* ---------------- 追加邀请 ---------------- */
  'POST /api/v1/coop/events/:id/invites': async ({ params, data, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    if (event.initiator_username !== username) throw { code: 'FORBIDDEN', message: '仅发起方可邀请', statusCode: 403 }
    const body = data || {}
    const target = String(body.username || '').trim()
    const account = getAccountByUsername(target)
    if (!account || account.role !== 'band' || account.status !== 'active') {
      throw { code: 'NOT_FOUND', message: '乐队账号不存在', statusCode: 404 }
    }
    event.participants.push(makeParticipant(target, 'invited', body.songs || [], false))
    return publicEvent(event)
  },

  /* ---------------- 同意（可带曲目） ---------------- */
  'POST /api/v1/coop/events/:id/invites/:invite_id/accept': async ({ params, data, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    const me = findParticipant(event, username)
    if (!me) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    if (me.is_initiator) throw { code: 'FORBIDDEN', message: '发起方无需接受', statusCode: 403 }
    me.invite_status = 'agreed'
    if (data && Array.isArray(data.songs)) me.songs = data.songs
    // 阵容变化（同意方计入 band_names/setlist），同步 LIVES
    ensureCoopLive(event)
    bumpLiveVersion()
    return { invite: { ...me } }
  },

  /* ---------------- 拒绝 ---------------- */
  'POST /api/v1/coop/events/:id/invites/:invite_id/reject': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    const me = findParticipant(event, username)
    if (!me) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    me.invite_status = 'rejected'
    return { invite: { ...me } }
  },

  /* ---------------- 改本队曲目（仅本人） ---------------- */
  'PATCH /api/v1/coop/events/:id/invites/:invite_id/songs': async ({ params, data, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    const me = findParticipant(event, username)
    if (!me) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    if (me.is_initiator) throw { code: 'FORBIDDEN', message: '发起方曲目不可在此修改', statusCode: 403 }
    me.songs = (data && Array.isArray(data.songs)) ? data.songs : []
    return { invite: { ...me } }
  },

  /* ---------------- 撤销同意 ---------------- */
  'POST /api/v1/coop/events/:id/invites/:invite_id/revoke': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    const me = findParticipant(event, username)
    if (!me) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    me.invite_status = 'invited'
    return { invite: { ...me } }
  },

  /* ---------------- 申请退出 ---------------- */
  'POST /api/v1/coop/events/:id/invites/:invite_id/exit-request': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    const me = findParticipant(event, username)
    if (!me) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    me.invite_status = 'exit_requested'
    return { invite: { ...me } }
  },

  /* ---------------- 发起方审批退出（→removed） ---------------- */
  'POST /api/v1/coop/events/:id/invites/:invite_id/approve-exit': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    if (event.initiator_username !== username) throw { code: 'FORBIDDEN', message: '仅发起方可审批退出', statusCode: 403 }
    const target = (event.participants || []).find((p) => String(p.invite_id) === String(params && params.invite_id))
    if (!target) throw { code: 'NOT_FOUND', message: '邀请不存在', statusCode: 404 }
    target.invite_status = 'removed'
    return { invite: { ...target } }
  },

  /* ---------------- 发起方下架拼盘（coop_events.status + LIVES 联动回草稿） ---------------- */
  'POST /api/v1/coop/events/:id/offline': async ({ params, headers }) => {
    await delay()
    const username = requireLogin(headers)
    const event = findEvent(Number(params && params.id))
    if (event.initiator_username !== username) throw { code: 'FORBIDDEN', message: '仅发起方可下架', statusCode: 403 }
    event.status = 'draft'
    ensureCoopLive(event)
    bumpLiveVersion()
    return publicEvent(event)
  }
}
