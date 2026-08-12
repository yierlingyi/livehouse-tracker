/**
 * IndexedDB 封装 — 管理 staging_store / active_store / sync_meta（V4.4 §11.1 双区模式）
 *
 * 双区模式：
 *   staging_store（keyPath: 'id'）— 首次 /full 期间写入，未原子切换前不对外可见
 *   active_store（keyPath: 'id'）— 正式缓存，页面只读 active_store
 *   sync_meta（keyPath: 'key'）  — scope / cursor / last_synced_at 等同步元数据
 *
 * 灾难恢复：openDB 打开失败时尝试 deleteDatabase 重建（缓存仅需重新同步）。
 */

const DB_NAME = 'band_live_cache'
const DB_VERSION = 1

let dbPromise = null

function ensureStores(db) {
  if (!db.objectStoreNames.contains('staging_store')) {
    db.createObjectStore('staging_store', { keyPath: 'id' })
  }
  if (!db.objectStoreNames.contains('active_store')) {
    db.createObjectStore('active_store', { keyPath: 'id' })
  }
  if (!db.objectStoreNames.contains('sync_meta')) {
    db.createObjectStore('sync_meta', { keyPath: 'key' })
  }
}

function openInternal() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      const e = new Error('INDEXEDDB_UNSUPPORTED')
      e.code = 'INDEXEDDB_UNSUPPORTED'
      return reject(e)
    }
    let req
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION)
    } catch (err) {
      return reject(err)
    }
    req.onupgradeneeded = (e) => ensureStores(e.target.result)
    req.onsuccess = (e) => {
      const db = e.target.result
      // 其他标签页尝试升级时主动关闭，避免阻塞
      db.onversionchange = () => db.close()
      resolve(db)
    }
    req.onerror = () => reject(req.error)
    req.onblocked = () => { /* 等待其他连接关闭 */ }
  })
}

/**
 * 初始化数据库（onupgradeneeded 创建 3 个 store）。
 * 打开失败（损坏等）自动删除重建。
 * @returns {Promise<IDBDatabase>}
 */
export function openDB() {
  if (!dbPromise) {
    dbPromise = openInternal().catch((err) => {
      dbPromise = null
      // 灾难恢复：删除损坏数据库后重建（V4.4 核心原则）
      return new Promise((resolve, reject) => {
        const del = indexedDB.deleteDatabase(DB_NAME)
        del.onsuccess = () => openInternal().then(resolve).catch(reject)
        del.onerror = () => reject(del.error || err)
        del.onblocked = () => { /* 等待其他连接关闭 */ }
      })
    })
  }
  return dbPromise
}

async function getDB() {
  return openDB()
}

/**
 * 批量写入 staging（首次 /full 期间）。
 * @param {Array<Object>} lives
 */
export async function writeStaging(lives) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('staging_store', 'readwrite')
    const store = tx.objectStore('staging_store')
    for (const live of lives) store.put(live)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 按 id 数组从 staging 删除（首次 /full catch-up 期间的 deletes）。
 * @param {Array<number>} ids
 */
export async function deleteFromStaging(ids) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('staging_store', 'readwrite')
    const store = tx.objectStore('staging_store')
    for (const id of ids) store.delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 原子切换：清空 active → 复制 staging → 清空 staging。
 * 全部操作在单个事务内完成，任一步失败整体回滚，不会产生半同步状态。
 */
export async function swapStagingToActive() {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['active_store', 'staging_store'], 'readwrite')
    const active = tx.objectStore('active_store')
    const staging = tx.objectStore('staging_store')

    active.clear()

    const readReq = staging.getAll()
    readReq.onsuccess = () => {
      const items = readReq.result || []
      for (const item of items) active.put(item)
      staging.clear()
    }

    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 增量 upsert 到 active。
 * @param {Array<Object>} lives
 */
export async function upsertActive(lives) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('active_store', 'readwrite')
    const store = tx.objectStore('active_store')
    for (const live of lives) store.put(live)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 按 id 数组从 active 删除。
 * @param {Array<number>} ids
 */
export async function deleteFromActive(ids) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('active_store', 'readwrite')
    const store = tx.objectStore('active_store')
    for (const id of ids) store.delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 读取 active 全部数据（首页列表）。
 * @returns {Promise<Array<Object>>}
 */
export async function getActiveAll() {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('active_store', 'readonly')
    const req = tx.objectStore('active_store').getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

/**
 * 按 id 读取 active 单条（详情页）。
 * @param {number|string} id
 * @returns {Promise<Object|null>}
 */
export async function getActiveById(id) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('active_store', 'readonly')
    const req = tx.objectStore('active_store').get(Number(id))
    req.onsuccess = () => resolve(req.result || null)
    req.onerror = () => reject(req.error)
  })
}

/**
 * 保存元数据（scope / cursor / last_synced_at 等）。
 * @param {string} key
 * @param {*} value
 */
export async function saveMeta(key, value) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('sync_meta', 'readwrite')
    tx.objectStore('sync_meta').put({ key, value })
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

/**
 * 读取元数据；不存在返回 null。
 * @param {string} key
 * @returns {Promise<*|null>}
 */
export async function getMeta(key) {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('sync_meta', 'readonly')
    const req = tx.objectStore('sync_meta').get(key)
    req.onsuccess = () => resolve(req.result ? req.result.value : null)
    req.onerror = () => reject(req.error)
  })
}

/**
 * 清空全部 3 个 store（灾难恢复 / 重新全量同步前）。
 */
export async function clearAll() {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(['active_store', 'staging_store', 'sync_meta'], 'readwrite')
    tx.objectStore('active_store').clear()
    tx.objectStore('staging_store').clear()
    tx.objectStore('sync_meta').clear()
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

export { DB_NAME, DB_VERSION }
