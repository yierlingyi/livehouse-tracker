/**
 * 主题读写 — getTheme / setTheme / applyTheme（三端共用）
 *
 * - getTheme()：读 uni.getStorageSync('theme')，默认 'light'
 * - setTheme(mode)：写入 storage 并立即 applyTheme()
 * - applyTheme(mode?)：H5 上给 documentElement 与 body 打 data-theme；
 *   mp/非 H5 环境安全降级（无 document 时静默跳过）
 */
import { getTheme as getStoredTheme, setTheme as storeTheme } from './storage.js'

const DEFAULT_THEME = 'light'

/**
 * 读取当前主题（storage 为唯一事实，默认 light）
 * @returns {'light'|'dark'}
 */
export function getTheme() {
  const mode = getStoredTheme()
  return mode === 'dark' ? 'dark' : DEFAULT_THEME
}

/**
 * 切换并落盘主题，同时应用到当前页面
 * @param {'light'|'dark'} mode
 */
export function setTheme(mode) {
  const m = mode === 'dark' ? 'dark' : DEFAULT_THEME
  storeTheme(m)
  applyTheme(m)
}

/**
 * 把主题应用到 DOM。H5：documentElement + body 同时打 data-theme，
 * 保证 page[data-theme='dark'] 编译后的选择器（body/uni-page-body）能匹配。
 * 非 H5 环境无 document，安全降级为 no-op。
 * @param {'light'|'dark'} [mode]
 */
export function applyTheme(mode) {
  const m = mode || getTheme()
  try {
    if (typeof document === 'undefined') return
    if (document.documentElement) {
      document.documentElement.setAttribute('data-theme', m)
    }
    if (document.body) {
      document.body.setAttribute('data-theme', m)
    }
  } catch (e) {
    /* 忽略：非 H5 或 DOM 未就绪时静默降级 */
  }
}
