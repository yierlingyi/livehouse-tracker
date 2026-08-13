<template>
  <view class="page">
    <view class="login-header">
      <view class="login-logo">♪</view>
      <text class="login-title">乐队管理后台</text>
      <text class="login-sub">Admin Console</text>
    </view>

    <view class="login-form">
      <view class="form-field">
        <text class="field-label">账号</text>
        <input
          v-model="username"
          class="field-input"
          placeholder="请输入管理员账号"
          placeholder-class="ph"
          @confirm="doLogin"
        />
      </view>
      <view class="form-field">
        <text class="field-label">密码</text>
        <input
          v-model="password"
          class="field-input"
          password
          placeholder="请输入密码"
          placeholder-class="ph"
          @confirm="doLogin"
        />
      </view>

      <button class="login-btn" :loading="loading" @click="doLogin">登 录</button>
      <text class="login-hint">无公开注册，管理员账号由系统内部创建</text>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { adminLogin } from '../../services/admin-api.js'
import { setToken, setAccount } from '../../common/storage.js'

const username = ref('')
const password = ref('')
const loading = ref(false)

async function doLogin() {
  if (loading.value) return
  const uname = String(username.value || '').trim()
  if (!uname || !password.value) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await adminLogin({ username: uname, password: password.value })
    const token = res && res.token
    const account = res && res.account
    if (!token) throw new Error('登录响应缺少 token')
    setToken(token)
    setAccount(account)
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => {
      uni.reLaunch({ url: '/pages/shows/index' })
    }, 400)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '登录失败，请稍后重试', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  display: flex;
  flex-direction: column;
}

.login-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 120rpx 48rpx 72rpx;
}
.login-logo {
  width: 128rpx;
  height: 128rpx;
  border-radius: 50%;
  background: var(--color-primary, #e5484d);
  color: #ffffff;
  font-size: 64rpx;
  text-align: center;
  line-height: 128rpx;
  margin-bottom: 28rpx;
}
.login-title {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}
.login-sub {
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.login-form {
  padding: 32rpx 40rpx 48rpx;
}
.form-field {
  margin-bottom: 28rpx;
}
.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.field-input {
  height: 88rpx;
  padding: 0 28rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.ph {
  color: var(--color-text-muted, #9ca3af);
}

.login-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin-top: 16rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}
.login-btn[disabled] {
  opacity: 0.7;
}

.login-hint {
  display: block;
  margin-top: 28rpx;
  text-align: center;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
