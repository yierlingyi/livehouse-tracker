<template>
  <view class="setlist-editor">
    <view v-for="(item, index) in songs" :key="index" class="song-row">
      <view class="song-index">{{ index + 1 }}</view>
      <input
        v-model="item.song_title"
        class="song-input"
        placeholder="歌曲名称"
        placeholder-class="song-input-ph"
      />
      <view class="song-actions">
        <text class="song-btn" @click.stop="moveUp(index)">↑</text>
        <text class="song-btn" @click.stop="moveDown(index)">↓</text>
        <text class="song-btn song-btn-del" @click.stop="remove(index)">✕</text>
      </view>
    </view>

    <view class="add-row">
      <button class="add-btn" @click="add">＋ 添加歌曲</button>
    </view>
  </view>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  // v-model：[{song_title, band_id?}]
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: '歌曲名称' }
})

const emit = defineEmits(['update:modelValue'])

const songs = ref(clone(props.modelValue))

function clone(arr) {
  return (arr || []).map((s) => ({
    song_title: (s && s.song_title) || '',
    band_id: (s && s.band_id) != null ? s.band_id : null
  }))
}

watch(
  () => props.modelValue,
  (val) => {
    songs.value = clone(val)
  },
  { deep: true }
)

watch(
  songs,
  (val) => {
    emit(
      'update:modelValue',
      val.map((s) => ({ song_title: s.song_title, band_id: s.band_id }))
    )
  },
  { deep: true }
)

function add() {
  songs.value.push({ song_title: '', band_id: null })
}

function remove(i) {
  songs.value.splice(i, 1)
}

function moveUp(i) {
  if (i <= 0) return
  const arr = songs.value
  const tmp = arr[i - 1]
  arr[i - 1] = arr[i]
  arr[i] = tmp
}

function moveDown(i) {
  if (i >= songs.value.length - 1) return
  const arr = songs.value
  const tmp = arr[i + 1]
  arr[i + 1] = arr[i]
  arr[i] = tmp
}
</script>

<style scoped>
.setlist-editor {
  width: 100%;
}
.song-row {
  display: flex;
  align-items: center;
  margin-bottom: 12rpx;
}
.song-index {
  flex-shrink: 0;
  width: 48rpx;
  text-align: center;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-muted, #9ca3af);
}
.song-input {
  flex: 1;
  min-width: 0;
  height: 72rpx;
  padding: 0 20rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-text, #1f2329);
  background: var(--color-bg, #f5f6f8);
  border-radius: 8rpx;
}
.song-input-ph {
  color: var(--color-text-muted, #9ca3af);
}
.song-actions {
  flex-shrink: 0;
  display: flex;
  margin-left: 12rpx;
}
.song-btn {
  width: 52rpx;
  height: 52rpx;
  margin-left: 8rpx;
  text-align: center;
  line-height: 52rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-border, #e5e7eb);
  border-radius: 8rpx;
}
.song-btn-del {
  color: var(--color-primary, #e5484d);
}
.add-row {
  margin-top: 8rpx;
}
.add-btn {
  height: 72rpx;
  line-height: 72rpx;
  font-size: var(--font-size-base, 28rpx);
  color: var(--color-primary, #e5484d);
  background: transparent;
  border: 1rpx dashed var(--color-primary, #e5484d);
  border-radius: var(--radius, 16rpx);
}
</style>
