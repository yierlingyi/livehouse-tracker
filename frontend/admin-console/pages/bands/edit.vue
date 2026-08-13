<template>
  <view class="page">
    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>

    <template v-else-if="account">
      <view class="info-card">
        <view class="info-row">
          <text class="info-label">登录账号</text>
          <text class="info-value">{{ account.username }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">状态</text>
          <text class="info-value" :class="'status-' + account.status">{{ accountStatusText(account.status) }}</text>
        </view>
      </view>

      <view class="form-card">
        <view class="field-wrap">
          <text class="field-label">乐队名称</text>
          <input v-model="bandName" class="input" placeholder="请输入乐队名称" />
        </view>
        <view class="field-wrap">
          <text class="field-label">乐队简介</text>
          <textarea v-model="intro" class="textarea" placeholder="请输入乐队简介" />
        </view>
      </view>

      <button class="save-btn" :loading="saving" @click="save">保存修改</button>
      <button class="del-btn" :loading="deleting" @click="confirmDelete">删除账号</button>
    </template>

    <EmptyState v-else text="账号不存在" />
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import EmptyState from '../../common/components/EmptyState.vue'
import { requireAuth } from '../../common/guard.js'
import { ACCOUNT_STATUS } from '../../common/constants.js'
import { getBand, updateBand, deleteBand } from '../../services/admin-api.js'

const bandId = ref(null)
const loading = ref(true)
const saving = ref(false)
const deleting = ref(false)

const account = ref(null)
const bandName = ref('')
const intro = ref('')

onLoad(async (options) => {
  if (!requireAuth({ endpoint: 'admin' })) return
  bandId.value = options && options.id
  try {
    const res = await getBand(bandId.value)
    account.value = (res && res.account) || null
    const band = (res && res.band) || {}
    bandName.value = band.band_name || account.value.band_name || ''
    intro.value = band.intro || ''
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载账号失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function accountStatusText(s) {
  return ACCOUNT_STATUS[s] || s || '未知'
}

async function save() {
  if (!bandName.value.trim()) {
    uni.showToast({ title: '请填写乐队名称', icon: 'none' })
    return
  }
  saving.value = true
  try {
    await updateBand(bandId.value, {
      band_name: bandName.value.trim(),
      intro: intro.value
    })
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 400)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

function confirmDelete() {
  const name = account.value.band_name || account.value.username
  uni.showModal({
    title: '删除账号',
    content: '确定删除账号「' + name + '」吗？此操作不可恢复。',
    confirmText: '删除',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      deleting.value = true
      try {
        await deleteBand(bandId.value)
        uni.showToast({ title: '已删除', icon: 'success' })
        setTimeout(() => uni.navigateBack(), 400)
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '删除失败', icon: 'none' })
      } finally {
        deleting.value = false
      }
    }
  })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 60rpx;
}

.state-box {
  padding: 160rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.info-card,
.form-card {
  margin: 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 24rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.info-label {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.info-value {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.status-pending {
  color: var(--color-warning, #f59e0b);
}
.status-active {
  color: var(--color-success, #16a34a);
}
.status-rejected {
  color: var(--color-primary, #e5484d);
}

.field-wrap {
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.input {
  width: 100%;
  height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.textarea {
  width: 100%;
  min-height: 160rpx;
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
.del-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin: 20rpx 24rpx 0;
  font-size: var(--font-size-lg, 32rpx);
  color: var(--color-primary, #e5484d);
  background: var(--color-surface, #ffffff);
  border: 1rpx solid var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}
</style>
