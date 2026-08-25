<script setup lang="ts">
import { useI18n } from 'vue-i18n'
// App header — sticky top bar from mockups/css/components.css .app-header.
// Shows logo + title on the left, optional back button, right slot.
//
// F4.1.4 polish: left section now truncates long titles with
// ellipsis instead of bleeding into the right slot. Defensive CSS --
// any title passed from any view stays inside the header strip.
//
// LANGUAGE + THEME (2026-08-18). The controls live HERE, not in each shell,
// because this component is the single header for all five shells -- every
// view that once rendered its own <CHeader> has since removed it (the comments
// in those files record the doubled top bar that caused). One placement,
// four cabinets plus the storefront.
//
// The owner found this himself: both mechanisms worked and neither had any UI
// once signed in. The earlier fix put them on `views/auth/` only and reported
// "every signed-out screen" -- the authenticated app, where a user spends all
// of their time, had never been inside the denominator of that check.

import { useRouter } from 'vue-router'
import { ChevronLeft } from 'lucide-vue-next'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { safeNavigate } from '@/composables/safeNavigate'

withDefaults(
  defineProps<{
    title?: string
    showBack?: boolean
    showLogo?: boolean
  }>(),
  { showBack: false, showLogo: true },
)

const router = useRouter()

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    void safeNavigate(router.push('/'), '[CHeader] to home')
  }
}

// A1: the back control is an icon with no text, so its accessible name has to
// come from an aria-label. This component had no i18n binding at all.
const { t } = useI18n()
</script>

<template>
  <header class="c-header">
    <div class="c-header__left">
      <button v-if="showBack" :aria-label="t('common.back')" class="c-header__back" @click="goBack">
        <ChevronLeft :size="24" />
      </button>
      <AivisLogo v-if="showLogo && !showBack" :height="28" :show-text="false" />
      <span v-if="title" class="c-header__title">{{ title }}</span>
    </div>
    <div class="c-header__right">
      <CAppControls />
      <slot name="right" />
    </div>
  </header>
</template>

<style scoped>
.c-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg-page);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.c-header__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  /* Claim the remaining width and allow the title child to shrink
     below its intrinsic content size (needed for ellipsis). */
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.c-header__title {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--primary-active);
  /* Truncate long titles with ellipsis rather than push the right
     slot off the edge. */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.c-header__back {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-primary);
  padding: var(--space-1);
  display: flex;
  align-items: center;
  margin-left: -4px;
  flex-shrink: 0;
}
.c-header__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  /* Right slot must never shrink -- if someone adds action buttons
     they should stay full size; the title absorbs the space loss. */
  flex-shrink: 0;
}
</style>
