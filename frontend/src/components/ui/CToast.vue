<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const { toasts, removeToast } = useToast()
</script>

<template>
  <div class="c-toast-container">
    <TransitionGroup name="c-toast">
      <div v-for="toast in toasts" :key="toast.id" :class="['c-toast', `c-toast--${toast.type}`]">
        <span class="c-toast__message">{{ toast.message }}</span>
        <button
          class="c-toast__close"
          :aria-label="t('shared.toast.close')"
          @click="removeToast(toast.id)"
        >
          &times;
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.c-toast-container {
  position: fixed;
  bottom: calc(64px + var(--space-md));
  right: var(--space-md);
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  max-width: 360px;
}

@media (max-width: 480px) {
  .c-toast-container {
    left: var(--space-md);
    right: var(--space-md);
    max-width: none;
  }
}

.c-toast {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  font-size: var(--text-caption);
  color: var(--text-on-accent);
}

.c-toast--success {
  background: var(--success);
}

.c-toast--error {
  background: var(--error);
}

.c-toast--warning {
  background: var(--warning);
  color: var(--text);
}

.c-toast--info {
  background: var(--primary);
}

.c-toast__message {
  flex: 1;
}

.c-toast__close {
  background: none;
  border: none;
  color: inherit;
  font-size: var(--text-xl);
  line-height: 1;
  cursor: pointer;
  padding: 0;
  opacity: 0.8;
}

.c-toast__close:hover {
  opacity: 1;
}

.c-toast-enter-active,
.c-toast-leave-active {
  transition:
    opacity 0.3s,
    transform 0.3s;
}

.c-toast-enter-from,
.c-toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
