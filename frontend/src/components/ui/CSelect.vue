<script setup lang="ts">
// Dropdown select with label and error state. Custom arrow via CSS.

export interface SelectOption {
  value: string
  label: string
}

withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    options: SelectOption[]
    placeholder?: string
    error?: string
  }>(),
  { modelValue: '' },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function onChange(e: Event): void {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}
</script>

<template>
  <div class="c-input-group">
    <label v-if="label" class="c-input-label">{{ label }}</label>
    <select
      class="c-select"
      :class="{ 'c-select--error': !!error }"
      :value="modelValue"
      @change="onChange"
    >
      <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
      <option v-for="opt in options" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
    </select>
    <div v-if="error" class="c-input-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.c-input-group { margin-bottom: 16px; }
.c-input-label { display: block; font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }

.c-select {
  width: 100%; padding: 14px 16px; padding-right: 40px;
  border: 2px solid var(--border-default); border-radius: var(--radius-md);
  font-size: 15px; font-family: inherit;
  background: var(--bg-page); color: var(--text-primary); cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23525252' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 16px center;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.c-select:focus { outline: none; border-color: var(--primary); box-shadow: var(--shadow-focus); }
.c-select--error { border-color: var(--danger); }
.c-input-error { font-size: 12px; color: var(--danger); margin-top: 4px; }
</style>
