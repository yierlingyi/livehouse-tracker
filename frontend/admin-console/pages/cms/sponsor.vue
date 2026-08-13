<template>
  <view class="page">
    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>

    <template v-else>
      <view class="form-card">
        <view class="section-title">感谢文本</view>
        <textarea
          v-model="form.thanks_text"
          class="textarea"
          placeholder="请输入感谢文本（支持多行，保存后按换行渲染）"
        />

        <view class="section-title">收款二维码 1</view>
        <view class="upload-wrap">
          <UploadImage v-model="form.qr_image_urls[0]" hint="上传二维码" />
        </view>

        <view class="section-title">收款二维码 2</view>
        <view class="upload-wrap">
          <UploadImage v-model="form.qr_image_urls[1]" hint="上传二维码" />
        </view>
      </view>

      <button class="save-btn" :loading="saving" @click="save">保存</button>
    </template>
  </view>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import UploadImage from '../../common/components/UploadImage.vue'
import { requireAuth } from '../../common/guard.js'
import { getSponsor, updateSponsor } from '../../services/admin-api.js'

const loading = ref(true)
const saving = ref(false)

const form = reactive({
  thanks_text: '',
  qr_image_urls: ['', '']
})

onLoad(async () => {
  if (!requireAuth({ endpoint: 'admin' })) return
  try {
    const res = await getSponsor()
    form.thanks_text = (res && res.thanks_text) || ''
    const urls = (res && res.qr_image_urls) || []
    form.qr_image_urls = [urls[0] || '', urls[1] || '']
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    await updateSponsor({
      thanks_text: form.thanks_text,
      qr_image_urls: form.qr_image_urls
    })
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 400)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
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

.state-box {
  padding: 160rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.form-card {
  margin: 24rpx;
  padding: 0 24rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.section-title {
  padding: 24rpx 0 12rpx;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.textarea {
  width: 100%;
  min-height: 200rpx;
  padding: 16rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-bg, #f5f6f8);
  border-radius: var(--radius, 16rpx);
}
.upload-wrap {
  margin-top: 8rpx;
}

.save-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin: 24rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}
</style>
