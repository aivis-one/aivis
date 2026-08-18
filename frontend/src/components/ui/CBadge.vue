<script setup lang="ts">
// Status badge. Variants from mockups/css/components.css.

defineProps<{
  variant?: 'success' | 'warning' | 'danger' | 'primary' | 'accent' | 'neutral'
  text: string
}>()
</script>

<template>
  <span class="c-badge" :class="'c-badge--' + (variant ?? 'neutral')">{{ text }}</span>
</template>

<style scoped>
.c-badge {
  font-size: var(--fs-xs); font-weight: 600; padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm); display: inline-block; white-space: nowrap;
}
.c-badge--success { background: var(--success-subtle); color: var(--success); }
.c-badge--warning { background: var(--warning-subtle); color: var(--warning); }
.c-badge--danger { background: var(--danger-subtle); color: var(--danger); }
.c-badge--primary { background: var(--primary-subtle); color: var(--primary); }
.c-badge--accent { background: var(--accent-subtle); color: var(--accent); }
.c-badge--neutral { background: var(--bg-subtle); color: var(--text-secondary); }
</style>
