<template>
  <view class="page">
    <view class="page-header">
      <text class="page-title">创建拼盘</text>
    </view>

    <!-- 基础 Live 信息 -->
    <view class="section">
      <view class="section-title">基础 Live 信息</view>
      <FormField label="拼盘名称" required>
        <input class="input" v-model="form.title" placeholder="例如：夏日祭 金属拼盘" />
      </FormField>
      <FormField label="海报">
        <UploadImage v-model="form.poster_image_url" hint="上传海报" />
      </FormField>
      <FormField label="演出日期" required>
        <picker mode="date" :value="form.live_date" @change="form.live_date = $event.detail.value">
          <view class="picker-value" :class="{ placeholder: !form.live_date }">{{ form.live_date || '请选择日期' }}</view>
        </picker>
      </FormField>
      <FormField label="开始时间" required>
        <picker mode="time" :value="form.start_time" @change="form.start_time = $event.detail.value">
          <view class="picker-value" :class="{ placeholder: !form.start_time }">{{ form.start_time || '请选择时间' }}</view>
        </picker>
      </FormField>
      <FormField label="场地" required>
        <picker
          mode="selector"
          :range="venues"
          range-key="name"
          :value="venueIndex"
          @change="onVenueChange"
        >
          <view class="picker-value" :class="{ placeholder: !form.livehouse_id }">{{ venueName }}</view>
        </picker>
      </FormField>
      <FormField label="票价">
        <input class="input" type="digit" v-model="form.ticket_price" placeholder="门票价格（可空）" />
      </FormField>
    </view>

    <!-- 本队信息 -->
    <view class="section">
      <view class="section-title">本队曲目</view>
      <view class="section-body">
        <SetlistEditor
          :model-value="ownSongs"
          @update:model-value="setOwnSongs"
        />
      </view>
    </view>

    <!-- 邀请其他乐队 -->
    <view class="section">
      <view class="section-title">{{ isEditing ? '受邀乐队（编辑模式）' : '邀请其他乐队' }}</view>
      <view class="section-body">
        <view class="invite-row" v-if="!isEditing">
          <input
            class="input invite-input"
            v-model="inviteInput.username"
            placeholder="输入乐队账号"
            @input="onInviteInput"
          />
          <button class="btn btn-primary invite-add-btn" :disabled="!canAdd" @click="addInvite">添加</button>
        </view>
        <view class="invite-hint" v-if="!isEditing && inviteInput.username.trim()">
          <text v-if="inviteInput.checking" class="hint-checking">验证中…</text>
          <text v-else-if="inviteInput.exists === true" class="hint-ok">✓ 账号存在</text>
          <text v-else-if="inviteInput.exists === false" class="hint-err">✗ 账号不存在</text>
        </view>
        <view class="invite-duplicate" v-if="!isEditing && duplicateHint">该乐队已在邀请列表</view>
        <view class="invite-empty" v-if="isEditing && !inviteList.length">
          <text class="invite-empty-text">该拼盘暂无其他受邀乐队</text>
        </view>

        <view v-if="inviteList.length" class="invite-list">
          <view v-for="(inv, idx) in inviteList" :key="inv.username" class="invite-item">
            <view class="invite-item-header">
              <text class="invite-username">@{{ inv.username }}</text>
              <text v-if="!isEditing" class="invite-remove" @click="removeInvite(idx)">移除</text>
            </view>
            <view class="invite-songs-label">为该乐队分配曲目</view>
            <SetlistEditor
              :model-value="inv.songs"
              @update:model-value="setInviteSongs(inv, $event)"
            />
          </view>
        </view>
        <view v-else class="invite-empty">
          <text class="invite-empty-text">尚未邀请乐队，可在保存后继续追加</text>
        </view>
      </view>
    </view>

    <view class="footer">
      <view class="footer-btns">
        <button class="btn btn-outline btn-block" :loading="saving" :disabled="saving" @click="saveDraft">
          保存草稿
        </button>
        <button class="btn btn-primary btn-block" :loading="saving" :disabled="saving" @click="publish">
          发布
        </button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import coopApi from '../../services/coop-api.js'
import { requireAuth } from '../../common/guard.js'
import FormField from '../../common/components/FormField.vue'
import UploadImage from '../../common/components/UploadImage.vue'
import SetlistEditor from '../../common/components/SetlistEditor.vue'

const form = ref({
  title: '',
  livehouse_id: null,
  live_date: '',
  start_time: '',
  ticket_price: '',
  poster_image_url: ''
})
const ownSongs = ref([{ song_title: '', band_id: null }])
const venues = ref([])
const saving = ref(false)
/** 编辑模式：从 manage 页带 ?id= 进入时加载草稿回填 */
const editingId = ref(null)

const inviteInput = ref({ username: '', checking: false, exists: null, timer: null })
const duplicateHint = ref(false)
const inviteList = ref([])

const venueName = computed(() => {
  const v = venues.value.find((x) => x.id === form.value.livehouse_id)
  return v ? v.name : '请选择场地'
})
const venueIndex = computed(() => {
  const i = venues.value.findIndex((x) => x.id === form.value.livehouse_id)
  return i < 0 ? 0 : i
})
const canAdd = computed(
  () =>
    inviteInput.value.exists === true &&
    !inviteList.value.some((x) => x.username === inviteInput.value.username.trim())
)
const isEditing = computed(() => editingId.value != null)

function onVenueChange(e) {
  const i = Number(e.detail.value)
  form.value.livehouse_id = venues.value[i] ? venues.value[i].id : null
}

/* ---- SetlistEditor 受控回写（避免组件 emit 新引用导致的循环触发） ---- */

function setOwnSongs(v) {
  if (!coopApi.sameSongs(ownSongs.value, v)) ownSongs.value = v
}
function setInviteSongs(inv, v) {
  if (!coopApi.sameSongs(inv.songs, v)) inv.songs = v
}

/* ---- 邀请实时验证（防抖 300ms） ---- */

function onInviteInput(e) {
  inviteInput.value.username = (e && e.detail && e.detail.value) || inviteInput.value.username
  duplicateHint.value = false
  const username = inviteInput.value.username.trim()
  clearTimeout(inviteInput.value.timer)
  if (!username) {
    inviteInput.value.exists = null
    inviteInput.value.checking = false
    return
  }
  inviteInput.value.checking = true
  inviteInput.value.timer = setTimeout(async () => {
    try {
      const res = await coopApi.accountExists(username)
      inviteInput.value.exists = !!(res && res.exists)
    } catch (e) {
      inviteInput.value.exists = false
    }
    inviteInput.value.checking = false
  }, 300)
}

function addInvite() {
  const username = inviteInput.value.username.trim()
  if (!username || inviteInput.value.exists !== true) return
  if (inviteList.value.some((x) => x.username === username)) {
    duplicateHint.value = true
    return
  }
  inviteList.value.push({ username, songs: [{ song_title: '', band_id: null }] })
  inviteInput.value.username = ''
  inviteInput.value.exists = null
  inviteInput.value.checking = false
}

function removeInvite(idx) {
  inviteList.value.splice(idx, 1)
}

/* ---- 提交（新建 / 编辑草稿共用） ---- */

function buildPayload(action) {
  const payload = {
    title: form.value.title.trim(),
    livehouse_id: form.value.livehouse_id,
    live_date: form.value.live_date,
    start_time: form.value.start_time,
    ticket_price: form.value.ticket_price ? Number(form.value.ticket_price) : 0,
    poster_image_url: form.value.poster_image_url,
    own_songs: coopApi.cleanSongs(ownSongs.value),
    action
  }
  // 新建时落地受邀乐队；编辑模式不带 invites（受邀乐队在管理页维护，避免重复邀请）
  if (!isEditing.value) {
    payload.invites = inviteList.value.map((i) => ({
      username: i.username,
      songs: coopApi.cleanSongs(i.songs)
    }))
  }
  return payload
}

async function submit(action) {
  if (isEditing.value) {
    await coopApi.patchEvent(editingId.value, buildPayload(action))
  } else {
    await coopApi.createEvent(buildPayload(action))
  }
}

async function saveDraft() {
  if (!form.value.title.trim()) {
    uni.showToast({ title: '请填写拼盘名称', icon: 'none' })
    return
  }
  if (!form.value.livehouse_id) {
    uni.showToast({ title: '请选择场地', icon: 'none' })
    return
  }
  if (saving.value) return
  saving.value = true
  try {
    await submit('save_draft')
    uni.showToast({ title: '已保存草稿', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 600)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

/** 发布校验：必填 名称/场地/日期/时间（与后端 action=publish 校验一致） */
function validatePublish() {
  if (!form.value.title.trim()) return '请填写拼盘名称'
  if (!form.value.livehouse_id) return '请选择场地'
  if (!form.value.live_date) return '请选择演出日期'
  if (!form.value.start_time) return '请选择开始时间'
  return ''
}

async function publish() {
  const err = validatePublish()
  if (err) {
    uni.showToast({ title: err, icon: 'none' })
    return
  }
  if (saving.value) return
  saving.value = true
  try {
    await submit('publish')
    uni.showToast({ title: '已发布', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 600)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '发布失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

/* ---- 编辑模式：加载草稿回填 ---- */

async function loadEvent(id) {
  const d = await coopApi.getEventDetail(id)
  if (!d) throw new Error('拼盘不存在')
  form.value = {
    title: d.title || '',
    livehouse_id: d.livehouse_id || null,
    live_date: d.live_date || '',
    start_time: (d.start_time || '').slice(0, 5),
    ticket_price: d.ticket_price != null && d.ticket_price !== '' ? String(d.ticket_price) : '',
    poster_image_url: d.poster_image_url || ''
  }
  const me = (d.participants || []).find((p) => p.is_me) || null
  if (me && Array.isArray(me.songs) && me.songs.length) {
    ownSongs.value = me.songs.map((s) => ({
      song_title: s.song_title || '',
      band_id: s.band_id != null ? s.band_id : null
    }))
  }
  // 受邀乐队回填展示（编辑模式不重发 invites）
  inviteList.value = (d.participants || [])
    .filter((p) => !p.is_me && p.invite_status !== 'removed' && p.invite_status !== 'rejected')
    .map((p) => ({
      username: p.username,
      songs: (p.songs || []).map((s) => ({
        song_title: s.song_title || '',
        band_id: s.band_id != null ? s.band_id : null
      }))
    }))
}

onLoad(async (options) => {
  if (!requireAuth()) return
  try {
    const res = await coopApi.listLivehouses()
    venues.value = (res && res.items) || []
  } catch (e) {
    venues.value = []
  }
  const qid = options && options.id != null ? Number(options.id) : null
  if (qid) {
    editingId.value = qid
    try {
      await loadEvent(qid)
    } catch (e) {
      uni.showToast({ title: (e && e.message) || '加载拼盘失败', icon: 'none' })
      setTimeout(() => uni.navigateBack(), 600)
    }
  }
})

onUnload(() => {
  clearTimeout(inviteInput.value.timer)
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 160rpx;
}
.page-header {
  padding: 32rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.page-title {
  font-size: var(--font-size-xl, 36rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}

.section {
  margin-top: 20rpx;
}
.section-title {
  padding: 20rpx 24rpx 8rpx;
  font-size: var(--font-size-sm, 26rpx);
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
}
.section-body {
  background: var(--color-surface, #ffffff);
  padding: 24rpx;
}
.input {
  width: 100%;
  height: 72rpx;
  padding: 0 20rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-bg, #f5f6f8);
  border-radius: 8rpx;
}
.picker-value {
  height: 72rpx;
  line-height: 72rpx;
  padding: 0 20rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-bg, #f5f6f8);
  border-radius: 8rpx;
}
.picker-value.placeholder {
  color: var(--color-text-muted, #9ca3af);
}

/* 邀请区 */
.invite-row {
  display: flex;
  align-items: center;
}
.invite-input {
  flex: 1;
  min-width: 0;
}
.invite-add-btn {
  flex-shrink: 0;
  margin-left: 16rpx;
  min-width: 140rpx;
}
.invite-hint {
  margin-top: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
}
.hint-checking {
  color: var(--color-text-muted, #9ca3af);
}
.hint-ok {
  color: var(--color-success, #16a34a);
}
.hint-err {
  color: var(--color-primary, #e5484d);
}
.invite-duplicate {
  margin-top: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-warning, #f59e0b);
}
.invite-empty {
  margin-top: 16rpx;
  padding: 40rpx 0;
  text-align: center;
}
.invite-empty-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.invite-list {
  margin-top: 8rpx;
}
.invite-item {
  margin-top: 24rpx;
  padding: 20rpx;
  border: 1rpx solid var(--color-border, #e5e7eb);
  border-radius: var(--radius, 16rpx);
}
.invite-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12rpx;
}
.invite-username {
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.invite-remove {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-primary, #e5484d);
}
.invite-songs-label {
  margin-bottom: 12rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}

.footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 20rpx 24rpx calc(20rpx + env(safe-area-inset-bottom));
  background: var(--color-surface, #ffffff);
  border-top: 1rpx solid var(--color-border, #e5e7eb);
}
.footer-btns {
  display: flex;
  gap: 16rpx;
}
.btn {
  height: 80rpx;
  line-height: 80rpx;
  border-radius: var(--radius, 16rpx);
  font-size: var(--font-size-base, 28rpx);
  text-align: center;
  padding: 0 32rpx;
}
.btn[disabled] {
  opacity: 0.5;
}
.btn-block {
  flex: 1;
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
