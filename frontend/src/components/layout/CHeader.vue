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

import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChevronLeft } from 'lucide-vue-next'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'

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
  void safeNavigate(
    router.push({ name: `${shell}-notifications` }),
    '[CHeader] to notifications',
  )
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
})
onUnmounted(() => {
  notifications.stopPolling()
})
watch(showBell, (isAuth) => {
  if (isAuth) {
    notifications.startPolling()
  } else {
    notifications.stopPolling()
  }
})
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
      <button
        v-if="showBell"
        type="button"
        class="c-header__bell"
        :aria-label="t('common.notifications')"
        @click="goToNotifications"
      >
        <Bell :size="20" />
        <span v-if="unreadDisplay" class="c-header__bell-badge">{{ unreadDisplay }}</span>
      </button>
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

.c-header__bell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  /* A5: 44px tap-target floor, same box CAppControls' own buttons use. */
  min-width: var(--size-2xl);
  min-height: var(--size-2xl);
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s;
}
.c-header__bell:hover {
  color: var(--primary);
}

.c-header__bell-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--danger);
  color: var(--on-danger);
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  pointer-events: none;
}
</style>
