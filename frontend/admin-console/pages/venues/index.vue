<template>
  <view class="page">
    <view class="topbar">
      <text class="topbar-title">场地管理</text>
      <view class="add-btn" @click="goAdd">
        <text class="add-btn-text">＋ 新增场地</text>
      </view>
    </view>

    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>
    <template v-else>
      <view class="list-wrap">
        <ListCard
          v-for="venue in venues"
          :key="venue.id"
          :thumb="venue.image_url"
          :title="venue.name"
          :sub="venue.intro"
          @click="goEdit(venue.id)"
        >
          <template #extra>
            <view class="row-actions">
              <text class="act-btn" @click.stop="goEdit(venue.id)">编辑</text>
              <text class="act-btn act-danger" @click.stop="confirmDelete(venue)">删除</text>
            </view>
          </template>
        </ListCard>
        <EmptyState v-if="!venues.length" text="暂无场地" />
      </view>
    </template>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'
import { requireAuth } from '../../common/guard.js'
import { listVenues, deleteVenue } from '../../services/admin-api.js'

const venues = ref([])
const loading = ref(false)

onShow(() => {
  if (!requireAuth({ endpoint: 'admin' })) return
  load()
})

async function load() {
  loading.value = true
  try {
    const res = await listVenues()
    venues.value = (res && res.items) || []
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载场地失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goAdd() {
  uni.navigateTo({ url: '/pages/venues/edit' })
}

function goEdit(id) {
  uni.navigateTo({ url: '/pages/venues/edit?id=' + id })
}

function confirmDelete(venue) {
  uni.showModal({
    title: '删除场地',
    content: '确定删除场地「' + venue.name + '」吗？',
    confirmText: '删除',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await deleteVenue(venue.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        load()
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '删除失败', icon: 'none' })
      }
    }
  })
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.topbar-title {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 700;
  color: var(--color-text, #1f2329);
}
.add-btn {
  padding: 12rpx 28rpx;
  background: var(--color-primary, #e5484d);
  border-radius: 999rpx;
}
.add-btn-text {
  font-size: var(--font-size-sm, 26rpx);
  color: #ffffff;
}

.state-box {
  padding: 160rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.list-wrap {
  padding: 24rpx;
}

.row-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.act-btn {
  padding: 8rpx 20rpx;
  margin-top: 8rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-primary, #e5484d);
  background: rgba(229, 72, 77, 0.08);
  border-radius: 8rpx;
}
.act-btn.act-danger {
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
</style>
