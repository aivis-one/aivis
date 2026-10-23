<script setup lang="ts">
import { computed, useAttrs, useId } from 'vue'
import { AlertTriangle } from '@/components/ui/icons'
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
const errorId = fieldId + '-error'
</script>

<template>
  <div
    class="ds-field c-field"
    :data-size="size === 'compact' ? 'sm' : undefined"
    v-bind="rootAttrs"
  >
    <label v-if="label" :for="fieldId" class="ds-field__label">{{ label }}</label>
    <textarea
      :id="fieldId"
      class="ds-input"
      :class="{ 'ds-input--num': mono }"
      :value="modelValue"
      :placeholder="placeholder"
      :rows="rows"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? errorId : undefined"
      v-bind="controlAttrs"
      @input="onInput"
    />
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
