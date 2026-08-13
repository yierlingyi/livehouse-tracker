/**
 * Admin 管理 Mock（§4.5）
 *
 * - GET   /api/v1/admin/lives?kind=all|normal|coop  所有 Live（含非 published）
 * - PATCH /api/v1/admin/lives/:id                   强制编辑
 * - POST  /api/v1/admin/lives/:id/offline           强制下架（status+review_status→draft，用户端即时隐藏）
 * - GET   /api/v1/admin/bands?filter=pending|all    乐队账号库 / 审核队列
 * - GET   /api/v1/admin/bands/:id                   账号详情
 * - PATCH /api/v1/admin/bands/:id                   通过/拒绝/改资料
 * - DELETE /api/v1/admin/bands/:id                  删除账号
 *
 * 全部要求管理员鉴权（requireAdmin）。
 */
import {
  delay,
  requireAdmin,
  ACCOUNTS,
  getAccountByUsername,
  publicAccount,
  listAccounts,
  removeAccount,
  updateAccount
} from './_state.js'
import { LIVES, bumpLiveVersion, markLivePublished } from './lives.mock.js'
import { LIVEHOUSES } from './livehouse.mock.js'

function adminLiveItem(l) {
  return {
    id: l.id,
    title: l.title,
    live_date: l.live_date,
    kind: l.kind || 'normal',
    review_status: l.review_status,
    status: l.status,
    band_names: l.band_names || [],
    city: l.city,
    livehouse_id: l.livehouse_id
  }
}

/** 编辑页详情投影（live 复用乐队端字段，与后端 serialize_band_live 对齐） */
function adminLiveDetail(l) {
  const venue = LIVEHOUSES.find((v) => v.id === Number(l.livehouse_id)) || null
  return {
    live: {
      id: l.id,
      owner: l.owner || '',
      title: l.title,
      livehouse_id: l.livehouse_id,
      livehouse_name: (l.venue && l.venue.name) || (venue && venue.name) || '',
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
      setlist: l.setlist || []
    },
    venue: venue || null,
    setlist: l.setlist || [],
    poster_image_url: l.poster_image_url || ''
  }
}

function bandItem(a) {
  return {
    id: a.id,
    username: a.username,
    band_name: a.band_name,
    status: a.status,
    created_at: a.created_at
  }
}

export default {
  /* ---------------- 所有 Live（all/normal/coop 过滤） ---------------- */
  'GET /api/v1/admin/lives': async ({ headers, data }) => {
    await delay()
    requireAdmin(headers)
    const kind = String((data && data.kind) || 'all')
    const items = LIVES
      .filter((l) => {
        if (kind === 'all') return true
        if (kind === 'normal') return (l.kind || 'normal') !== 'coop'
        if (kind === 'coop') return (l.kind || 'normal') === 'coop'
        return true
      })
      .map(adminLiveItem)
    return { items }
  },

  /* ---------------- 编辑页详情（任意 review_status，强制编辑不再 404） ---------------- */
  'GET /api/v1/admin/lives/:id': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    return adminLiveDetail(live)
  },

  /* ---------------- 强制编辑任意 Live ---------------- */
  'PATCH /api/v1/admin/lives/:id': async ({ params, data, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    const body = data || {}
    if (body.title != null) live.title = String(body.title)
    if (body.live_date != null) live.live_date = body.live_date
    if (body.start_time != null) { live.start_time = body.start_time; live.sort_start_time = body.start_time }
    if (body.ticket_price != null) live.ticket_price = body.ticket_price
    if (body.ticket_url != null) live.ticket_url = body.ticket_url
    if (body.poster_image_url != null) live.poster_image_url = body.poster_image_url
    if (body.livehouse_id != null) {
      live.livehouse_id = Number(body.livehouse_id)
      const venue = LIVEHOUSES.find((v) => v.id === live.livehouse_id)
      if (venue) {
        live.city = venue.city
        live.venue = { id: venue.id, name: venue.name, address: venue.address, phone: venue.phone }
      }
    }
    if (Array.isArray(body.band_names)) live.band_names = body.band_names
    if (Array.isArray(body.setlist)) live.setlist = body.setlist
    if (body.review_status === 'published') {
      live.review_status = 'published'
      live.status = 'announced'
      markLivePublished(live)
    } else if (body.review_status === 'draft') {
      live.review_status = 'draft'
    }
    live.updated_at = new Date().toISOString()
    bumpLiveVersion()
    return { live: adminLiveItem(live) }
  },

  /* ---------------- 强制下架：status + review_status → draft ---------------- */
  'POST /api/v1/admin/lives/:id/offline': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const live = LIVES.find((l) => l.id === id)
    if (!live) throw { code: 'NOT_FOUND', message: '演出不存在', statusCode: 404 }
    live.status = 'draft'
    live.review_status = 'draft'
    live.updated_at = new Date().toISOString()
    bumpLiveVersion()
    return { live: adminLiveItem(live) }
  },

  /* ---------------- 乐队账号库 / 审核队列 ---------------- */
  'GET /api/v1/admin/bands': async ({ headers, data }) => {
    await delay()
    requireAdmin(headers)
    const filter = String((data && data.filter) || 'all')
    const items = listAccounts()
      .filter((a) => a.role === 'band')
      .filter((a) => (filter === 'pending' ? a.status === 'pending' : true))
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
      .map(bandItem)
    return { items }
  },

  /* ---------------- 账号详情 ---------------- */
  'GET /api/v1/admin/bands/:id': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const account = listAccounts().find((a) => a.role === 'band' && a.id === id)
    if (!account) throw { code: 'NOT_FOUND', message: '账号不存在', statusCode: 404 }
    return {
      account: publicAccount(account),
      band: { id: account.id, band_name: account.band_name, intro: account.intro || '' }
    }
  },

  /* ---------------- 通过 / 拒绝 / 改资料 ---------------- */
  'PATCH /api/v1/admin/bands/:id': async ({ params, data, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const account = listAccounts().find((a) => a.role === 'band' && a.id === id)
    if (!account) throw { code: 'NOT_FOUND', message: '账号不存在', statusCode: 404 }
    const body = data || {}
    if (body.action === 'approve') account.status = 'active'
    else if (body.action === 'reject') account.status = 'rejected'
    if (body.band_name != null) account.band_name = String(body.band_name)
    if (body.intro != null) account.intro = String(body.intro)
    return {
      account: publicAccount(account),
      band: { id: account.id, band_name: account.band_name, intro: account.intro || '' }
    }
  },

  /* ---------------- 删除账号 ---------------- */
  'DELETE /api/v1/admin/bands/:id': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const account = listAccounts().find((a) => a.role === 'band' && a.id === id)
    if (!account) throw { code: 'NOT_FOUND', message: '账号不存在', statusCode: 404 }
    removeAccount(account.username)
    return { ok: true }
  }
}
