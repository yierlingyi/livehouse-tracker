/**
 * 格式化工具（三端共用）
 */

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/**
 * 日期 → 「M月D日 周X」
 * @param {string} dateStr YYYY-MM-DD
 * @returns {string}
 */
export function formatDate(dateStr) {
  if (!dateStr) return ''
  const s = String(dateStr).slice(0, 10)
  const d = new Date(s + 'T00:00:00')
  if (isNaN(d.getTime())) return s
  return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + WEEKDAYS[d.getDay()]
}

/**
 * 时间 → 「HH:mm」（空返回「待定」）
 * @param {string} timeStr
 * @returns {string}
 */
export function formatTime(timeStr) {
  if (!timeStr) return '待定'
  return String(timeStr).slice(0, 5)
}

/**
 * 价格 → 「¥xx」
 * @param {number|string|null} price
 * @returns {string}
 */
export function formatPrice(price) {
  if (price == null || price === '') return '待定'
  const n = Number(price)
  if (isNaN(n)) return String(price)
  if (Number.isInteger(n)) return '¥' + n
  return '¥' + n.toFixed(2)
}
