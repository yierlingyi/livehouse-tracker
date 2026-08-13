/**
 * 内容管理 CMS Mock（§4.6）
 *
 * - 同好群：GET /api/v1/cms/groups（公开）；POST/PATCH/DELETE（admin）
 * - 赞助：  GET /api/v1/cms/sponsor（公开）；PUT（admin）
 * - 项目：  GET /api/v1/cms/project（公开）；PUT（admin）
 */
import { delay, requireAdmin } from './_state.js'

export const CMS_GROUPS = [
  { id: 1, city: 'Tokyo', platform: 'wechat', group_id: 'tokyo_live_01' },
  { id: 2, city: 'Tokyo', platform: 'qq', group_id: '88012345' },
  { id: 3, city: 'Osaka', platform: 'wechat', group_id: 'osaka_live_02' },
  { id: 4, city: 'Beijing', platform: 'wechat', group_id: 'bj_rock_club' },
  { id: 5, city: 'Beijing', platform: 'qq', group_id: '66098765' }
]

export const CMS_SPONSOR = {
  thanks_text: '感谢每一位支持独立音乐现场的朋友。\n你的每一份支持，都是舞台灯光亮起的原因。',
  qr_image_urls: ['/static/mock-cover.svg', '/static/mock-cover.svg']
}

export const CMS_PROJECT = {
  intro: '乐队演出平台 — 面向乐迷、乐队与 Livehouse 的一站式演出信息与协同管理平台。\n本项目为课程/社区开源项目，欢迎参与。',
  github_url: 'https://github.com/example/band-live-platform',
  author: 'G0 Shared Foundation Team',
  license: 'MIT'
}

let nextGroupId = 100

export default {
  /* ---------------- 同好群 ---------------- */
  'GET /api/v1/cms/groups': async () => {
    await delay()
    return { items: CMS_GROUPS.map((g) => ({ ...g })) }
  },

  'POST /api/v1/cms/groups': async ({ data, headers }) => {
    await delay()
    requireAdmin(headers)
    const body = data || {}
    if (!body.city || !body.platform || !body.group_id) {
      throw { code: 'VALIDATION_ERROR', message: '请填写城市、平台与群号' }
    }
    const group = {
      id: nextGroupId++,
      city: String(body.city).trim(),
      platform: body.platform === 'qq' ? 'qq' : 'wechat',
      group_id: String(body.group_id).trim()
    }
    CMS_GROUPS.push(group)
    return group
  },

  'PATCH /api/v1/cms/groups/:id': async ({ params, data, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const group = CMS_GROUPS.find((g) => g.id === id)
    if (!group) throw { code: 'NOT_FOUND', message: '群组不存在', statusCode: 404 }
    Object.assign(group, data || {}, { id: group.id })
    return group
  },

  'DELETE /api/v1/cms/groups/:id': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const idx = CMS_GROUPS.findIndex((g) => g.id === id)
    if (idx === -1) throw { code: 'NOT_FOUND', message: '群组不存在', statusCode: 404 }
    CMS_GROUPS.splice(idx, 1)
    return { ok: true }
  },

  /* ---------------- 赞助 ---------------- */
  'GET /api/v1/cms/sponsor': async () => {
    await delay()
    return { thanks_text: CMS_SPONSOR.thanks_text, qr_image_urls: CMS_SPONSOR.qr_image_urls.slice() }
  },

  'PUT /api/v1/cms/sponsor': async ({ data, headers }) => {
    await delay()
    requireAdmin(headers)
    const body = data || {}
    if (typeof body.thanks_text === 'string') CMS_SPONSOR.thanks_text = body.thanks_text
    if (Array.isArray(body.qr_image_urls)) {
      CMS_SPONSOR.qr_image_urls = body.qr_image_urls.slice(0, 2)
    }
    return { thanks_text: CMS_SPONSOR.thanks_text, qr_image_urls: CMS_SPONSOR.qr_image_urls.slice() }
  },

  /* ---------------- 项目声明 ---------------- */
  'GET /api/v1/cms/project': async () => {
    await delay()
    return { ...CMS_PROJECT }
  },

  'PUT /api/v1/cms/project': async ({ data, headers }) => {
    await delay()
    requireAdmin(headers)
    const body = data || {}
    Object.assign(CMS_PROJECT, {
      intro: body.intro != null ? String(body.intro) : CMS_PROJECT.intro,
      github_url: body.github_url != null ? String(body.github_url) : CMS_PROJECT.github_url,
      author: body.author != null ? String(body.author) : CMS_PROJECT.author,
      license: body.license != null ? String(body.license) : CMS_PROJECT.license
    })
    return { ...CMS_PROJECT }
  }
}
