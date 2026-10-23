<script setup lang="ts">
// Avatar, on the design system's Avatar (K50): a photo if a url is given, otherwise
// the initials of the name on a disc. The system has three sizes; a number of
// pixels is read as the nearest: up to 32 the small one, up to 40 the default, more
// the large one (56). A photo carries the name as its alt text; initials are an
// image role named by the name, or hidden when there is no name.

import { computed } from 'vue'

const props = withDefaults(defineProps<{ name?: string; url?: string; size?: number }>(), {
  size: 40,
})

const initials = computed(() => {
  if (!props.name) return '?'
  return props.name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
})

const step = computed(() => (props.size <= 32 ? 'sm' : props.size <= 40 ? undefined : 'lg'))
</script>

<template>
  <span v-if="url" class="ds-avatar" :data-size="step"
    ><img :src="url" :alt="name ?? ''"
  /></span>
  <span
    v-else
    class="ds-avatar"
    :data-size="step"
    :role="name ? 'img' : undefined"
    :aria-label="name || undefined"
    :aria-hidden="name ? undefined : 'true'"
    >{{ initials }}</span
  >
</template>
