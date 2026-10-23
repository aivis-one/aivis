<script setup lang="ts">
// Progress bar, on the design system's Progress (K18). The accessible name is
// the caller's (an aria-label on the component lands on the progressbar).

import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{ value: number; max?: number; color?: string }>(), {
  max: 100,
  color: 'var(--primary)',
})

const pct = computed(() => Math.min(100, Math.max(0, (props.value / props.max) * 100)))
</script>

<template>
  <div class="ds-progress">
    <div
      class="ds-progress__track"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="Math.round(pct)"
      :style="{ '--_fill': color }"
      v-bind="$attrs"
    >
      <span class="ds-progress__fill" :style="{ '--value': pct + '%' }" />
    </div>
  </div>
</template>
