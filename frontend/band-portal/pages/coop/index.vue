<template>
  <view class="page">
    <view class="page-header">
      <text class="page-title">拼盘专区</text>
      <text class="page-sub">多乐队联合演出一站管理</text>
    </view>

    <view class="entry-list">
      <view class="entry-card" @click="goCreate">
        <view class="entry-icon entry-icon-primary">
          <text class="entry-icon-text">＋</text>
        </view>
        <view class="entry-body">
          <text class="entry-title">创建拼盘</text>
          <text class="entry-desc">发起多乐队联合 Live，邀请其他乐队并分配曲目</text>
        </view>
        <text class="entry-arrow">›</text>
      </view>

      <view class="entry-card" @click="goReceive">
        <view class="entry-icon entry-icon-blue">
          <text class="entry-icon-text">✉</text>
          <view v-if="inviteCount > 0" class="entry-badge">
            <text class="entry-badge-text">{{ inviteCount > 99 ? '99+' : inviteCount }}</text>
          </view>
        </view>
        <view class="entry-body">
          <text class="entry-title">接收拼盘</text>
          <text class="entry-desc">查看收到的拼盘邀请，同意、拒绝或修改本队曲目</text>
        </view>
        <text class="entry-arrow">›</text>
      </view>

      <view class="entry-card" @click="goManage">
        <view class="entry-icon entry-icon-green">
          <text class="entry-icon-text">≡</text>
        </view>
        <view class="entry-body">
          <text class="entry-title">管理拼盘</text>
          <text class="entry-desc">查看所有关联拼盘与实时状态，发起方审批退出、接收方变更状态</text>
        </view>
        <text class="entry-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import coopApi from '../../services/coop-api.js'
import { requireAuth } from '../../common/guard.js'

const inviteCount = ref(0)

function goCreate() {
  uni.navigateTo({ url: '/pages/coop/create' })
}
function goReceive() {
  uni.navigateTo({ url: '/pages/coop/receive' })
}
function goManage() {
  uni.navigateTo({ url: '/pages/coop/manage' })
}

async function loadBadge() {
  if (!requireAuth()) return
  try {
    const res = await coopApi.listInvites()
    inviteCount.value = (res && res.items || []).filter((i) => i.invite_status === 'invited').length
  } catch (e) {
    inviteCount.value = 0
  }
}

onShow(loadBadge)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 48rpx;
}
.page-header {
  padding: 40rpx 32rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.page-title {
  display: block;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.page-sub {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}

.entry-list {
  padding: 24rpx 24rpx 0;
}
.entry-card {
  display: flex;
  align-items: center;
  padding: 28rpx 24rpx;
  margin-bottom: 20rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}
.entry-icon {
  position: relative;
  flex-shrink: 0;
  width: 88rpx;
  height: 88rpx;
  margin-right: 24rpx;
  border-radius: 20rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.entry-icon-primary {
  background: rgba(229, 72, 77, 0.12);
}
.entry-icon-blue {
  background: rgba(59, 130, 246, 0.12);
}
.entry-icon-green {
  background: rgba(22, 163, 74, 0.12);
}
.entry-icon-text {
  font-size: 40rpx;
  color: var(--color-text, #1f2329);
}
.entry-badge {
  position: absolute;
  top: -12rpx;
  right: -12rpx;
  min-width: 36rpx;
  height: 36rpx;
  padding: 0 8rpx;
  border-radius: 18rpx;
  background: var(--color-primary, #e5484d);
  display: flex;
  align-items: center;
  justify-content: center;
}
.entry-badge-text {
  font-size: 22rpx;
  color: #ffffff;
  font-weight: 600;
}
.entry-body {
  flex: 1;
  min-width: 0;
}
.entry-title {
  display: block;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.entry-desc {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
  line-height: 1.5;
}
.entry-arrow {
  flex-shrink: 0;
  margin-left: 16rpx;
  font-size: 44rpx;
  color: var(--color-text-muted, #9ca3af);
}
</style>
