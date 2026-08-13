<template>
  <view class="page">
    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>

    <template v-else>
      <view class="form-card">
        <FormField label="演出名称" required>
          <input v-model="form.title" class="input" placeholder="请输入演出名称" />
        </FormField>

        <FormField label="场地" required>
          <picker :range="venueNames" :value="venueIndex" @change="onVenueChange">
            <view class="picker-value">{{ venueNames[venueIndex] || '请选择场地' }}</view>
          </picker>
        </FormField>

        <FormField label="演出日期" required>
          <picker mode="date" :value="form.live_date" @change="onDateChange">
            <view class="picker-value">{{ form.live_date || '请选择日期' }}</view>
          </picker>
        </FormField>

        <FormField label="开始时间">
          <picker mode="time" :value="form.start_time" @change="onTimeChange">
            <view class="picker-value">{{ form.start_time || '请选择时间' }}</view>
          </picker>
        </FormField>

        <FormField label="票价（元）">
          <input v-model="form.ticket_price" class="input" type="digit" placeholder="如 150" />
        </FormField>

        <FormField label="购票链接">
          <input v-model="form.ticket_url" class="input" placeholder="https://..." />
        </FormField>

        <FormField label="海报">
          <UploadImage v-model="form.poster_image_url" hint="上传海报" />
        </FormField>

        <FormField label="参演乐队（逗号分隔）">
          <input v-model="bandNamesText" class="input" placeholder="如 霓虹乐队, 回声碎片" />
        </FormField>

        <view class="setlist-field">
          <text class="field-label">Setlist 曲目</text>
          <SetlistEditor v-model="form.setlist" />
        </view>
      </view>

      <button class="save-btn" :loading="saving" @click="save">保存修改</button>
    </template>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import FormField from '../../common/components/FormField.vue'
import UploadImage from '../../common/components/UploadImage.vue'
import SetlistEditor from '../../common/components/SetlistEditor.vue'
import { requireAuth } from '../../common/guard.js'
import { getLive, updateLive, listVenues } from '../../services/admin-api.js'

const liveId = ref(null)
const loading = ref(true)
const saving = ref(false)

const venues = ref([])
const form = reactive({
  title: '',
  livehouse_id: null,
  live_date: '',
  start_time: '',
  ticket_price: '',
  ticket_url: '',
  poster_image_url: '',
  band_names: [],
  setlist: []
})

const venueNames = computed(() => venues.value.map((v) => v.name))
const venueIndex = computed(() => {
  const idx = venues.value.findIndex((v) => v.id === form.livehouse_id)
  return idx >= 0 ? idx : 0
})

const bandNamesText = computed({
  get() {
    return (form.band_names || []).join(', ')
  },
  set(val) {
    form.band_names = String(val || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  }
})

onLoad(async (options) => {
  if (!requireAuth({ endpoint: 'admin' })) return
  liveId.value = options && options.id
  try {
    const [venueRes, liveRes] = await Promise.all([
      listVenues(),
      getLive(liveId.value)
    ])
    venues.value = (venueRes && venueRes.items) || []
    const live = (liveRes && liveRes.live) || {}
    form.title = live.title || ''
    form.livehouse_id = live.livehouse_id || ((liveRes && liveRes.venue && liveRes.venue.id) || null)
    form.live_date = live.live_date || ''
    form.start_time = live.start_time ? String(live.start_time).slice(0, 5) : ''
    form.ticket_price = live.ticket_price != null ? String(live.ticket_price) : ''
    form.ticket_url = live.ticket_url || ''
    form.poster_image_url = liveRes.poster_image_url || live.poster_image_url || ''
    form.band_names = Array.isArray(live.band_names) ? live.band_names.slice() : []
    form.setlist = Array.isArray(liveRes.setlist) ? liveRes.setlist.slice() : []
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载演出失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function onVenueChange(e) {
  const idx = Number(e.detail.value)
  const v = venues.value[idx]
  if (v) form.livehouse_id = v.id
}

function onDateChange(e) {
  form.live_date = e.detail.value
}

function onTimeChange(e) {
  form.start_time = e.detail.value
}

async function save() {
  if (!form.title.trim()) {
    uni.showToast({ title: '请填写演出名称', icon: 'none' })
    return
  }
  if (!form.livehouse_id) {
    uni.showToast({ title: '请选择场地', icon: 'none' })
    return
  }
  saving.value = true
  try {
    await updateLive(liveId.value, {
      title: form.title.trim(),
      livehouse_id: form.livehouse_id,
      live_date: form.live_date,
      start_time: form.start_time,
      ticket_price: form.ticket_price ? Number(form.ticket_price) : null,
      ticket_url: form.ticket_url,
      poster_image_url: form.poster_image_url,
      band_names: form.band_names,
      setlist: (form.setlist || []).map((s) => ({
        song_title: (s && s.song_title) || '',
        band_id: (s && s.band_id) != null ? s.band_id : null
      })).filter((s) => s.song_title)
    })
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 400)
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--color-bg, #f5f6f8);
  padding-bottom: 60rpx;
}

.state-box {
  padding: 160rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

.form-card {
  background: var(--color-surface, #ffffff);
  margin: 24rpx;
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}

.input {
  width: 100%;
  height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.picker-value {
  width: 100%;
  height: 72rpx;
  line-height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
}
.setlist-field {
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}

.save-btn {
  height: 92rpx;
  line-height: 92rpx;
  margin: 24rpx;
  font-size: var(--font-size-lg, 32rpx);
  font-weight: 600;
  color: #ffffff;
  background: var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}
</style>
