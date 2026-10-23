<script setup lang="ts">
// Numeric stat card, on the design system's Stat tile (K46): a label above a mono
// figure, an optional change (with an arrow that repeats its direction, never
// colour alone) and a sub line.
//
// A5 / keyboard reach: a stat card carrying a @click IS a control. THE SIGNAL IS
// THE LISTENER, NOT A PROP: a prop can be forgotten at a call site, and forgetting
// at a call site is exactly how the defect was made (four staff dashboard tiles
// with no keyboard way in). If a parent attaches @click, the tile is interactive:
// the label is a native <button> (the system's one link of an interactive tile)
// whose area stretches over the whole tile, so Enter and Space come from the
// platform and the click reaches the parent's handler. The display-only call sites
// stay plain tiles and out of the tab order.
//
// The system's tile has no icon; the `icon` slot is kept for the call sites that
// use it and draws above the label.
import { computed, useAttrs } from 'vue'
import { ArrowDownLeft, ArrowUpRight } from '@/components/ui/icons'

defineProps<{
  value: string
  label: string
  sub?: string
  change?: string
  changeDir?: 'up' | 'down'
}>()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })
const rootAttrs = computed(() => {
  const { onClick: _onClick, ...rest } = attrs
  return rest
})
function press(e: MouseEvent): void {
  const handler = attrs.onClick as ((e: MouseEvent) => void) | Array<(e: MouseEvent) => void> | undefined
  if (Array.isArray(handler)) handler.forEach((h) => h(e))
  else handler?.(e)
}
const interactive = computed(() => attrs.onClick !== undefined)
</script>

<template>
  <div class="ds-stat" :class="{ 'ds-stat--interactive': interactive }" v-bind="rootAttrs">
    <slot name="icon" />
    <p class="ds-stat__label">
      <button v-if="interactive" type="button" class="ds-stat__link" @click="press">{{ label }}</button>
      <template v-else>{{ label }}</template>
    </p>
    <p class="ds-stat__value">{{ value }}</p>
    <p v-if="change" class="ds-stat__change" :data-trend="changeDir ?? 'up'">
      <ArrowDownLeft v-if="changeDir === 'down'" size="sm" />
      <ArrowUpRight v-else size="sm" />
      <span>{{ change }}</span>
    </p>
    <p v-if="sub" class="ds-stat__sub">{{ sub }}</p>
  </div>
</template>
