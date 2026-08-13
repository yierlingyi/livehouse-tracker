
<template>
  <view class="dashboard-page">
    <view class="dash-header">
      <text class="dash-hello">你好，{{ bandName || '乐队' }}</text>
      <text class="dash-sub">管理你的演出与发布</text>
    </view>

    <view class="entry-card" @click="goNew">
      <view class="entry-icon entry-icon-primary">
        <text class="entry-icon-text">＋</text>
      </view>
      <view class="entry-body">
        <text class="entry-title">新建 Live</text>
        <text class="entry-desc">创建一场新的演出并发布</text>
      </view>
      <text class="entry-arrow">›</text>
    </view>

    <view class="entry-card" @click="goDrafts">
      <view class="entry-icon">
        <text class="entry-icon-text">✎</text>
      </view>
      <view class="entry-body">
        <text class="entry-title">草稿箱</text>
        <text class="entry-desc">{{ draftCount }} 场未发布的演出</text>
      </view>
      <text class="entry-arrow">›</text>
    </view>

    <view class="entry-card" @click="goPublished">
      <view class="entry-icon">
        <text class="entry-icon-text">♪</text>
      </view>
      <view class="entry-body">
        <text class="entry-title">已发布 Live</text>
        <text class="entry-desc">{{ publishedCount }} 场在线的演出</text>
      </view>
      <text class="entry-arrow">›</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { requireAuth } from '../../common/guard.js'
import { getBandMe } from '../../services/band-api.js'

const bandName = ref('')
const draftCount = ref(0)
const publishedCount = ref(0)

onShow(() => {
  if (!requireAuth({ endpoint: 'band' })) return
  loadMe()
})

async function loadMe() {
  try {
    const res = await getBandMe()
    if (res && res.band) {
      bandName.value = res.band.name || ''
    }
    if (res && res.lives) {
      draftCount.value = res.lives.draft || 0
      publishedCount.value = res.lives.published || 0
    }
  } catch (err) {
    // 401 已由 http.js 处理；其余错误静默
  }
}

function goNew() {
  uni.navigateTo({ url: '/pages/dashboard/live-edit' })
}
function goDrafts() {
  uni.navigateTo({ url: '/pages/dashboard/drafts' })
}
function goPublished() {
  uni.navigateTo({ url: '/pages/dashboard/published' })
}
</script>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  padding: 32rpx 24rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.dash-header {
  padding: 24rpx 8rpx 32rpx;
}
.dash-hello {
  display: block;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}
.dash-sub {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
.entry-card {
  display: flex;
  align-items: center;
  padding: 28rpx 24rpx;
  margin-bottom: 20rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.04);
}
.entry-icon {
  flex-shrink: 0;
  width: 88rpx;
  height: 88rpx;
  border-radius: 20rpx;
  background: var(--color-bg, #f5f6f8);
  display: flex;
  align-items: center;
  justify-content: center;
}
.entry-icon-primary {
  background: var(--color-primary, #e5484d);
}
.entry-icon-text {
  font-size: 44rpx;
  color: var(--color-primary, #e5484d);
}
.entry-icon-primary .entry-icon-text {
  color: #ffffff;
}
.entry-body {
  flex: 1;
  min-width: 0;
  margin-left: 24rpx;
}
.entry-title {
  display: block;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.entry-desc {
  display: block;
  margin-top: 6rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
.entry-arrow {
  flex-shrink: 0;
  font-size: 48rpx;
  color: var(--color-text-muted, #9ca3af);
}
</style>
