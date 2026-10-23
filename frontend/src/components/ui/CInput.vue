<script setup lang="ts">
import { useI18n } from 'vue-i18n'
// Text input with label, error state, and optional password toggle.

import { computed, ref, useAttrs, useId } from 'vue'
import { AlertTriangle, Eye, EyeOff } from '@/components/ui/icons'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    label?: string
    placeholder?: string
    error?: string
    type?: string
    autocomplete?: string
    // 'compact' is the dense panel field the balance screens use: tighter box,
    // thinner rule, LARGER text -- amounts are read, not skimmed. It is not a
    // smaller control, which is why it is not called 'sm'.
    size?: 'default' | 'compact'
  }>(),
  { modelValue: '', type: 'text', size: 'default' },
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

const showPassword = ref(false)
const isPassword = props.type === 'password'

function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}

// A4: a visible label is not an accessible name unless it is ASSOCIATED.
// These carried <label> with no `for` and the control with no `id`, so a screen
// reader saw an unlabelled field beside some loose text. useId() (Vue 3.5) pairs
// them and stays unique across every instance on the page.
const fieldId = useId()
const errorId = fieldId + '-error'

// A1: the reveal control is an icon with no text, and its NAME changes with
// state -- announcing "show password" while the password is already visible is
// worse than no label at all.
const { t } = useI18n()
</script>

<template>
  <div
    class="ds-field c-field"
    :data-size="size === 'compact' ? 'sm' : undefined"
    v-bind="rootAttrs"
  >
    <label v-if="label" :for="fieldId" class="ds-field__label">{{ label }}</label>
    <div class="ds-input-wrap">
      <input
        :id="fieldId"
        class="ds-input"
        :class="{ 'ds-input--reveal': isPassword }"
        :type="isPassword && showPassword ? 'text' : type"
        :value="modelValue"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="error ? errorId : undefined"
        v-bind="controlAttrs"
        @input="onInput"
      />
      <button
        v-if="isPassword"
        type="button"
        class="ds-input-reveal"
        :aria-label="showPassword ? t('common.hidePassword') : t('common.showPassword')"
        @click="showPassword = !showPassword"
      >
        <EyeOff v-if="showPassword" :size="20" />
        <Eye v-else :size="20" />
      </button>
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
