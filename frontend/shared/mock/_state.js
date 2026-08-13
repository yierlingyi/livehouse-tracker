/**
 * Mock 私有共享状态（不参与 index.js 路由注册，仅各 mock 模块内部使用）
 *
 * - 账号表 + 登录会话（跨 auth / venues / coop 共享，保证登录态与审核动作联动）
 * - 通用工具：delay / token 解析 / requireLogin / requireAdmin
 *
 * 说明：跨模块登录态必须放在一处共享，否则 auth.mock.js 发放的 token
 * 无法被 venues.mock.js（管理员校验）等其它模块识别。
 */

/** 模拟网络延迟 100~300ms */
export function delay() {
  return new Promise((r) => setTimeout(r, 150 + Math.random() * 150))
}

/**
 * 预置账号表（内存态）
 * band_pending 为待审核账号；admin 为管理员。
 */
export const ACCOUNTS = {
  band_pending: { id: 5, username: 'band_pending', password: 'band_pending', band_name: '深海鲸落', intro: '后摇氛围团，正在审核中。', role: 'band', status: 'pending', created_at: '2026-08-10T09:00:00Z' },
  admin: { id: 99, username: 'admin', password: 'admin123', band_name: '', intro: '', role: 'admin', status: 'active', created_at: '2026-01-01T00:00:00Z' }
}

let nextAccountId = 100
const sessions = new Map()

/** 去除敏感字段（password）后返回公开账号对象 */
export function publicAccount(a) {
  if (!a) return null
  const { password, ...rest } = a
  return rest
}

export function listAccounts() {
  return Object.keys(ACCOUNTS).map((k) => ACCOUNTS[k])
}

export function getAccountByUsername(username) {
  return ACCOUNTS[username] || null
}

export function addAccount(username, fields) {
  if (ACCOUNTS[username]) throw { code: 'ACCOUNT_EXISTS', message: '账号已存在' }
  ACCOUNTS[username] = Object.assign(
    { id: nextAccountId++, username, password: '', band_name: '', intro: '', role: 'band', status: 'pending', created_at: new Date().toISOString() },
    fields || {}
  )
  ACCOUNTS[username].username = username
  return ACCOUNTS[username]
}

export function removeAccount(username) {
  delete ACCOUNTS[username]
}

export function updateAccount(username, fields) {
  const a = ACCOUNTS[username]
  if (!a) return null
  Object.assign(a, fields || {})
  return a
}

/* ---------------- 会话 / 鉴权 ---------------- */

export function issueToken(username) {
  const token = 'mock-' + username + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
  sessions.set(token, username)
  return token
}

export function extractToken(headers) {
  const h = headers || {}
  const auth = h.Authorization || h.authorization || ''
  return String(auth).replace(/^Bearer\s+/i, '').trim()
}

export function currentUsername(headers) {
  const token = extractToken(headers)
  return (token && sessions.get(token)) || null
}

/** 未登录/失效 token → 抛 401 */
export function requireLogin(headers) {
  const username = currentUsername(headers)
  if (!username) throw { code: 'UNAUTHORIZED', message: '未登录或登录已过期', statusCode: 401 }
  return username
}

/** 非管理员 → 抛 403 */
export function requireAdmin(headers) {
  const username = requireLogin(headers)
  const account = ACCOUNTS[username]
  if (!account || account.role !== 'admin') {
    throw { code: 'FORBIDDEN', message: '无权限操作', statusCode: 403 }
  }
  return username
}
