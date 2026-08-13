<template>
  <view class="page">
    <view class="page-header">
      <text class="page-title">管理拼盘</text>
      <text class="page-sub">每 5 秒自动刷新实时状态</text>
    </view>

    <view v-if="loading" class="state-box">
      <text class="state-text">加载中…</text>
    </view>

    <view v-else-if="events.length" class="event-list">
      <view v-for="event in events" :key="event.id" class="card">
        <view class="card-head">
          <text class="card-title">{{ event.title }}</text>
          <text class="status-badge" :class="event.status">
            {{ event.status === 'published' ? '已发布' : '草稿' }}
          </text>
        </view>
        <view class="card-meta">
          <text>{{ formatDate(event.live_date) }} {{ formatTime(event.start_time) }}</text>
        </view>

        <view class="status-line">
          <text class="status-line-text">{{ statusText(event) }}</text>
        </view>

        <view class="participants">
          <view v-for="inv in event.invites" :key="inv.username" class="p-row">
            <view class="p-info">
              <text class="p-name">{{ inv.band_name || inv.username }}</text>
              <text v-if="inv.is_initiator" class="p-tag p-tag-init">发起方</text>
              <text v-if="inv.is_me" class="p-tag p-tag-me">我</text>
            </view>
            <view class="p-right">
              <text class="p-badge" :class="inv.invite_status">{{ statusLabel(inv.invite_status) }}</text>
              <button
                v-if="isInitiator(event) && inv.invite_status === 'exit_requested'"
                class="btn btn-mini"
                :disabled="busy"
                @click="onApproveExit(event, inv)"
              >
                同意退出
              </button>
            </view>
          </view>
        </view>

        <view class="card-actions">
          <!-- 发起方：草稿 → 发布/编辑/删除；已发布 → 下架 -->
          <template v-if="isInitiator(event)">
            <template v-if="event.status === 'draft'">
              <button class="btn btn-primary" :disabled="busy" @click="onPublish(event)">发布</button>
              <button class="btn btn-outline" :disabled="busy" @click="onEdit(event)">编辑</button>
              <button class="btn btn-danger-outline" :disabled="busy" @click="onDelete(event)">删除</button>
            </template>
            <template v-else>
              <button class="btn btn-danger-outline" :disabled="busy" @click="onOffline(event)">下架拼盘</button>
            </template>
          </template>
          <!-- 接收方 -->
          <template v-else>
            <button
              v-if="myStatus(event) === 'invited'"
              class="btn btn-primary"
              :disabled="busy"
              @click="onAccept(event)"
            >
              同意
            </button>
            <button
              v-if="myStatus(event) === 'agreed'"
              class="btn btn-outline"
              :disabled="busy"
              @click="onRevoke(event)"
            >
              撤销同意
            </button>
            <button
              v-if="myStatus(event) === 'invited' || myStatus(event) === 'agreed'"
              class="btn btn-outline"
              :disabled="busy"
              @click="onReject(event)"
            >
              {{ myStatus(event) === 'agreed' ? '改为拒绝' : '拒绝' }}
            </button>
            <button
              v-if="myStatus(event) === 'invited' || myStatus(event) === 'agreed'"
              class="btn btn-outline"
              :disabled="busy"
              @click="openEdit(event)"
            >
              修改曲目
            </button>
            <button
              v-if="myStatus(event) === 'invited' || myStatus(event) === 'agreed'"
              class="btn btn-outline"
              :disabled="busy"
              @click="onExitRequest(event)"
            >
              申请退出
            </button>
            <text v-if="myStatus(event) === 'exit_requested'" class="status-text">
              已申请退出，等待发起方审批
            </text>
            <text v-if="myStatus(event) === 'rejected'" class="status-text">已拒绝</text>
          </template>
        </view>

        <view v-if="editingEventId === event.id" class="song-editor">
          <view class="song-editor-label">我的曲目</view>
          <SetlistEditor
            :model-value="editingSongs"
            @update:model-value="setEditingSongs"
          />
          <view class="song-editor-btns">
            <button class="btn btn-primary" :disabled="busy" @click="saveSongs(event)">保存曲目</button>
            <button class="btn btn-outline" @click="closeEdit">取消</button>
          </view>
        </view>
      </view>
    </view>

    <EmptyState v-else text="暂无关联拼盘" />
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import coopApi from '../../services/coop-api.js'
import { requireAuth } from '../../common/guard.js'
import { formatDate, formatTime } from '../../common/format.js'
import { INVITE_STATUS } from '../../common/constants.js'
import EmptyState from '../../common/components/EmptyState.vue'
import SetlistEditor from '../../common/components/SetlistEditor.vue'

const events = ref([])
const loading = ref(false)
const busy = ref(false)
const editingEventId = ref(null)
const editingSongs = ref([])
let timer = null

function statusLabel(s) {
  return INVITE_STATUS[s] || s
}

function myInvite(event) {
  return (event.invites || []).find((i) => i.is_me) || null
}
function isInitiator(event) {
  const me = myInvite(event)
  return !!(me && me.is_initiator)
}
function myStatus(event) {
  const me = myInvite(event)
  return me ? me.invite_status : ''
}
function mySongsOf(event) {
  const me = myInvite(event)
  return (me && me.songs) || []
}

/** 聚合实时状态：如「2/4 乐队已同意 · 1 拒绝 · 1 申请退出」 */
function statusText(event) {
  const invites = event.invites || []
  const total = invites.length
  const agreed = invites.filter((i) => i.invite_status === 'agreed').length
  const rejected = invites.filter((i) => i.invite_status === 'rejected').length
  const exitReq = invites.filter((i) => i.invite_status === 'exit_requested').length
  let s = agreed + '/' + total + ' 乐队已同意'
  const extra = []
  if (rejected) extra.push(rejected + ' 拒绝')
  if (exitReq) extra.push(exitReq + ' 申请退出')
  if (extra.length) s += ' · ' + extra.join(' · ')
  return s
}

function setEditingSongs(v) {
  if (!coopApi.sameSongs(editingSongs.value, v)) editingSongs.value = v
}

/* ---- 加载 + 5s 轮询 ---- */

async function fetchEvents() {
  const res = await coopApi.listEvents()
  events.value = (res && res.items) || []
}

/** 首次/前台展示加载（显示 loading） */
async function load() {
  if (!requireAuth()) return
  loading.value = true
  try {
    await fetchEvents()
  } catch (e) {
    events.value = []
  } finally {
    loading.value = false
  }
}

/** 静默刷新（动作后 / 轮询，不闪 loading） */
async function silentRefresh() {
  try {
    await fetchEvents()
  } catch (e) {
    /* 静默失败，保留现有列表 */
  }
}

function clearTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function runLoop() {
  clearTimer()
  timer = setInterval(silentRefresh, 5000)
}

/* ---- 动作统一入口 ---- */

async function doAction(fn, successMsg) {
  if (busy.value) return
  busy.value = true
  try {
    await fn()
    if (successMsg) uni.showToast({ title: successMsg, icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    busy.value = false
  }
  await silentRefresh()
}

function onApproveExit(event, inv) {
  return doAction(async () => {
    await coopApi.approveExit(event.id, null, inv.username)
  }, '已同意退出')
}

function onOffline(event) {
  return doAction(async () => {
    await coopApi.offlineEvent(event.id)
  }, '已下架')
}

function onPublish(event) {
  return doAction(async () => {
    // 带全量字段发布，避免后端部分更新清空 setlist/海报
    const d = await coopApi.getEventDetail(event.id)
    const me = (d.participants || []).find((p) => p.is_me) || null
    await coopApi.patchEvent(event.id, {
      title: d.title || '',
      livehouse_id: d.livehouse_id || null,
      live_date: d.live_date || '',
      start_time: (d.start_time || '').slice(0, 5),
      ticket_price: d.ticket_price,
      poster_image_url: d.poster_image_url || '',
      own_songs: (me && me.songs) || [],
      action: 'publish'
    })
  }, '已发布')
}

function onEdit(event) {
  uni.navigateTo({ url: '/pages/coop/create?id=' + event.id })
}

function onDelete(event) {
  return doAction(async () => {
    await coopApi.deleteEvent(event.id)
  }, '已删除')
}

function onAccept(event) {
  return doAction(async () => {
    const songs =
      editingEventId.value === event.id ? editingSongs.value : mySongsOf(event)
    await coopApi.acceptInvite(event.id, null, songs)
    editingEventId.value = null
    editingSongs.value = []
  }, '已同意')
}

function onRevoke(event) {
  return doAction(async () => {
    await coopApi.revokeAgree(event.id, null)
  }, '已撤销同意')
}

function onReject(event) {
  return doAction(async () => {
    await coopApi.rejectInvite(event.id, null)
  }, '已拒绝')
}

function onExitRequest(event) {
  return doAction(async () => {
    await coopApi.exitRequest(event.id, null)
  }, '已申请退出')
}

function openEdit(event) {
  editingEventId.value = event.id
  editingSongs.value = coopApi.cloneSongs(mySongsOf(event))
}

function closeEdit() {
  editingEventId.value = null
  editingSongs.value = []
}

function saveSongs(event) {
  return doAction(async () => {
    await coopApi.updateSongs(event.id, null, editingSongs.value)
    editingEventId.value = null
    editingSongs.value = []
  }, '曲目已保存')
}

onShow(() => {
  load()
  runLoop()
})
onHide(clearTimer)
onUnload(clearTimer)
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

.event-list {
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
.status-badge.published {
  background: rgba(22, 163, 74, 0.12);
  color: var(--color-success, #16a34a);
}
.status-badge.draft {
  background: var(--color-border, #e5e7eb);
  color: var(--color-text-muted, #9ca3af);
}
.card-meta {
  margin-top: 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}

.status-line {
  margin-top: 16rpx;
  padding: 16rpx 20rpx;
  background: var(--color-bg, #f5f6f8);
  border-radius: var(--radius, 16rpx);
}
.status-line-text {
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-primary, #e5484d);
}

.participants {
  margin-top: 16rpx;
}
.p-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10rpx 0;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.p-row:last-child {
  border-bottom: none;
}
.p-info {
  display: flex;
  align-items: center;
  min-width: 0;
}
.p-name {
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.p-tag {
  margin-left: 12rpx;
  padding: 2rpx 12rpx;
  border-radius: 16rpx;
  font-size: var(--font-size-xs, 22rpx);
}
.p-tag-init {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}
.p-tag-me {
  background: rgba(229, 72, 77, 0.12);
  color: var(--color-primary, #e5484d);
}
.p-right {
  display: flex;
  align-items: center;
}
.p-badge {
  padding: 2rpx 14rpx;
  border-radius: 16rpx;
  font-size: var(--font-size-xs, 22rpx);
}
.p-badge.invited {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}
.p-badge.agreed {
  background: rgba(22, 163, 74, 0.12);
  color: var(--color-success, #16a34a);
}
.p-badge.rejected {
  background: rgba(229, 72, 77, 0.12);
  color: var(--color-primary, #e5484d);
}
.p-badge.exit_requested {
  background: rgba(245, 158, 11, 0.12);
  color: var(--color-warning, #f59e0b);
}
.p-badge.removed {
  background: var(--color-border, #e5e7eb);
  color: var(--color-text-muted, #9ca3af);
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 16rpx;
}
.status-text {
  display: block;
  width: 100%;
  padding: 8rpx 0;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.song-editor {
  margin-top: 16rpx;
  padding: 16rpx;
  background: var(--color-bg, #f5f6f8);
  border-radius: var(--radius, 16rpx);
}
.song-editor-label {
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.song-editor-btns {
  display: flex;
  gap: 12rpx;
  margin-top: 16rpx;
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
.btn-mini {
  height: 56rpx;
  line-height: 56rpx;
  margin-left: 16rpx;
  padding: 0 20rpx;
  font-size: var(--font-size-xs, 22rpx);
  border-radius: 12rpx;
  background: var(--color-warning, #f59e0b);
  color: #ffffff;
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
.btn-danger-outline {
  background: transparent;
  color: var(--color-primary, #e5484d);
  border: 1rpx solid var(--color-primary, #e5484d);
}
</style>
