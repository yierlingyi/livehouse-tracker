<template>
  <view class="upload-image" @click="choose">
    <image
      v-if="currentUrl"
      class="up-image"
      :src="resolveImageUrl(currentUrl)"
      mode="aspectFill"
      @error="imageError = true"
    />
    <view v-else class="up-placeholder">
      <text class="up-plus">＋</text>
      <text class="up-hint">{{ hint }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { API_BASE, USE_MOCK, resolveImageUrl } from '../http.js'
import { getToken } from '../storage.js'

const props = defineProps({
  // 兼容两种写法：v-model（modelValue）与单向 imageUrl
  imageUrl: { type: String, default: '' },
  modelValue: { type: String, default: '' },
  hint: { type: String, default: '上传图片' },
  // mock 模式占位图（默认用各端 static/mock-cover.svg）
  mockUrl: { type: String, default: '/static/mock-cover.svg' }
})

const emit = defineEmits(['update:modelValue'])

const imageError = ref(false)

const currentUrl = computed(() => {
  if (props.modelValue || props.imageUrl) {
    if (imageError.value) return ''
    return props.modelValue || props.imageUrl
  }
  return ''
})

function emitUrl(url) {
  imageError.value = false
  emit('update:modelValue', url || '')
}

function choose() {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    success: (res) => {
      const tempPath = res.tempFilePaths && res.tempFilePaths[0]
      if (!tempPath) return
      if (USE_MOCK) {
        // mock 模式：直接返回本地占位图，不走网络
        uni.showToast({ title: '已选择图片（Mock）', icon: 'none' })
        emitUrl(props.mockUrl)
        return
      }
      uploadReal(tempPath)
    }
  })
}

// 真实模式：multipart 上传 POST /api/v1/upload
function uploadReal(filePath) {
  uni.uploadFile({
    url: API_BASE + '/api/v1/upload',
    filePath,
    name: 'file',
    header: (() => {
      const token = getToken()
      return token ? { Authorization: 'Bearer ' + token } : {}
    })(),
    success: (res) => {
      try {
        const body = JSON.parse(res.data || '{}')
        if (body && body.url) {
          emitUrl(body.url)
        } else {
          uni.showToast({ title: (body && body.message) || '上传失败', icon: 'none' })
        }
      } catch (e) {
        uni.showToast({ title: '上传响应解析失败', icon: 'none' })
      }
    },
    fail: (err) => {
      uni.showToast({ title: (err && err.errMsg) || '上传失败', icon: 'none' })
    }
  })
}
</script>

<style scoped>
.upload-image {
  position: relative;
  width: 240rpx;
  height: 240rpx;
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.up-image {
  width: 100%;
  height: 100%;
}
.up-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--color-border, #e5e7eb);
}
.up-plus {
  font-size: 64rpx;
  color: var(--color-text-muted, #9ca3af);
  line-height: 1;
}
.up-hint {
  margin-top: 8rpx;
  font-size: var(--font-size-xs, 22rpx);
  color: var(--color-text-muted, #9ca3af);
}
</style>
