<script setup lang="ts">
import { useI18n } from 'vue-i18n'
// App header — sticky top bar.
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

import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChevronLeft, Wallet } from '@/components/ui/icons'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useNotificationsStore } from '@/stores/notifications'
import { formatPrice } from '@/utils/format'

withDefaults(
  defineProps<{
    title?: string
    showBack?: boolean
    showLogo?: boolean
  }>(),
  { showBack: false, showLogo: true },
)

const router = useRouter()
const route = useRoute()

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

// ---------------------------------------------------------------------------
// The bell (Phase 6)
// ---------------------------------------------------------------------------
//
// GATING ON useAuthStore().isAuthenticated, THE SAME MECHANISM OTHER
// CONDITIONALLY-SHOWN UI IN THIS APP USES (e.g. PublicProductsSection,
// StaffMoreView). This component is the single header for all five
// shells including PublicShell (see file header) -- PublicShell wraps
// anonymous storefront visitors in the SAME <CHeader>, so the bell
// must not simply "always render" the way CAppControls does.
// LoginView / RegisterView / the password-reset screens never reach
// this component at all (each renders its own inline <header>, no
// <CHeader> import -- confirmed by grep), so no separate route-based
// exclusion is needed for them; the auth-store gate alone covers
// every surface that DOES render CHeader.
const authStore = useAuthStore()
const notifications = useNotificationsStore()

const showBell = computed(() => authStore.isAuthenticated)

// Route to a role-specific name (investor-notifications,
// agent-notifications, ...), read off route.meta.shell -- the same
// tag each shell's route record already carries for its
// role/permission check, reused here instead of hardcoding a
// role -> route-name map that could drift from it.
function goToNotifications(): void {
  const shell = route.meta.shell as string | undefined
  if (!shell) return
  void safeNavigate(router.push({ name: `${shell}-notifications` }), '[CHeader] to notifications')
}

// ---------------------------------------------------------------------------
// The buyer account (investor and integrator shells)
// ---------------------------------------------------------------------------
//
// The buyer's top bar shows one figure: the buyer account -- the top-up
// balance, spent only on AIVIS parts and returned only through support
// (`activeBalance.confirmed`, the one BalanceView reads). The integrator's top
// bar shows two labelled figures, never combined: the commission (the
// withdrawal account, `passiveBalance.confirmed`) first, then the buyer
// account. A press on either opens the Balance screen.
const dashboardStore = useDashboardStore()

// The project account's top bar shows one figure: the project's balance (its
// earnings in the Cabinet), withdrawn on request.
const companyDashboardStore = useCompanyDashboardStore()

const isCompanyShell = computed(() => route.meta.shell === 'company')

const showBalance = computed(
  () =>
    authStore.isAuthenticated &&
    (route.meta.shell === 'investor' ||
      route.meta.shell === 'agent' ||
      route.meta.shell === 'company'),
)

const isAgentShell = computed(() => route.meta.shell === 'agent')

const balanceDisplay = computed(() =>
  isCompanyShell.value
    ? formatPrice(companyDashboardStore.summary?.passive_balance?.confirmed ?? 0, 'USD')
    : formatPrice(dashboardStore.summary?.active_balance?.confirmed ?? 0, 'USD'),
)

const commissionDisplay = computed(() =>
  formatPrice(dashboardStore.summary?.passive_balance?.confirmed ?? 0, 'USD'),
)

function goToBalance(): void {
  void safeNavigate(
    router.push({
      name: isCompanyShell.value
        ? 'company-balance'
        : route.meta.shell === 'agent'
          ? 'agent-balance'
          : 'investor-balance',
    }),
    '[CHeader] to balance',
  )
}

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

const unreadDisplay = computed(() => {
  const n = notifications.unreadCount
  if (n <= 0) return null
  return n > 99 ? '99+' : String(n)
})

// Poll while, and only while, signed in. CHeader remounts on every
// shell transition (InvestorShell <-> StaffShell etc. are different
// route records with different component instances), which already
// starts/stops the timer on login/logout/avatar-mode in the common
// case; the isAuthenticated watch is the defensive fallback for a
// transition that keeps this component instance alive.
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
  <header class="c-header ds-header">
    <div class="c-header__left">
      <button
        v-if="showBack"
        type="button"
        :aria-label="t('common.back')"
        class="ds-button ds-button--ghost ds-button--icon"
        @click="goBack"
      >
        <ChevronLeft />
      </button>
      <AivisLogo v-if="showLogo && !showBack" :height="28" :show-text="false" />
      <span v-if="title" class="c-header__title ds-header__title">{{ title }}</span>
    </div>
    <div class="c-header__right">
      <template v-if="showBalance && isAgentShell">
        <button
          type="button"
          class="c-header__balance c-header__balance--labelled"
          :aria-label="t('agent.header.commission')"
          @click="goToBalance"
        >
          <span class="c-header__balance-label">{{ t('agent.header.commission') }}</span>
          <span class="c-header__balance-amount">{{ commissionDisplay }}</span>
        </button>
        <button
          type="button"
          class="c-header__balance c-header__balance--labelled"
          :aria-label="t('inv.header.balance')"
          @click="goToBalance"
        >
          <span class="c-header__balance-label">{{ t('inv.header.balance') }}</span>
          <span class="c-header__balance-amount">{{ balanceDisplay }}</span>
        </button>
      </template>
      <button
        v-else-if="showBalance"
        type="button"
        class="c-header__balance"
        :aria-label="t(isCompanyShell ? 'comp.header.balance' : 'inv.header.balance')"
        @click="goToBalance"
      >
        <Wallet size="sm" aria-hidden="true" />
        <span class="c-header__balance-amount">{{ balanceDisplay }}</span>
      </button>
      <button
        v-if="showBell"
        type="button"
        class="c-header__bell ds-button ds-button--ghost ds-button--icon"
        :aria-label="t('common.notifications')"
        @click="goToNotifications"
      >
        <Bell />
        <span v-if="unreadDisplay" class="c-header__bell-badge">{{ unreadDisplay }}</span>
      </button>
      <CAppControls />
      <slot name="right" />
    </div>
  </header>
</template>

<style scoped>
/* The system's header (K25) is the look: sticky, the surface ground, a hairline
   below, --header-height at least. What is the cabinet's own stays here: the
   header sits above the shell's content and the tab bar. */
.c-header {
  z-index: 100;
  justify-content: space-between;
}
.c-header__left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  /* Claim the remaining width and allow the title child to shrink
     below its intrinsic content size (needed for ellipsis). */
  flex: 1;
  min-inline-size: 0;
  overflow: hidden;
}
.c-header__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  /* Right slot must never shrink -- if someone adds action buttons
     they should stay full size; the title absorbs the space loss. */
  flex-shrink: 0;
}

/* The balance chip: the system has no counterpart, so it is the cabinet's own,
   on the system's tokens. */
.c-header__balance {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-block-size: var(--touch-min);
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding-block: 0;
  padding-inline: var(--space-1);
  font-size: var(--fs-sm);
  font-weight: 700;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  transition: color var(--dur-fast) var(--ease-standard);
}
.c-header__balance:hover {
  color: var(--primary);
}
.c-header__balance-amount {
  white-space: nowrap;
}
.c-header__balance--labelled {
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
  line-height: var(--lh-tight);
}
.c-header__balance-label {
  font-family: var(--font-body);
  font-size: var(--fs-3xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.c-header__bell {
  position: relative;
}

.c-header__bell-badge {
  position: absolute;
  inset-block-start: var(--space-1);
  inset-inline-end: var(--space-1);
  min-inline-size: var(--space-4);
  block-size: var(--space-4);
  padding-inline: var(--space-1);
  border-radius: var(--radius-pill);
  background: var(--danger);
  color: var(--on-danger);
  font-size: var(--fs-3xs);
  font-weight: 700;
  line-height: var(--space-4);
  text-align: center;
  pointer-events: none;
}
</style>
