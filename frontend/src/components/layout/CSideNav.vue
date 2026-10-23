<script setup lang="ts">
// Side navigation for the tablet and desktop tiers.
//
// ONE menu with its labels switched off, not a third layout. It is the rail and
// wide tiers of the design system's navigation (K25): the icon rail from the
// system's 880 width, the same rail with labels from its 1120 width. Below 880
// it is not rendered at all and CTabBar carries navigation instead; the two are
// mutually exclusive at every width, which is why they had to land in one change.
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
  CalendarClock,
  FileText,
  ShieldCheck,
  MessageCircle,
  HelpCircle,
} from '@/components/ui/icons'
import type { TabItem } from '@/router/tabs'
import { safeNavigate } from '@/composables/safeNavigate'

// `items` are the shell's tabs; `extra` are the lines that, on a phone, lie
// inside one of those tabs and on the web stand as lines of their own.
const props = withDefaults(defineProps<{ items: TabItem[]; extra?: TabItem[] }>(), {
  extra: () => [],
})

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

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
  CalendarClock,
  FileText,
  ShieldCheck,
  MessageCircle,
  HelpCircle,
}

// A line is active under its own path. A tab whose section holds a line of the
// extra list (Partners holds the balance) gives way to that line while the
// route is inside it, so one place is marked, not two.
function isActive(tab: TabItem): boolean {
  if (!route.path.startsWith(tab.path)) return false
  return !props.extra.some(
    (e) => e !== tab && e.path.length > tab.path.length && route.path.startsWith(e.path),
  )
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
      type="button"
      class="c-sidenav__item ds-navitem"
      :aria-label="t(tab.labelKey)"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="navigate(tab)"
    >
      <component :is="iconMap[tab.icon]" />
      <span class="ds-navitem__label">{{ t(tab.labelKey) }}</span>
    </button>
    <template v-if="extra.length > 0">
      <hr class="c-sidenav__rule" />
      <button
        v-for="tab in extra"
        :key="tab.id"
        type="button"
        class="c-sidenav__item ds-navitem"
        :aria-label="t(tab.labelKey)"
        :aria-current="isActive(tab) ? 'page' : undefined"
        @click="navigate(tab)"
      >
        <component :is="iconMap[tab.icon]" />
        <span class="ds-navitem__label">{{ t(tab.labelKey) }}</span>
      </button>
    </template>
  </nav>
</template>

<style scoped>
/* Not rendered below the rail tier: the phone uses CTabBar. Mobile-first, so the
   menu appears at a min-width rather than the bar disappearing at a max-width. */
.c-sidenav {
  display: none;
}

/* K25, the rail tier (from --bp-lg). The system draws the rail inside its
   one-grid shell; the cabinet keeps its two navigation components, so the rail's
   box is written here from the same tokens, rule for rule. */
@media (min-width: 880px) {
  .c-sidenav {
    --_pad: calc(var(--focus-width) + var(--focus-offset));
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    flex: 0 0 auto;
    box-sizing: border-box;
    inline-size: calc(var(--size-4xl) + var(--space-4));
    padding: var(--_pad);
    padding-block: var(--space-3);
    border-inline-end: thin solid var(--border-subtle);
    background: var(--bg-surface);
    overflow-y: auto;
  }

  .c-sidenav__item {
    min-block-size: var(--size-3xl);
    border: none;
    background: none;
    font-family: inherit;
  }
  .c-sidenav__item[aria-current='page'] {
    background: var(--primary-subtle);
  }
  /* The current mark in the rail: a line at the start, in the primary colour. */
  .c-sidenav__item[aria-current='page']::before {
    inset-block: var(--space-2);
    inset-inline: auto;
    inset-inline-start: 0;
    inline-size: calc(var(--border-input-width) * 2);
    block-size: auto;
    margin-inline: 0;
    background: var(--primary);
  }

  /* The line between the shell's tabs and the lines that lie inside them. */
  .c-sidenav__rule {
    inline-size: 100%;
    margin-block: var(--space-2);
    border: none;
    border-block-start: thin solid var(--border-subtle);
  }

  /* Hidden in the rail; the accessible name is on the button's aria-label. */
  .c-sidenav__item .ds-navitem__label {
    position: absolute;
    inline-size: thin;
    block-size: thin;
    margin: calc(var(--border-input-width) * -1);
    padding: 0;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

/* The wide tier (from --bp-xl): the rail with its labels. */
@media (min-width: 1120px) {
  .c-sidenav {
    inline-size: calc(var(--size-4xl) * 4 + var(--space-2));
  }
  .c-sidenav__item {
    flex-direction: row;
    justify-content: flex-start;
    gap: var(--space-3);
    padding-inline: var(--space-3);
    font-size: var(--fs-sm);
    text-align: start;
  }
  .c-sidenav__item .ds-navitem__label {
    position: static;
    inline-size: auto;
    block-size: auto;
    margin: 0;
    overflow: visible;
    clip-path: none;
    white-space: normal;
  }
}

@media (prefers-reduced-motion: reduce) {
  .c-sidenav__item {
    transition: none;
  }
}
</style>
