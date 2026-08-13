<template>
  <view class="page">
    <!-- 新增 / 编辑表单 -->
    <view class="form-card">
      <view class="form-card-title">{{ editingId ? '编辑同好群' : '新增同好群' }}</view>

      <view class="field-wrap">
        <text class="field-label">城市</text>
        <picker :range="CITIES" @change="onCityChange">
          <view class="picker-value">{{ form.city || '请选择城市' }}</view>
        </picker>
      </view>

      <view class="field-wrap">
        <text class="field-label">平台</text>
        <picker :range="platformLabels" @change="onPlatformChange">
          <view class="picker-value">{{ platformLabel(form.platform) }}</view>
        </picker>
      </view>

      <view class="field-wrap">
        <text class="field-label">群号</text>
        <input v-model="form.group_id" class="input" placeholder="请输入群号" />
      </view>

      <view class="form-actions">
        <button class="btn btn-primary" :loading="saving" @click="save">
          {{ editingId ? '保存' : '新增' }}
        </button>
        <button v-if="editingId" class="btn btn-cancel" @click="resetForm">取消</button>
      </view>
    </view>

    <!-- 列表 -->
    <view class="list-wrap">
      <view v-if="loading" class="state-box">
        <text class="state-text">加载中...</text>
      </view>
      <template v-else>
        <ListCard
          v-for="g in groups"
          :key="g.id"
          :title="g.city + ' · ' + platformLabel(g.platform)"
          :sub="'群号：' + g.group_id"
          @click="startEdit(g)"
        >
          <template #extra>
            <view class="row-actions">
              <text class="act-btn" @click.stop="startEdit(g)">编辑</text>
              <text class="act-btn act-danger" @click.stop="confirmDelete(g)">删除</text>
            </view>
          </template>
        </ListCard>
        <EmptyState v-if="!groups.length" text="暂无同好群" />
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import ListCard from '../../common/components/ListCard.vue'
import EmptyState from '../../common/components/EmptyState.vue'
import { requireAuth } from '../../common/guard.js'
import { CITIES, PLATFORMS } from '../../common/constants.js'
import { listGroups, createGroup, updateGroup, deleteGroup } from '../../services/admin-api.js'

const groups = ref([])
const loading = ref(false)
const saving = ref(false)
const editingId = ref(null)

const form = reactive({ city: 'Tokyo', platform: 'wechat', group_id: '' })

const platformLabels = Object.keys(PLATFORMS).map((k) => PLATFORMS[k])

onShow(() => {
  if (!requireAuth({ endpoint: 'admin' })) return
  load()
})

async function load() {
  loading.value = true
  try {
    const res = await listGroups()
    groups.value = (res && res.items) || []
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载同好群失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function platformLabel(p) {
  return PLATFORMS[p] || (p === 'qq' ? 'QQ' : '微信')
}

function onCityChange(e) {
  form.city = CITIES[Number(e.detail.value)]
}

function onPlatformChange(e) {
  const keys = Object.keys(PLATFORMS)
  form.platform = keys[Number(e.detail.value)]
}

function resetForm() {
  editingId.value = null
  form.city = 'Tokyo'
  form.platform = 'wechat'
  form.group_id = ''
}

function startEdit(g) {
  editingId.value = g.id
  form.city = g.city
  form.platform = g.platform
  form.group_id = g.group_id
}

async function save() {
  if (!form.city || !form.group_id.trim()) {
    uni.showToast({ title: '请填写城市与群号', icon: 'none' })
    return
  }
  const payload = {
    city: form.city,
    platform: form.platform,
    group_id: form.group_id.trim()
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateGroup(editingId.value, payload)
      uni.showToast({ title: '已保存', icon: 'success' })
    } else {
      await createGroup(payload)
      uni.showToast({ title: '已新增', icon: 'success' })
    }
    resetForm()
    load()
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

function confirmDelete(g) {
  uni.showModal({
    title: '删除同好群',
    content: '确定删除「' + g.city + ' · ' + platformLabel(g.platform) + ' · ' + g.group_id + '」吗？',
    confirmText: '删除',
    confirmColor: '#e5484d',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await deleteGroup(g.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        if (editingId.value === g.id) resetForm()
        load()
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
  padding-bottom: 60rpx;
}

.form-card {
  margin: 24rpx 24rpx 8rpx;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius, 16rpx);
  overflow: hidden;
}
.form-card-title {
  padding: 24rpx 24rpx 0;
  font-size: var(--font-size-base, 28rpx);
  font-weight: 600;
  color: var(--color-text, #1f2329);
}
.field-wrap {
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
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
.form-actions {
  display: flex;
  padding: 20rpx 24rpx 24rpx;
}
.btn {
  flex: 1;
  height: 80rpx;
  line-height: 80rpx;
  font-size: var(--font-size-base, 28rpx);
  border-radius: var(--radius, 16rpx);
}
.btn-primary {
  color: #ffffff;
  background: var(--color-primary, #e5484d);
}
.btn-cancel {
  margin-left: 16rpx;
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-bg, #f5f6f8);
}

.list-wrap {
  padding: 24rpx;
}

.state-box {
  padding: 80rpx 0;
  text-align: center;
}
.state-text {
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}

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
</style>
