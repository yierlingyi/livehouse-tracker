<template>
  <view class="empty-state">
    <view class="empty-icon">♪</view>
    <text class="empty-text">{{ text }}</text>
  </view>
</template>

<script setup>
defineProps({
  text: { type: String, default: '暂无数据' }
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 160rpx 48rpx;
}
.empty-icon {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: var(--color-border, #e5e7eb);
  color: var(--color-text-muted, #9ca3af);
  font-size: 56rpx;
  text-align: center;
  line-height: 120rpx;
}
.empty-text {
  margin-top: 24rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
