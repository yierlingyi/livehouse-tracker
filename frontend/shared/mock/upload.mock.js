/**
 * 文件上传 Mock（§4.7）
 *
 * POST /api/v1/upload → {url}（mock 模式返回 static/ 本地占位图 URL）
 * 说明：UploadImage.vue 在 mock 模式不会走这里（直接返回占位图），
 * 此路由供通过 request() 显式上传的调用兜底。
 */
import { delay } from './_state.js'

export default {
  'POST /api/v1/upload': async () => {
    await delay()
    return { url: '/static/mock-cover.svg' }
  }
}
