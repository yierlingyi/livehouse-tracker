<template>
  <view class="sync-status" :class="{ offline }">
    <view class="sync-status-left">
      <view v-if="syncing" class="spinner" />
      <view v-else class="dot" :class="offline ? 'dot-fail' : 'dot-ok'" />
      <text class="status-text">
        <template v-if="syncing">{{ syncingText }}</template>
        <template v-else>{{ lastSyncedText }}</template>
      </text>
    </view>
    <text v-if="offline" class="offline-tag">离线模式</text>
    <text v-else-if="syncing" class="progress-text">{{ progressText }}</text>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  syncing: { type: Boolean, default: false },
  lastSyncedAt: { type: Number, default: null },
  offline: { type: Boolean, default: false },
  progress: { type: Object, default: null }
})

const lastSyncedText = computed(() => {
  if (!props.lastSyncedAt) return '上次同步：从未同步'
  const mins = Math.floor((Date.now() - props.lastSyncedAt) / 60000)
  if (mins < 1) return '上次同步：刚刚'
  if (mins < 60) return '上次同步：' + mins + ' 分钟前'
  const hours = Math.floor(mins / 60)
  if (hours < 24) return '上次同步：' + hours + ' 小时前'
  const days = Math.floor(hours / 24)
  return '上次同步：' + days + ' 天前'
})

const syncingText = computed(() => {
  const p = props.progress
  if (p && p.stage === 'full') {
    return '正在同步演出数据（第 ' + p.page + ' 页）'
  }
  if (p && p.stage === 'sync') return '正在应用增量更新...'
  return '正在同步...'
})

const progressText = computed(() => {
  const p = props.progress
  if (!p) return ''
  if (p.stage === 'full') return p.received + ' 条'
  return '更新中'
})
</script>

<style scoped>
.sync-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.sync-status-left {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.spinner {
  width: 28rpx;
  height: 28rpx;
  border: 3rpx solid var(--color-border, #e5e7eb);
  border-top-color: var(--color-primary, #e5484d);
  border-radius: 50%;
  animation: sync-spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes sync-spin {
  to { transform: rotate(360deg); }
}
.dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-ok {
  background: var(--color-success, #16a34a);
}
.dot-fail {
  background: var(--color-warning, #f59e0b);
}
.status-text {
  margin-left: 14rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.offline-tag {
  flex-shrink: 0;
  margin-left: 12rpx;
  padding: 2rpx 12rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: #b45309;
  background: #fef3c7;
  border-radius: 6rpx;
}
.progress-text {
  flex-shrink: 0;
  margin-left: 12rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
