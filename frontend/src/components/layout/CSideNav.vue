<script setup lang="ts">
// Side navigation for the tablet and desktop tiers.
//
// ONE menu with its labels switched off, not a third layout — the owner's
// ruling. Tablet (>=820) renders it as an icon rail; desktop (>=1280) shows
// the same rail with labels. Below 820 it is not rendered at all and CTabBar
// carries navigation instead; the two are mutually exclusive at every width,
// which is why they had to land in one change.
//
// It takes the SAME TabItem[] the tab bar takes, from @/router/tabs, so the
// two can never drift apart: a tab added for the phone appears here for free.
//
// ACCESSIBILITY: the label element is hidden by `display: none` in rail mode,
// which removes it from the accessibility tree too — so the accessible name
// comes from an aria-label carried on the button at EVERY width, not from the
// visible text. Rows are 44px minimum in both tiers (B-4's floor), which is
// also why the rail is 72px rather than the 56px an icon alone would need.

import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Home, Briefcase, Store, Wallet, Menu,
  Link, Coins, Package, BarChart3, Settings,
  Users, CreditCard, LayoutGrid,
} from 'lucide-vue-next'
import type { TabItem } from '@/router/tabs'
import { safeNavigate } from '@/composables/safeNavigate'

defineProps<{ items: TabItem[] }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const iconMap: Record<string, Component> = {
  Home, Briefcase, Store, Wallet, Menu,
  Link, Coins, Package, BarChart3, Settings,
  Users, CreditCard, LayoutGrid,
}

function isActive(tab: TabItem): boolean {
  return route.path.startsWith(tab.path)
}

function navigate(tab: TabItem): void {
  if (route.path !== tab.path) {
    void safeNavigate(router.push(tab.path), `[CSideNav] to ${tab.path}`)
  }
}
</script>

<template>
  <nav class="c-sidenav" :aria-label="t('common.primaryNav')">
    <button
      v-for="tab in items"
      :key="tab.id"
      class="c-sidenav__item"
      :class="{ 'c-sidenav__item--active': isActive(tab) }"
      :aria-label="t(tab.labelKey)"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="navigate(tab)"
    >
      <span class="c-sidenav__icon">
        <component :is="iconMap[tab.icon]" :size="20" />
      </span>
      <span class="c-sidenav__label">{{ t(tab.labelKey) }}</span>
    </button>
  </nav>
</template>

<style scoped>
/* Not rendered below the tablet tier: the phone uses CTabBar. Mobile-first,
   so the menu appears at a min-width rather than the bar disappearing at a
   max-width — the product is written that way throughout. */
.c-sidenav { display: none; }

@media (min-width: 820px) {
  .c-sidenav {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    flex: 0 0 auto;
    width: 72px;
    padding: var(--space-3) var(--space-2);
    border-inline-end: 1px solid var(--border-default);
    background: var(--bg-page);
    overflow-y: auto;
  }

  .c-sidenav__item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--size-2xl);
    padding: var(--space-2);
    border: none;
    border-radius: var(--radius-md);
    background: none;
    color: var(--text-tertiary);
    font-family: inherit;
    font-size: var(--fs-sm);
    font-weight: 500;
    cursor: pointer;
    transition: color 0.2s, background-color 0.2s;
    /* Rail: the icon centres in the row. Desktop re-aligns to the start. */
    justify-content: center;
  }

  .c-sidenav__item:hover { color: var(--primary-hover); background: var(--bg-subtle); }
  .c-sidenav__item:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
  .c-sidenav__item--active { color: var(--primary); background: var(--primary-subtle); }

  .c-sidenav__icon { display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }

  /* Hidden in the rail; the accessible name is on the button's aria-label. */
  .c-sidenav__label { display: none; }
}

@media (min-width: 1280px) {
  .c-sidenav { width: 232px; padding: var(--space-3); }
  .c-sidenav__item { justify-content: flex-start; padding-inline: var(--space-3); }
  .c-sidenav__label { display: block; line-height: 1.2; text-align: start; }
}

@media (prefers-reduced-motion: reduce) {
  .c-sidenav__item { transition: none; }
}
</style>
