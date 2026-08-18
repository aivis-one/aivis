<script setup lang="ts">
// Universal button with variant styling from mockups/css/components.css.

withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'telegram' | 'link'
    size?: 'default' | 'sm'
    disabled?: boolean
    loading?: boolean
  }>(),
  { variant: 'primary', size: 'default', disabled: false, loading: false },
)
</script>

<template>
  <button
    class="c-btn"
    :class="['c-btn--' + variant, size === 'sm' && 'c-btn--sm']"
    :disabled="disabled || loading"
  >
    <span v-if="loading" class="c-btn__spinner" />
    <slot v-else />
  </button>
</template>

<style scoped>
.c-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 28px;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 15px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
  font-family: inherit;
  width: 100%;
}

.c-btn:disabled {
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

/* Primary (accent orange) */
.c-btn--primary { background: var(--accent); color: var(--on-accent); }
.c-btn--primary:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
.c-btn--primary:active:not(:disabled) { transform: scale(0.98); }
.c-btn--primary:disabled { background: var(--border-default); color: var(--text-tertiary); }

/* Secondary (outlined teal) */
.c-btn--secondary { background: var(--bg-page); color: var(--primary); border: 2px solid var(--primary); }
.c-btn--secondary:hover:not(:disabled) { background: var(--primary); color: var(--on-primary); transform: translateY(-2px); }
.c-btn--secondary:active:not(:disabled) { transform: scale(0.98); }

/* Outline (neutral) */
.c-btn--outline { background: transparent; color: var(--text-secondary); border: 2px solid var(--border-default); }
.c-btn--outline:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }

/* Danger */
.c-btn--danger { background: var(--danger); color: var(--on-danger); }
.c-btn--danger:hover:not(:disabled) { opacity: 0.9; transform: translateY(-2px); }

/* Telegram */
.c-btn--telegram { background: var(--telegram); color: white; }
.c-btn--telegram:hover:not(:disabled) {
  background: var(--telegram-dark);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(42, 171, 238, 0.3);
}

/* Link */
.c-btn--link {
  background: none;
  color: var(--primary);
  font-size: 14px;
  font-weight: 500;
  padding: 8px;
  width: auto;
}
.c-btn--link:hover:not(:disabled) { text-decoration: underline; }

/* Size: small */
.c-btn--sm { padding: 10px 16px; font-size: 13px; }

/* Spinner */
.c-btn__spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: c-spin 0.8s linear infinite;
}

@keyframes c-spin {
  to { transform: rotate(360deg); }
}
</style>
