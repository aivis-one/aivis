<script setup lang="ts">
import { computed, useAttrs, useId } from 'vue'
import { AlertTriangle, ChevronDown } from '@/components/ui/icons'
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
const errorId = fieldId + '-error'
</script>

<template>
  <div class="ds-field c-field" v-bind="rootAttrs">
    <label v-if="label" :for="fieldId" class="ds-field__label">{{ label }}</label>
    <div class="ds-select">
      <select
        :id="fieldId"
        class="ds-input"
        :value="modelValue"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="error ? errorId : undefined"
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
      <ChevronDown :size="16" />
    </div>
    <p v-if="error" :id="errorId" class="ds-field__error">
      <AlertTriangle :size="16" />
      <span>{{ error }}</span>
    </p>
  </div>
</template>

<style scoped>
/* The cabinet's forms stack their fields on this gap. */
.c-field {
  margin-block-end: var(--space-4);
}
</style>
