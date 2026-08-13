/**
 * 页面守卫（band/admin 端使用；User App 无登录态不需要）
 *
 * - requireAuth({endpoint})：读 token + account，account.status==='active' 才放行；
 *   否则 reLaunch 登录页并返回 false。受保护页 onShow 首行调用。
 * - guardLaunch({loginPage, homePage})：App.vue onLaunch 兜底——
 *   已登录且落在登录/注册页 → 回首页；未登录且当前不在登录/注册页 → 去登录页。
 */
import { getToken, getAccount } from './storage.js'

const DEFAULT_LOGIN = '/pages/login/index'

function reLaunch(url) {
  try {
    uni.reLaunch({ url })
  } catch (e) { /* ignore */ }
}

/**
 * 页面级守卫：token + account 且 status==='active' 才放行。
 * @param {{endpoint?: 'band'|'admin'}} [opts] endpoint 预留（band/admin 登录页相同）
 * @returns {boolean} 是否放行
 */
export function requireAuth(opts = {}) {
  const token = getToken()
  const account = getAccount()
  if (token && account && account.status === 'active') {
    return true
  }
  reLaunch(DEFAULT_LOGIN)
  return false
}

/**
 * onLaunch 兜底守卫。
 * @param {{loginPage?: string, homePage?: string}} [opts]
 */
export function guardLaunch(opts = {}) {
  const loginPage = opts.loginPage || DEFAULT_LOGIN
  const homePage = opts.homePage
  const token = getToken()
  const account = getAccount()
  const authed = !!(token && account && account.status === 'active')

  if (authed && homePage) {
    // 已登录：若启动页是登录/注册页则直接去首页
    reLaunch(homePage)
    return
  }

  try {
    const pages = getCurrentPages()
    const route = pages && pages.length ? (pages[pages.length - 1].route || '') : ''
    const onLogin = route.indexOf('pages/login/') === 0
    if (!authed && !onLogin) {
      reLaunch(loginPage)
    }
  } catch (e) { /* ignore */ }
}
