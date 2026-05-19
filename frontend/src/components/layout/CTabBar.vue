<script setup lang="ts">
// Bottom tab bar from mockups/css/components.css .tab-bar.
// Renders TabItem[] with Lucide icons, highlights active route.
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

// Map icon string names to Lucide components.
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
    void safeNavigate(router.push(tab.path), `[CTabBar] to ${tab.path}`)
  }
}
</script>

<template>
  <nav class="c-tabbar">
    <button
      v-for="tab in items"
      :key="tab.id"
      class="c-tabbar__item"
      :class="{ 'c-tabbar__item--active': isActive(tab) }"
      @click="navigate(tab)"
    >
      <span class="c-tabbar__icon">
        <component :is="iconMap[tab.icon]" :size="20" />
      </span>
      <span class="c-tabbar__label">{{ t(tab.labelKey) }}</span>
    </button>
  </nav>
</template>

<style scoped>
.c-tabbar {
  position: sticky; bottom: 0; left: 0; right: 0;
  display: flex; justify-content: space-around;
  background: var(--bg); border-top: 1px solid var(--border);
  /* iter 2.5 cta-fix: height is the source-of-truth via
     --tab-bar-height; sub-route floating CTAs reference the same
     token to stay pinned above the bar. The token measures the
     interactive strip; bottom safe-area inset is added on top so
     touch targets keep their full size on notched devices. */
  height: calc(var(--tab-bar-height) + env(safe-area-inset-bottom, 0px));
  padding: 8px 0 calc(8px + env(safe-area-inset-bottom, 0px));
  z-index: 100;
}
.c-tabbar__item {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 6px 12px; min-width: 56px; min-height: 44px;
  color: var(--text-tertiary); font-size: 10px; font-weight: 500;
  cursor: pointer; transition: color 0.2s;
  border: none; background: none; font-family: inherit;
  position: relative;
}
.c-tabbar__item:hover { color: var(--primary-light); }
.c-tabbar__item--active { color: var(--primary); }
.c-tabbar__item--active::after {
  content: ''; position: absolute;
  bottom: calc(8px + env(safe-area-inset-bottom, 0px));
  left: 50%; transform: translateX(-50%);
  width: 4px; height: 4px; border-radius: 50%; background: var(--accent);
}
.c-tabbar__icon { display: flex; align-items: center; justify-content: center; }
.c-tabbar__label { line-height: 1; }
[dir="rtl"] .c-tabbar { direction: rtl; }
</style>
