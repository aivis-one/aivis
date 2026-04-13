<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost'
    size?: 'sm' | 'md' | 'lg'
    disabled?: boolean
    loading?: boolean
    type?: 'button' | 'submit'
  }>(),
  {
    variant: 'primary',
    size: 'md',
    type: 'button',
  },
)

defineEmits<{
  click: [event: MouseEvent]
}>()
</script>

<template>
  <button
    :type="type"
    :class="['c-btn', `c-btn--${variant}`, `c-btn--${size}`]"
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="c-btn__spinner" />
    <slot />
  </button>
</template>

<style scoped>
.c-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-xs);
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font);
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.2s,
    opacity 0.2s;
  width: 100%;
}

.c-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.c-btn:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

/* Variants */
.c-btn--primary {
  background: var(--accent);
  color: var(--text-on-accent);
}
.c-btn--primary:hover:not(:disabled) {
  background: var(--accent-dark);
}

.c-btn--secondary {
  background: var(--bg-elevated);
  color: var(--text);
  border: 1px solid var(--border);
}
.c-btn--secondary:hover:not(:disabled) {
  background: var(--bg-subtle);
}

.c-btn--ghost {
  background: transparent;
  color: var(--primary);
}
.c-btn--ghost:hover:not(:disabled) {
  background: var(--t-tint-8);
}

/* Sizes */
.c-btn--sm {
  padding: var(--space-xs) var(--space-sm);
  font-size: var(--text-caption);
}
.c-btn--md {
  padding: var(--space-sm) var(--space-md);
  font-size: var(--text-md);
}
.c-btn--lg {
  padding: var(--space-md) var(--space-lg);
  font-size: var(--text-lg);
}

/* Spinner */
.c-btn__spinner {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
