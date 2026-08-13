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

    <view v-else-if="data" class="project">
      <view v-if="data.intro" class="section">
        <text class="section-title">项目介绍</text>
        <view class="intro-body">
          <RichText :content="data.intro" />
        </view>
      </view>

      <view class="section">
        <view class="info-row" @click="openGithub">
          <text class="info-label">GitHub</text>
          <text class="info-value link">{{ data.github_url || '—' }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">作者</text>
          <text class="info-value">{{ data.author || '—' }}</text>
        </view>
        <view class="info-row">
          <text class="info-label">开源协议</text>
          <text class="info-value">{{ data.license || '—' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import RichText from '../../common/components/RichText.vue'
import ErrorPage from '../../components/ErrorPage.vue'
import { fetchProject } from '../../services/api.js'

const data = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchProject()
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  } finally {
    loading.value = false
  }
}

onShow(() => {
  load()
})

function openGithub() {
  const url = data.value && data.value.github_url
  if (!url) return
  // #ifdef H5
  window.open(url, '_blank')
  // #endif
  // #ifndef H5
  uni.setClipboardData({
    data: url,
    success: () => uni.showToast({ title: 'GitHub 地址已复制', icon: 'none' })
  })
  // #endif
}
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

.project {
  padding: 24rpx;
}
.section {
  padding: 24rpx;
  margin-bottom: 24rpx;
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

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22rpx 0;
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
.info-value.link {
  color: var(--color-primary, #e5484d);
}
</style>
