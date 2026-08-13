/**
 * Mock 路由注册表（共享单一事实源）
 *
 * 约定：每个模块 `export default { 'METHOD path': handler }`，
 * index.js 用 Object.assign 合并为 HANDLERS 并导出 lookup(method, path)。
 * 后续子 agent 只编辑各自 mock 文件的 default 导出，本文件无需再改。
 *
 * 注意：mock 文件不使用 import.meta（避免 HBuilderX 编译问题），只写普通 ES module。
 */
import auth from './auth.mock.js'
import lives from './lives.mock.js'
import livehouse from './livehouse.mock.js'
import bands from './bands.mock.js'
import coop from './coop.mock.js'
import cms from './cms.mock.js'
import venues from './venues.mock.js'
import upload from './upload.mock.js'
import admin from './admin.mock.js'
import band from './band.mock.js'

/** 所有 'METHOD path' → handler */
export const HANDLERS = Object.assign(
  {},
  auth,
  lives,
  livehouse,
  bands,
  coop,
  cms,
  venues,
  upload,
  admin,
  band
)

// 编译为路由表：支持 ':param' 路径占位（如 /api/v1/lives/:id）
const ROUTES = []
for (const [key, handler] of Object.entries(HANDLERS)) {
  const sp = key.indexOf(' ')
  const method = String(key.slice(0, sp)).toUpperCase()
  const path = key.slice(sp + 1)
  const paramNames = []
  const regexStr = path.replace(/:[^/]+/g, (m) => {
    paramNames.push(m.slice(1))
    return '([^/]+)'
  })
  ROUTES.push({
    method,
    regex: new RegExp('^' + regexStr + '$'),
    paramNames,
    handler
  })
}

/**
 * 查找匹配的 handler。
 * 字面路径（/full、/sync）在插入顺序上先于参数路径（/:id）注册，保证精确匹配优先。
 * @param {string} method
 * @param {string} path
 * @returns {{handler:Function, params:Object}|null}
 */
export function lookup(method, path) {
  const m = String(method).toUpperCase()
  for (const r of ROUTES) {
    if (r.method !== m) continue
    const match = r.regex.exec(path)
    if (match) {
      const params = {}
      r.paramNames.forEach((name, i) => {
        try {
          params[name] = decodeURIComponent(match[i + 1])
        } catch (e) {
          params[name] = match[i + 1]
        }
      })
      return { handler: r.handler, params }
    }
  }
  return null
}
