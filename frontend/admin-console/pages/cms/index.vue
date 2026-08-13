<template>
  <view class="page">
    <view class="header">
      <text class="title">内容管理</text>
    </view>

    <view class="menu">
      <view class="menu-item" @click="go('/pages/cms/groups')">
        <view class="menu-icon">群</view>
        <view class="menu-body">
          <text class="menu-title">同好群管理</text>
          <text class="menu-sub">维护城市社群群号（微信 / QQ）</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>

      <view class="menu-item" @click="go('/pages/cms/sponsor')">
        <view class="menu-icon menu-icon-sponsor">赞</view>
        <view class="menu-body">
          <text class="menu-title">赞助管理</text>
          <text class="menu-sub">编辑感谢文本与收款二维码</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>

      <view class="menu-item" @click="go('/pages/cms/project')">
        <view class="menu-icon menu-icon-project">项</view>
        <view class="menu-body">
          <text class="menu-title">项目声明管理</text>
          <text class="menu-sub">GitHub 地址 / 作者信息 / 开源协议</text>
        </view>
        <text class="menu-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { onShow } from '@dcloudio/uni-app'
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

.menu {
  padding: 24rpx;
}
.menu-item {
  display: flex;
  align-items: center;
  padding: 28rpx 24rpx;
  margin-bottom: 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.menu-icon {
  flex-shrink: 0;
  width: 72rpx;
  height: 72rpx;
  border-radius: 12rpx;
  background: var(--color-primary, #e5484d);
  color: #ffffff;
  font-size: var(--font-size-base, 28rpx);
  text-align: center;
  line-height: 72rpx;
}
.menu-icon-sponsor {
  background: var(--color-warning, #f59e0b);
}
.menu-icon-project {
  background: var(--color-success, #16a34a);
}
.menu-body {
  flex: 1;
  min-width: 0;
  margin-left: 20rpx;
}
.menu-title {
  display: block;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.menu-sub {
  display: block;
  margin-top: 6rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
.menu-arrow {
  flex-shrink: 0;
  font-size: 40rpx;
  color: var(--color-text-muted, #9ca3af);
}
</style>
