
<template>
  <view class="login-page">
    <view class="login-card">
      <view class="login-head">
        <text class="login-title">乐队工作台</text>
        <text class="login-sub">登录乐队账号</text>
      </view>

      <view class="field">
        <text class="field-label">账号</text>
        <input
          v-model="username"
          class="field-input"
          placeholder="请输入乐队账号"
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
          @confirm="doLogin"
        />
      </view>

      <view class="remember-row" @click="remember = !remember">
        <view class="checkbox" :class="{ checked: remember }">
          <text v-if="remember" class="checkbox-mark">✓</text>
        </view>
        <text class="remember-text">记住密码</text>
      </view>

      <button class="login-btn" :loading="loading" :disabled="loading" @click="doLogin">
        登 录
      </button>

      <view class="register-link" @click="goRegister">
        <text class="register-text">没有账号？去注册</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { login } from '../../services/auth.js'
import { setToken, setAccount, getRemembered, setRemembered } from '../../common/storage.js'

const username = ref('')
const password = ref('')
const remember = ref(false)
const loading = ref(false)

onLoad((query) => {
  if (query && query.reason === 'session_expired') {
    uni.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
  }
  const remembered = getRemembered()
  if (remembered && remembered.username) {
    username.value = remembered.username
    password.value = remembered.password || ''
    remember.value = true
  }
})

function goRegister() {
  uni.navigateTo({ url: '/pages/login/register' })
}

async function doLogin() {
  if (loading.value) return
  const u = String(username.value || '').trim()
  const p = String(password.value || '')
  if (!u || !p) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await login({ username: u, password: p })
    if (res && res.token) {
      setToken(res.token)
      setAccount(res.account || null)
    }
    // 记住密码：勾选存，未勾选清除
    if (remember.value) {
      setRemembered(u, p)
    } else {
      setRemembered('')
    }
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => {
      uni.reLaunch({ url: '/pages/dashboard/index' })
    }, 400)
  } catch (err) {
    if (err && err.code === 'PENDING') {
      uni.showModal({
        title: '提示',
        content: '账号审核中，请等待管理员审核',
        showCancel: false,
        confirmText: '知道了'
      })
      return
    }
    uni.showToast({ title: (err && err.message) || '登录失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  padding: 120rpx 40rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.login-card {
  padding: 48rpx 40rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.06);
}
.login-head {
  margin-bottom: 40rpx;
  text-align: center;
}
.login-title {
  display: block;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}
.login-sub {
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
.remember-row {
  display: flex;
  align-items: center;
  margin: 8rpx 0 32rpx;
}
.checkbox {
  width: 36rpx;
  height: 36rpx;
  border-radius: 8rpx;
  border: 2rpx solid var(--color-border, #e5e7eb);
  background: var(--color-bg, #f5f6f8);
  display: flex;
  align-items: center;
  justify-content: center;
}
.checkbox.checked {
  border-color: var(--color-primary, #e5484d);
  background: var(--color-primary, #e5484d);
}
.checkbox-mark {
  font-size: 24rpx;
  color: #ffffff;
  line-height: 1;
}
.remember-text {
  margin-left: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.login-btn {
  height: 92rpx;
  line-height: 92rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: 12rpx;
}
.login-btn[disabled] {
  opacity: 0.7;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
.register-link {
  margin-top: 32rpx;
  text-align: center;
}
.register-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-primary, #e5484d);
}
</style>
