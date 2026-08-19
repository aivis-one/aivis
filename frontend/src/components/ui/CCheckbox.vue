<script setup lang="ts">
// Checkbox with label. Mockup checkbox-row pattern.

import { Check } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{ modelValue?: boolean; label?: string }>(),
  { modelValue: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

function toggle(): void {
  emit('update:modelValue', !props.modelValue)
}
</script>

<template>
  <div class="c-checkbox" @click="toggle">
    <div class="c-checkbox__box" :class="{ 'c-checkbox__box--checked': modelValue }">
      <Check v-if="modelValue" :size="16" />
    </div>
    <span v-if="label" class="c-checkbox__label">{{ label }}</span>
    <span v-else class="c-checkbox__label"><slot /></span>
  </div>
</template>

<style scoped>
.c-checkbox { display: flex; align-items: flex-start; gap: var(--space-3); cursor: pointer; user-select: none; }
.c-checkbox__box {
  width: var(--size-2xs); height: var(--size-2xs); min-width: var(--size-2xs); border: 2px solid var(--border-default);
  border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; color: var(--on-primary); margin-top: var(--space-1);
}
.c-checkbox__box--checked { background: var(--primary); border-color: var(--primary); }
.c-checkbox__label { font-size: var(--fs-xs); color: var(--text-secondary); line-height: 1.4; }
</style>
