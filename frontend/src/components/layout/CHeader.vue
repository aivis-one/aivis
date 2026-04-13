<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<template>
  <header class="c-header">
    <div class="c-header__title">
      {{ title }}
    </div>
  </header>
</template>

<style scoped>
.c-header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 56px;
  padding: 0 var(--space-md);
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  padding-top: env(safe-area-inset-top);
}

.c-header__title {
  font-size: var(--text-subtitle);
  font-weight: 700;
  color: var(--text);
}
</style>
