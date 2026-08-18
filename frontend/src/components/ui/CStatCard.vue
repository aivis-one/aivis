<script setup lang="ts">
// Numeric stat card from mockup stats-grid pattern.

defineProps<{
  value: string
  label: string
  sub?: string
  change?: string
  changeDir?: 'up' | 'down'
}>()
</script>

<template>
  <div class="c-stat">
    <div class="c-stat__icon"><slot name="icon" /></div>
    <div class="c-stat__label">{{ label }}</div>
    <div class="c-stat__value">{{ value }}</div>
    <div v-if="change" class="c-stat__change" :class="'c-stat__change--' + (changeDir ?? 'up')">{{ change }}</div>
    <div v-if="sub" class="c-stat__sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.c-stat {
  background: var(--bg-page); box-shadow: var(--shadow-1);
  border-radius: var(--radius-lg); padding: var(--space-4);
  transition: all 0.2s;
}
.c-stat:hover { transform: translateY(-2px); box-shadow: var(--shadow-2); }
.c-stat__icon { margin-bottom: var(--space-2); }
.c-stat__label { font-size: var(--fs-xs); color: var(--text-secondary); margin-bottom: var(--space-1); }
.c-stat__value { font-size: var(--fs-xl); font-weight: 700; color: var(--text-primary); }
.c-stat__change { font-size: var(--fs-xs); font-weight: 600; margin-top: var(--space-1); }
.c-stat__change--up { color: var(--success); }
.c-stat__change--down { color: var(--danger); }
.c-stat__sub { font-size: var(--fs-xs); color: var(--text-tertiary); margin-top: var(--space-1); }
</style>
