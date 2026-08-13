/**
 * 场地 Livehouse Mock（§4.4 公开只读 + 供 venues.mock.js 共享内存态）
 *
 * - GET /api/v1/livehouses      列表 → {items:[{id,name,intro,image_url}]}
 * - GET /api/v1/livehouses/{id} 详情 → {id,name,address,phone,intro,image_url,floorplan_url}
 *
 * LIVEHOUSES 导出给 venues.mock.js 做 admin 增删改（同一内存数组，改动实时可见）。
 */
import { delay, requireAdmin } from './_state.js'

export const LIVEHOUSES = [
  {
    id: 1,
    name: 'Live Garage 涩谷',
    city: 'Tokyo',
    address: '東京都渋谷区宇田川町13-8',
    phone: '03-1234-5678',
    intro: '涩谷地下独立音乐现场，容纳 300 人，音响口碑极佳。',
    image_url: '/static/mock-cover.svg',
    floorplan_url: '/static/mock-cover.svg'
  },
  {
    id: 2,
    name: 'Blue Note 横滨',
    city: 'Tokyo',
    address: '神奈川県横浜市中区山下町200',
    phone: '045-222-3333',
    intro: '爵士与现代摇滚并存的滨水场馆，可容纳 500 人。',
    image_url: '/static/mock-cover.svg',
    floorplan_url: '/static/mock-cover.svg'
  },
  {
    id: 3,
    name: 'Umeda Banana Hall',
    city: 'Osaka',
    address: '大阪府大阪市北区梅田1-1',
    phone: '06-6666-7777',
    intro: '梅田核心区的老牌 Livehouse，常年承办独立与金属演出。',
    image_url: '/static/mock-cover.svg',
    floorplan_url: '/static/mock-cover.svg'
  },
  {
    id: 4,
    name: 'Mao Livehouse 北京',
    city: 'Beijing',
    address: '北京市朝阳区三里屯路19号',
    phone: '010-5555-6666',
    intro: '三里屯地标性音乐现场，国内独立乐队巡演必经之地。',
    image_url: '/static/mock-cover.svg',
    floorplan_url: '/static/mock-cover.svg'
  }
]

let nextVenueId = 100

export default {
  'GET /api/v1/livehouses': async () => {
    await delay()
    return {
      items: LIVEHOUSES.map((v) => ({
        id: v.id,
        name: v.name,
        intro: v.intro,
        image_url: v.image_url
      }))
    }
  },

  'GET /api/v1/livehouses/:id': async ({ params }) => {
    await delay()
    const id = Number(params && params.id)
    const venue = LIVEHOUSES.find((v) => v.id === id)
    if (!venue) throw { code: 'NOT_FOUND', message: '场地不存在', statusCode: 404 }
    return venue
  },

  /* ---------------- Admin 场地增删改（§4.4） ---------------- */
  'POST /api/v1/livehouses': async ({ data, headers }) => {
    await delay()
    requireAdmin(headers)
    const body = data || {}
    if (!body.name) throw { code: 'VALIDATION_ERROR', message: '请填写场地名称' }
    const venue = {
      id: nextVenueId++,
      name: String(body.name).trim(),
      city: String(body.city || 'Tokyo'),
      address: String(body.address || ''),
      phone: String(body.phone || ''),
      intro: String(body.intro || ''),
      image_url: body.image_url || '/static/mock-cover.svg',
      floorplan_url: body.floorplan_url || '/static/mock-cover.svg'
    }
    LIVEHOUSES.push(venue)
    return venue
  },

  'PATCH /api/v1/livehouses/:id': async ({ params, data, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const venue = LIVEHOUSES.find((v) => v.id === id)
    if (!venue) throw { code: 'NOT_FOUND', message: '场地不存在', statusCode: 404 }
    Object.assign(venue, data || {}, { id: venue.id })
    return venue
  },

  'DELETE /api/v1/livehouses/:id': async ({ params, headers }) => {
    await delay()
    requireAdmin(headers)
    const id = Number(params && params.id)
    const idx = LIVEHOUSES.findIndex((v) => v.id === id)
    if (idx === -1) throw { code: 'NOT_FOUND', message: '场地不存在', statusCode: 404 }
    LIVEHOUSES.splice(idx, 1)
    return { ok: true }
  }
}
