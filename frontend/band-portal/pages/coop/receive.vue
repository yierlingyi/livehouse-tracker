<template>
  <view class="page">
    <view class="page-header">
      <text class="page-title">接收拼盘</text>
      <text class="page-sub">共 {{ items.length }} 条邀请</text>
    </view>

    <view v-if="loading" class="state-box">
      <text class="state-text">加载中…</text>
    </view>

    <view v-else-if="items.length" class="invite-list">
      <view v-for="item in items" :key="item.event_id" class="card">
        <view class="card-head">
          <text class="card-title">{{ item.title }}</text>
          <text class="status-badge" :class="item.invite_status">{{ statusLabel(item.invite_status) }}</text>
        </view>

        <view class="card-row">
          <text class="row-label">发起乐队</text>
          <text class="row-value">{{ item.initiator_band }}</text>
        </view>
        <view class="card-row">
          <text class="row-label">时间</text>
          <text class="row-value">{{ formatDate(item.live_date) }}</text>
        </view>
        <view class="card-row">
          <text class="row-label">地址</text>
          <text class="row-value">{{ item.venue_address }}</text>
        </view>
        <view class="card-row card-row-top">
          <text class="row-label">分配曲目</text>
          <view class="row-songs">
            <template v-for="(s, i) in item.editSongs" :key="i">
              <text v-if="s && s.song_title" class="song-chip">《{{ s.song_title }}》</text>
            </template>
            <text v-if="!hasSongs(item)" class="song-empty">（暂未分配曲目）</text>
          </view>
        </view>

        <view class="card-actions">
          <template v-if="item.invite_status === 'invited'">
            <button class="btn btn-primary" :disabled="item.busy" @click="accept(item)">同意</button>
            <button class="btn btn-outline" :disabled="item.busy" @click="reject(item)">拒绝</button>
            <button class="btn btn-outline" :disabled="item.busy" @click="toggleEdit(item)">
              {{ item.showEdit ? '收起曲目' : '修改本队曲目' }}
            </button>
          </template>
          <template v-else>
            <button class="btn btn-outline" :disabled="item.busy" @click="toggleEdit(item)">
              {{ item.showEdit ? '收起曲目' : '修改本队曲目' }}
            </button>
          </template>
        </view>

        <view v-if="item.showEdit" class="song-editor">
          <SetlistEditor
            :model-value="item.editSongs"
            @update:model-value="setItemSongs(item, $event)"
          />
          <view class="song-editor-btns">
            <button class="btn btn-primary" :disabled="item.busy" @click="saveSongs(item)">保存曲目</button>
            <button class="btn btn-outline" :disabled="item.busy" @click="item.showEdit = false">收起</button>
          </view>
        </view>
      </view>
    </view>

    <EmptyState v-else text="暂无待处理的拼盘邀请" />
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import coopApi from '../../services/coop-api.js'
import { requireAuth } from '../../common/guard.js'
import { formatDate } from '../../common/format.js'
import { INVITE_STATUS } from '../../common/constants.js'
import EmptyState from '../../common/components/EmptyState.vue'
import SetlistEditor from '../../common/components/SetlistEditor.vue'

const items = ref([])
const loading = ref(false)

function statusLabel(s) {
  return INVITE_STATUS[s] || s
}
function hasSongs(item) {
  return (item.editSongs || []).some((s) => s && s.song_title && String(s.song_title).trim())
}
function setItemSongs(item, v) {
  if (!coopApi.sameSongs(item.editSongs, v)) item.editSongs = v
}

function toggleEdit(item) {
  item.showEdit = !item.showEdit
}

async function fetchInvites() {
  const res = await coopApi.listInvites()
  items.value = (res && res.items || []).map((it) => ({
    ...it,
    editSongs: coopApi.cloneSongs(it.assigned_songs),
    showEdit: false,
    busy: false
  }))
}

/** 首次/前台展示加载（显示 loading） */
async function load() {
  if (!requireAuth()) return
  loading.value = true
  try {
    await fetchInvites()
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

/** 动作后静默刷新（不闪 loading） */
async function silentRefresh() {
  try {
    await fetchInvites()
  } catch (e) {
    /* 静默失败，保留现有列表 */
  }
}

async function accept(item) {
  item.busy = true
  try {
    await coopApi.acceptInvite(item.event_id, null, item.editSongs)
    uni.showToast({ title: '已同意', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    item.busy = false
  }
  await silentRefresh()
}

async function reject(item) {
  item.busy = true
  try {
    await coopApi.rejectInvite(item.event_id, null)
    uni.showToast({ title: '已拒绝', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    item.busy = false
  }
  await silentRefresh()
}

async function saveSongs(item) {
  item.busy = true
  try {
    await coopApi.updateSongs(item.event_id, null, item.editSongs)
    uni.showToast({ title: '曲目已保存', icon: 'success' })
    item.showEdit = false
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    item.busy = false
  }
  await silentRefresh()
}

onShow(load)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 48rpx;
}
.page-header {
  padding: 32rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.page-title {
  display: block;
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.page-sub {
  display: block;
  margin-top: 6rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.state-box {
  padding: 120rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text-muted, #9ca3af);
}

.invite-list {
  padding: 24rpx 24rpx 0;
}
.card {
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  padding: 24rpx;
  margin-bottom: 20rpx;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12rpx;
}
.card-title {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.status-badge {
  flex-shrink: 0;
  margin-left: 16rpx;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  font-size: var(--font-size-xs, 22rpx);
}
.status-badge.invited {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}
.status-badge.agreed {
  background: rgba(22, 163, 74, 0.12);
  color: var(--color-success, #16a34a);
}
.status-badge.rejected {
  background: rgba(229, 72, 77, 0.12);
  color: var(--color-primary, #e5484d);
}
.status-badge.exit_requested {
  background: rgba(245, 158, 11, 0.12);
  color: var(--color-warning, #f59e0b);
}
.status-badge.removed {
  background: var(--color-border, #e5e7eb);
  color: var(--color-text-muted, #9ca3af);
}

.card-row {
  display: flex;
  align-items: center;
  padding: 8rpx 0;
}
.card-row-top {
  align-items: flex-start;
}
.row-label {
  flex-shrink: 0;
  width: 140rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
.row-value {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.row-songs {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
}
.song-chip {
  padding: 4rpx 16rpx;
  background: var(--color-bg, #f5f6f8);
  border-radius: 20rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-secondary, #6b7280);
}
.song-empty {
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}

.song-editor {
  margin-top: 16rpx;
  padding: 16rpx;
  background: var(--color-bg, #f5f6f8);
  border-radius: var(--radius, 16rpx);
}
.song-editor-btns {
  display: flex;
  gap: 12rpx;
  margin-top: 16rpx;
}
.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 20rpx;
}
.btn {
  height: 72rpx;
  line-height: 72rpx;
  padding: 0 28rpx;
  border-radius: var(--radius, 16rpx);
  font-size: var(--font-size-base, 28rpx);
}
.btn[disabled] {
  opacity: 0.5;
}
.btn-primary {
  background: var(--color-primary, #e5484d);
  color: #ffffff;
}
.btn-outline {
  background: transparent;
  color: var(--color-primary, #e5484d);
  border: 1rpx solid var(--color-primary, #e5484d);
}
</style>
