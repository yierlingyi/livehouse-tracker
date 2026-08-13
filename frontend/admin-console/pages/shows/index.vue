<template>
  <view class="page">
    <!-- 顶部 segmented：Live 管理 | 乐队管理 -->
    <view class="segmented">
      <view
        class="seg-item"
        :class="{ active: seg === 'live' }"
        @click="switchSeg('live')"
      >Live 管理</view>
      <view
        class="seg-item"
        :class="{ active: seg === 'band' }"
        @click="switchSeg('band')"
      >乐队管理</view>
    </view>

    <!-- ============ Live 管理 ============ -->
    <view v-if="seg === 'live'" class="section">
      <view class="chips">
        <view
          v-for="f in LIVE_FILTERS"
          :key="f.value"
          class="chip"
          :class="{ active: liveKind === f.value }"
          @click="switchKind(f.value)"
        >{{ f.label }}</view>
      </view>

      <view v-if="liveLoading" class="state-box">
        <text class="state-text">加载中...</text>
      </view>
      <template v-else>
        <ListCard
          v-for="live in lives"
          :key="live.id"
          :title="live.title"
          :sub="liveSub(live)"
          :caption="liveCaption(live)"
          @click="goEditLive(live.id)"
        >
          <template #extra>
            <view class="row-actions">
              <text class="act-btn" @click.stop="goEditLive(live.id)">编辑</text>
              <text
                v-if="live.review_status === 'published'"
                class="act-btn act-danger"
                @click.stop="confirmOffline(live)"
              >强制下架</text>
              <text v-else class="act-label">已下架</text>
            </view>
          </template>
        </ListCard>
        <EmptyState v-if="!lives.length" text="暂无演出" />
      </template>
    </view>

    <!-- ============ 乐队管理 ============ -->
    <view v-else class="section">
      <view class="chips">
        <view
          class="chip"
          :class="{ active: bandFilter === 'pending' }"
          @click="switchBandFilter('pending')"
        >待审核</view>
        <view
          class="chip"
          :class="{ active: bandFilter === 'all' }"
          @click="switchBandFilter('all')"
        >全部账号</view>
      </view>

      <view v-if="bandLoading" class="state-box">
        <text class="state-text">加载中...</text>
      </view>
      <template v-else>
        <ListCard
          v-for="band in bands"
          :key="band.id"
          :title="band.band_name || band.username"
          :sub="'账号：' + band.username"
          :caption="'状态：' + accountStatusText(band.status) + ' · ' + createdText(band.created_at)"
          @click="goEditBand(band.id)"
        >
          <template #extra>
            <view class="row-actions">
              <text
                v-if="band.status === 'pending'"
                class="act-btn"
                @click.stop="goAudit(band.id)"
              >审核</text>
              <text class="act-btn" @click.stop="goEditBand(band.id)">编辑</text>
              <text class="act-btn act-danger" @click.stop="confirmDeleteBand(band)">删除</text>
            </view>
          </template>
        </ListCard>
        <EmptyState v-if="!bands.length" text="暂无乐队账号" />
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'
import { requireAuth } from '../../common/guard.js'
import { formatDate, formatTime } from '../../common/format.js'
import { ACCOUNT_STATUS, LIVE_KIND, ADMIN_LIVE_FILTERS } from '../../common/constants.js'
import {
  listLives,
  offlineLive,
  listBands,
  deleteBand
} from '../../services/admin-api.js'

const LIVE_FILTERS = ADMIN_LIVE_FILTERS

const seg = ref('live')
const liveKind = ref('all')
const bandFilter = ref('pending')

const lives = ref([])
const bands = ref([])
const liveLoading = ref(false)
const bandLoading = ref(false)

onShow(() => {
  if (!requireAuth({ endpoint: 'admin' })) return
  if (seg.value === 'live') loadLives()
  else loadBands()
})

function switchSeg(v) {
  seg.value = v
  if (v === 'live') loadLives()
  else loadBands()
}

/* ---------------- Live 管理 ---------------- */

async function loadLives() {
  liveLoading.value = true
  try {
    const res = await listLives(liveKind.value)
    lives.value = (res && res.items) || []
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载演出失败', icon: 'none' })
  } finally {
    liveLoading.value = false
  }
}

function switchKind(k) {
  if (liveKind.value === k) return
  liveKind.value = k
  loadLives()
}

function liveSub(live) {
  const d = live.live_date ? formatDate(live.live_date) : '日期待定'
  return d + ' ' + formatTime(live.start_time)
}

function liveCaption(live) {
  const kind = LIVE_KIND[live.kind] || '普通'
  const review = live.review_status === 'published' ? '已发布' : '未发布'
  const bands = live.band_names && live.band_names.length ? live.band_names.join(' / ') : '阵容待定'
  return kind + ' · ' + review + ' · ' + bands
}

function goEditLive(id) {
  uni.navigateTo({ url: '/pages/shows/live-edit?id=' + id })
}

function confirmOffline(live) {
  uni.showModal({
    title: '强制下架',
    content: '确定强制下架《' + live.title + '》吗？下架后用户端将立即隐藏。',
    confirmText: '下架',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await offlineLive(live.id)
        uni.showToast({ title: '已强制下架', icon: 'success' })
        loadLives()
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '下架失败', icon: 'none' })
      }
    }
  })
}

/* ---------------- 乐队管理 ---------------- */

async function loadBands() {
  bandLoading.value = true
  try {
    const res = await listBands(bandFilter.value)
    bands.value = (res && res.items) || []
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载乐队失败', icon: 'none' })
  } finally {
    bandLoading.value = false
  }
}

function switchBandFilter(f) {
  if (bandFilter.value === f) return
  bandFilter.value = f
  loadBands()
}

function accountStatusText(s) {
  return ACCOUNT_STATUS[s] || s || '未知'
}

function createdText(str) {
  if (!str) return ''
  return '创建于 ' + String(str).slice(0, 10)
}

function goAudit(id) {
  uni.navigateTo({ url: '/pages/bands/audit?id=' + id })
}

function goEditBand(id) {
  uni.navigateTo({ url: '/pages/bands/edit?id=' + id })
}

function confirmDeleteBand(band) {
  const name = band.band_name || band.username
  uni.showModal({
    title: '删除账号',
    content: '确定删除乐队账号「' + name + '」吗？此操作不可恢复。',
    confirmText: '删除',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await deleteBand(band.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        loadBands()
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

/* segmented 顶部 */
.segmented {
  display: flex;
  padding: 20rpx 24rpx 8rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.seg-item {
  flex: 1;
  height: 72rpx;
  line-height: 72rpx;
  text-align: center;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-secondary, #6b7280);
  border-radius: var(--radius, 16rpx);
  transition: all 0.2s ease;
}
.seg-item.active {
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  font-weight: 600;
}

.section {
  padding: 24rpx;
}

/* 过滤 chips */
.chips {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 20rpx;
}
.chip {
  padding: 10rpx 28rpx;
  margin-right: 16rpx;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-surface, #ffffff);
  border: 1rpx solid var(--color-border, #e5e7eb);
  border-radius: 999rpx;
}
.chip.active {
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-color: var(--color-primary, #e5484d);
}

.state-box {
  padding: 120rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

/* 行操作按钮 */
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
.act-label {
  padding: 8rpx 20rpx;
  margin-top: 8rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
