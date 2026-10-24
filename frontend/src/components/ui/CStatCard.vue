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
// The `icon` slot is the system's icon part (`.ds-stat__icon`, K46): the first
// child, above the label, drawn only when a call site fills the slot. The control
// of an interactive tile is a native <button class="ds-stat__link">, which the
// system draws the same as its anchor form.
//
// `to` makes the tile a link to another screen (K46: the label holds ONE a.ds-stat__link
// that stretches over the tile; a router link, so a real anchor). It is the anchor
// form of the same interactive tile; a tile with `to` takes no @click for the same job.
//
// `pending` is K46's pending figure: aria-busy on the tile, a skeleton bar where the
// figure stands and one status text naming what loads (the label). When the value
// arrives the screen drops `pending`.
import { computed, useAttrs } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { ArrowDownLeft, ArrowUpRight } from '@/components/ui/icons'

const props = defineProps<{
  value?: string
  label: string
  sub?: string
  change?: string
  changeDir?: 'up' | 'down'
  /** The screen the tile goes to; draws the tile as a link (K46). */
  to?: RouteLocationRaw
  /** The figure is still loading: draws K46's pending figure instead of the value. */
  pending?: boolean
}>()

const { t } = useI18n()

const attrs = useAttrs()
defineOptions({ inheritAttrs: false })
const rootAttrs = computed(() => {
  const { onClick: _onClick, ...rest } = attrs
  return rest
})
function press(e: MouseEvent): void {
  const handler = attrs.onClick as
    | ((e: MouseEvent) => void)
    | Array<(e: MouseEvent) => void>
    | undefined
  if (Array.isArray(handler)) handler.forEach((h) => h(e))
  else handler?.(e)
}
const interactive = computed(() => props.to !== undefined || attrs.onClick !== undefined)
</script>

<template>
  <div
    class="ds-stat"
    :class="{ 'ds-stat--interactive': interactive }"
    :aria-busy="pending ? 'true' : undefined"
    v-bind="rootAttrs"
  >
    <span v-if="$slots.icon" class="ds-stat__icon"><slot name="icon" /></span>
    <p class="ds-stat__label">
      <RouterLink v-if="to !== undefined" class="ds-stat__link" :to="to">{{ label }}</RouterLink>
      <button v-else-if="interactive" type="button" class="ds-stat__link" @click="press">
        {{ label }}
      </button>
      <template v-else>{{ label }}</template>
    </p>
    <p class="ds-stat__value">
      <template v-if="pending">
        <span class="ds-skeleton ds-stat__pending" aria-hidden="true" />
        <span class="ds-sr-only" role="status">{{ t('common.stat.loading', { label }) }}</span>
      </template>
      <template v-else>{{ value }}</template>
    </p>
    <p v-if="change && !pending" class="ds-stat__change" :data-trend="changeDir ?? 'up'">
      <ArrowDownLeft v-if="changeDir === 'down'" size="sm" />
      <ArrowUpRight v-else size="sm" />
      <span>{{ change }}</span>
    </p>
    <p v-if="sub" class="ds-stat__sub">{{ sub }}</p>
  </div>
</template>
