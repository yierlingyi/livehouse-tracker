<template>
  <view class="list-card" @click="$emit('click')">
    <!-- 缩略图（无图显示占位） -->
    <image v-if="thumb" class="card-thumb" :src="resolveImageUrl(thumb)" mode="aspectFill" />
    <view v-else class="card-thumb card-thumb-ph">
      <text class="card-thumb-ph-text">♪</text>
    </view>

    <!-- 主体 -->
    <view class="card-body">
      <text class="card-title">{{ title }}</text>
      <text v-if="sub" class="card-sub">{{ sub }}</text>
      <text v-if="caption" class="card-caption">{{ caption }}</text>
    </view>

    <!-- 右侧扩展区（具名插槽 extra；无 extra 时可用默认插槽） -->
    <view v-if="$slots.extra" class="card-extra">
      <slot name="extra" />
    </view>
    <view v-else-if="$slots.default" class="card-extra">
      <slot />
    </view>
  </view>
</template>

<script setup>
import { resolveImageUrl } from '../http.js'

defineProps({
  title: { type: String, default: '' },
  sub: { type: String, default: '' },
  caption: { type: String, default: '' },
  thumb: { type: String, default: '' }
})

defineEmits(['click'])
</script>

<style scoped>
.list-card {
  display: flex;
  align-items: center;
  padding: 20rpx;
  margin-bottom: 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.card-thumb {
  flex-shrink: 0;
  width: 96rpx;
  height: 96rpx;
  border-radius: 12rpx;
  margin-right: 20rpx;
}
.card-thumb-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-border, #e5e7eb);
}
.card-thumb-ph-text {
  font-size: 40rpx;
  color: var(--color-text-muted, #9ca3af);
}
.card-body {
  flex: 1;
  min-width: 0;
}
.card-title {
  display: block;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.card-sub {
  display: block;
  margin-top: 6rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.card-caption {
  display: block;
  margin-top: 6rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
.card-extra {
  flex-shrink: 0;
  margin-left: 12rpx;
}
</style>
