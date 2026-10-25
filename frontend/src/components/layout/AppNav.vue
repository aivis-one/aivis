<script setup lang="ts">
// The frame's one menu (K25): `nav.ds-nav` holding the role's items as links. The
// system draws it as the tab bar below 880, the icon rail from 880 and the rail
// with labels from 1120; nothing here switches between them. From 880 the mark of
// AIVIS stands at the head of the list (the system hides it on the phone), level with
// the header's line and not a link, and in the labelled rail the wordmark stands beside it.
//
// THE WEB MENU holds more than the phone's five: `extra` are the role's other sections
// that have a screen (News and events, Documents, Support, FAQ), put
// before the last item (Settings) from 880; the tab bar below 880 lists the five only.
// The foot of the rail holds the collapse control (labelled rail only; folds it to icons
// only, the state belongs to the frame: `collapsed`, set on the shell as data-nav, this
// menu only reports the press) and, last, the log out item.
//
// The items come from router/tabs.ts, the same list for every width. The current
// item is `aria-current="page"`; an item is current under its own path, so a
// screen inside a tab keeps its tab marked.

import type { Component } from 'vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  BarChart3,
  Briefcase,
  CalendarClock,
  FileText,
  HelpCircle,
  Home,
  LayoutGrid,
  MessageCircle,
  LogOut,
  Newspaper,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Store,
  Users,
  Wallet,
} from '@/components/ui/icons'
import { safeNavigate } from '@/composables/safeNavigate'
import type { TabItem } from '@/router/tabs'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ items: TabItem[]; extra?: TabItem[]; collapsed?: boolean }>()
const emit = defineEmits<{ toggle: [] }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

// A tab's `icon` is the name of one of these exports.
const iconMap: Record<string, Component> = {
  BarChart3,
  Briefcase,
  CalendarClock,
  FileText,
  HelpCircle,
  Home,
  LayoutGrid,
  MessageCircle,
  Newspaper,
  Package,
  Settings,
  Store,
  Users,
  Wallet,
}

const markSrc = `${import.meta.env.BASE_URL}aivis-mark.svg`

// The web menu starts where the system's rail starts (880, --bp-lg; the system marks no menu item as web-only yet); below it the nav is
// the tab bar and lists the five tabs only. Without matchMedia (a test) the menu is the web's.
const WEB_MENU = '(min-width: 880px)'
const web = ref<boolean>(
  typeof window === 'undefined' || typeof window.matchMedia !== 'function'
    ? true
    : window.matchMedia(WEB_MENU).matches,
)
let mql: MediaQueryList | null = null
function onChange(e: MediaQueryListEvent): void {
  web.value = e.matches
}
onMounted(() => {
  if (typeof window.matchMedia !== 'function') return
  mql = window.matchMedia(WEB_MENU)
  web.value = mql.matches
  mql.addEventListener('change', onChange)
})
onBeforeUnmount(() => mql?.removeEventListener('change', onChange))

// The extras go before the last item (Settings), so Settings stays at the foot of the list.
const menu = computed<TabItem[]>(() => {
  const extra = web.value ? (props.extra ?? []) : []
  if (extra.length === 0) return props.items
  return [...props.items.slice(0, -1), ...extra, ...props.items.slice(-1)]
})

function isActive(tab: TabItem): boolean {
  return route.path.startsWith(tab.path)
}

// The log out item: the same act as the entry screens' Sign out.
const leaving = ref(false)
async function logOut(): Promise<void> {
  if (leaving.value) return
  leaving.value = true
  try {
    await authStore.logout()
  } finally {
    leaving.value = false
    void safeNavigate(router.push('/login'), '[AppNav] to login')
  }
}
</script>

<template>
  <nav class="ds-nav" :aria-label="t('common.primaryNav')">
    <ul class="ds-nav__list">
      <li class="ds-nav__brand">
        <div class="ds-nav__logo" role="img" aria-label="AIVIS">
          <img class="ds-nav__mark" :src="markSrc" alt="" />
          <svg
            class="ds-nav__wordmark"
            viewBox="237 453 120 25"
            aria-hidden="true"
            focusable="false"
          >
            <g fill="currentColor">
              <rect x="257.17" y="461.49" width="2.86" height="14.96" />
              <circle cx="258.6" cy="457.31" r="1.85" />
              <rect x="280.22" y="461.49" width="2.86" height="14.96" />
              <circle cx="281.66" cy="457.31" r="1.85" />
              <path
                d="M253.6,467.69c0-9.06-10.51-7.22-13.09-4.37l1.12,2.07c2.91-2.1,9-3.08,8.71,2.04h-5.4c-2.56,0-5.09,2.19-5.01,4.91.15,5.03,7.84,6.23,10.67,2.55v1.56h2.99c.06-4.34,0-4.99,0-8.76ZM245.47,474.49c-3.39-.31-3.3-4.54,0-4.54h4.98c0,3.22-2.03,4.8-4.98,4.54Z"
              />
              <path
                d="M355.46,468.39c0-8.27-10.61-9.92-13.64-3.31-4.17,9.09,6.28,15.68,12.72,9.19l-1.48-1.85c-2.8,3.22-8.91,2.06-9.3-2.47h11.71v-1.56ZM343.75,467.73c.63-5.5,8.68-5.63,9.17,0h-9.17Z"
              />
              <path
                d="M313.98,461.27c-10.02.8-9.49,16.24,1.65,15.44,10.08-.73,9.29-16.3-1.65-15.44ZM315.1,474.37c-7.08.34-7.34-10.02-1.13-10.76,7.48-.89,8.07,10.43,1.13,10.76Z"
              />
              <path
                d="M327.76,463.31v-1.82h-2.6v14.96h2.66c0-3.02-.06-4.9-.06-7.57,0-5.56,7.81-6.41,7.81-2.1v9.67h2.73v-9.95c0-5.41-7.31-6.94-10.54-3.19Z"
              />
              <path
                d="M290.6,465.59c-.08-3.07,5.96-2.15,7.54-.98l.72-2.08c-3.11-2.08-10.44-2.42-10.98,2.68-.61,5.76,7.93,4.07,8.86,6.59.31.83,0,1.59-.72,2.07-2.01,1.35-5.75.11-7.63-1.06l-.91,2.19c3.99,2.99,13.25,3.29,12.03-3.64-.75-4.28-8.84-2.79-8.92-5.78Z"
              />
              <polygon
                points="270.16 473.06 265.09 461.49 262.16 461.49 268.58 476.46 271.7 476.46 277.9 461.49 274.99 461.49 270.16 473.06"
              />
              <circle cx="303.76" cy="474.87" r="1.85" />
            </g>
          </svg>
        </div>
      </li>
      <li v-for="tab in menu" :key="tab.id">
        <RouterLink v-slot="{ href, navigate }" :to="tab.path" custom>
          <a
            class="ds-navitem"
            :href="href"
            :aria-current="isActive(tab) ? 'page' : undefined"
            @click="navigate"
          >
            <component :is="iconMap[tab.icon]" />
            <span class="ds-navitem__label">{{ t(tab.labelKey) }}</span>
          </a>
        </RouterLink>
      </li>
    </ul>
    <!-- The foot of the rail: the collapse control (labelled rail only) and the log out item -->
    <div class="ds-nav__foot">
      <button
        type="button"
        class="ds-navitem ds-nav__collapse"
        :aria-expanded="collapsed ? 'false' : 'true'"
        @click="emit('toggle')"
      >
        <PanelLeftClose class="ds-nav__icon--close" />
        <PanelLeftOpen class="ds-nav__icon--open" />
        <span class="ds-navitem__label">{{
          collapsed ? t('common.nav.expand') : t('common.nav.collapse')
        }}</span>
      </button>
      <button type="button" class="ds-navitem ds-nav__logout" :disabled="leaving" @click="logOut">
        <LogOut />
        <span class="ds-navitem__label">{{ t('common.nav.logout') }}</span>
      </button>
    </div>
  </nav>
</template>
