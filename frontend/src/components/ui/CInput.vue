<script setup lang="ts">
import { useI18n } from 'vue-i18n'
// Text input with label, error state, and optional password toggle.

import { computed, ref, useAttrs, useId } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'

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

// A1: the reveal control is an icon with no text, and its NAME changes with
// state -- announcing "show password" while the password is already visible is
// worse than no label at all.
const { t } = useI18n()
</script>

<template>
  <div class="c-input-group" v-bind="rootAttrs">
    <label v-if="label" :for="fieldId" class="c-input-label">{{ label }}</label>
    <div class="c-input-wrapper">
      <input
        :id="fieldId"
        class="c-input"
        :class="[
          { 'c-input--error': !!error },
          size === 'compact' && 'c-input--compact',
          isPassword && 'c-input--reveal',
        ]"
        :type="isPassword && showPassword ? 'text' : type"
        :value="modelValue"
        :placeholder="placeholder"
        :autocomplete="autocomplete"
        v-bind="controlAttrs"
        @input="onInput"
      />
      <button
        v-if="isPassword"
        type="button"
        class="c-input-toggle"
        :aria-label="showPassword ? t('common.hidePassword') : t('common.showPassword')"
        @click="showPassword = !showPassword"
      >
        <EyeOff v-if="showPassword" :size="20" />
        <Eye v-else :size="20" />
      </button>
    </div>
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

.c-input {
  width: 100%;
  padding: var(--space-4) var(--space-4);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--fs-sm);
  font-family: inherit;
  background: var(--bg-page);
  color: var(--text-primary);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.c-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.c-input::placeholder {
  color: var(--text-tertiary);
}

/* The kit had no disabled state at all, which went unnoticed because until
   attribute pass-through existed nothing could pass `disabled` to the control.
   The forms that adopt this variant disable their fields while submitting. */
.c-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.c-input--error {
  border-color: var(--danger);
  animation: c-shake 0.3s ease;
}

.c-input--compact {
  padding: var(--space-3);
  border-width: 1px;
  border-radius: var(--radius-sm);
  font-size: var(--fs-body);
  transition: border-color 0.15s;
}

.c-input-wrapper {
  position: relative;
}
/* Only a field that actually HAS a reveal button reserves room for one. This
   matched every .c-input in the wrapper, so an email field carried 48px of
   right padding for a button that was never rendered. */
.c-input-wrapper .c-input--reveal {
  padding-right: var(--space-7);
}

.c-input-toggle {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  padding: var(--space-1);
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
}

/* A5: the PAINTED box stays this size on purpose; the HIT AREA is expanded past
   it with a centred overlay. Growing the box itself would move the text this
   control sits inside or beside. max() so an already-large box never shrinks. */
.c-input-toggle::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}

.c-input-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  margin-top: var(--space-1);
}

@keyframes c-shake {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-4px);
  }
  75% {
    transform: translateX(4px);
  }
}
</style>
