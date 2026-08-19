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
  display: flex; align-items: center; gap: var(--space-4);
  margin: var(--space-5) 0; width: 100%;
}
.c-divider::before, .c-divider::after {
  content: ''; flex: 1; height: 1px; background: var(--border-default);
}
/* Hide pseudo-elements when no text — show single line */
.c-divider:not(:has(.c-divider__text))::after { display: none; }
.c-divider__text { font-size: var(--fs-xs-lg); color: var(--text-tertiary); white-space: nowrap; }

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.c-divider__text { max-width: var(--maxw-prose); }
</style>
