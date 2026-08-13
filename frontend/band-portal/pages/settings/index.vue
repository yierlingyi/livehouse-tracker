
<template>
  <view class="settings-page">
    <view class="card">
      <view class="row">
        <text class="row-label">主题</text>
        <ThemeSwitch />
      </view>
    </view>

    <view class="card">
      <view class="row">
        <text class="row-label">乐队名称</text>
        <text class="row-value">{{ bandName || '未设置' }}</text>
      </view>
      <view class="row">
        <text class="row-label">登录账号</text>
        <text class="row-value">{{ username || '-' }}</text>
      </view>
      <view class="row">
        <text class="row-label">QQ 绑定</text>
        <text class="row-value" :class="{ 'row-value-empty': !qqBind }">{{ qqBind || '未绑定' }}</text>
      </view>
    </view>

    <view class="card">
      <view class="action" @click="confirmLogout">
        <text class="action-text">登出</text>
      </view>
    </view>

    <view class="card">
      <view class="action" @click="switchAccount">
        <text class="action-text">切换账号</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { requireAuth } from '../../common/guard.js'
import { logout } from '../../services/auth.js'
import { getBandMe } from '../../services/band-api.js'
import { clearAuth } from '../../common/storage.js'
import ThemeSwitch from '../../common/components/ThemeSwitch.vue'

const bandName = ref('')
const username = ref('')
const qqBind = ref('')

onShow(() => {
  if (!requireAuth({ endpoint: 'band' })) return
  loadMe()
})

async function loadMe() {
  try {
    const res = await getBandMe()
    if (res) {
      bandName.value = (res.band && res.band.name) || ''
      qqBind.value = (res.band && res.band.qq_bind) || ''
      username.value = (res.account && res.account.username) || ''
    }
  } catch (err) {
    // 401 已由 http.js 处理
  }
}

async function doLogout() {
  try {
    await logout()
  } catch (err) {
    /* 后端注销失败不阻塞本地登出 */
  }
  clearAuth()
  uni.reLaunch({ url: '/pages/login/index' })
}

function confirmLogout() {
  uni.showModal({
    title: '提示',
    content: '确定退出登录吗？',
    confirmText: '登出',
    confirmColor: '#e5484d',
    success: (res) => {
      if (res.confirm) doLogout()
    }
  })
}

function switchAccount() {
  uni.showModal({
    title: '切换账号',
    content: '确定切换账号吗？将退出当前登录。',
    confirmText: '切换',
    confirmColor: '#e5484d',
    success: (res) => {
      if (res.confirm) doLogout()
    }
  })
}
</script>

<style scoped>
.settings-page {
  min-height: 100vh;
  padding: 24rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.card {
  margin-bottom: 20rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 96rpx;
  padding: 0 28rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.row:last-child {
  border-bottom: none;
}
.row-label {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.row-value {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
}
.row-value-empty {
  color: var(--color-text-muted, #9ca3af);
}
.action {
  min-height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}
.action-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-primary, #e5484d);
  font-weight: 600;
}
</style>
