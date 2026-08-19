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
  padding: var(--space-7) var(--space-5); text-align: center;
}
.c-empty__icon { margin-bottom: var(--space-4); color: var(--text-tertiary); }
.c-empty__title { font-size: var(--fs-body); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-2); }
.c-empty__desc { font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.5; max-width: 280px; }

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.c-empty__desc { max-width: var(--maxw-prose); }
</style>
