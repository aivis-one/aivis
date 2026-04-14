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
  background: var(--bg); box-shadow: var(--shadow-sm);
  border-radius: var(--radius-lg); padding: 16px;
  transition: all 0.2s;
}
.c-stat:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.c-stat__icon { margin-bottom: 8px; }
.c-stat__label { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.c-stat__value { font-size: 22px; font-weight: 700; color: var(--text); }
.c-stat__change { font-size: 12px; font-weight: 600; margin-top: 4px; }
.c-stat__change--up { color: var(--success); }
.c-stat__change--down { color: var(--danger); }
.c-stat__sub { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
</style>
