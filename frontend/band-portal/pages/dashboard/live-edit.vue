
<template>
  <view class="edit-page">
    <view class="edit-form">
      <FormField label="Live 名称" required>
        <input
          v-model="form.title"
          class="input"
          placeholder="请输入演出名称"
          placeholder-class="input-ph"
          :maxlength="60"
        />
      </FormField>

      <FormField label="海报">
        <UploadImage v-model="form.poster_image_url" hint="点击上传海报" />
      </FormField>

      <FormField label="场地" required>
        <picker
          mode="selector"
          :range="livehouseNames"
          :value="livehouseIndex"
          @change="onLivehouseChange"
        >
          <view class="picker-value" :class="{ 'picker-empty': livehouseIndex < 0 }">
            {{ livehouseIndex >= 0 ? livehouseNames[livehouseIndex] : '请选择演出场地' }}
          </view>
        </picker>
      </FormField>

      <FormField label="演出日期" required>
        <picker mode="date" :value="form.live_date" start="2026-01-01" @change="onDateChange">
          <view class="picker-value" :class="{ 'picker-empty': !form.live_date }">
            {{ form.live_date || '请选择演出日期' }}
          </view>
        </picker>
      </FormField>

      <FormField label="开始时间" required>
        <picker mode="time" :value="form.start_time" @change="onTimeChange">
          <view class="picker-value" :class="{ 'picker-empty': !form.start_time }">
            {{ form.start_time || '请选择开始时间' }}
          </view>
        </picker>
      </FormField>

      <FormField label="门票价格">
        <input
          v-model="form.ticket_price"
          class="input"
          type="digit"
          placeholder="例如 120（留空为待定）"
          placeholder-class="input-ph"
        />
      </FormField>

      <FormField label="购票链接">
        <input
          v-model="form.ticket_url"
          class="input"
          placeholder="例如 https://example.com/tickets"
          placeholder-class="input-ph"
        />
      </FormField>

      <view class="setlist-block">
        <view class="setlist-label">
          <text class="setlist-title">Setlist（曲目单）</text>
          <text class="setlist-hint">可拖动调整顺序</text>
        </view>
        <SetlistEditor v-model="form.setlist" />
      </view>
    </view>

    <view class="action-bar">
      <button class="btn btn-draft" :loading="saving" :disabled="saving" @click="saveDraft">
        保存草稿
      </button>
      <button class="btn btn-publish" :loading="publishing" :disabled="publishing" @click="publish">
        发 布
      </button>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { requireAuth } from '../../common/guard.js'
import FormField from '../../common/components/FormField.vue'
import UploadImage from '../../common/components/UploadImage.vue'
import SetlistEditor from '../../common/components/SetlistEditor.vue'
import { createLive, updateLive, publishLive, getLive, getLivehouses } from '../../services/band-api.js'

const editId = ref(null)
const saving = ref(false)
const publishing = ref(false)
const livehouses = ref([])

const form = ref({
  title: '',
  poster_image_url: '',
  livehouse_id: null,
  live_date: '',
  start_time: '',
  ticket_price: '',
  ticket_url: '',
  setlist: []
})

const livehouseNames = computed(() => livehouses.value.map((v) => v.name))
const livehouseIndex = computed(() => {
  const idx = livehouses.value.findIndex((v) => v.id === form.value.livehouse_id)
  return idx
})

onLoad((query) => {
  if (query && query.id) {
    editId.value = Number(query.id)
    uni.setNavigationBarTitle({ title: '编辑 Live' })
    loadLive(editId.value)
  }
  loadLivehouses()
})

onShow(() => {
  if (!requireAuth({ endpoint: 'band' })) return
})

async function loadLivehouses() {
  try {
    const res = await getLivehouses()
    livehouses.value = (res && res.items) || []
  } catch (err) {
    /* ignore */
  }
}

async function loadLive(id) {
  try {
    const res = await getLive(id)
    const live = (res && res.live) || {}
    form.value = {
      title: live.title || '',
      poster_image_url: live.poster_image_url || '',
      livehouse_id: live.livehouse_id != null ? live.livehouse_id : null,
      live_date: live.live_date || '',
      start_time: live.start_time || '',
      ticket_price: live.ticket_price != null && live.ticket_price !== '' ? String(live.ticket_price) : '',
      ticket_url: live.ticket_url || '',
      setlist: ((res && res.setlist) || live.setlist || []).map((s) => ({
        song_title: s.song_title || '',
        band_id: s.band_id != null ? s.band_id : null
      }))
    }
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '加载演出失败', icon: 'none' })
  }
}

function onLivehouseChange(e) {
  const idx = Number(e.detail.value)
  const venue = livehouses.value[idx]
  if (venue) form.value.livehouse_id = venue.id
}
function onDateChange(e) {
  form.value.live_date = e.detail.value
}
function onTimeChange(e) {
  form.value.start_time = e.detail.value
}

function buildPayload(action) {
  return {
    title: String(form.value.title || '').trim(),
    livehouse_id: form.value.livehouse_id,
    live_date: form.value.live_date,
    start_time: form.value.start_time,
    ticket_price: form.value.ticket_price !== '' ? Number(form.value.ticket_price) : 0,
    ticket_url: String(form.value.ticket_url || '').trim(),
    poster_image_url: form.value.poster_image_url || '',
    setlist: form.value.setlist
      .filter((s) => s && s.song_title && String(s.song_title).trim())
      .map((s) => ({ song_title: String(s.song_title).trim(), band_id: s.band_id != null ? s.band_id : null })),
    action
  }
}

function validatePublish(payload) {
  if (!payload.title) return '请填写 Live 名称'
  if (!payload.livehouse_id) return '请选择演出场地'
  if (!payload.live_date) return '请选择演出日期'
  if (!payload.start_time) return '请选择开始时间'
  return ''
}

async function saveDraft() {
  if (saving.value || publishing.value) return
  const payload = buildPayload('save_draft')
  if (!payload.title) {
    uni.showToast({ title: '请至少填写 Live 名称', icon: 'none' })
    return
  }
  saving.value = true
  try {
    if (editId.value) {
      await updateLive(editId.value, payload)
    } else {
      await createLive(payload)
    }
    uni.showToast({ title: '已保存草稿', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 400)
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

async function publish() {
  if (saving.value || publishing.value) return
  const payload = buildPayload('publish')
  const msg = validatePublish(payload)
  if (msg) {
    uni.showToast({ title: msg, icon: 'none' })
    return
  }
  publishing.value = true
  try {
    if (editId.value) {
      await updateLive(editId.value, payload)
      await publishLive(editId.value)
    } else {
      await createLive(payload)
    }
    uni.showToast({ title: '发布成功', icon: 'success' })
    setTimeout(() => {
      // 回工作台 tab（保留页面栈与 tabBar；reLaunch 会清空页面栈导致无返回按钮）
      uni.switchTab({ url: '/pages/dashboard/index' })
    }, 500)
  } catch (err) {
    uni.showToast({ title: (err && err.message) || '发布失败', icon: 'none' })
  } finally {
    publishing.value = false
  }
}
</script>

<style scoped>
.edit-page {
  min-height: 100vh;
  padding-bottom: 160rpx;
  background: var(--color-bg, #f5f6f8);
  box-sizing: border-box;
}
.edit-form {
  padding-top: 20rpx;
}
.input {
  height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.input-ph {
  color: var(--color-text-muted, #9ca3af);
}
.picker-value {
  min-height: 72rpx;
  line-height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.picker-empty {
  color: var(--color-text-muted, #9ca3af);
}
.setlist-block {
  padding: 24rpx;
}
.setlist-label {
  display: flex;
  align-items: baseline;
  margin-bottom: 16rpx;
}
.setlist-title {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.setlist-hint {
  margin-left: 12rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
.action-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  padding: 20rpx 24rpx calc(20rpx + env(safe-area-inset-bottom));
  background: var(--color-surface, #ffffff);
  border-top: 1rpx solid var(--color-border, #e5e7eb);
}
.btn {
  flex: 1;
  height: 88rpx;
  line-height: 88rpx;
  margin: 0 10rpx;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  border-radius: 12rpx;
}
.btn-draft {
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-bg, #f5f6f8);
  border: 1rpx solid var(--color-border, #e5e7eb);
}
.btn-publish {
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
.btn-publish[disabled] {
  opacity: 0.7;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
</style>
