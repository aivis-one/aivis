<script setup lang="ts">
// Progress bar with configurable value, max, and color.

import { computed } from 'vue'

const props = withDefaults(defineProps<{ value: number; max?: number; color?: string }>(), {
  max: 100,
  color: 'var(--primary)',
})

const pct = computed(() => Math.min(100, Math.max(0, (props.value / props.max) * 100)))
</script>

<template>
  <div class="c-progress">
    <div class="c-progress__fill" :style="{ width: pct + '%', background: color }" />
  </div>
</template>

<style scoped>
.c-progress {
  width: 100%;
  height: 6px;
  background: var(--border-default);
  border-radius: var(--radius-pill);
  overflow: hidden;
}
.c-progress__fill {
  height: 100%;
  border-radius: var(--radius-pill);
  transition: width 0.3s ease;
}
</style>
