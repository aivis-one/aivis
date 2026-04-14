<script setup lang="ts">
// Horizontal divider with optional centered text (e.g. "or").

defineProps<{ text?: string }>()
</script>

<template>
  <div class="c-divider">
    <span v-if="text" class="c-divider__text">{{ text }}</span>
  </div>
</template>

<style scoped>
.c-divider {
  display: flex; align-items: center; gap: 16px;
  margin: 24px 0; width: 100%;
}
.c-divider::before, .c-divider::after {
  content: ''; flex: 1; height: 1px; background: var(--border);
}
/* Hide pseudo-elements when no text — show single line */
.c-divider:not(:has(.c-divider__text))::after { display: none; }
.c-divider__text { font-size: 13px; color: var(--text-tertiary); white-space: nowrap; }
</style>
