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
      <EmptyState text="暂无乐队" />
    </view>

    <view v-else class="list">
      <ListCard
        v-for="b in items"
        :key="b.id"
        :title="b.name"
        :thumb="b.cover_url"
        @click="goDetail(b.id)"
      />
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'
import ErrorPage from '../../components/ErrorPage.vue'
import { fetchBands } from '../../services/api.js'

const items = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchBands()
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

function goDetail(id) {
  uni.navigateTo({ url: '/pages/bands/detail?id=' + id })
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
</style>
