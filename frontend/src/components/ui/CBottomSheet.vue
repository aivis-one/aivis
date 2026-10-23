<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CBottomSheet (Phase F4.1)
// =============================================================================
//
// Slide-up modal anchored to the bottom of the viewport. Used for
// filter pickers, action lists, and other sheets that should feel
// native on mobile.
//
// Structure:
//   - overlay (click to close, if closeOnOverlay)
//   - drag handle (visual only)
//   - header (optional title prop, or `header` slot)
//   - body (default slot, scrollable, capped at 85dvh)
//
// Matches CModal's API shape for familiarity: same `open` prop,
// same `close` event.
// =============================================================================

import { ref, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'

const props = withDefaults(
  defineProps<{
    open: boolean
    closeOnOverlay?: boolean
    title?: string
  }>(),
  { closeOnOverlay: true },
)

const emit = defineEmits<{ close: [] }>()

function onOverlay(): void {
  if (props.closeOnOverlay) emit('close')
}

const { t } = useI18n()

// This component offered NO dismissal a keyboard could reach: no close button,
// no Escape, only a click on the overlay. Five of its six call sites happened
// to put a Cancel button in the body; TransactionDetailSheet is read-only and
// did not, so it could not be closed without a mouse. A sheet should not
// depend on each caller remembering to supply the way out.
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))
</script>

<template>
  <Teleport to="body">
    <Transition name="c-sheet">
      <div v-if="open" class="c-sheet-overlay" @click.self="onOverlay">
        <div ref="dialogEl" class="c-sheet-dialog" role="dialog" aria-modal="true" tabindex="-1">
          <div class="c-sheet-handle" />
          <button
            type="button"
            class="c-sheet-close"
            :aria-label="t('common.close')"
            @click="emit('close')"
          >
            <X :size="20" />
          </button>
          <div v-if="title || $slots.header" class="c-sheet-header">
            <slot name="header">
              <h3 class="c-sheet-title">
                {{ title }}
              </h3>
            </slot>
          </div>
          <div class="c-sheet-body">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* The system has no sheet; this one keeps its form and takes the system's
   scrim, surface, modal radius, shadow and motion tokens. */
.c-sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--scrim);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.c-sheet-close {
  position: absolute;
  inset-block-start: var(--space-2);
  inset-inline-end: var(--space-3);
  min-inline-size: var(--tap-min);
  min-block-size: var(--tap-min);
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
}

.c-sheet-dialog {
  position: relative;
  background: var(--bg-surface);
  border-radius: var(--radius-modal) var(--radius-modal) 0 0;
  inline-size: 100%;
  max-inline-size: var(--maxw-form-wide);
  max-block-size: 85vh;
  max-block-size: 85dvh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-deep);
}

.c-sheet-handle {
  inline-size: var(--size-xl);
  block-size: var(--space-1);
  background: var(--border-default);
  border-radius: var(--radius-pill);
  margin: var(--space-2) auto var(--space-1);
  flex-shrink: 0;
}

.c-sheet-header {
  padding-block: var(--space-3);
  padding-inline: var(--space-4-lg);
  border-block-end: thin solid var(--border-default);
  flex-shrink: 0;
}

.c-sheet-title {
  font-family: var(--font-display);
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.c-sheet-body {
  padding-block: var(--space-4) var(--space-4-lg);
  padding-inline: var(--space-4-lg);
  overflow-y: auto;
  flex: 1;
}

/* Transition: overlay fades, dialog slides from the bottom. */
.c-sheet-enter-active,
.c-sheet-leave-active {
  transition: opacity var(--dur-base) var(--ease-standard);
}
.c-sheet-enter-active .c-sheet-dialog,
.c-sheet-leave-active .c-sheet-dialog {
  transition: transform var(--dur-base) var(--ease-exit);
}
.c-sheet-enter-from,
.c-sheet-leave-to {
  opacity: 0;
}
.c-sheet-enter-from .c-sheet-dialog,
.c-sheet-leave-to .c-sheet-dialog {
  transform: translateY(100%);
}
</style>
