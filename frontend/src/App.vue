<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- Root component (iter 2.6 batch 2)
// =============================================================================
//
// Root auth gate + avatar overlay banner.
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
// Avatar mode (UNCHANGED):
//   When staff is operating as another user, a fixed banner is shown
//   at the top of the screen with a "Return to Staff" button.
//
// Telegram failure (UNCHANGED):
//   If Telegram WebApp init fails and we are not in standalone mode,
//   we show the auth-error screen with a Retry button instead of
//   RouterView. Standalone mode (regular browser) does NOT see this
//   screen even on transient init issues -- standalone has no
//   Telegram dependency.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost, Shield } from 'lucide-vue-next'

import { useAuthStore } from '@/stores/auth'
import { useAuth } from '@/composables/useAuth'
import { useAvatar } from '@/composables/useAvatar'
import LoadingView from '@/views/auth/LoadingView.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const { initAuth, retryAuth, isReady, isStandalone, authError } = useAuth()
const { isAvatarActive, loading: avatarLoading, endAvatarSession } = useAvatar()

/** Display name for avatar banner. */
const avatarTargetName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    if (fn) return String(fn)
  }
  return authStore.user?.email ?? '…'
})

onMounted(() => {
  initAuth()
})
</script>

<template>
  <!-- Avatar overlay banner — fixed at top, above everything -->
  <div v-if="isAvatarActive && authStore.isAuthenticated" class="avatar-banner">
    <div class="avatar-banner__left">
      <Ghost :size="16" />
      <span class="avatar-banner__text">
        Avatar: {{ avatarTargetName }}
      </span>
    </div>
    <button
      class="avatar-banner__btn"
      :disabled="avatarLoading"
      @click="endAvatarSession"
    >
      <Shield :size="16" />
      {{ t('staff.avatar.return') }}
    </button>
  </div>

  <!-- Phase 1: auth initialization in progress -->
  <LoadingView v-if="!isReady" />

  <!-- Phase 2: Telegram auth failure (standalone mode skips this branch) -->
  <div
    v-else-if="authError && !isStandalone && !authStore.isAuthenticated"
    class="auth-error-screen"
  >
    <p class="auth-error-text">{{ authError }}</p>
    <button class="auth-error-retry" @click="retryAuth">{{ t('common.retry') }}</button>
  </div>

  <!-- Phase 3 (iter 2.6 batch 2): router-driven content for both
       authenticated and anonymous visitors. globalGuard / route meta
       decide what renders. The avatar-active class still pads the top
       so the fixed banner doesn't overlap content. -->
  <div v-else :class="{ 'app--avatar-active': isAvatarActive && authStore.isAuthenticated }">
    <RouterView />
  </div>
</template>

<style scoped>
/* Avatar overlay banner */
.avatar-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--accent);
  color: var(--on-accent);
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.avatar-banner__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.avatar-banner__text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.avatar-banner__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  /* An inverse chip ON the accent banner. Was `white`, which is identical in
     light but puts light-amber text on white in dark. --on-accent tracks the
     banner, so the pair inverts together. */
  background: var(--on-accent);
  color: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.avatar-banner__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.avatar-banner__btn:hover:not(:disabled) {
  opacity: 0.9;
}

/* Push content down when avatar banner is visible */
.app--avatar-active {
  padding-top: 40px;
}

/* Auth error screen */
.auth-error-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  gap: var(--space-4);
  padding: 24px;
}
.auth-error-text {
  font-size: 14px;
  color: var(--danger);
  text-align: center;
}
.auth-error-retry {
  padding: 12px 24px;
  border-radius: var(--radius-md);
  /* --primary, not --accent: this is the screen's PRIMARY action. The owner
     found eight of these and they were fixed; the sweep found this one
     outside that pass's scope. `background: var(--accent)` resolves
     perfectly, so no token audit can ever see it -- only reading the
     selector name against the token name does. */
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 600;
  font-size: 15px;
  border: none;
  cursor: pointer;
}
</style>
