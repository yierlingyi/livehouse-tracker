<template>
  <view class="error-page">
    <view class="error-icon">!</view>
    <text class="error-title">出错了</text>
    <text class="error-message">{{ message }}</text>
    <button v-if="showRetry" class="retry-btn" @click="$emit('retry')">重试</button>
  </view>
</template>

<script setup>
defineProps({
  message: { type: String, default: '加载失败，请稍后重试' },
  showRetry: { type: Boolean, default: true }
})

defineEmits(['retry'])
</script>

<style scoped>
.error-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120rpx 48rpx;
}
.error-icon {
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  background: #fee2e2;
  color: var(--color-primary, #e5484d);
  font-size: 56rpx;
  font-weight: 600;
  text-align: center;
  line-height: 96rpx;
}
.error-title {
  margin-top: 28rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.error-message {
  margin-top: 12rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
  text-align: center;
  word-break: break-all;
}
.retry-btn {
  margin-top: 48rpx;
  width: 320rpx;
  height: 80rpx;
  line-height: 80rpx;
  font-size: var(--font-size-base, 28rpx);
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: 40rpx;
  text-align: center;
}
</style>
