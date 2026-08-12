/**
 * 同步引擎 — 实现 V4.4 §11 客户端同步流程
 *
 * 首次同步（§11.1）：/full 全量 → staging_store → /sync catch-up → swap 原子切换 → 保存 cursor
 * 增量同步（§11.2）：读取本地 scope + cursor → 循环 /sync → 直接作用于 active_store
 * 错误处理（§14）：refetch_full → clearAll + firstSync；backoff_retry → 退避 + incrementalSync
 */

import { fetchFullFirstPage, fetchFullNextPage, fetchSync, getErrorAction } from './api.js'
import {
  openDB,
  writeStaging,
  deleteFromStaging,
  swapStagingToActive,
  upsertActive,
  deleteFromActive,
  saveMeta,
  getMeta,
  clearAll
} from './db.js'

const DEFAULT_CITY = 'Tokyo'

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 首次同步（V4.4 §11.1）
 *
 * 1. /full 第一页
 * 2. 保存 scope 与 snapshot_cursor（临时同步状态）
 * 3. 按 next_token 拉完所有页，写入 staging_store
 * 4-6. /sync catch-up（循环直到 has_more=false），累积 upsert/delete 到 staging_store
 * 7. swapStagingToActive 原子替换（清空 active → 复制 staging → 清空 staging）
 * 8. 保存最终 cursor
 *
 * @param {string} city
 * @param {(p:{stage:'full'|'sync', page?:number, cursor?:number, received:number})=>void} [onProgress]
 * @returns {Promise<{scope:Object, cursor:number}>}
 */
export async function firstSync(city, onProgress) {
  await openDB()

  // 1. /full 第一页
  const firstPage = await fetchFullFirstPage(city)
  if (!firstPage || typeof firstPage !== 'object' || !firstPage.scope || !firstPage.scope.city) {
    const e = new Error('服务器返回数据异常，请稍后重试')
    e.code = 'BAD_FULL_RESPONSE'
    throw e
  }
  const { scope, snapshot_cursor } = firstPage

  // 2. 保存 scope 与 snapshot_cursor
  await saveMeta('scope', scope)
  await saveMeta('city', scope.city)
  await saveMeta('cursor', Number(snapshot_cursor || 0))

  // 3. 拉完所有 /full 页 → staging_store
  let received = 0
  let pageNo = 1
  const writeAndTrack = async (data) => {
    if (data && data.length) await writeStaging(data)
    received += (data && data.length) || 0
  }

  await writeAndTrack(firstPage.data)
  if (onProgress) onProgress({ stage: 'full', page: pageNo, received })

  let nextToken = firstPage.next_token
  while (nextToken) {
    const page = await fetchFullNextPage(nextToken)
    pageNo += 1
    await writeAndTrack(page.data)
    nextToken = page.next_token
    if (onProgress) onProgress({ stage: 'full', page: pageNo, received })
  }

  // 4-6. /sync catch-up → staging_store（与 /full 同一 Scope）
  let cursor = Number(snapshot_cursor || 0)
  let hasMore = true
  while (hasMore) {
    const batch = await fetchSync(
      scope.city,
      scope.scope_start_date,
      scope.scope_end_date,
      cursor
    )
    if (batch.data && batch.data.length) await writeStaging(batch.data)
    if (batch.deletes && batch.deletes.length) await deleteFromStaging(batch.deletes)
    cursor = Number(batch.cursor)
    hasMore = !!batch.has_more
    if (onProgress) onProgress({ stage: 'sync', cursor, received })
  }

  // 7. 原子替换
  await swapStagingToActive()

  // 8. 保存最终 cursor
  await saveMeta('cursor', cursor)
  await saveMeta('last_synced_at', Date.now())
  await saveMeta('synced_city', scope.city)

  return { scope, cursor }
}

/**
 * 增量同步（V4.4 §11.2）
 *
 * 1. 读取本地 scope 与 cursor
 * 2. 循环 /sync 直到 has_more=false
 * 3. upsert 覆盖写入 active_store
 * 4. delete 按 id 删除
 * 5. 每次返回后保存 cursor
 *
 * @returns {Promise<{cursor:number}>}
 */
export async function incrementalSync() {
  await openDB()

  const scope = await getMeta('scope')
  const cursorRaw = await getMeta('cursor')

  if (!scope || cursorRaw == null) {
    const err = new Error('NO_SYNC_STATE')
    err.code = 'NO_SYNC_STATE'
    throw err
  }

  let cursor = Number(cursorRaw)
  let hasMore = true

  while (hasMore) {
    const batch = await fetchSync(
      scope.city,
      scope.scope_start_date,
      scope.scope_end_date,
      cursor
    )
    if (batch.data && batch.data.length) await upsertActive(batch.data)
    if (batch.deletes && batch.deletes.length) await deleteFromActive(batch.deletes)
    cursor = Number(batch.cursor)
    hasMore = !!batch.has_more
  }

  await saveMeta('cursor', cursor)
  await saveMeta('last_synced_at', Date.now())

  return { cursor }
}

/**
 * 同步错误处理（V4.4 §14 错误码 → 客户端动作）
 *
 * - refetch_full（INVALID_PAGE_TOKEN / FULL_PAGE_TOKEN_EXPIRED /
 *                  SYNC_CURSOR_EXPIRED / INVALID_CURSOR）→ clearAll + firstSync
 * - backoff_retry（RATE_LIMITED）→ 退避 5s 后 incrementalSync
 * - stop_and_retry（SYNC_INVARIANT_BROKEN）→ 停止写入本地水位，抛出由调用方稍后重试
 * - unknown → 抛出
 *
 * @param {Error & {code?:string, network?:boolean}} error
 */
export async function handleSyncError(error) {
  const code = error && error.code
  const action = getErrorAction(code)

  if (action === 'refetch_full') {
    // 先取 city 再清空，否则 scope 已被清掉
    const scope = await getMeta('scope')
    const city = (scope && scope.city) || (await getMeta('city')) || DEFAULT_CITY
    await clearAll()
    return firstSync(city)
  }

  if (action === 'backoff_retry') {
    await delay(5000)
    return incrementalSync()
  }

  throw error
}

export { DEFAULT_CITY }
