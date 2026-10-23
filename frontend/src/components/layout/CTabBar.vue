<script setup lang="ts">
// Bottom tab bar: the bar tier of the design system's navigation (K25). Renders
// TabItem[] with the system's icons; the current item is aria-current="page".
//
// iter 2.7 Block A1 (R1 §2):
//   STAFF_TABS no longer carries the `kyc` tab (KYC merged into Users).
//   ShieldCheck removed from the icon imports / iconMap because no tab
//   in any role uses it any more. The new `platform` tab uses
//   LayoutGrid -- added to the imports and the map.

import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Home,
  Briefcase,
  Store,
  Wallet,
  Menu,
  Link,
  Coins,
  Package,
  BarChart3,
  Settings,
  Users,
  CreditCard,
  LayoutGrid,
  Newspaper,
} from '@/components/ui/icons'
import type { TabItem } from '@/router/tabs'
import { safeNavigate } from '@/composables/safeNavigate'

defineProps<{ items: TabItem[] }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// Map icon string names to Lucide components.
const iconMap: Record<string, Component> = {
  Home,
  Briefcase,
  Store,
  Wallet,
  Menu,
  Link,
  Coins,
  Package,
  BarChart3,
  Settings,
  Users,
  CreditCard,
  LayoutGrid,
  Newspaper,
}

function isActive(tab: TabItem): boolean {
  return route.path.startsWith(tab.path)
}

function navigate(tab: TabItem): void {
  if (route.path !== tab.path) {
    void safeNavigate(router.push(tab.path), `[CTabBar] to ${tab.path}`)
  }
}
</script>

<template>
  <nav class="c-tabbar" :aria-label="t('common.primaryNav')">
    <button
      v-for="tab in items"
      :key="tab.id"
      type="button"
      class="c-tabbar__item ds-navitem"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="navigate(tab)"
    >
      <component :is="iconMap[tab.icon]" />
      <span class="ds-navitem__label">{{ t(tab.labelKey) }}</span>
    </button>
  </nav>
</template>

<style scoped>
/* K25, the bar tier: sticky under the content, the surface ground, a hairline
   above, the safe-area insets. The items are the system's .ds-navitem. The
   system draws the bar inside its one-grid shell; the cabinet keeps its two
   navigation components, so the bar's box is written here from the same tokens.
   --tab-bar-height (variables.css) is the bar's height, and the floating
   call-to-action strips pin themselves above it. */
.c-tabbar {
  --_pad: calc(var(--focus-width) + var(--focus-offset));
  position: sticky;
  inset-block-end: 0;
  z-index: 100;
  box-sizing: border-box;
  display: flex;
  gap: var(--space-1);
  padding: var(--_pad);
  padding-block-end: calc(var(--_pad) + var(--space-safe-bottom));
  padding-inline: calc(var(--_pad) + var(--space-safe-left)) calc(var(--_pad) + var(--space-safe-right));
  background: var(--bg-surface);
  border-block-start: thin solid var(--border-subtle);
}
.c-tabbar__item {
  flex: 1 1 0;
  min-inline-size: 0;
  border: none;
  background: none;
  font-family: inherit;
}
.c-tabbar__item:hover {
  background: var(--bg-subtle);
}
@media (max-width: 480px) {
  .c-tabbar__item {
    min-block-size: var(--size-3xl);
  }
}
</style>
