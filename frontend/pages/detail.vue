<template>
  <view class="page">
    <ErrorPage
      v-if="error && !live"
      :message="error"
      @retry="load"
    />

    <view v-else-if="live" class="detail">
      <!-- 海报（加载失败显示灰色占位，V4.4 §18） -->
      <view class="poster-wrap">
        <image
          v-if="live.poster_image_url && !posterError"
          class="poster"
          :src="live.poster_image_url"
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

        <view class="info-card">
          <view class="info-row">
            <text class="info-label">日期</text>
            <text class="info-value">{{ formatDate(live.live_date) }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">时间</text>
            <text class="info-value">{{ formatTime(live) }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">场地</text>
            <text class="info-value">场地 #{{ live.livehouse_id }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">票价</text>
            <text class="info-value">{{ live.ticket_price || '待定' }}</text>
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

        <button
          v-if="live.ticket_url"
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
import ErrorPage from '../components/ErrorPage.vue'
import { openDB, getActiveById } from '../services/db.js'

const live = ref(null)
const error = ref('')
const posterError = ref(false)

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

let detailId = ''

async function load() {
  error.value = ''
  posterError.value = false
  try {
    await openDB()
    live.value = await getActiveById(detailId)
    if (!live.value) error.value = '未找到该演出'
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  }
}

onLoad((options) => {
  detailId = (options && options.id) || ''
  load()
})

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return d.getMonth() + 1 + '月' + d.getDate() + '日 ' + weekdays[d.getDay()]
}

function formatTime(l) {
  if (l.start_time) return l.start_time.slice(0, 5)
  return '待定'
}

function openTicket() {
  if (!live.value || !live.value.ticket_url) return
  // #ifdef H5
  window.open(live.value.ticket_url, '_blank')
  // #endif
  // #ifndef H5
  uni.setClipboardData({
    data: live.value.ticket_url,
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
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
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
  background: #f3f4f6;
  border-radius: 8rpx;
}
.band-empty {
  margin-top: 16rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
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
