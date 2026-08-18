<script setup lang="ts">
// Card container with border and hover elevation.

withDefaults(
  defineProps<{ hoverable?: boolean; padding?: string }>(),
  { hoverable: false, padding: '16px' },
)
</script>

<template>
  <div class="c-card" :class="{ 'c-card--hover': hoverable }" :style="{ padding }">
    <slot />
  </div>
</template>

<style scoped>
.c-card {
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  transition: all 0.2s;
}
.c-card--hover:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
</style>
