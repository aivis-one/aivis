<script setup lang="ts">
import { computed, useAttrs, useId } from 'vue'
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

// ATTRIBUTE PASS-THROUGH -- the same arrangement CInput and CTextarea already
// carry. Without it every fallthrough attribute lands on the outer <div>, where
// it does nothing: an `aria-label` written on <CSelect> named the wrapper, not
// the control, so the one remedy a reader would reach for was a silent no-op.
// class/style stay on the root so a consumer can still position the group;
// everything else, listeners included, goes to the <select>.
defineOptions({ inheritAttrs: false })
const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const controlAttrs = computed(() => {
  const { class: _c, style: _s, ...rest } = attrs
  return rest
})

function onChange(e: Event): void {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}

// A4: a visible label is not an accessible name unless it is ASSOCIATED. This
// carried <label> with no `for` and the control with no `id`, so a screen
// reader saw an unlabelled field beside some loose text. useId() (Vue 3.5)
// pairs them and stays unique across every instance on the page.
const fieldId = useId()
</script>

<template>
  <div class="c-input-group" v-bind="rootAttrs">
    <label v-if="label" :for="fieldId" class="c-input-label">{{ label }}</label>
    <select
      :id="fieldId"
      class="c-select"
      :class="{ 'c-select--error': !!error }"
      :value="modelValue"
      v-bind="controlAttrs"
      @change="onChange"
    >
      <option v-if="placeholder" value="" disabled>
        {{ placeholder }}
      </option>
      <option v-for="opt in options" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
    </select>
    <div v-if="error" class="c-input-error">
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.c-input-group {
  margin-bottom: var(--space-4);
}
.c-input-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.c-select {
  width: 100%;
  padding: var(--space-4) var(--space-4);
  padding-right: var(--space-6-lg);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--fs-sm);
  font-family: inherit;
  background: var(--bg-page);
  color: var(--text-primary);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23525252' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 16px center;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}
.c-select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}
.c-select--error {
  border-color: var(--danger);
}
.c-input-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  margin-top: var(--space-1);
}
</style>
