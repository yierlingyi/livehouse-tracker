<template>
  <view class="page">
    <view v-if="loading && !items.length" class="empty">
      <text class="empty-text">加载中...</text>
    </view>

    <ErrorPage
      v-else-if="error && !items.length"
      :message="error"
      @retry="load"
    />

    <view v-else-if="!items.length" class="empty">
      <EmptyState text="暂无同好群" />
    </view>

    <view v-else class="list">
      <view
        v-for="g in items"
        :key="g.id"
        class="group-card"
      >
        <view class="group-left">
          <text class="group-city">{{ g.city }}</text>
          <text class="group-platform" :class="'platform-' + g.platform">{{ platformText(g.platform) }}</text>
        </view>
        <text class="group-id">{{ g.group_id }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import EmptyState from '../../common/components/EmptyState.vue'
import ErrorPage from '../../components/ErrorPage.vue'
import { fetchCommunityGroups } from '../../services/api.js'
import { PLATFORMS } from '../../common/constants.js'

const items = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchCommunityGroups()
    items.value = (res && res.items) || []
  } catch (e) {
    error.value = (e && e.message) || '加载失败'
  } finally {
    loading.value = false
  }
}

onShow(() => {
  load()
})

function platformText(p) {
  return PLATFORMS[p] || p || ''
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

.list {
  padding: 24rpx;
}
.group-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 24rpx;
  margin-bottom: 16rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
}
.group-left {
  display: flex;
  align-items: center;
}
.group-city {
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.group-platform {
  margin-left: 16rpx;
  padding: 2rpx 12rpx;
  font-size: var(--font-size-xs, 22rpx);
  border-radius: 6rpx;
}
.platform-wechat {
  color: #16a34a;
  background: #dcfce7;
}
.platform-qq {
  color: #2563eb;
  background: #dbeafe;
}
.group-id {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
  word-break: break-all;
}
</style>
