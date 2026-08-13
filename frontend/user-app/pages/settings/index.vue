<template>
  <view class="page">
    <view class="group">
      <view class="menu-row" @click="go('/pages/settings/city-switch')">
        <text class="menu-label">城市选择</text>
        <text class="menu-value">{{ city || '未选择' }}</text>
        <text class="menu-arrow">›</text>
      </view>

      <view class="menu-row">
        <text class="menu-label">主题切换</text>
        <ThemeSwitch />
      </view>

      <view class="menu-row" @click="go('/pages/settings/community-groups')">
        <text class="menu-label">同好群</text>
        <text class="menu-arrow">›</text>
      </view>

      <view class="menu-row" @click="go('/pages/settings/sponsor')">
        <text class="menu-label">赞助</text>
        <text class="menu-arrow">›</text>
      </view>

      <view class="menu-row" @click="go('/pages/settings/project')">
        <text class="menu-label">项目声明</text>
        <text class="menu-arrow">›</text>
      </view>
    </view>

    <view class="footer">
      <text class="footer-text">乐队演出 · 普通用户端</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ThemeSwitch from '../../common/components/ThemeSwitch.vue'
import { getMeta } from '../../services/db.js'

const city = ref('')

onShow(async () => {
  try {
    const scope = await getMeta('scope')
    if (scope && scope.city) city.value = scope.city
  } catch (e) {
    /* 忽略：尚未同步时显示「未选择」 */
  }
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

.group {
  margin: 24rpx;
  padding: 8rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.menu-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.menu-row:last-child {
  border-bottom: none;
}
.menu-label {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.menu-value {
  flex: 1;
  margin-left: 24rpx;
  text-align: right;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.menu-arrow {
  margin-left: 12rpx;
  font-size: 32rpx;
  color: var(--color-text-muted, #9ca3af);
}

.footer {
  padding: 48rpx 0;
  text-align: center;
}
.footer-text {
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
