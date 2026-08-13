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
          <text class="info-label">当前状态</text>
          <text class="info-value" :class="'status-' + account.status">{{ accountStatusText(account.status) }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">申请时间</text>
          <text class="info-value">{{ (account.created_at || '').slice(0, 19) || '—' }}</text>
        </view>
      </view>

      <!-- 可修改资料（修改后通过时以表单内容提交） -->
      <view class="form-card">
        <view class="form-card-title">乐队资料</view>
        <view class="field-wrap">
          <text class="field-label">乐队名称</text>
          <input v-model="bandName" class="input" placeholder="请输入乐队名称" />
        </view>
        <view class="field-wrap">
          <text class="field-label">乐队简介</text>
          <textarea v-model="intro" class="textarea" placeholder="请输入乐队简介" />
        </view>
      </view>

      <view class="btn-group">
        <button class="btn btn-primary" :loading="saving" @click="doApprove">通过</button>
        <button class="btn btn-danger" :loading="saving" @click="doReject">拒绝</button>
      </view>
      <text class="btn-hint">可先修改乐队名称/简介，再点击「通过」将修改后的资料一并生效</text>
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
import { getBand, updateBand } from '../../services/admin-api.js'

const bandId = ref(null)
const loading = ref(true)
const saving = ref(false)

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

async function doApprove() {
  saving.value = true
  try {
    await updateBand(bandId.value, {
      action: 'approve',
      band_name: bandName.value.trim(),
      intro: intro.value
    })
    uni.showToast({ title: '已通过审核', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 400)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

async function doReject() {
  uni.showModal({
    title: '拒绝申请',
    content: '确定拒绝该乐队的注册申请吗？',
    confirmText: '拒绝',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      saving.value = true
      try {
        await updateBand(bandId.value, { action: 'reject' })
        uni.showToast({ title: '已拒绝', icon: 'success' })
        setTimeout(() => uni.navigateBack(), 400)
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
      } finally {
        saving.value = false
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

.form-card-title {
  padding: 24rpx 24rpx 0;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
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

.btn-group {
  display: flex;
  padding: 0 24rpx;
}
.btn {
  flex: 1;
  height: 92rpx;
  line-height: 92rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  border-radius: var(--radius, 16rpx);
}
.btn-primary {
  margin-right: 12rpx;
  color: #ffffff;
  background: var(--color-success, #16a34a);
}
.btn-danger {
  margin-left: 12rpx;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
.btn-hint {
  display: block;
  margin: 24rpx;
  text-align: center;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
