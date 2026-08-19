<script setup lang="ts">
// Universal button with variant styling from mockups/css/components.css.

withDefaults(
  defineProps<{
    variant?: 'primary' | 'accent' | 'secondary' | 'outline' | 'danger' | 'telegram' | 'link'
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
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5-lg);
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: var(--fs-sm);
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

/* Primary === --primary (azure), per the design system.
   This read `background: var(--accent)` -- named primary, painted with the
   ACCENT -- so every primary CTA in the product, Sign In included, came out
   amber. The design system defines .btn-primary as --primary/--on-primary and
   .btn-accent as --accent/--on-accent, in three of its own files. The accent
   variant below is the one that keeps amber, for a deliberate second action. */
.c-btn--primary { background: var(--primary); color: var(--on-primary); }
.c-btn--primary:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
.c-btn--primary:active:not(:disabled) { background: var(--primary-active); transform: scale(0.98); }
.c-btn--primary:disabled { background: var(--border-default); color: var(--text-tertiary); }

/* Accent (amber) -- the design system's .btn-accent */
.c-btn--accent { background: var(--accent); color: var(--on-accent); }
.c-btn--accent:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
.c-btn--accent:active:not(:disabled) { transform: scale(0.98); }
.c-btn--accent:disabled { background: var(--border-default); color: var(--text-tertiary); }

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
.c-btn--telegram { background: var(--telegram); color: var(--on-telegram); }
.c-btn--telegram:hover:not(:disabled) {
  background: var(--telegram-dark);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(42, 171, 238, 0.3);
}

/* Link */
.c-btn--link {
  background: none;
  color: var(--primary);
  font-size: var(--fs-sm);
  font-weight: 500;
  padding: var(--space-2);
  width: auto;
}
.c-btn--link:hover:not(:disabled) { text-decoration: underline; }

/* Size: small */
.c-btn--sm { padding: var(--space-3) var(--space-4); font-size: var(--fs-xs-lg); }

/* Spinner */
.c-btn__spinner {
  width: var(--size-2xs);
  height: var(--size-2xs);
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  border: 2px solid currentColor;
  opacity: 0.35;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: c-spin 0.8s linear infinite;
}

@keyframes c-spin {
  to { transform: rotate(360deg); }
}
</style>
