<template>
  <view class="page">
    <view class="header">
      <text class="title">系统设置</text>
    </view>

    <view class="group">
      <view class="group-item">
        <text class="group-label">主题</text>
        <ThemeSwitch />
      </view>
    </view>

    <view class="group">
      <view class="group-item" @click="go('/pages/settings/admin-add')">
        <text class="group-label">新增管理员</text>
        <text class="group-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { onShow } from '@dcloudio/uni-app'
import ThemeSwitch from '../../common/components/ThemeSwitch.vue'
import { requireAuth } from '../../common/guard.js'

onShow(() => {
  requireAuth({ endpoint: 'admin' })
})

function go(url) {
  uni.navigateTo({ url })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.header {
  padding: 28rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.title {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}

.group {
  margin: 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 24rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.group-item:last-child {
  border-bottom: none;
}
.group-label {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.group-arrow {
  font-size: 40rpx;
  color: var(--color-text-muted, #9ca3af);
}
</style>
