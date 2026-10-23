<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- Root component (iter 2.6 batch 2)
// =============================================================================
//
// Root auth gate.
//
// Flow (iter 2.6 batch 2 rework):
//   !isReady                                  → LoadingView
//   authError && !isStandalone && !auth       → Error screen with retry
//                                                (Telegram init failure)
//   default                                   → <RouterView /> (always)
//
// PREVIOUSLY the "Phase 3: not authenticated" branch rendered
// LoginView / RegisterView directly through an `authView` ref +
// emit('go-login' | 'go-register') reactive switch. URL was decoupled
// from screen state. iter 2.6 batch 2 removed that branch because:
//
//   1. The public storefront (/public/*) needs RouterView to be live
//      for anonymous visitors. Gating RouterView behind isAuthenticated
//      made /public/* unreachable without first logging in.
//   2. With router-driven auth screens, the URL always reflects what
//      the user sees. A user who lands on /login then taps "Create
//      account" navigates to /register -- one-line `router.push`
//      from LoginView replaces the old `emit('go-register')` dance.
//   3. ?next= propagation works end-to-end. globalGuard pushes
//      anonymous visitors to /login?next=<path>; LoginView reads
//      `next` and replace()s back. With the standalone-flow this
//      could not work -- there was no URL to replace TO.
//
// HOW ANONYMOUS VISITORS REACH THE LOGIN SCREEN.
//   - Root (`/`) -> root.beforeEnter -> getRoleDashboard(null) ->
//     '/login' -> RouterView mounts LoginView (route name 'login',
//     meta.public=true). Same end UX as before, plumbed through
//     the router instead of through App.vue's reactive switch.
//   - Anonymous visit to a protected URL -> globalGuard returns
//     { name: 'login', query: { next: <path> } } -> same flow.
//   - Anonymous visit to /public/* -> globalGuard's public branch
//     lets it through to PublicShell + RouterView.
//
// Avatar mode:
//   When staff is operating as another user, the frame shows the banner row
//   (K25, the warning look) above the header with a "Return to Staff" button:
//   components/layout/AvatarBanner.vue, drawn by AppShell and by AuthShell.
//
// Telegram failure:
//   If Telegram WebApp init fails and we are not in standalone mode,
//   we show the auth-error screen (the auth shell, K33, with a danger Alert,
//   K09, and a primary Retry, K01) instead of RouterView. Standalone mode
//   (regular browser) does NOT see this screen even on transient init issues --
//   standalone has no Telegram dependency.
// =============================================================================

import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle } from '@/components/ui/icons'

import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import { useRoleRefresh } from '@/composables/useRoleRefresh'
import AuthShell from '@/components/layout/AuthShell.vue'
import LoadingView from '@/views/auth/LoadingView.vue'
import KycRequiredPrompt from '@/components/shared/KycRequiredPrompt.vue'
import IntroCards from '@/components/shared/IntroCards.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const { initAuth, retryAuth, isReady, isStandalone, authError } = useAuth()

// An approved applicant moves to the integrator cabinet without signing in again.
useRoleRefresh()

onMounted(() => {
  initAuth()
})
</script>

<template>
  <!-- Phase 1: auth initialization in progress -->
  <LoadingView v-if="!isReady" />

  <!-- Phase 2: Telegram auth failure (standalone mode skips this branch) -->
  <AuthShell v-else-if="authError && !isStandalone && !authStore.isAuthenticated">
    <div class="ds-auth__icon" aria-hidden="true"><AlertTriangle /></div>
    <h1 class="ds-auth__title">{{ t('common.error') }}</h1>
    <div class="ds-alert ds-alert--danger" role="alert">
      <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ authError }}</p>
      </div>
    </div>
    <div class="ds-auth__form">
      <button type="button" class="ds-button ds-button--primary" @click="retryAuth">
        {{ t('common.retry') }}
      </button>
    </div>
  </AuthShell>

  <!-- Phase 3 (iter 2.6 batch 2): router-driven content for both
       authenticated and anonymous visitors. globalGuard / route meta
       decide what renders. -->
  <RouterView v-else />

  <!-- The message a closed action answers with before verification -->
  <KycRequiredPrompt />

  <!-- What the service is, shown once before the first entry -->
  <IntroCards />
</template>
