<script setup lang="ts">
// The frame's header (K25): the leading slot, one h1, the actions. The slot holds
// the back control; in the nav-less frame (the storefront, which has no menu) it
// holds the AIVIS mark as a link to the home page, the same mark and the same
// target the menu's mark has.
//
// WHAT A SCREEN SETS comes from `useScreenHeader` (./screenHeader): the title,
// the back target and the screen's own icon buttons. The lead line is drawn by
// the shell, in main. A screen that sets no title is named by the tab it lies in,
// else by the product name, so the h1 is never empty.
//
// THE FRAME'S OWN ACTIONS, in this order: the figure chips (the buyer account,
// the integrator's commission and buyer account, the project's balance), the bell
// with its unread count, the screen's own icon buttons, the language and theme
// controls, and the right slot (the storefront's Register and Sign in).
//
// The bell and the polling of unread notifications run only while signed in; the
// balance is loaded when a figure is shown. Both were the old header's duties and
// stay with the header.

import { computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell } from '@/components/ui/icons'
import CAppControls from '@/components/ui/CAppControls.vue'
import CBackLink from '@/components/ui/CBackLink.vue'
import { safeNavigate } from '@/composables/safeNavigate'
import { getRoleDashboard } from '@/router/guards'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useNotificationsStore } from '@/stores/notifications'
import { tabsFor } from '@/router/tabs'
import { formatPrice } from '@/utils/format'
import { useCurrentScreenHeader } from './screenHeader'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()
const companyDashboardStore = useCompanyDashboardStore()
const notifications = useNotificationsStore()

const header = useCurrentScreenHeader()

// ---------------------------------------------------------------------------
// The title
// ---------------------------------------------------------------------------
const tabTitle = computed(() => {
  const tab = tabsFor(route.meta.shell)?.find((item) => route.path.startsWith(item.path))
  return tab ? t(tab.labelKey) : undefined
})
const title = computed(() => header.value.title ?? tabTitle.value ?? t('app.name'))

// ---------------------------------------------------------------------------
// The mark of the nav-less frame
// ---------------------------------------------------------------------------
// A route with no tab list (the storefront) has no menu to carry the mark, so the
// leading slot does; where a screen sets a back control the control has the slot.
const navless = computed(() => !tabsFor(route.meta.shell))
const markSrc = `${import.meta.env.BASE_URL}aivis-mark.svg`
// A visitor with no role has the storefront's list of projects as the start.
const homeRoute = computed(() =>
  authStore.role ? getRoleDashboard(authStore.role) : '/public/companies',
)
const homeLabel = computed(() => `${t('app.name')}, ${t('tab.home')}`)

// ---------------------------------------------------------------------------
// The back control
// ---------------------------------------------------------------------------
const backTarget = computed(() => {
  const back = header.value.back
  return back === true || typeof back === 'function' ? undefined : back
})

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    void safeNavigate(router.push('/'), '[AppHeader] to home')
  }
}

// A route target is a link and goes by itself; `true` is one step back; a function is
// the screen's own handler and the control a button calling it.
const onBack = computed(() => {
  const back = header.value.back
  if (back === true) return goBack
  return typeof back === 'function' ? back : undefined
})

// ---------------------------------------------------------------------------
// The figures
// ---------------------------------------------------------------------------
// The buyer's header shows one figure: the buyer account, the top-up balance
// spent only on AIVIS parts (`activeBalance.confirmed`, the one BalanceView
// reads). The integrator's shows two labelled figures, never combined: the
// commission (`passiveBalance.confirmed`) first, then the buyer account. The
// project's shows one: its balance. A press opens the Balance screen.
const isCompanyShell = computed(() => route.meta.shell === 'company')
const isAgentShell = computed(() => route.meta.shell === 'agent')

const showBalance = computed(
  () =>
    authStore.isAuthenticated &&
    (route.meta.shell === 'investor' ||
      route.meta.shell === 'agent' ||
      route.meta.shell === 'company'),
)

const balanceDisplay = computed(() =>
  isCompanyShell.value
    ? formatPrice(companyDashboardStore.summary?.passive_balance?.confirmed ?? 0, 'USD')
    : formatPrice(dashboardStore.summary?.active_balance?.confirmed ?? 0, 'USD'),
)
const commissionDisplay = computed(() =>
  formatPrice(dashboardStore.summary?.passive_balance?.confirmed ?? 0, 'USD'),
)
const balanceLabel = computed(() =>
  isCompanyShell.value ? t('comp.header.balance') : t('inv.header.balance'),
)
const balanceRoute = computed(() => ({
  name: isCompanyShell.value
    ? 'company-balance'
    : isAgentShell.value
      ? 'agent-balance'
      : 'investor-balance',
}))

function loadBalanceIfNeeded(): void {
  if (!showBalance.value) return
  if (isCompanyShell.value) {
    if (!companyDashboardStore.summary && !companyDashboardStore.loading) {
      void companyDashboardStore.refresh()
    }
    return
  }
  if (!dashboardStore.summary && !dashboardStore.loading) {
    void dashboardStore.refresh()
  }
}

// ---------------------------------------------------------------------------
// The bell
// ---------------------------------------------------------------------------
// Shown only to a signed-in user; the route is role-specific
// (investor-notifications, agent-notifications, ...), read off the same
// `meta.shell` tag the shell's route record carries.
const showBell = computed(() => authStore.isAuthenticated)
const notificationsRoute = computed(() =>
  route.meta.shell ? { name: `${route.meta.shell}-notifications` } : undefined,
)
const unreadDisplay = computed(() => {
  const n = notifications.unreadCount
  if (n <= 0) return null
  return n > 99 ? '99+' : String(n)
})
const bellLabel = computed(() =>
  unreadDisplay.value
    ? `${t('common.notifications')}, ${unreadDisplay.value}`
    : t('common.notifications'),
)

// Poll while, and only while, signed in.
onMounted(() => {
  if (showBell.value) notifications.startPolling()
  loadBalanceIfNeeded()
})
onUnmounted(() => {
  notifications.stopPolling()
})
watch(showBalance, loadBalanceIfNeeded)
watch(showBell, (isAuth) => {
  if (isAuth) {
    notifications.startPolling()
  } else {
    notifications.stopPolling()
  }
})
</script>

<template>
  <header class="ds-header">
    <div v-if="header.back || navless" class="ds-header__lead">
      <CBackLink
        v-if="header.back"
        icon-only
        :label="t('common.back')"
        :to="backTarget"
        @click="onBack"
      />
      <RouterLink v-else class="ds-header__logo" :to="homeRoute" :aria-label="homeLabel">
        <img class="ds-header__mark" :src="markSrc" alt="" />
      </RouterLink>
    </div>
    <h1 class="ds-header__title">{{ title }}</h1>
    <div class="ds-header__actions">
      <template v-if="showBalance && isAgentShell">
        <RouterLink class="ds-header__figure" :to="balanceRoute">
          <span class="ds-header__figure-label">{{ t('agent.header.commission') }}</span>
          <span class="ds-header__figure-amount">{{ commissionDisplay }}</span>
        </RouterLink>
        <RouterLink class="ds-header__figure" :to="balanceRoute">
          <span class="ds-header__figure-label">{{ t('inv.header.balance') }}</span>
          <span class="ds-header__figure-amount">{{ balanceDisplay }}</span>
        </RouterLink>
      </template>
      <RouterLink v-else-if="showBalance" class="ds-header__figure" :to="balanceRoute">
        <span class="ds-header__figure-label">{{ balanceLabel }}</span>
        <span class="ds-header__figure-amount">{{ balanceDisplay }}</span>
      </RouterLink>
      <RouterLink
        v-if="showBell && notificationsRoute"
        class="ds-button ds-button--ghost ds-button--icon"
        :to="notificationsRoute"
        :aria-label="bellLabel"
      >
        <Bell size="sm" />
        <span v-if="unreadDisplay" class="ds-badge ds-badge--count" aria-hidden="true">{{
          unreadDisplay
        }}</span>
      </RouterLink>
      <template v-for="action in header.actions" :key="action.id">
        <RouterLink
          v-if="action.to"
          class="ds-button ds-button--ghost ds-button--icon"
          :to="action.to"
          :aria-label="action.label"
        >
          <component :is="action.icon" size="sm" />
        </RouterLink>
        <button
          v-else
          type="button"
          class="ds-button ds-button--ghost ds-button--icon"
          :aria-label="action.label"
          @click="action.onClick?.()"
        >
          <component :is="action.icon" size="sm" />
        </button>
      </template>
      <CAppControls />
      <slot name="right" />
    </div>
  </header>
</template>
