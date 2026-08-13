<template>
  <view class="page">
    <!-- 顶部城市入口 -->
    <view class="header" @click="goCitySwitch">
      <text class="city-name">{{ city || '选择城市' }}</text>
      <text class="city-arrow">›</text>
    </view>

    <!-- 同步状态指示器 -->
    <SyncStatus
      :syncing="syncing"
      :last-synced-at="lastSyncedAt"
      :offline="offline"
      :progress="progress"
    />

    <!-- 首次同步中 -->
    <view v-if="!lives.length && syncing" class="empty">
      <text class="empty-text">正在同步演出数据...</text>
    </view>

    <!-- 错误且无缓存数据 -->
    <ErrorPage
      v-else-if="lastError && !lives.length"
      :message="lastError"
      @retry="refresh"
    />

    <!-- 空数据 -->
    <view v-else-if="!lives.length" class="empty">
      <text class="empty-text">暂无演出数据</text>
    </view>

    <!-- 按日期分组的演出列表 -->
    <view v-else class="list-wrap">
      <view v-for="group in groupedLives" :key="group.date" class="day-group">
        <view class="day-header">{{ formatDate(group.date) }}</view>
        <view
          v-for="live in group.items"
          :key="live.id"
          class="live-card"
          @click="goDetail(live.id)"
        >
          <!-- 海报占位色块：V4.4 /full 投影不含海报字段，用本地色块 + 演出名/乐队名首字兜底 -->
          <view class="poster-block" :style="{ backgroundColor: blockColor(live) }">
            <text class="poster-char">{{ posterChar(live) }}</text>
          </view>

          <view class="live-info">
            <text class="live-title">{{ live.title }}</text>
            <text class="live-bands">{{ formatBands(live.band_names) }}</text>
            <text class="live-meta">{{ venueName(live) }} · {{ live.city }}</text>
            <view class="live-bottom">
              <text class="live-time">{{ formatTime(live.start_time) }}</text>
              <text class="live-price">{{ formatPrice(live.ticket_price) }}</text>
            </view>
          </view>
        </view>
      </view>

      <view class="list-footer">
        <text v-if="offline" class="footer-text">离线模式 · 数据可能不是最新</text>
        <text v-else class="footer-text">共 {{ lives.length }} 场演出</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import SyncStatus from '../../components/SyncStatus.vue'
import ErrorPage from '../../components/ErrorPage.vue'
import { openDB, getActiveAll, getMeta } from '../../services/db.js'
import { incrementalSync, handleSyncError } from '../../services/sync_engine.js'
import { fetchLivehouses } from '../../services/api.js'
import { formatDate, formatTime, formatPrice } from '../../common/format.js'

const city = ref('')
const lives = ref([])
const syncing = ref(false)
const offline = ref(false)
const lastSyncedAt = ref(null)
const lastError = ref('')
const progress = ref(null)

/* 场地名映射：/full 投影只有 livehouse_id，名称从公开接口补全（失败则兜底「场地 #id」） */
let venueMap = null
let venueMapPromise = null
function ensureVenueMap() {
  if (venueMap) return Promise.resolve(venueMap)
  if (!venueMapPromise) {
    venueMapPromise = fetchLivehouses()
      .then((res) => {
        const m = {}
        ;((res && res.items) || []).forEach((v) => {
          m[v.id] = v.name
        })
        venueMap = m
        return m
      })
      .catch(() => {
        venueMap = {}
        return venueMap
      })
  }
  return venueMapPromise
}
function venueName(live) {
  if (venueMap && venueMap[live.livehouse_id]) return venueMap[live.livehouse_id]
  return '场地 #' + live.livehouse_id
}

const groupedLives = computed(() => {
  const map = new Map()
  for (const live of lives.value) {
    const key = live.live_date
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(live)
  }
  const groups = []
  for (const [date, items] of map) {
    items.sort((a, b) => {
      const ta = a.sort_start_time || '99:99:99'
      const tb = b.sort_start_time || '99:99:99'
      if (ta !== tb) return ta < tb ? -1 : 1
      return (a.id || 0) - (b.id || 0)
    })
    groups.push({ date, items })
  }
  groups.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  return groups
})

const BLOCK_COLORS = ['#e5484d', '#f59e0b', '#16a34a', '#2563eb', '#7c3aed', '#0891b2', '#db2777']
function blockColor(live) {
  return BLOCK_COLORS[Math.abs(Number(live.id) || 0) % BLOCK_COLORS.length]
}
function posterChar(live) {
  const title = (live.title || '').trim()
  if (title) return title.slice(0, 1)
  const names = live.band_names || []
  if (names.length && String(names[0]).trim()) return String(names[0]).trim().slice(0, 1)
  return '♪'
}

function formatBands(bands) {
  if (!bands || !bands.length) return '阵容待定'
  return bands.join(' / ')
}

async function loadLives() {
  lives.value = await getActiveAll()
  lastSyncedAt.value = await getMeta('last_synced_at')
}

async function refresh() {
  if (syncing.value) return
  syncing.value = true
  lastError.value = ''
  try {
    await incrementalSync()
    offline.value = false
    await loadLives()
  } catch (e) {
    await handleIncrementalError(e)
  } finally {
    syncing.value = false
    progress.value = null
    uni.stopPullDownRefresh()
  }
}

async function handleIncrementalError(e) {
  // 网络异常：保留本地缓存，提示离线模式（V4.4 §18）
  if (e && (e.network || e.code === 'NETWORK_ERROR')) {
    offline.value = true
    return
  }
  try {
    // refetch_full（清空并重新 /full）/ backoff_retry（退避重试）
    await handleSyncError(e)
    offline.value = false
    await loadLives()
  } catch (e2) {
    if (e2 && (e2.network || e2.code === 'NETWORK_ERROR')) {
      offline.value = true
    } else {
      lastError.value = (e2 && e2.message) || '同步失败，请稍后重试'
    }
  }
}

onShow(async () => {
  try {
    await openDB()
    const scope = await getMeta('scope')
    if (!scope || !scope.city) {
      // 尚未选择过城市 → 去城市切换页完成首次全量同步
      uni.reLaunch({ url: '/pages/settings/city-switch' })
      return
    }
    city.value = scope.city
    await loadLives()
    // 尽力补全场地名（离线时静默失败，回退「场地 #id」）
    await ensureVenueMap()
    await refresh()
  } catch (e) {
    lastError.value = (e && e.message) || '初始化失败'
  }
})

onPullDownRefresh(() => {
  refresh()
})

function goDetail(id) {
  uni.navigateTo({ url: '/pages/gigs/detail?id=' + id })
}

function goCitySwitch() {
  uni.navigateTo({ url: '/pages/settings/city-switch' })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24rpx;
  background: var(--color-surface, #ffffff);
}
.city-name {
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.city-arrow {
  margin-left: 8rpx;
  font-size: 32rpx;
  color: var(--color-text-muted, #9ca3af);
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 160rpx 48rpx;
}
.empty-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-muted, #9ca3af);
}

.list-wrap {
  padding: 16rpx 24rpx 40rpx;
}
.day-group {
  margin-top: 24rpx;
}
.day-header {
  padding: 8rpx 8rpx 16rpx;
  font-size: var(--font-size-sm, 26rpx);
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
}
.live-card {
  display: flex;
  align-items: center;
  padding: 20rpx;
  margin-bottom: 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.poster-block {
  flex-shrink: 0;
  width: 140rpx;
  height: 140rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 20rpx;
  border-radius: 12rpx;
}
.poster-char {
  font-size: 56rpx;
  font-weight: 600;
  color: #ffffff;
}
.live-info {
  flex: 1;
  min-width: 0;
}
.live-title {
  display: block;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.live-bands {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.live-meta {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.live-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10rpx;
}
.live-time {
  font-size: var(--font-size-sm, 26rpx);
  font-weight: 600;
  color: var(--color-primary, #e5484d);
}
.live-price {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text, #1f2329);
}
.list-footer {
  padding: 32rpx 0;
  text-align: center;
}
.footer-text {
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
