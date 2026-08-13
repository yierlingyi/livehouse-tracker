/**
 * 认证与账号 Mock（§4.1）
 *
 * 预置账号：band_pending（pending）、admin（admin）
 * 登录校验 username+password；pending 账号返回 status='pending'（前端据此提示审核中）。
 * 所有 handler 直接返回数据体；错误抛 {code, message[, statusCode]}。
 */
import {
  delay,
  ACCOUNTS,
  publicAccount,
  issueToken,
  requireAdmin,
  requireLogin,
  getAccountByUsername
} from './_state.js'

export default {
  /* ---------------- 乐队注册：注册成功 → status=pending，等待管理员审核 ---------------- */
  'POST /api/v1/auth/register': async ({ data }) => {
    await delay()
    const username = String((data && data.username) || '').trim()
    const password = String((data && data.password) || '')
    const band_name = String((data && data.band_name) || '').trim()
    if (!username || !password || !band_name) {
      throw { code: 'VALIDATION_ERROR', message: '请填写完整的账号、密码与乐队名称' }
    }
    if (getAccountByUsername(username)) {
      throw { code: 'ACCOUNT_EXISTS', message: '账号已存在' }
    }
    const account = {
      id: Math.max.apply(null, Object.keys(ACCOUNTS).map((k) => ACCOUNTS[k].id)) + 1,
      username,
      password,
      band_name,
      intro: '',
      role: 'band',
      status: 'pending',
      created_at: new Date().toISOString()
    }
    ACCOUNTS[username] = account
    return { account: publicAccount(account) }
  },

  /* ---------------- 乐队登录：pending → 拒绝并提示审核中 ---------------- */
  'POST /api/v1/auth/login': async ({ data }) => {
    await delay()
    const username = String((data && data.username) || '').trim()
    const password = String((data && data.password) || '')
    const account = getAccountByUsername(username)
    if (!account || account.password !== password) {
      throw { code: 'INVALID_CREDENTIALS', message: '账号或密码错误' }
    }
    if (account.role !== 'band') {
      throw { code: 'INVALID_CREDENTIALS', message: '该账号为管理员账号，请使用管理员入口登录' }
    }
    if (account.status === 'pending') {
      throw { code: 'PENDING', message: '账号审核中，请等待管理员审核', status: 'pending' }
    }
    if (account.status !== 'active') {
      throw { code: 'ACCOUNT_DISABLED', message: '账号不可用，请联系管理员' }
    }
    const token = issueToken(username)
    return { token, account: publicAccount(account) }
  },

  'POST /api/v1/auth/logout': async () => {
    await delay()
    return { ok: true }
  },

  /* ---------------- 当前账号 ---------------- */
  'GET /api/v1/auth/me': async ({ headers }) => {
    await delay()
    const username = requireLogin(headers)
    const account = getAccountByUsername(username)
    if (!account) throw { code: 'UNAUTHORIZED', message: '未登录或登录已过期', statusCode: 401 }
    return { account: publicAccount(account) }
  },

  /* ---------------- 管理员登录 ---------------- */
  'POST /api/v1/admin/login': async ({ data }) => {
    await delay()
    const username = String((data && data.username) || '').trim()
    const password = String((data && data.password) || '')
    const account = getAccountByUsername(username)
    if (!account || account.password !== password || account.role !== 'admin') {
      throw { code: 'INVALID_CREDENTIALS', message: '账号或密码错误' }
    }
    const token = issueToken(username)
    return { token, account: publicAccount(account) }
  },

  /* ---------------- 拼盘邀请实时校验账号是否存在（仅 active 乐队） ---------------- */
  'GET /api/v1/accounts/:username/exists': async ({ params }) => {
    await delay()
    const username = (params && params.username) || ''
    const account = getAccountByUsername(username)
    return { exists: !!(account && account.role === 'band' && account.status === 'active') }
  },

  /* ---------------- 新增管理员（admin） ---------------- */
  'POST /api/v1/admin/accounts': async ({ data, headers }) => {
    await delay()
    requireAdmin(headers)
    const username = String((data && data.username) || '').trim()
    const password = String((data && data.password) || '')
    if (!username || !password) throw { code: 'VALIDATION_ERROR', message: '请填写用户名和密码' }
    if (getAccountByUsername(username)) throw { code: 'ACCOUNT_EXISTS', message: '账号已存在' }
    const account = {
      id: Math.max.apply(null, Object.keys(ACCOUNTS).map((k) => ACCOUNTS[k].id)) + 1,
      username,
      password,
      band_name: '',
      intro: '',
      role: 'admin',
      status: 'active',
      created_at: new Date().toISOString()
    }
    ACCOUNTS[username] = account
    return { account: { id: account.id, username, role: 'admin' } }
  }
}
