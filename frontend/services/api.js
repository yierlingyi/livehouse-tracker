/**
 * HTTP 客户端 — 封装 /full 与 /sync 同步接口（V4.4 §9 / §10）
 *
 * 错误响应遵循 backend/contracts/shared.json#/definitions/Error：
 *   { code, message }
 * 网络失败 / 超时统一归一为 { code: 'NETWORK_ERROR', network: true }。
 */

// API 基地址。HBuilderX / uni-app 使用 VUE_APP_API_BASE 环境变量；
// 未配置时使用同源（H5 由部署侧反代 /api，小程序配置域名白名单）。
// 在 HBuilderX 中：项目根目录创建 .env 文件，写入 VUE_APP_API_BASE=http://127.0.0.1:8000
const API_BASE = (() => {
  try {
    // HBuilderX CLI / uni-app 方式
    if (typeof process !== 'undefined' && process.env && process.env.VUE_APP_API_BASE) {
      return String(process.env.VUE_APP_API_BASE).replace(/\/+$/, '')
    }
  } catch (e) { /* ignore */ }
  // 也可在 manifest.json 的 h5.router.base 或源码中直接修改此处
  return ''
})()
const DEFAULT_TIMEOUT = 15000

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

function normalizeHttpError(payload, statusCode) {
  const body = payload && typeof payload === 'object' ? payload : {}
  const err = new Error(body.message || ('请求失败 HTTP ' + statusCode))
  err.code = body.code || 'UNKNOWN_ERROR'
  err.statusCode = statusCode
  return err
}

function request(path, data) {
  const url = API_BASE + path
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      data: data || {},
      method: 'GET',
      timeout: DEFAULT_TIMEOUT,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(normalizeHttpError(res.data, res.statusCode))
        }
      },
      fail: (err) => {
        const e = new Error((err && err.errMsg) || 'NETWORK_ERROR')
        e.code = 'NETWORK_ERROR'
        e.network = true
        reject(e)
      }
    })
  })
}

/**
 * /full 第一页（V4.4 §9）
 * @param {string} city
 * @param {number} [pageSize=500]
 * @returns {Promise<{data:Array, scope:Object, snapshot_cursor:string, has_more:boolean, next_token:string|null}>}
 */
export function fetchFullFirstPage(city, pageSize = 500) {
  return request('/api/v1/lives/full', { city, page_size: pageSize })
}

/**
 * /full 后续页
 * @param {string} nextToken 签名 keyset token
 * @param {number} [pageSize=500]
 * @returns {Promise<{data:Array, scope:Object, snapshot_cursor:string, has_more:boolean, next_token:string|null}>}
 */
export function fetchFullNextPage(nextToken, pageSize = 500) {
  return request('/api/v1/lives/full', { page_token: nextToken, page_size: pageSize })
}

/**
 * /sync 增量回放（V4.4 §10）
 * @param {string} city
 * @param {string} scopeStart scope_start_date
 * @param {string} scopeEnd scope_end_date
 * @param {number|string} since 客户端当前 cursor（已处理到的版本）
 * @param {number} [limit=1000]
 * @returns {Promise<{data:Array, deletes:Array<number>, cursor:number, has_more:boolean}>}
 */
export function fetchSync(city, scopeStart, scopeEnd, since, limit = 1000) {
  return request('/api/v1/lives/sync', {
    city,
    scope_start_date: scopeStart,
    scope_end_date: scopeEnd,
    since,
    limit
  })
}

export { API_BASE }
