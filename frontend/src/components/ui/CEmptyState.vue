<script setup lang="ts">
// Empty state, on the design system's Empty state (K48): nothing here yet, or a
// load that failed. An icon (drawn at --icon-size-xl by the system whatever size
// the caller passes), a title, a description capped at the reading measure, and an
// actions slot (Retry, Create). `tone="danger"` tints the icon for a failed load
// and gives the block role="alert"; `framed` draws the dashed frame.

defineProps<{
  title?: string
  description?: string
  tone?: 'danger'
  framed?: boolean
}>()
</script>

<template>
  <div
    class="ds-empty"
    :class="{ 'ds-empty--framed': framed }"
    :data-tone="tone"
    :role="tone === 'danger' ? 'alert' : undefined"
  >
    <span v-if="$slots.icon" class="ds-empty__icon"><slot name="icon" /></span>
    <h3 v-if="title" class="ds-empty__title">{{ title }}</h3>
    <p v-if="description" class="ds-empty__text">{{ description }}</p>
    <div v-if="$slots.actions" class="ds-empty__actions"><slot name="actions" /></div>
  </div>
</template>
