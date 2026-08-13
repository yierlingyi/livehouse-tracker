/**
 * 乐队资料 Mock（§4.4 公开只读）
 *
 * - GET /api/v1/bands      列表 → {items:[{id,name,cover_url}]}
 * - GET /api/v1/bands/{id} 详情 → {id,name,intro,cover_url,members:[{name,role?}]}
 *
 * 注意：乐队资料是独立实体（后端 band_profiles），不展示地址/电话。
 * 列表/详情均为公开只读，无需鉴权。
 */
import { delay } from './_state.js'

// 业务乐队资料（公开只读）。预置资料随测试账号清理移除，当前为空；
// 运行时可通过 band.mock.js 的 /api/v1/band/me 等接口维护，列表保持公开只读。
export const BAND_PROFILES = []

let nextBandId = 100

export default {
  'GET /api/v1/bands': async () => {
    await delay()
    return {
      items: BAND_PROFILES.map((b) => ({ id: b.id, name: b.name, cover_url: b.cover_url }))
    }
  },

  'GET /api/v1/bands/:id': async ({ params }) => {
    await delay()
    const id = Number(params && params.id)
    const band = BAND_PROFILES.find((b) => b.id === id)
    if (!band) throw { code: 'NOT_FOUND', message: '乐队不存在', statusCode: 404 }
    return {
      id: band.id,
      name: band.name,
      intro: band.intro,
      cover_url: band.cover_url,
      members: band.members || []
    }
  }
}

export { nextBandId }
