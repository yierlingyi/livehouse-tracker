<template>
  <view class="page">
    <ErrorPage
      v-if="error && !live"
      :message="error"
      @retry="load"
    />

    <view v-else-if="live" class="detail">
      <!-- 海报：优先完整详情接口返回；失败用占位 -->
      <view class="poster-wrap">
        <image
          v-if="posterUrl && !posterError"
          class="poster"
          :src="posterUrl"
          mode="aspectFill"
          @error="posterError = true"
        />
        <view v-else class="poster-placeholder">
          <text class="placeholder-text">♪</text>
        </view>
      </view>

      <view class="body">
        <view class="title-row">
          <text class="title">{{ live.title }}</text>
          <text class="tag" :class="statusClass">{{ statusText }}</text>
        </view>

        <view v-if="offline" class="offline-banner">离线模式 · 当前为基础缓存信息</view>

        <view class="info-card">
          <view class="info-row">
            <text class="info-label">日期</text>
            <text class="info-value">{{ formatDate(live.live_date) }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">时间</text>
            <text class="info-value">{{ formatTime(live.start_time) }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">场地</text>
            <text class="info-value">{{ venueName }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">地址</text>
            <text class="info-value">{{ venueAddress || '待定' }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">票价</text>
            <text class="info-value">{{ priceText }}</text>
          </view>
        </view>

        <view class="section">
          <text class="section-title">演出阵容</text>
          <view class="band-list">
            <text
              v-for="(b, i) in live.band_names"
              :key="i"
              class="band-item"
            >{{ b }}</text>
            <text v-if="!live.band_names || !live.band_names.length" class="band-empty">
              阵容待定
            </text>
          </view>
        </view>

        <!-- 曲目单（来自 /lives/{id} 完整详情） -->
        <view v-if="setlist.length" class="section">
          <text class="section-title">曲目单</text>
          <view class="setlist">
            <view
              v-for="(s, i) in setlist"
              :key="i"
              class="setlist-item"
            >
              <text class="setlist-index">{{ i + 1 }}</text>
              <text class="setlist-song">{{ s.song_title }}</text>
            </view>
          </view>
        </view>

        <button
          v-if="ticketUrl"
          class="buy-btn"
          @click="openTicket"
        >立即购票</button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import ErrorPage from '../../components/ErrorPage.vue'
import { openDB, getActiveById } from '../../services/db.js'
import { fetchLiveDetail } from '../../services/api.js'
import { formatDate, formatTime, formatPrice } from '../../common/format.js'
import { resolveImageUrl } from '../../common/http.js'

const live = ref(null)
const full = ref(null) // {live, venue, setlist, poster_image_url}
const error = ref('')
const posterError = ref(false)
const offline = ref(false)

const STATUS_TEXT = {
  announced: '已公布',
  on_sale: '售票中',
  completed: '已结束',
  cancelled: '已取消'
}
const STATUS_CLASS = {
  announced: 'status-announced',
  on_sale: 'status-on-sale',
  completed: 'status-completed',
  cancelled: 'status-cancelled'
}

const statusText = computed(() => {
  if (!live.value) return ''
  return STATUS_TEXT[live.value.status] || live.value.status || ''
})
const statusClass = computed(() => {
  if (!live.value) return ''
  return STATUS_CLASS[live.value.status] || ''
})

const posterUrl = computed(() => {
  const f = full.value
  const l = live.value
  const raw = (f && f.poster_image_url) || (l && l.poster_image_url) || ''
  return resolveImageUrl(raw)
})
const venueName = computed(() => {
  const f = full.value
  const l = live.value
  if (f && f.venue && f.venue.name) return f.venue.name
  return '场地 #' + (l && l.livehouse_id != null ? l.livehouse_id : '?')
})
const venueAddress = computed(() => {
  return (full.value && full.value.venue && full.value.venue.address) || ''
})
const setlist = computed(() => {
  return (full.value && full.value.setlist) || []
})
const ticketUrl = computed(() => {
  const f = full.value
  const l = live.value
  return (f && f.live && f.live.ticket_url) || (l && l.ticket_url) || ''
})
const priceText = computed(() => {
  const f = full.value
  const l = live.value
  const price = f && f.live && f.live.ticket_price != null
    ? f.live.ticket_price
    : (l && l.ticket_price)
  return formatPrice(price)
})

let detailId = ''

async function load() {
  error.value = ''
  posterError.value = false
  offline.value = false
  try {
    await openDB()
    // 1. base 从 active_store 缓存读
    const base = await getActiveById(detailId)
    if (!base) {
      // 缓存缺失 → 尝试在线直接拉详情
      live.value = null
      try {
        const res = await fetchLiveDetail(detailId)
        full.value = res
        live.value = (res && res.live) || null
        if (!live.value) error.value = '未找到该演出'
      } catch (e2) {
        error.value = '未找到该演出'
      }
      return
    }
    live.value = base

    // 2. 拉完整详情（海报/场地地址/setlist）；失败降级为缓存基础信息
    try {
      const res = await fetchLiveDetail(detailId)
      full.value = res
    } catch (e) {
      full.value = null
      offline.value = !!(e && (e.network || e.code === 'NETWORK_ERROR'))
    }
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  }
}

onLoad((options) => {
  detailId = (options && options.id) || ''
  load()
})

function openTicket() {
  const url = ticketUrl.value
  if (!url) return
  // #ifdef H5
  window.open(url, '_blank')
  // #endif
  // #ifndef H5
  uni.setClipboardData({
    data: url,
    success: () => uni.showToast({ title: '购票链接已复制', icon: 'none' })
  })
  // #endif
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.detail {
  padding-bottom: 60rpx;
}

.poster-wrap {
  width: 100%;
  height: 480rpx;
  background: #e5e7eb;
}
.poster {
  width: 100%;
  height: 480rpx;
}
.poster-placeholder {
  width: 100%;
  height: 480rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e5e7eb;
}
.placeholder-text {
  font-size: 120rpx;
  color: #9ca3af;
}

.body {
  padding: 24rpx;
}
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.title {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
  line-height: 1.4;
}
.tag {
  flex-shrink: 0;
  margin-left: 16rpx;
  padding: 6rpx 16rpx;
  font-size: var(--font-size-xs, 22rpx);
  border-radius: 8rpx;
}
.status-announced { color: #1d4ed8; background: #dbeafe; }
.status-on-sale { color: #b91c1c; background: #fee2e2; }
.status-completed { color: #6b7280; background: #e5e7eb; }
.status-cancelled { color: #6b7280; background: #f3f4f6; }

.offline-banner {
  margin-top: 16rpx;
  padding: 12rpx 20rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: #b45309;
  background: #fef3c7;
  border-radius: 8rpx;
}

.info-card {
  margin-top: 24rpx;
  padding: 8rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.info-row:last-child {
  border-bottom: none;
}
.info-label {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
}
.info-value {
  flex: 1;
  margin-left: 24rpx;
  text-align: right;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  word-break: break-all;
}

.section {
  margin-top: 24rpx;
  padding: 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.section-title {
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.band-list {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}
.band-item {
  padding: 8rpx 20rpx;
  margin: 8rpx 12rpx 0 0;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-border, #e5e7eb);
  border-radius: 8rpx;
}
.band-empty {
  margin-top: 16rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.setlist {
  margin-top: 8rpx;
}
.setlist-item {
  display: flex;
  align-items: center;
  padding: 20rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.setlist-item:last-child {
  border-bottom: none;
}
.setlist-index {
  flex-shrink: 0;
  width: 48rpx;
  height: 48rpx;
  line-height: 48rpx;
  text-align: center;
  font-size: var(--font-size-sm, 26rpx);
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: 50%;
  margin-right: 20rpx;
}
.setlist-song {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}

.buy-btn {
  margin-top: 48rpx;
  height: 88rpx;
  line-height: 88rpx;
  font-size: var(--font-size-lg, 32rpx);
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: 44rpx;
}
</style>
