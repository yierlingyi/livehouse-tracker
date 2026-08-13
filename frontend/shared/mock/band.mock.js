/**
 * 乐队资料与 Live — Band Portal Mock（§4.2）
 *
 * - GET/PATCH  /api/v1/band/me                 我的资料（band_name / qq_bind / lives 计数）
 * - POST       /api/v1/band/lives              创建 Live（action: save_draft | publish）
 * - GET        /api/v1/band/lives              ?status=draft|published 过滤，仅当前账号
 * - GET        /api/v1/band/lives/:id          详情（含 setlist）
 * - PATCH      /api/v1/band/lives/:id          编辑（已发布内容 → 回 draft，需重新发布）
 * - DELETE     /api/v1/band/lives/:id          删除草稿
 * - POST       /api/v1/band/lives/:id/publish  发布（→ published 直接上线）
 * - POST       /api/v1/band/lives/:id/offline  下架（status+review_status→draft）
 *
 * 数据复用 lives.mock.js 的 LIVES（保持与 /full /sync 一致）：
 *   - 本账号创建的 live 打上 owner 字段（= username），publish 后 review_status='published'
 *     会出现在 /full /sync 投影中（同城时 user-app 可见）。
 *   - offline / publish / 增删改 时调用 bumpLiveVersion() 推进版本，使 /sync 感知。
 * 场地复用 livehouse.mock.js 的 LIVEHOUSES（含 city，决定 live 出现在哪个城市）。
 */
import {
  delay,
  publicAccount,
  requireLogin,
  getAccountByUsername
} from './_state.js'
import { LIVES, bumpLiveVersion } from './lives.mock.js'
import { LIVEHOUSES } from './livehouse.mock.js'

let bandIdSeed = 1000

/** 生成乐队自建 Live 的 id（避开 lives.mock.js 预置的 1xx/2xx/3xx） */
function nextBandId() {
  bandIdSeed += 1
  return bandIdSeed
}

/** 当前登录者必须是乐队账号，否则 403 */
function requireBand(headers) {
  const username = requireLogin(headers)
  const account = getAccountByUsername(username)
  if (!account || account.role !== 'band') {
    throw { code: 'FORBIDDEN', message: '无权限操作', statusCode: 403 }
  }
  return account
}

/** 序列化为乐队端需要的 Live 投影（含 setlist / 场地名 / review_status） */
function serializeBandLive(l) {
  return {
    id: l.id,
    owner: l.owner || '',
    title: l.title,
    livehouse_id: l.livehouse_id,
    livehouse_name: (l.venue && l.venue.name) || '',
    live_date: l.live_date,
    start_time: l.start_time,
    ticket_price: l.ticket_price,
    ticket_url: l.ticket_url || '',
    poster_image_url: l.poster_image_url || '',
    city: l.city || '',
    band_names: l.band_names || [],
    status: l.status || 'announced',
    kind: l.kind || 'normal',
    review_status: l.review_status || 'draft',
    updated_at: l.updated_at,
    setlist: (l.setlist || []).map((s) => ({
      song_title: s.song_title || '',
      band_id: s.band_id != null ? s.band_id : null
    }))
  }
}

/** 当前账号自建的 Live（按 live_date/start_time/id 排序） */
function myLives(username) {
  return LIVES
    .filter((l) => l.owner === username)
    .sort((a, b) => {
      if (a.live_date !== b.live_date) return a.live_date < b.live_date ? -1 : 1
      if (a.start_time !== b.start_time) return a.start_time < b.start_time ? -1 : 1
      return a.id - b.id
    })
}

/** 从 livehouse 快照字段 */
function venueSnapshot(venue) {
  return { id: venue.id, name: venue.name, address: venue.address, phone: venue.phone }
}

/** 校验并归一 POST/PATCH 的字段（setlist 归一、venue 查表；title 可为空，由调用方按需校验） */
function buildLiveFields(data) {
  const body = data || {}
  const title = String(body.title != null ? body.title : '').trim()

  let venue = null
  if (body.livehouse_id != null && body.livehouse_id !== '' && body.livehouse_id !== 0) {
    venue = LIVEHOUSES.find((v) => v.id === Number(body.livehouse_id))
    if (!venue) throw { code: 'VALIDATION_ERROR', message: '所选场地不存在' }
  }

  const setlist = Array.isArray(body.setlist)
    ? body.setlist.map((s) => ({
        song_title: String((s && s.song_title) || '').trim(),
        band_id: (s && s.band_id) != null ? s.band_id : null
      })).filter((s) => s.song_title)
    : []

  return {
    title,
    venue,
    live_date: String(body.live_date || ''),
    start_time: String(body.start_time || ''),
    ticket_price: body.ticket_price != null && body.ticket_price !== '' ? Number(body.ticket_price) : 0,
    ticket_url: String(body.ticket_url || '').trim(),
    poster_image_url: body.poster_image_url || '/static/mock-cover.svg',
    setlist
  }
}

/** 校验发布必需字段 */
function assertPublishReady(fields) {
  if (!fields.title) throw { code: 'VALIDATION_ERROR', message: '请填写 Live 名称' }
  if (!fields.venue) throw { code: 'VALIDATION_ERROR', message: '请选择演出场地' }
  if (!fields.live_date) throw { code: 'VALIDATION_ERROR', message: '请选择演出日期' }
  if (!fields.start_time) throw { code: 'VALIDATION_ERROR', message: '请选择演出时间' }
}

export default {
  /* ---------------- 我的资料 / 设置 ---------------- */
  'GET /api/v1/band/me': async ({ headers }) => {
    await delay()
    const account = requireBand(headers)
    const mine = myLives(account.username)
    return {
      account: publicAccount(account),
      band: { id: account.id, name: account.band_name, qq_bind: account.qq_bind || null },
      lives: {
        draft: mine.filter((l) => l.review_status !== 'published').length,
        published: mine.filter((l) => l.review_status === 'published').length
      }
    }
  },

  'PATCH /api/v1/band/me': async ({ headers, data }) => {
    await delay()
    const account = requireBand(headers)
    const body = data || {}
    if (body.band_name !== undefined) account.band_name = String(body.band_name).trim()
    if (body.qq_bind !== undefined) account.qq_bind = String(body.qq_bind).trim()
    return {
      account: publicAccount(account),
      band: { id: account.id, name: account.band_name, qq_bind: account.qq_bind || null }
    }
  },

  /* ---------------- 我的 Live 创建 / 列表 ---------------- */
  'POST /api/v1/band/lives': async ({ headers, data }) => {
    await delay()
    const account = requireBand(headers)
    const action = (data && data.action) === 'publish' ? 'publish' : 'save_draft'
    const fields = buildLiveFields(data)
    if (!fields.title) throw { code: 'VALIDATION_ERROR', message: '请填写 Live 名称' }
    if (action === 'publish') assertPublishReady(fields)

    const id = nextBandId()
    const live = {
      id,
      owner: account.username,
      livehouse_id: fields.venue ? fields.venue.id : null,
      live_date: fields.live_date,
      start_time: fields.start_time,
      sort_start_time: fields.start_time,
      title: fields.title,
      ticket_price: fields.ticket_price,
      ticket_url: fields.ticket_url || 'https://example.com/tickets/' + id,
      poster_image_url: fields.poster_image_url,
      city: fields.venue ? fields.venue.city : '',
      band_names: [account.band_name || account.username],
      status: 'announced',
      kind: 'normal',
      review_status: action === 'publish' ? 'published' : 'draft',
      updated_at: new Date().toISOString(),
      venue: fields.venue ? venueSnapshot(fields.venue) : null,
      setlist: fields.setlist
    }
    LIVES.push(live)
    bumpLiveVersion()
    return { live: serializeBandLive(live) }
  },

  'GET /api/v1/band/lives': async ({ headers, data }) => {
    await delay()
    const account = requireBand(headers)
    const status = (data && data.status) || ''
    let mine = myLives(account.username)
    if (status === 'published') {
      mine = mine.filter((l) => l.review_status === 'published')
    } else if (status === 'draft') {
      mine = mine.filter((l) => l.review_status !== 'published')
    }
    return { items: mine.map(serializeBandLive) }
  },

  /* ---------------- 我的 Live 详情 ---------------- */
  'GET /api/v1/band/lives/:id': async ({ headers, params }) => {
    await delay()
    const account = requireBand(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id && l.owner === account.username)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    return { live: serializeBandLive(live), setlist: live.setlist || [] }
  },

  /* ---------------- 编辑（已发布 → 回 draft） ---------------- */
  'PATCH /api/v1/band/lives/:id': async ({ headers, params, data }) => {
    await delay()
    const account = requireBand(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id && l.owner === account.username)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }

    const body = data || {}
    const fields = buildLiveFields(body)
    if (body.title !== undefined && fields.title) live.title = fields.title
    if (fields.venue) {
      live.livehouse_id = fields.venue.id
      live.city = fields.venue.city
      live.venue = venueSnapshot(fields.venue)
    }
    if (body.live_date !== undefined) live.live_date = fields.live_date
    if (body.start_time !== undefined) {
      live.start_time = fields.start_time
      live.sort_start_time = fields.start_time
    }
    if (body.ticket_price !== undefined) live.ticket_price = fields.ticket_price
    if (body.ticket_url !== undefined) live.ticket_url = fields.ticket_url
    if (body.poster_image_url !== undefined) live.poster_image_url = fields.poster_image_url
    if (Array.isArray(body.setlist)) live.setlist = fields.setlist

    live.updated_at = new Date().toISOString()
    // 编辑后回 draft（已发布内容需重新发布）
    live.review_status = 'draft'
    bumpLiveVersion()
    return { live: serializeBandLive(live) }
  },

  /* ---------------- 删除草稿 ---------------- */
  'DELETE /api/v1/band/lives/:id': async ({ headers, params }) => {
    await delay()
    const account = requireBand(headers)
    const id = Number(params && params.id)
    const idx = LIVES.findIndex((l) => l.id === id && l.owner === account.username)
    if (idx === -1) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    LIVES.splice(idx, 1)
    bumpLiveVersion()
    return { ok: true }
  },

  /* ---------------- 发布（直接上线 published） ---------------- */
  'POST /api/v1/band/lives/:id/publish': async ({ headers, params }) => {
    await delay()
    const account = requireBand(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id && l.owner === account.username)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    assertPublishReady({
      title: live.title,
      venue: live.venue,
      live_date: live.live_date,
      start_time: live.start_time
    })
    live.review_status = 'published'
    live.status = 'announced'
    live.updated_at = new Date().toISOString()
    bumpLiveVersion()
    return { live: serializeBandLive(live) }
  },

  /* ---------------- 下架（status+review_status→draft，用户端即时隐藏） ---------------- */
  'POST /api/v1/band/lives/:id/offline': async ({ headers, params }) => {
    await delay()
    const account = requireBand(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id && l.owner === account.username)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    live.status = 'draft'
    live.review_status = 'draft'
    live.updated_at = new Date().toISOString()
    bumpLiveVersion()
    return { live: serializeBandLive(live) }
  }
}
