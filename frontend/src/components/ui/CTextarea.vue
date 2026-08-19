<script setup lang="ts">
import { computed, useAttrs, useId } from 'vue'
// Multi-line text input with label and error state.

withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    placeholder?: string
    error?: string
    rows?: number
    // See CInput for why this is 'compact' and not 'sm'.
    size?: 'default' | 'compact'
    // Payout details are copied and compared character by character, so the
    // fields that hold them are set in the mono token rather than the body one.
    mono?: boolean
  }>(),
  { modelValue: '', rows: 4, size: 'default', mono: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

// Native attributes belong on the CONTROL, not on the group wrapper. Without
// this, `disabled`, `step`, `min`, `inputmode`, `readonly` and friends land on
// the outer <div> and do nothing -- a field that silently ignores :disabled is
// worse than one that never offered it. class/style stay on the root so a
// consumer can still position the group; everything else, listeners included,
// goes to the control.
defineOptions({ inheritAttrs: false })
const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const controlAttrs = computed(() => {
  const { class: _c, style: _s, ...rest } = attrs
  return rest
})


function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
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
    <textarea
      :id="fieldId"
      class="c-textarea"
      :class="[
        { 'c-textarea--error': !!error },
        size === 'compact' && 'c-textarea--compact',
        mono && 'c-textarea--mono',
      ]"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      v-bind="controlAttrs"
      @input="onInput"
    />
    <div v-if="error" class="c-input-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.c-input-group { margin-bottom: var(--space-4); }
.c-input-label { display: block; font-size: var(--fs-xs); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-2); }

.c-textarea {
  width: 100%; padding: var(--space-4) var(--space-4); border: 2px solid var(--border-default);
  border-radius: var(--radius-md); font-size: var(--fs-sm); font-family: inherit;
  background: var(--bg-page); color: var(--text-primary); resize: vertical;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.c-textarea--compact {
  padding: var(--space-3);
  border-width: 1px;
  border-radius: var(--radius-sm);
  line-height: 1.5;
  transition: border-color 0.15s;
}

.c-textarea--mono { font-family: var(--font-mono); }

.c-textarea:focus { outline: none; border-color: var(--primary); box-shadow: var(--shadow-focus); }
.c-textarea::placeholder { color: var(--text-tertiary); }
/* The kit had no disabled state at all, which went unnoticed because until
   attribute pass-through existed nothing could pass `disabled` to the control.
   The forms that adopt this variant disable their fields while submitting. */
.c-textarea:disabled { opacity: 0.6; cursor: not-allowed; }
.c-textarea--error { border-color: var(--danger); }
.c-input-error { font-size: var(--fs-xs); color: var(--danger); margin-top: var(--space-1); }
</style>
