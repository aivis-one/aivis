<script setup lang="ts">
// Empty state placeholder with icon slot, title, and description.

defineProps<{ title?: string; description?: string }>()
</script>

<template>
  <div class="c-empty">
    <div class="c-empty__icon">
      <slot name="icon" />
    </div>
    <div v-if="title" class="c-empty__title">
      {{ title }}
    </div>
    <div v-if="description" class="c-empty__desc">
      {{ description }}
    </div>
  </div>
</template>

<style scoped>
.c-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-block: var(--space-7);
  padding-inline: var(--space-5);
  text-align: center;
}
.c-empty__icon {
  margin-block-end: var(--space-4);
  color: var(--text-secondary);
}
.c-empty__title {
  font-size: var(--fs-body);
  font-weight: 600;
  color: var(--text-primary);
  margin-block-end: var(--space-2);
}
/* Descriptive text only: capped at the reading measure. */
.c-empty__desc {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: var(--lh-normal);
  max-inline-size: var(--maxw-prose);
}
</style>
