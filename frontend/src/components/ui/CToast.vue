<script setup lang="ts">
// Global toast notification. Place once in App.vue or shell.
// Driven by useToast() composable.

import { useToast } from '@/composables/useToast'

const { toastState } = useToast()
</script>

<template>
  <Teleport to="body">
    <div
      class="c-toast"
      :class="[toastState.visible && 'c-toast--show', 'c-toast--' + toastState.variant]"
    >
      {{ toastState.message }}
    </div>
  </Teleport>
</template>

<style scoped>
.c-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  /* info/success/danger backgrounds all INVERT between themes; warning
     overrides this below because amber needs dark text in both. */
  color: var(--on-primary);
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--fs-sm);
  font-weight: 500;
  font-family: var(--font-body);
  opacity: 0;
  transition: all 0.3s ease;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  max-width: 90vw;
  text-align: center;
  pointer-events: none;
}

.c-toast--show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

.c-toast--info {
  background: var(--primary);
  color: var(--on-primary);
}
.c-toast--success {
  background: var(--success);
  color: var(--on-success);
}
.c-toast--error {
  background: var(--danger);
  color: var(--on-danger);
}
.c-toast--warning {
  background: var(--warning);
  color: var(--text-primary);
}
</style>
