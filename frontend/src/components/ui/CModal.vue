<script setup lang="ts">
// Modal overlay. Closes on overlay click (if allowed) or close button.

import { X } from 'lucide-vue-next'

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
</script>

<template>
  <Teleport to="body">
    <Transition name="c-modal">
      <div v-if="open" class="c-modal-overlay" @click.self="onOverlay">
        <div class="c-modal-dialog">
          <button v-if="showClose" class="c-modal-close" @click="emit('close')">
            <X :size="20" />
          </button>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.c-modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5); display: flex;
  align-items: center; justify-content: center; padding: var(--space-5);
}
.c-modal-dialog {
  background: var(--bg-page); border-radius: var(--radius-lg);
  padding: var(--space-5); width: 100%; max-width: 420px;
  max-height: 90vh; overflow-y: auto; position: relative;
  box-shadow: var(--shadow-deep);
}
.c-modal-close {
  position: absolute; top: 12px; right: 12px;
  background: none; border: none; cursor: pointer;
  color: var(--text-tertiary); padding: var(--space-1);
  display: flex; align-items: center;
}
.c-modal-close:hover { color: var(--text-primary); }

/* Transition */
.c-modal-enter-active, .c-modal-leave-active { transition: opacity 0.2s; }
.c-modal-enter-active .c-modal-dialog, .c-modal-leave-active .c-modal-dialog { transition: transform 0.2s; }
.c-modal-enter-from, .c-modal-leave-to { opacity: 0; }
.c-modal-enter-from .c-modal-dialog { transform: scale(0.95); }
.c-modal-leave-to .c-modal-dialog { transform: scale(0.95); }
</style>
