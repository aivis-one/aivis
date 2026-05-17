<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PublicShell (iter 2.6 R1 §1.6, Block A1
//                                   + R22 STYLE-22-02)
// =============================================================================
//
// Layout wrapper for /public/* routes. The anonymous-storefront
// counterpart to InvestorShell / AgentShell / CompanyShell / StaffShell.
//
// DIFFERENCES FROM AUTHENTICATED SHELLS:
//   - No CTabBar. Anonymous visitors have no tabs to navigate between;
//     the storefront is a linear browse flow (list -> company ->
//     product -> auth wall).
//   - Header carries a "Sign in" CTA on the right that routes to
//     /login with `?next=<current path>` so the visitor returns to
//     the same public page after a successful sign-in. LoginView reads
//     `next` and replace()s to it (iter 2.6 Batch 2 §A4).
//   - CToast is included so PublicAttachmentsSection, rate-limit
//     handlers (usePublicErrorToast), etc. can surface notifications
//     without each public view importing the toast component itself.
//
// STRUCTURE.
//   Mirrors InvestorShell's flex column (header / main, with the
//   bottom tabbar slot deliberately empty). `min-height: 100dvh`
//   matches the authenticated shells; main scrolls independently so
//   the header stays sticky.
//
// SAFE-AREA.
//   The header pads `env(safe-area-inset-top)` so the storefront looks
//   right on notched devices. No bottom inset to worry about -- there
//   is no fixed bottom bar.
//
// R22 STYLE-22-02:
//   goToLogin() catches navigation rejections with the same filter
//   used by useAuthWall (R20 STYLE-20-01): NavigationFailureType
//   `duplicated` / `cancelled` / `aborted` are benign (rapid taps,
//   guard pre-emption) and stay silent; anything else logs to the
//   console with a contextual prefix. Previously `void router.push()`
//   swallowed every rejection -- a missing route, a thrown guard,
//   anything -- with no diagnostic surface.
// =============================================================================

import { computed } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRoute,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'

import CbsLogo from '@/components/ui/CbsLogo.vue'
import CToast from '@/components/ui/CToast.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Always include the current public path as ?next= so LoginView can
// replace() back to it post-auth. Exclude the root edge case (a user
// at `/` won't hit PublicShell since /public/* is the entry point,
// but defence-in-depth: empty `next` is the safer baseline).
const nextQuery = computed<string | undefined>(() => {
  const path = route.fullPath
  if (!path || path === '/') return undefined
  return path
})

function goToLogin(): void {
  router
    .push({
      name: 'login',
      query: nextQuery.value ? { next: nextQuery.value } : undefined,
    })
    .catch((err: unknown) => {
      // Benign vue-router rejection types: double-tap / guard
      // pre-emption / abort by a newer navigation. Keep these
      // silent so real issues (unknown route name, thrown guard,
      // ...) remain visible in the console.
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error('[PublicShell] navigation to login failed:', err)
    })
}
</script>

<template>
  <div class="public-shell">
    <header class="public-shell__header">
      <CbsLogo :height="28" />
      <button
        type="button"
        class="public-shell__login"
        @click="goToLogin"
      >
        {{ t('public.shell.loginButton') }}
      </button>
    </header>

    <main class="public-shell__main">
      <RouterView />
    </main>

    <CToast />
  </div>
</template>

<style scoped>
.public-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg);
}

.public-shell__header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(16px + env(safe-area-inset-top, 0px)) 20px 16px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}

.public-shell__login {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: var(--accent);
  color: white;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.public-shell__login:hover {
  opacity: 0.9;
}

.public-shell__login:active {
  opacity: 0.8;
}

.public-shell__main {
  flex: 1;
  overflow-y: auto;
}
</style>
