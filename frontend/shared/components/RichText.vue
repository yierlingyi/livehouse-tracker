<template>
  <view class="rich-text">
    <template v-for="(line, i) in lines" :key="i">
      <view v-if="line" class="rich-line">{{ line }}</view>
      <view v-else class="rich-blank" />
    </template>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 纯文本内容，\n 按换行渲染
  content: { type: String, default: '' }
})

const lines = computed(() => String(props.content || '').split('\n'))
</script>

<style scoped>
.rich-text {
  width: 100%;
  word-break: break-all;
}
.rich-line {
  font-size: var(--font-size-base, 28rpx);
  line-height: 1.6;
  color: var(--color-text, #1f2329);
}
.rich-blank {
  height: 24rpx;
}
</style>
