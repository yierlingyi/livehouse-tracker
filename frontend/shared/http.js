/**
 * 通用 HTTP 客户端（三端共用）
 *
 * 职责：
 * - request(method, path, data, options) 统一出口
 * - 自动附加 Authorization: Bearer <token>（白名单接口 / 公开 GET 除外）
 * - 错误归一为 {code, message} 的 Error（含 statusCode，用于 401 判定）
 * - 401：清 token/account → uni.reLaunch 登录页（仅 band/admin 端启用，可通过
 *   参数逐请求关闭）。默认关闭，band/admin 调用 setAuthRedirectEnabled(true) 开启。
 * - Mock 开关：VITE_USE_MOCK==='true' 时请求改走 mock/index.js 的 handler，
 *   否则走 uni.request 打真实后端。API_BASE 读 VITE_API_BASE，try/catch 回退同源。
 */
import { getToken, clearAuth } from './storage.js'
import { lookup } from './mock/index.js'

/**
 * 兼容 HBuilderX / Vite 双环境读取 env：
 * 先读 import.meta.env，再读 process.env（HBuilderX 构建可能只暴露其一）。
 * 读取不到时回退默认值：USE_MOCK 默认 'true'（mock 优先开发流），API_BASE 默认同源。
 */
function readEnv(name, fallback) {
  try {
    if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env[name] != null) {
      return String(import.meta.env[name])
    }
  } catch (e) { /* ignore */ }
  try {
    if (typeof process !== 'undefined' && process.env && process.env[name] != null) {
      return String(process.env[name])
    }
  } catch (e) { /* ignore */ }
  return fallback
}

export const API_BASE = readEnv('VITE_API_BASE', '').replace(/\/+$/, '')

export const USE_MOCK = readEnv('VITE_USE_MOCK', 'true') === 'true'

// 运行时诊断（浏览器控制台可确认 mock/真实模式与 API 地址；排查后可按需删除）
if (typeof console !== 'undefined' && console.log) {
  console.log('[http] USE_MOCK=' + USE_MOCK + ' API_BASE="' + API_BASE + '"')
}

const DEFAULT_TIMEOUT = 15000

/** 401 → 跳登录的重定向开关（band/admin 端在入口开启） */
let authRedirectEnabled = false

/**
 * 开启/关闭 401 全局重定向（User App 保持关闭；band/admin 开启）。
 * @param {boolean} enabled
 */
export function setAuthRedirectEnabled(enabled) {
  authRedirectEnabled = !!enabled
}

/* ---------------- 鉴权附加规则 ---------------- */

function isAuthWhitelisted(path) {
  if (['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/admin/login'].indexOf(path) !== -1) {
    return true
  }
  // /accounts/{username}/exists
  if (/^\/api\/v1\/accounts\/[^/]+\/exists$/.test(path)) return true
  // /full /sync（User App 数据源，公开）
  if (/\/lives\/full$/.test(path) || /\/lives\/sync$/.test(path)) return true
  return false
}

function isPublicGet(method, path) {
  if (method !== 'GET') return false
  // 演出详情（公开，含场地+setlist）
  if (/^\/api\/v1\/lives\/\d+$/.test(path)) return true
  // 场地 / 乐队 / CMS 公开只读
  const publics = [
    '/api/v1/livehouses',
    '/api/v1/bands',
    '/api/v1/cms/groups',
    '/api/v1/cms/sponsor',
    '/api/v1/cms/project'
  ]
  for (const p of publics) {
    if (path === p || path.indexOf(p + '/') === 0) return true
  }
  return false
}

function shouldAttachAuth(method, path) {
  if (isAuthWhitelisted(path)) return false
  if (isPublicGet(method, path)) return false
  return true
}

/* ---------------- 错误归一 ---------------- */

function normalizeError(payload) {
  const body = payload && typeof payload === 'object' ? payload : {}
  const err = new Error(body.message || '请求失败')
  err.code = body.code || 'UNKNOWN_ERROR'
  if (body.statusCode != null) err.statusCode = body.statusCode
  return err
}

function networkError(message) {
  const err = new Error(message || '网络错误，请检查连接')
  err.code = 'NETWORK_ERROR'
  err.network = true
  return err
}

/* ---------------- 401 处理 ---------------- */

function handle401() {
  try {
    clearAuth()
  } catch (e) { /* ignore */ }
  try {
    uni.reLaunch({ url: '/pages/login/index?reason=session_expired' })
  } catch (e) { /* ignore */ }
}

function decideRedirect401(options) {
  if (options && typeof options.redirect401 !== 'undefined') return !!options.redirect401
  return authRedirectEnabled
}

/* ---------------- 真实请求 ---------------- */

function realRequest(method, path, data) {
  const url = API_BASE + path
  const token = getToken()
  const header = { 'Content-Type': 'application/json' }
  if (shouldAttachAuth(method, path) && token) {
    header.Authorization = 'Bearer ' + token
  }
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      data: data || {},
      method: method || 'GET',
      header,
      timeout: DEFAULT_TIMEOUT,
      success: (res) => {
        const status = res && res.statusCode
        if (status === 0 || status == null) {
          reject(networkError())
          return
        }
        if (status >= 200 && status < 300) {
          resolve(res.data)
          return
        }
        if (status === 401) {
          reject(normalizeError({ code: 'UNAUTHORIZED', message: '登录已过期，请重新登录', statusCode: 401 }))
          return
        }
        reject(normalizeError(
          (res.data && typeof res.data === 'object') ? res.data : { code: 'HTTP_' + status, message: '请求失败 HTTP ' + status }
        ))
      },
      fail: (err) => {
        reject(networkError((err && err.errMsg) || undefined))
      }
    })
  })
}

/* ---------------- Mock 请求 ---------------- */

async function mockRequest(method, path, data) {
  const found = lookup(method, path)
  if (!found || typeof found.handler !== 'function') {
    throw { code: 'MOCK_NOT_FOUND', message: 'Mock 接口未定义: ' + method + ' ' + path }
  }
  const token = getToken()
  const ctx = {
    method: String(method).toUpperCase(),
    path,
    data: data || {},
    params: found.params || {},
    headers: {
      Authorization: token ? 'Bearer ' + token : ''
    }
  }
  // handler 直接返回数据体；抛出的 {code,message,statusCode} 会被上层归一
  return found.handler(ctx)
}

/* ---------------- 统一出口 ---------------- */

/**
 * 发起请求（真实后端或 mock 二选一）。
 * @param {string} method GET/POST/PATCH/PUT/DELETE
 * @param {string} path /api/v1/...
 * @param {Object} [data] 请求体
 * @param {{redirect401?: boolean}} [options] redirect401 逐请求覆盖全局开关
 * @returns {Promise<*>} 成功返回数据体；失败抛 {code,message,statusCode?} 的 Error
 */
export async function request(method, path, data, options) {
  let result
  try {
    result = USE_MOCK
      ? await mockRequest(method, path, data)
      : await realRequest(method, path, data)
  } catch (err) {
    const normalized = err instanceof Error ? err : normalizeError(err)
    if (normalized.statusCode === 401 && decideRedirect401(options)) {
      handle401()
    }
    throw normalized
  }
  return result
}

/**
 * 图片 URL 解析：把后端返回的根相对路径（/static/uploads/...）拼上前端 API_BASE，
 * 使 <image src> 能正确加载。mock 相对路径与绝对/data URL 原样透传。
 * @param {string} url 后端返回的图片地址（相对路径 / 绝对 http(s) / data:）
 * @returns {string} 可直接用于 <image src> 的地址
 */
export function resolveImageUrl(url) {
  if (!url) return ''
  if (USE_MOCK) return url
  if (/^(https?:)?\/\//i.test(url)) return url
  if (/^data:/i.test(url)) return url
  return API_BASE + (url.charAt(0) === '/' ? url : '/' + url)
}
