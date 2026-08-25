<script setup lang="ts">
// Checkbox with label. Mockup checkbox-row pattern.
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
import { Check } from 'lucide-vue-next'

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
  margin-top: var(--space-1);
}

/* Transparent, NOT hidden. A5: sized to the tap floor and centred on the drawn
   box, so the box stays 20px while the target the pointer meets is 44px. */
.c-checkbox__input {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.c-checkbox__box {
  width: var(--size-2xs);
  height: var(--size-2xs);
  min-width: var(--size-2xs);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  color: var(--on-primary);
}
.c-checkbox__box--checked {
  background: var(--primary);
  border-color: var(--primary);
}

/* A7: the input itself is invisible, so the ring goes on what the user sees. */
.c-checkbox__input:focus-visible + .c-checkbox__box {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.c-checkbox__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}
</style>
