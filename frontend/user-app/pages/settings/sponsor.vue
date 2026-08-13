<template>
  <view class="page">
    <view v-if="loading && !data" class="empty">
      <text class="empty-text">加载中...</text>
    </view>

    <ErrorPage
      v-else-if="error && !data"
      :message="error"
      @retry="load"
    />

    <view v-else-if="data" class="sponsor">
      <view class="thanks-card">
        <RichText :content="data.thanks_text" />
      </view>

      <view class="qr-row">
        <view
          v-for="(url, i) in qrUrls"
          :key="i"
          class="qr-box"
        >
          <image v-if="url" class="qr-img" :src="resolveImageUrl(url)" mode="aspectFit" />
          <view v-else class="qr-img qr-ph">
            <text class="qr-ph-text">♪</text>
          </view>
          <text class="qr-caption">收款码 {{ i + 1 }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import RichText from '../../common/components/RichText.vue'
import ErrorPage from '../../components/ErrorPage.vue'
import { resolveImageUrl } from '../../common/http.js'
import { fetchSponsor } from '../../services/api.js'

const data = ref(null)
const loading = ref(false)
const error = ref('')

const qrUrls = computed(() => (data.value && data.value.qr_image_urls) || [])

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchSponsor()
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  } finally {
    loading.value = false
  }
}

onShow(() => {
  load()
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}
.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 160rpx 48rpx;
}
.empty-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-muted, #9ca3af);
}

.sponsor {
  padding: 24rpx;
}
.thanks-card {
  padding: 32rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}

.qr-row {
  display: flex;
  justify-content: center;
  margin-top: 24rpx;
}
.qr-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24rpx;
  margin: 0 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.qr-img {
  width: 240rpx;
  height: 240rpx;
}
.qr-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-border, #e5e7eb);
}
.qr-ph-text {
  font-size: 56rpx;
  color: var(--color-text-muted, #9ca3af);
}
.qr-caption {
  margin-top: 16rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
</style>
