<script setup lang="ts">
import { useI18n } from 'vue-i18n'
// Modal overlay. Closes on Escape, on overlay click (if allowed), or on the
// close button.

import { ref, toRef } from 'vue'
import { X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'

const props = withDefaults(
  defineProps<{
    open: boolean
    closeOnOverlay?: boolean
    showClose?: boolean
  }>(),
  { closeOnOverlay: true, showClose: true },
)

const emit = defineEmits<{ close: [] }>()

function onOverlay(): void {
  if (props.closeOnOverlay) emit('close')
}

// A1: the close control is an icon with no text; its name must come from an
// aria-label. This component had no i18n binding.
const { t } = useI18n()

// Escape, focus containment and focus restore. The overlay click was the only
// dismissal a keyboard could not perform.
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))
</script>

<template>
  <Teleport to="body">
    <Transition name="c-modal">
      <div v-if="open" class="c-modal-overlay" @click.self="onOverlay">
        <div ref="dialogEl" class="c-modal-dialog" role="dialog" aria-modal="true" tabindex="-1">
          <button
            v-if="showClose"
            :aria-label="t('common.close')"
            class="c-modal-close"
            @click="emit('close')"
          >
            <X :size="20" />
          </button>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* The system has no dialog; this one keeps its form and takes the system's
   scrim, surface, modal radius, shadow and motion tokens. */
.c-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--scrim);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
}
.c-modal-dialog {
  background: var(--bg-surface);
  border-radius: var(--radius-modal);
  padding: var(--space-5);
  inline-size: 100%;
  max-inline-size: var(--maxw-form-wide);
  max-block-size: 90vh;
  overflow-y: auto;
  position: relative;
  box-shadow: var(--shadow-deep);
}
.c-modal-close {
  position: absolute;
  inset-block-start: var(--space-3);
  inset-inline-end: var(--space-3);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  padding: var(--space-1);
  display: flex;
  align-items: center;
}
.c-modal-close:hover {
  color: var(--text-primary);
}

/* Transition */
.c-modal-enter-active,
.c-modal-leave-active {
  transition: opacity var(--dur-base) var(--ease-standard);
}
.c-modal-enter-active .c-modal-dialog,
.c-modal-leave-active .c-modal-dialog {
  transition: transform var(--dur-base) var(--ease-standard);
}
.c-modal-enter-from,
.c-modal-leave-to {
  opacity: 0;
}
.c-modal-enter-from .c-modal-dialog {
  transform: scale(0.95);
}
.c-modal-leave-to .c-modal-dialog {
  transform: scale(0.95);
}
</style>
