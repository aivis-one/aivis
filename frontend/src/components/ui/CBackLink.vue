<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CBackLink (iter 2.7 batch B3)
// =============================================================================
//
// Inline back-link button. The single source of truth for the back-link
// shape introduced in iter 2.6 batch 4 (PublicAttachmentLandingView /
// PublicProductDetailView) and adopted across the auth-flow in iter 2.7
// batches B1 + B2 as part of the CHeader paradigm migration.
//
// Before this component the back-link CSS lived inline in 7 views
// (.ppd__back / .pd__back / .co__back / .cp__back / .iv__back /
// .dv__back / .pbc__back) -- the same ~25 lines of CSS copy-pasted
// seven times, plus a `<button>` + `<ArrowLeft>` markup in each
// template. R32 STYLE-32-02 flagged it as accumulating style debt;
// this component closes the debt.
//
// API.
//   <CBackLink :label="t('inv.product.backLink')" @click="goBack" />
//
//   - `label`: already-translated string. Caller owns i18n -- the same
//     contract as CButton (caller provides the slot content) and
//     CEmptyState (caller passes the translated title/description).
//   - `@click`: standard Vue event, propagated from the root <button>.
//     The view supplies a history-aware handler (router.back() with
//     a deep-link push fallback, per the paradigm in cheader-paradigm-
//     plan.md).
//
// POSITIONING.
//   The component carries no margin -- only the visual shape of the
//   button itself (padding, icon, label, hover, focus). Views own
//   positioning: pattern A (back-link above hero) wraps in a
//   `.<prefix>__back-row` with margin; pattern B (page-header block)
//   nests inside `.<prefix>__page-header` whose padding handles
//   spacing. Decoupling spacing from the button keeps the component
//   composable -- a future "back-link inside a card" use-case can
//   set its own surrounding gap without fighting hard-coded margins.
//
// FOCUS RING.
//   `:focus-visible` outline is provided here once, fixing R32
//   A11Y-32-01 across all consumers at the same time. Uses
//   `var(--accent)` to match the rest of the design system's focus
//   treatment. `:focus:not(:focus-visible)` is implicit -- only
//   keyboard / programmatic focus shows the ring; mouse focus is
//   suppressed by the browser default.
// =============================================================================

import { ArrowLeft } from 'lucide-vue-next'

defineProps<{
  label: string
}>()
</script>

<template>
  <button
    type="button"
    class="c-back-link"
  >
    <ArrowLeft :size="16" />
    {{ label }}
  </button>
</template>

<style scoped>
.c-back-link {
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-2);
  background: none;
  border: none;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: var(--fs-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background 0.12s ease, color 0.12s ease;
}

.c-back-link:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

/* R32 A11Y-32-01: keyboard focus ring. `:focus-visible` shows only
   on keyboard / programmatic focus -- mouse clicks suppress it via
   browser default behaviour. */
.c-back-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
