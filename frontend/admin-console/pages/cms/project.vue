<template>
  <view class="page">
    <view v-if="loading" class="state-box">
      <text class="state-text">加载中...</text>
    </view>

    <template v-else>
      <view class="form-card">
        <FormField label="项目介绍">
          <textarea v-model="form.intro" class="textarea" placeholder="请输入项目介绍" />
        </FormField>

        <FormField label="GitHub 地址">
          <input v-model="form.github_url" class="input" placeholder="https://github.com/..." />
        </FormField>

        <FormField label="作者信息">
          <input v-model="form.author" class="input" placeholder="作者 / 团队" />
        </FormField>

        <FormField label="开源协议">
          <input v-model="form.license" class="input" placeholder="如 MIT" />
        </FormField>
      </view>

      <button class="save-btn" :loading="saving" @click="save">保存</button>
    </template>
  </view>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import FormField from '../../common/components/FormField.vue'
import { requireAuth } from '../../common/guard.js'
import { getProject, updateProject } from '../../services/admin-api.js'

const loading = ref(true)
const saving = ref(false)

const form = reactive({
  intro: '',
  github_url: '',
  author: '',
  license: ''
})

onLoad(async () => {
  if (!requireAuth({ endpoint: 'admin' })) return
  try {
    const res = await getProject()
    form.intro = (res && res.intro) || ''
    form.github_url = (res && res.github_url) || ''
    form.author = (res && res.author) || ''
    form.license = (res && res.license) || ''
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    await updateProject({
      intro: form.intro,
      github_url: form.github_url,
      author: form.author,
      license: form.license
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
.textarea {
  width: 100%;
  min-height: 200rpx;
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
