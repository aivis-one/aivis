<script setup lang="ts">
// Checkbox with label, on the design system's Checkbox (K45): a tick, never a
// switch (an agreement is ticked like a signature; a setting that applies at once
// is a Toggle).
//
// A real <input type="checkbox"> inside the <label>, which gives it its accessible
// name from the label text with no id/for plumbing and keeps the whole row
// clickable. The input is transparent rather than hidden (the system draws it so):
// `display: none` and `visibility: hidden` both remove it from the focus order and
// the accessibility tree. The focus ring is drawn on the box the user can see.
// The label is the `label` prop or the default slot; a slot may hold links (the
// purchase terms), and a link opens its page without toggling the box.

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
  <label class="ds-checkbox" v-bind="rootAttrs">
    <input
      type="checkbox"
      class="ds-checkbox__input"
      :checked="modelValue"
      v-bind="controlAttrs"
      @change="onChange"
    />
    <span class="ds-checkbox__box"><Check class="ds-checkbox__tick" size="sm" /></span>
    <span class="ds-checkbox__text">
      <template v-if="label">{{ label }}</template>
      <slot v-else />
    </span>
  </label>
</template>
