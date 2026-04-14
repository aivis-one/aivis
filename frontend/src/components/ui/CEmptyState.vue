<script setup lang="ts">
// Empty state placeholder with icon slot, title, and description.

defineProps<{ title?: string; description?: string }>()
</script>

<template>
  <div class="c-empty">
    <div class="c-empty__icon"><slot name="icon" /></div>
    <div v-if="title" class="c-empty__title">{{ title }}</div>
    <div v-if="description" class="c-empty__desc">{{ description }}</div>
  </div>
</template>

<style scoped>
.c-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 48px 24px; text-align: center;
}
.c-empty__icon { margin-bottom: 16px; color: var(--text-tertiary); }
.c-empty__title { font-size: 16px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
.c-empty__desc { font-size: 13px; color: var(--text-secondary); line-height: 1.5; max-width: 280px; }
</style>
