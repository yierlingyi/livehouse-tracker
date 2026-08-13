<template>
  <view class="theme-switch" @click="toggle">
    <view class="theme-track" :class="{ dark: isDark }">
      <view class="theme-thumb" :class="{ dark: isDark }" />
    </view>
    <text class="theme-label">{{ isDark ? '暗色模式' : '亮色模式' }}</text>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { getTheme, setTheme } from '../theme.js'

const isDark = ref(getTheme() === 'dark')

function toggle() {
  isDark.value = !isDark.value
  setTheme(isDark.value ? 'dark' : 'light')
}
</script>

<style scoped>
.theme-switch {
  display: flex;
  align-items: center;
}
.theme-track {
  position: relative;
  width: 96rpx;
  height: 52rpx;
  border-radius: 26rpx;
  background: var(--color-border, #e5e7eb);
  transition: background 0.2s ease;
}
.theme-track.dark {
  background: var(--color-primary, #e5484d);
}
.theme-thumb {
  position: absolute;
  top: 6rpx;
  left: 6rpx;
  width: 40rpx;
  height: 40rpx;
  border-radius: 50%;
  background: var(--color-surface, #ffffff);
  transition: transform 0.2s ease;
  box-shadow: 0 2rpx 6rpx rgba(0, 0, 0, 0.2);
}
.theme-thumb.dark {
  transform: translateX(44rpx);
}
.theme-label {
  margin-left: 16rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
</style>
