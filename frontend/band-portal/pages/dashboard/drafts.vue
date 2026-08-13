
<template>
  <view class="drafts-page">
    <view v-if="loading" class="state-tip">加载中...</view>

    <EmptyState v-else-if="items.length === 0" text="暂无草稿，去新建一场 Live 吧" />

    <view v-else class="list">
      <view v-for="item in items" :key="item.id" class="draft-card">
        <ListCard
          :title="item.title"
          :sub="(formatDate(item.live_date) + ' ' + formatTime(item.start_time)).trim()"
          :caption="item.livehouse_name || '未选择场地'"
          @click="goEdit(item.id)"
        >
          <template #extra>
            <view class="ops">
              <text class="op op-edit" @click.stop="goEdit(item.id)">编辑</text>
              <text class="op op-del" @click.stop="confirmDelete(item)">删除</text>
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
import { getBandLives, deleteLive } from '../../services/band-api.js'
import { formatDate, formatTime } from '../../common/format.js'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'

const items = ref([])
const loading = ref(false)

onShow(() => {
  if (!requireAuth({ endpoint: 'band' })) return
  loadDrafts()
})

async function loadDrafts() {
  loading.value = true
  try {
    const res = await getBandLives('draft')
    items.value = (res && res.items) || []
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '加载草稿失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goEdit(id) {
  uni.navigateTo({ url: '/pages/dashboard/live-edit?id=' + id })
}

function confirmDelete(item) {
  uni.showModal({
    title: '删除草稿',
    content: '确定删除「' + item.title + '」吗？删除后不可恢复。',
    confirmText: '删除',
    confirmColor: '#e5484d',
    success: (res) => {
      if (res.confirm) doDelete(item.id)
    }
  })
}

async function doDelete(id) {
  try {
    await deleteLive(id)
    uni.showToast({ title: '已删除', icon: 'success' })
    loadDrafts()
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '删除失败', icon: 'none' })
  }
}
</script>

<style scoped>
.drafts-page {
  min-height: 100vh;
  padding: 24rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
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
.op-del {
  color: var(--color-primary, #e5484d);
  background: rgba(229, 72, 77, 0.1);
}
</style>
