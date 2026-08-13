
<template>
  <view class="register-page">
    <view class="register-card">
      <view class="register-head">
        <text class="register-title">乐队注册</text>
        <text class="register-sub">注册后需管理员审核通过方可登录</text>
      </view>

      <view class="field">
        <text class="field-label">乐队名称</text>
        <input
          v-model="bandName"
          class="field-input"
          placeholder="请输入乐队名称"
          placeholder-class="field-input-ph"
          :maxlength="32"
        />
      </view>

      <view class="field">
        <text class="field-label">账号</text>
        <input
          v-model="username"
          class="field-input"
          placeholder="用于登录的账号"
          placeholder-class="field-input-ph"
          :maxlength="32"
        />
      </view>

      <view class="field">
        <text class="field-label">密码</text>
        <input
          v-model="password"
          class="field-input"
          type="password"
          placeholder="请输入密码"
          placeholder-class="field-input-ph"
          :maxlength="64"
          @confirm="doRegister"
        />
      </view>

      <button class="register-btn" :loading="loading" :disabled="loading" @click="doRegister">
        注 册
      </button>

      <view class="back-link" @click="goBack">
        <text class="back-text">已有账号？去登录</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { register } from '../../services/auth.js'

const bandName = ref('')
const username = ref('')
const password = ref('')
const loading = ref(false)

function goBack() {
  uni.navigateBack({
    fail: () => uni.reLaunch({ url: '/pages/login/index' })
  })
}

async function doRegister() {
  if (loading.value) return
  const band = String(bandName.value || '').trim()
  const u = String(username.value || '').trim()
  const p = String(password.value || '')
  if (!band || !u || !p) {
    uni.showToast({ title: '请填写完整的乐队名称、账号与密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    await register({ username: u, password: p, band_name: band })
    uni.showModal({
      title: '注册成功',
      content: '注册成功，等待管理员审核',
      showCancel: false,
      confirmText: '去登录',
      success: () => {
        uni.reLaunch({ url: '/pages/login/index' })
      }
    })
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '注册失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  padding: 120rpx 40rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.register-card {
  padding: 48rpx 40rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.06);
}
.register-head {
  margin-bottom: 40rpx;
  text-align: center;
}
.register-title {
  display: block;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}
.register-sub {
  display: block;
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
.field {
  margin-bottom: 24rpx;
}
.field-label {
  display: block;
  margin-bottom: 10rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.field-input {
  height: 88rpx;
  padding: 0 24rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-bg, #f5f6f8);
  border-radius: 12rpx;
}
.field-input-ph {
  color: var(--color-text-muted, #9ca3af);
}
.register-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin-top: 8rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: 12rpx;
}
.register-btn[disabled] {
  opacity: 0.7;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
.back-link {
  margin-top: 32rpx;
  text-align: center;
}
.back-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-primary, #e5484d);
}
</style>
