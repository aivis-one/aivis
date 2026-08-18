<script setup lang="ts">
// Colored icon square from mockups/css/components.css .icon-box pattern.
// Wraps a slot (Lucide icon) in a tinted background square.

defineProps<{
  variant?: 'teal' | 'orange' | 'green' | 'yellow' | 'red' | 'blue' | 'neutral'
}>()
</script>

<template>
  <div class="c-icon-box" :class="'c-icon-box--' + (variant ?? 'neutral')">
    <slot />
  </div>
</template>

<style scoped>
.c-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.c-icon-box :deep(svg) {
  width: 22px;
  height: 22px;
}

.c-icon-box--teal { background: var(--primary-subtle); color: var(--primary); }
.c-icon-box--orange { background: var(--o-tint-15); color: var(--accent); }
.c-icon-box--green { background: var(--success-subtle); color: var(--success); }
.c-icon-box--yellow { background: var(--warning-subtle); color: var(--warning); }
.c-icon-box--red { background: var(--danger-subtle); color: var(--danger); }
.c-icon-box--blue { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.c-icon-box--neutral { background: var(--bg-subtle); color: var(--text-secondary); }
</style>
