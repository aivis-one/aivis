<script setup lang="ts">
// Icon box, on the design system: the icon of the nav tile (K34, the primary
// tint) and, for the other tones, the lead box of the row list (K23, `.ds-lead`
// with data-tone: success, warning, danger, accent, neutral). The slot is the icon.
//
// VARIANTS ARE NAMED FOR THEIR ROLE, NOT THEIR COLOUR.

defineProps<{
  variant?: 'primary' | 'accent' | 'success' | 'warning' | 'danger' | 'neutral'
}>()
</script>

<template>
  <span v-if="!variant || variant === 'primary'" class="ds-navtile__icon"><slot /></span>
  <span v-else class="ds-lead" :data-tone="variant"><slot /></span>
</template>
