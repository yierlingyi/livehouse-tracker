<template>
  <view class="form-field">
    <text class="field-label">
      {{ label }}<text v-if="required" class="field-required"> *</text>
    </text>
    <view class="field-control">
      <slot />
    </view>
  </view>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  required: { type: Boolean, default: false }
})
</script>

<style scoped>
.form-field {
  padding: 20rpx 24rpx;
  background: var(--color-surface, #ffffff);
  border-bottom: 1rpx solid var(--color-border, #e5e7eb);
}
.field-label {
  display: block;
  margin-bottom: 12rpx;
  font-size: var(--font-size-sm, 26rpx);
  color: var(--color-text-secondary, #6b7280);
}
.field-required {
  color: var(--color-primary, #e5484d);
}
.field-control {
  width: 100%;
}
</style>
