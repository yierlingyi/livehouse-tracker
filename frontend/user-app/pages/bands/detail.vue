<template>
  <view class="page">
    <ErrorPage
      v-if="error && !band"
      :message="error"
      @retry="load"
    />

    <view v-else-if="band" class="detail">
      <view v-if="band.cover_url && !coverError" class="cover-wrap">
        <image class="cover" :src="resolveImageUrl(band.cover_url)" mode="aspectFill" @error="coverError = true" />
      </view>
      <view v-else class="cover-wrap cover-ph">
        <text class="cover-ph-text">♪</text>
      </view>

      <view class="body">
        <text class="name">{{ band.name }}</text>

        <view v-if="band.intro" class="section">
          <text class="section-title">乐队简介</text>
          <view class="intro-body">
            <RichText :content="band.intro" />
          </view>
        </view>

        <view class="section">
          <text class="section-title">成员</text>
          <view v-if="members.length" class="member-list">
            <view
              v-for="(m, i) in members"
              :key="i"
              class="member-item"
            >
              <text class="member-name">{{ m.name }}</text>
              <text v-if="m.role" class="member-role">{{ m.role }}</text>
            </view>
          </view>
          <text v-else class="member-empty">成员待定</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import ErrorPage from '../../components/ErrorPage.vue'
import RichText from '../../common/components/RichText.vue'
import { resolveImageUrl } from '../../common/http.js'
import { fetchBandDetail } from '../../services/api.js'

const band = ref(null)
const error = ref('')
const coverError = ref(false)
let detailId = ''

const members = computed(() => (band.value && band.value.members) || [])

async function load() {
  error.value = ''
  coverError.value = false
  try {
    const res = await fetchBandDetail(detailId)
    band.value = res
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

.member-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.member-item:last-child {
  border-bottom: none;
}
.member-name {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.member-role {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.member-empty {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
