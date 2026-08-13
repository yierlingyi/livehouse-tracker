
<template>
  <view class="published-page">
    <view class="page-head">
      <text class="back-btn" @click="goBack">‹</text>
      <text class="head-title">已发布 Live</text>
    </view>

    <view v-if="loading" class="state-tip">加载中...</view>

    <EmptyState v-else-if="items.length === 0" text="还没有已发布的 Live" />

    <view v-else class="list">
      <view v-for="item in items" :key="item.id" class="pub-card">
        <ListCard
          :title="item.title"
          :sub="(formatDate(item.live_date) + ' ' + formatTime(item.start_time)).trim()"
          :caption="item.livehouse_name || '未选择场地'"
          @click="goEdit(item.id)"
        >
          <template #extra>
            <view class="ops">
              <text class="op op-edit" @click.stop="goEdit(item.id)">编辑</text>
              <text class="op op-off" @click.stop="confirmOffline(item)">下架</text>
            </view>
          </template>
        </ListCard>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { requireAuth } from '../../common/guard.js'
import { getBandLives, offlineLive } from '../../services/band-api.js'
import { formatDate, formatTime } from '../../common/format.js'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'

const items = ref([])
const loading = ref(false)

onShow(() => {
  if (!requireAuth({ endpoint: 'band' })) return
  loadPublished()
})

async function loadPublished() {
  loading.value = true
  try {
    const res = await getBandLives('published')
    items.value = (res && res.items) || []
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '加载已发布演出失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goBack() {
  const pages = getCurrentPages()
  if (pages.length > 1) uni.navigateBack()
  else uni.switchTab({ url: '/pages/dashboard/index' })
}

function goEdit(id) {
  uni.navigateTo({ url: '/pages/dashboard/live-edit?id=' + id })
}

function confirmOffline(item) {
  uni.showModal({
    title: '下架演出',
    content: '确定下架「' + item.title + '」吗？下架后用户端将立即隐藏，可回到草稿箱重新编辑发布。',
    confirmText: '下架',
    confirmColor: '#e5484d',
    success: (res) => {
      if (res.confirm) doOffline(item.id)
    }
  })
}

async function doOffline(id) {
  try {
    await offlineLive(id)
    uni.showToast({ title: '已下架回草稿', icon: 'success' })
    loadPublished()
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '下架失败', icon: 'none' })
  }
}
</script>

<style scoped>
.published-page {
  min-height: 100vh;
  padding: 24rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.page-head {
  display: flex;
  align-items: center;
  padding: 8rpx 0 16rpx;
}
.back-btn {
  flex-shrink: 0;
  width: 64rpx;
  height: 64rpx;
  line-height: 60rpx;
  text-align: center;
  font-size: 44rpx;
  color: var(--color-text, #1f2329);
  border-radius: 50%;
  background: var(--color-surface, #ffffff);
  border: 1rpx solid var(--color-border, #e5e7eb);
}
.head-title {
  flex: 1;
  margin-left: 16rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.state-tip {
  padding: 80rpx 0;
  text-align: center;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-muted, #9ca3af);
}
.ops {
  display: flex;
  align-items: center;
}
.op {
  padding: 8rpx 20rpx;
  margin-left: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  border-radius: 8rpx;
}
.op-edit {
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-bg, #f5f6f8);
}
.op-off {
  color: var(--color-primary, #e5484d);
  background: rgba(229, 72, 77, 0.1);
}
</style>
