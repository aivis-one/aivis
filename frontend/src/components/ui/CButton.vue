<script setup lang="ts">
// Universal button, on the design system's Button (K01).
//
// The cabinet's variant names map to the system's looks: primary, accent,
// danger and telegram stand as they are; secondary and outline are the
// system's `secondary` (bordered, quiet); link is `ghost` (no border, the
// link-style action). Size `default` is the system's md, `sm` its sm.

import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'accent' | 'secondary' | 'outline' | 'danger' | 'telegram' | 'link'
    size?: 'default' | 'sm'
    disabled?: boolean
    loading?: boolean
    // The button is full-width by default because that is what every existing
    // call site expects. `inline` sizes it to its own content, for the screens
    // where a stretched CTA reads as a mistake -- a 404, an empty state.
    inline?: boolean
  }>(),
  { variant: 'primary', size: 'default', disabled: false, loading: false, inline: false },
)

const look = computed(() => {
  if (props.variant === 'outline') return 'secondary'
  if (props.variant === 'link') return 'ghost'
  return props.variant
})
const block = computed(() => !props.inline && props.variant !== 'link')
</script>

<template>
  <button
    class="ds-button"
    :class="['ds-button--' + look, block && 'ds-button--block']"
    :data-size="size === 'sm' ? 'sm' : undefined"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <!-- The label stays in the tree while loading, so the button keeps its
         accessible name and its width; the spinner stands before it. -->
    <span v-if="loading" class="ds-button__spinner" aria-hidden="true" />
    <slot />
  </button>
</template>
