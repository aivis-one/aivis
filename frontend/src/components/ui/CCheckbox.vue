<script setup lang="ts">
// Checkbox with label.
//
// This was a <div @click="toggle"> with a drawn box and no input of any kind:
// no role, no aria-checked, no tabindex. It could not be focused, could not be
// operated from a keyboard, and did not appear to assistive technology as a
// control at all. It was also the ONLY checkbox in the product -- there is no
// <input type="checkbox"> or [type="radio"] anywhere else in src/**.
//
// It is now a real input. The <label> wrapper gives it its accessible name
// from the label text with no id/for plumbing, and keeps the whole row
// clickable exactly as before. The input is transparent rather than hidden:
// `display: none` and `visibility: hidden` both remove it from the focus order
// and the accessibility tree, which would reproduce the defect while looking
// fixed. The focus ring is drawn on the box the user can actually see.

import { computed, nextTick, useAttrs } from 'vue'
import { Check } from '@/components/ui/icons'

const props = withDefaults(defineProps<{ modelValue?: boolean; label?: string }>(), {
  modelValue: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

// Fallthrough attributes belong on the control, not on the <label> wrapper --
// the same arrangement CInput, CTextarea and CSelect carry.
defineOptions({ inheritAttrs: false })
const attrs = useAttrs()
const rootAttrs = computed(() => ({ class: attrs.class, style: attrs.style }))
const controlAttrs = computed(() => {
  const { class: _c, style: _s, ...rest } = attrs
  return rest
})

function onChange(e: Event): void {
  const el = e.target as HTMLInputElement
  emit('update:modelValue', el.checked)
  // A native checkbox flips its own `checked` on activation, whether or not the
  // parent accepts the new value. This is a CONTROLLED component: the drawn box
  // follows `modelValue`, so if the parent rejects or defers the change the
  // input and the box would disagree -- measured on StaffUsersView, which binds
  // :model-value one-way and updates through an API call. Re-assert the model
  // after the parent has had its turn.
  void nextTick(() => {
    el.checked = props.modelValue
  })
}
</script>

<template>
  <label class="c-checkbox" v-bind="rootAttrs">
    <span class="c-checkbox__control">
      <input
        type="checkbox"
        class="c-checkbox__input"
        :checked="modelValue"
        v-bind="controlAttrs"
        @change="onChange"
      />
      <span class="c-checkbox__box" :class="{ 'c-checkbox__box--checked': modelValue }">
        <Check v-if="modelValue" :size="16" />
      </span>
    </span>
    <span class="c-checkbox__label">
      <template v-if="label">{{ label }}</template>
      <slot v-else />
    </span>
  </label>
</template>

<style scoped>
/* The system has no checkbox (Radio and Toggle only); this one keeps its form
   and takes the system's input border, focus and tokens. */
.c-checkbox {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  cursor: pointer;
  user-select: none;
}

.c-checkbox__control {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  margin-block-start: var(--space-1);
}

/* Transparent, NOT hidden: sized to the touch floor and centred on the drawn
   box, so the box stays small while the target the pointer meets is --touch-min. */
.c-checkbox__input {
  position: absolute;
  inset-inline-start: 50%;
  inset-block-start: 50%;
  translate: -50% -50%;
  inline-size: max(100%, var(--touch-min));
  block-size: max(100%, var(--touch-min));
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.c-checkbox__box {
  inline-size: var(--size-2xs);
  block-size: var(--size-2xs);
  min-inline-size: var(--size-2xs);
  border: var(--border-input-width) solid var(--border-input);
  border-radius: var(--radius-xs);
  background: var(--bg-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background-color var(--dur-fast) var(--ease-standard),
    border-color var(--dur-fast) var(--ease-standard);
  color: var(--on-primary);
}
.c-checkbox:hover .c-checkbox__box {
  border-color: var(--border-input-hover);
}
.c-checkbox__box--checked {
  background: var(--primary);
  border-color: var(--primary);
}

/* The input itself is invisible, so the system's ring goes on what the user sees. */
.c-checkbox__input:focus-visible + .c-checkbox__box {
  outline: var(--focus-width) solid var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.c-checkbox__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: var(--lh-snug);
}
</style>
