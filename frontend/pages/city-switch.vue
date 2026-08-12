<template>
  <view class="page">
    <view class="header">
      <text class="title">选择城市</text>
    </view>

    <!-- 错误提示 -->
    <ErrorPage
      v-if="error && !syncing"
      :message="error"
      @retry="retryLast"
    />

    <!-- 城市列表 -->
    <view v-if="!syncing && !error" class="city-list">
      <view
        v-for="c in cities"
        :key="c"
        class="city-item"
        :class="{ current: c === currentCity }"
        @click="selectCity(c)"
      >
        <text class="city-name">{{ c }}</text>
        <text v-if="c === currentCity" class="city-check">当前</text>
      </view>
    </view>

    <!-- 首次同步进度 -->
    <view v-if="syncing" class="syncing-box">
      <text class="syncing-title">正在同步 {{ syncingCity }} 的演出数据</text>
      <view class="progress-track">
        <view class="progress-fill" :style="{ width: progressPercent + '%' }" />
      </view>
      <text class="syncing-detail">{{ progressText }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import ErrorPage from '../components/ErrorPage.vue'
import { getMeta } from '../services/db.js'
import { firstSync } from '../services/sync_engine.js'

const CITIES = ['Tokyo', 'Osaka', 'Shanghai', 'Beijing', 'Guangzhou', 'Shenzhen']

const cities = CITIES
const currentCity = ref('')
const syncing = ref(false)
const syncingCity = ref('')
const progress = ref(null)
const error = ref('')
const lastChosen = ref('')

const progressPercent = computed(() => {
  const p = progress.value
  if (!p) return 0
  if (p.stage === 'sync') return 92
  // /full 阶段按已拉取页数估算（页数未知，进度条仅作粗略示意）
  return Math.max(5, Math.min(90, p.page * 8))
})

const progressText = computed(() => {
  const p = progress.value
  if (!p) return ''
  if (p.stage === 'full') return '正在拉取演出列表... 已获取 ' + p.received + ' 条'
  return '正在应用增量更新...'
})

onLoad(async () => {
  try {
    const scope = await getMeta('scope')
    if (scope && scope.city) currentCity.value = scope.city
  } catch (e) {
    /* 忽略：首次进入无本地状态 */
  }
})

async function selectCity(c) {
  if (syncing.value) return
  lastChosen.value = c
  syncingCity.value = c
  syncing.value = true
  error.value = ''
  progress.value = { stage: 'full', page: 0, received: 0 }
  try {
    await firstSync(c, (p) => { progress.value = p })
    // 同步完成 → 回首页展示
    uni.reLaunch({ url: '/pages/index' })
  } catch (e) {
    error.value = (e && e.message) || '同步失败，请检查网络后重试'
  } finally {
    syncing.value = false
  }
}

function retryLast() {
  if (lastChosen.value) selectCity(lastChosen.value)
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.header {
  padding: 32rpx 24rpx;
  background: var(--color-surface, #ffffff);
}
.title {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}

.city-list {
  padding: 24rpx;
}
.city-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx 24rpx;
  margin-bottom: 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.city-name {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.city-check {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-primary, #e5484d);
}
.city-item.current {
  border: 1rpx solid var(--color-primary, #e5484d);
}

.syncing-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 48rpx;
}
.syncing-title {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.progress-track {
  width: 100%;
  height: 16rpx;
  margin-top: 32rpx;
  background: #e5e7eb;
  border-radius: 8rpx;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--color-primary, #e5484d);
  border-radius: 8rpx;
  transition: width 0.3s ease;
}
.syncing-detail {
  margin-top: 20rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
</style>
