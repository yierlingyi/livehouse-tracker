<template>
  <view class="page">
    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>

    <template v-else>
      <view class="form-card">
        <FormField label="场地名称" required>
          <input v-model="form.name" class="input" placeholder="请输入场地名称" />
        </FormField>

        <FormField label="所在城市">
          <picker :range="CITIES" :value="cityIndex" @change="onCityChange">
            <view class="picker-value">{{ form.city || '请选择城市' }}</view>
          </picker>
        </FormField>

        <FormField label="地址">
          <input v-model="form.address" class="input" placeholder="请输入详细地址" />
        </FormField>

        <FormField label="联系电话">
          <input v-model="form.phone" class="input" type="number" placeholder="请输入联系电话" />
        </FormField>

        <FormField label="场地图片">
          <UploadImage v-model="form.image_url" hint="上传外观图片" />
        </FormField>

        <FormField label="场地介绍">
          <textarea v-model="form.intro" class="textarea" placeholder="请输入场地介绍" />
        </FormField>

        <FormField label="平面图（可选）">
          <UploadImage v-model="form.floorplan_url" hint="上传平面图" />
        </FormField>
      </view>

      <button class="save-btn" :loading="saving" @click="save">{{ isEdit ? '保存修改' : '新增场地' }}</button>
    </template>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import FormField from '../../common/components/FormField.vue'
import UploadImage from '../../common/components/UploadImage.vue'
import { requireAuth } from '../../common/guard.js'
import { CITIES } from '../../common/constants.js'
import { getVenue, createVenue, updateVenue } from '../../services/admin-api.js'

const venueId = ref(null)
const loading = ref(false)
const saving = ref(false)

const form = reactive({
  name: '',
  city: '',
  address: '',
  phone: '',
  intro: '',
  image_url: '',
  floorplan_url: ''
})

const isEdit = computed(() => !!venueId.value)
const cityIndex = computed(() => {
  const idx = CITIES.indexOf(form.city)
  return idx >= 0 ? idx : 0
})

onLoad(async (options) => {
  if (!requireAuth({ endpoint: 'admin' })) return
  const id = options && options.id
  if (!id) {
    form.city = 'Tokyo'
    return
  }
  venueId.value = id
  loading.value = true
  try {
    const v = await getVenue(id)
    form.name = v.name || ''
    form.city = v.city || 'Tokyo'
    form.address = v.address || ''
    form.phone = v.phone || ''
    form.intro = v.intro || ''
    form.image_url = v.image_url || ''
    form.floorplan_url = v.floorplan_url || ''
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载场地失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function onCityChange(e) {
  form.city = CITIES[Number(e.detail.value)]
}

async function save() {
  if (!form.name.trim()) {
    uni.showToast({ title: '请填写场地名称', icon: 'none' })
    return
  }
  const payload = {
    name: form.name.trim(),
    city: form.city || 'Tokyo',
    address: form.address,
    phone: form.phone,
    intro: form.intro,
    image_url: form.image_url,
    floorplan_url: form.floorplan_url
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await updateVenue(venueId.value, payload)
      uni.showToast({ title: '已保存', icon: 'success' })
    } else {
      await createVenue(payload)
      uni.showToast({ title: '已新增', icon: 'success' })
    }
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
  margin: 24rpx;
  background: var(--color-surface, #ffffff);
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
.textarea {
  width: 100%;
  min-height: 160rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
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
