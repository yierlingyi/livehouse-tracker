/**
 * 认证服务（Band Portal）
 * 封装 /api/v1/auth/*（经 common/http.js，自动附加 Authorization）
 */
import { request } from '../common/http.js'

/**
 * 乐队注册 → status=pending（等待管理员审核）
 * @param {{username:string, password:string, band_name:string}} data
 * @returns {Promise<{account:Object}>}
 */
export function register(data) {
  return request('POST', '/api/v1/auth/register', data)
}

/**
 * 乐队登录 → {token, account}
 * @param {{username:string, password:string}} data
 * @returns {Promise<{token:string, account:Object}>}
 */
export function login(data) {
  return request('POST', '/api/v1/auth/login', data)
}

/** 注销 */
export function logout() {
  return request('POST', '/api/v1/auth/logout', {})
}

/** 当前账号 */
export function me() {
  return request('GET', '/api/v1/auth/me')
}
