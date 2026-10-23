<script setup lang="ts">
// The back control, on the design system's Button (K01): the ghost look with
// the arrow. With a label it is the button with the arrow and the words; with
// `icon-only` it is the ghost icon button the header's leading slot holds (the
// label is then its accessible name). Given a `to` it is a link (a real anchor
// to the parent screen); without one it is a button and the caller's @click
// does the going.

import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { ArrowLeft } from '@/components/ui/icons'

defineProps<{
  label: string
  iconOnly?: boolean
  to?: RouteLocationRaw
}>()
</script>

<template>
  <component
    :is="to ? RouterLink : 'button'"
    v-bind="to ? { to } : { type: 'button' }"
    class="ds-button ds-button--ghost"
    :class="{ 'ds-button--icon': iconOnly }"
    :aria-label="iconOnly ? label : undefined"
  >
    <ArrowLeft size="sm" />
    <span v-if="!iconOnly">{{ label }}</span>
  </component>
</template>
