<template>
  <view class="page">
    <view class="form-card">
      <FormField label="用户名" required>
        <input v-model="username" class="input" placeholder="请输入管理员用户名" />
      </FormField>

      <FormField label="密码" required>
        <input v-model="password" class="input" password placeholder="请输入密码" />
      </FormField>
    </view>

    <button class="save-btn" :loading="saving" @click="save">新增管理员</button>
    <text class="hint">新增的管理员账号可用于管理员后台登录</text>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import FormField from '../../common/components/FormField.vue'
import { requireAuth } from '../../common/guard.js'
import { createAdminAccount } from '../../services/admin-api.js'

const username = ref('')
const password = ref('')
const saving = ref(false)

onLoad(() => {
  requireAuth({ endpoint: 'admin' })
})

async function save() {
  const uname = String(username.value || '').trim()
  if (!uname || !password.value) {
    uni.showToast({ title: '请填写用户名和密码', icon: 'none' })
    return
  }
  saving.value = true
  try {
    await createAdminAccount({ username: uname, password: password.value })
    uni.showToast({ title: '新增成功', icon: 'success' })
    username.value = ''
    password.value = ''
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '新增失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 60rpx;
}

.form-card {
  margin: 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}

.input {
  width: 100%;
  height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}

.save-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin: 24rpx 24rpx 0;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}

.hint {
  display: block;
  margin: 24rpx;
  text-align: center;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
