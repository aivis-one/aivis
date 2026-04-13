<script setup lang="ts">
withDefaults(
  defineProps<{
    padding?: 'none' | 'sm' | 'md' | 'lg'
  }>(),
  {
    padding: 'md',
  },
)
</script>

<template>
  <div :class="['c-card', `c-card--${padding}`]">
    <slot />
  </div>
</template>

<style scoped>
.c-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.c-card--none {
  padding: 0;
}
.c-card--sm {
  padding: var(--space-sm);
}
.c-card--md {
  padding: var(--space-md);
}
.c-card--lg {
  padding: var(--space-lg);
}
</style>
