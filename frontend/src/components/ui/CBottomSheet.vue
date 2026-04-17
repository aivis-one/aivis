<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CBottomSheet (Phase F4.1)
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
</script>

<template>
  <Teleport to="body">
    <Transition name="c-sheet">
      <div v-if="open" class="c-sheet-overlay" @click.self="onOverlay">
        <div class="c-sheet-dialog">
          <div class="c-sheet-handle" />
          <div v-if="title || $slots.header" class="c-sheet-header">
            <slot name="header">
              <h3 class="c-sheet-title">{{ title }}</h3>
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
.c-sheet-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: flex-end; justify-content: center;
}

.c-sheet-dialog {
  background: var(--bg);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  width: 100%; max-width: 520px;
  max-height: 85vh; max-height: 85dvh;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-xl);
}

.c-sheet-handle {
  width: 40px; height: 4px;
  background: var(--border); border-radius: 2px;
  margin: 8px auto 4px;
  flex-shrink: 0;
}

.c-sheet-header {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.c-sheet-title {
  font-size: 16px; font-weight: 700;
  color: var(--text); margin: 0;
}

.c-sheet-body {
  padding: 16px 20px 20px;
  overflow-y: auto;
  flex: 1;
}

/* Transition: overlay fades, dialog slides from the bottom. */
.c-sheet-enter-active,
.c-sheet-leave-active { transition: opacity 0.2s; }
.c-sheet-enter-active .c-sheet-dialog,
.c-sheet-leave-active .c-sheet-dialog {
  transition: transform 0.25s ease-out;
}
.c-sheet-enter-from,
.c-sheet-leave-to { opacity: 0; }
.c-sheet-enter-from .c-sheet-dialog,
.c-sheet-leave-to .c-sheet-dialog { transform: translateY(100%); }
</style>
