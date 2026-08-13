/**
 * uni storage 封装（三端共用）
 *
 * - token / account：登录态（三端独立部署，key 可同名互不干扰）
 * - remembered：记住密码（base64 简单混淆，仅客户端便利、非安全）
 * - theme：主题（light/dark）
 *
 * 所有读取都有 try/catch，storage 异常时返回安全默认值，不抛错。
 */

const TOKEN_KEY = 'token'
const ACCOUNT_KEY = 'account'
const REMEMBERED_KEY = 'remembered'
const THEME_KEY = 'theme'

function getRaw(key) {
  try {
    return uni.getStorageSync(key)
  } catch (e) {
    return ''
  }
}

function setRaw(key, value) {
  try {
    uni.setStorageSync(key, value)
  } catch (e) {
    /* 忽略 storage 写入失败 */
  }
}

function removeRaw(key) {
  try {
    uni.removeStorageSync(key)
  } catch (e) {
    /* 忽略 */
  }
}

function getJSON(key, fallback) {
  const raw = getRaw(key)
  if (!raw) return fallback
  if (typeof raw === 'object') return raw
  try {
    return JSON.parse(raw)
  } catch (e) {
    return fallback
  }
}

function setJSON(key, value) {
  setRaw(key, JSON.stringify(value))
}

/* ---------------- token ---------------- */

export function getToken() {
  return getRaw(TOKEN_KEY) || ''
}

export function setToken(token) {
  setRaw(TOKEN_KEY, token || '')
}

/* ---------------- account ---------------- */

export function getAccount() {
  return getJSON(ACCOUNT_KEY, null)
}

export function setAccount(account) {
  if (account == null) {
    removeRaw(ACCOUNT_KEY)
  } else {
    setJSON(ACCOUNT_KEY, account)
  }
}

/** 登出：清 token + account */
export function clearAuth() {
  removeRaw(TOKEN_KEY)
  removeRaw(ACCOUNT_KEY)
}

/* ---------------- 记住密码（base64 混淆） ---------------- */

export function getRemembered() {
  const raw = getJSON(REMEMBERED_KEY, null)
  if (!raw || !raw.username) return null
  return {
    username: String(raw.username),
    password: decodeB64(String(raw.password || ''))
  }
}

/**
 * 记住/清除账号密码。
 * @param {string} username 传空字符串或 null 表示清除
 * @param {string} [password]
 */
export function setRemembered(username, password) {
  if (!username) {
    removeRaw(REMEMBERED_KEY)
    return
  }
  setJSON(REMEMBERED_KEY, {
    username: String(username),
    password: encodeB64(String(password || ''))
  })
}

/* ---------------- theme ---------------- */

export function getTheme() {
  const v = getRaw(THEME_KEY)
  return v === 'dark' ? 'dark' : 'light'
}

export function setTheme(mode) {
  setRaw(THEME_KEY, mode === 'dark' ? 'dark' : 'light')
}

/* ---------------- base64 工具（浏览器/uni 内置 btoa/atob） ---------------- */

function encodeB64(str) {
  try {
    if (typeof btoa === 'function') {
      return btoa(unescape(encodeURIComponent(str)))
    }
  } catch (e) { /* fallthrough */ }
  return str
}

function decodeB64(str) {
  try {
    if (typeof atob === 'function') {
      return decodeURIComponent(escape(atob(str)))
    }
  } catch (e) { /* fallthrough */ }
  return str
}
