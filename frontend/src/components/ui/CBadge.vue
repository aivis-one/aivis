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
  font-size: 11px; font-weight: 600; padding: 3px 8px;
  border-radius: var(--radius-sm); display: inline-block; white-space: nowrap;
}
.c-badge--success { background: var(--success-dim); color: var(--success); }
.c-badge--warning { background: var(--warning-dim); color: var(--warning); }
.c-badge--danger { background: var(--danger-dim); color: var(--danger); }
.c-badge--primary { background: var(--t-tint-8); color: var(--primary); }
.c-badge--accent { background: var(--o-tint-8); color: var(--accent); }
.c-badge--neutral { background: var(--bg-subtle); color: var(--text-secondary); }
</style>
