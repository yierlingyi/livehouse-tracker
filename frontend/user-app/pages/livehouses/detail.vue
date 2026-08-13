<template>
  <view class="page">
    <ErrorPage
      v-if="error && !venue"
      :message="error"
      @retry="load"
    />

    <view v-else-if="venue" class="detail">
      <view v-if="venue.image_url && !coverError" class="cover-wrap">
        <image class="cover" :src="resolveImageUrl(venue.image_url)" mode="aspectFill" @error="coverError = true" />
      </view>
      <view v-else class="cover-wrap cover-ph">
        <text class="cover-ph-text">♪</text>
      </view>

      <view class="body">
        <text class="name">{{ venue.name }}</text>

        <view class="info-card">
          <view class="info-row">
            <text class="info-label">地址</text>
            <text class="info-value">{{ venue.address || '待定' }}</text>
          </view>
          <view class="info-row">
            <text class="info-label">电话</text>
            <text class="info-value">{{ venue.phone || '待定' }}</text>
          </view>
        </view>

        <view v-if="venue.intro" class="section">
          <text class="section-title">场地介绍</text>
          <view class="intro-body">
            <RichText :content="venue.intro" />
          </view>
        </view>

        <view v-if="venue.image_url" class="section">
          <text class="section-title">外观图</text>
          <image class="gallery-img" :src="resolveImageUrl(venue.image_url)" mode="aspectFill" />
        </view>

        <view v-if="venue.floorplan_url" class="section">
          <text class="section-title">平面图</text>
          <image class="gallery-img" :src="resolveImageUrl(venue.floorplan_url)" mode="aspectFill" />
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import ErrorPage from '../../components/ErrorPage.vue'
import RichText from '../../common/components/RichText.vue'
import { resolveImageUrl } from '../../common/http.js'
import { fetchLivehouseDetail } from '../../services/api.js'

const venue = ref(null)
const error = ref('')
const coverError = ref(false)
let detailId = ''

async function load() {
  error.value = ''
  coverError.value = false
  try {
    const res = await fetchLivehouseDetail(detailId)
    venue.value = res
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  }
}

onLoad((options) => {
  detailId = (options && options.id) || ''
  load()
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.detail {
  padding-bottom: 60rpx;
}

.cover-wrap {
  width: 100%;
  height: 420rpx;
  background: #e5e7eb;
}
.cover {
  width: 100%;
  height: 420rpx;
}
.cover-ph {
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover-ph-text {
  font-size: 100rpx;
  color: #9ca3af;
}

.body {
  padding: 24rpx;
}
.name {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}

.info-card {
  margin-top: 24rpx;
  padding: 8rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.info-row:last-child {
  border-bottom: none;
}
.info-label {
  flex-shrink: 0;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
}
.info-value {
  flex: 1;
  margin-left: 24rpx;
  text-align: right;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  word-break: break-all;
}

.section {
  margin-top: 24rpx;
  padding: 24rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.section-title {
  display: block;
  margin-bottom: 16rpx;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.intro-body {
  width: 100%;
}
.gallery-img {
  width: 100%;
  height: 320rpx;
  border-radius: 12rpx;
}
</style>
