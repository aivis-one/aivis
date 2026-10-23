<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicShell (iter 2.6 R1 §1.6, Block A1
//                                   + iter 2.6 batch 3 relocation)
// =============================================================================
//
// Layout wrapper for /public/* routes. Anonymous-storefront counterpart
// to InvestorShell / AgentShell / CompanyShell / StaffShell.
//
// LOCATION (iter 2.6 batch 3).
//   Originally written to `frontend/src/layouts/PublicShell.vue` in
//   batch 2 -- an honest oversight since the four authenticated
//   shells already live under `frontend/src/components/layout/`. Batch
//   3 moves this file alongside them so the "where do shells live"
//   question has one answer for the whole codebase.
//
// COMPOSITION.
//   Same building blocks as InvestorShell: <CHeader> on top, scrollable
//   <main> with <RouterView />, <CToast> sibling. The differences with
//   InvestorShell:
//     - No <CTabBar>. Anonymous visitors have no tabs to navigate
//       between; the storefront is a linear browse flow (list ->
//       company -> product -> auth wall on Buy).
//     - The CHeader carries a "Sign in" CTA in its `right` slot,
//       routed to /login with `?next=<current path>` so the visitor
//       returns to the same public page post-auth (LoginView reads
//       `next` and replace()s, iter 2.6 Batch 2 §A4).
//   CHeader prop defaults (showBack=false, showLogo=true) match what
//   InvestorShell uses -- no overrides needed.
//
// LANGUAGE + THEME CONTROLS.
//   Added here 2026-08-18 when the four /public/* views turned out to have
//   neither -- the worst surface to miss, since `/r/:code` lands a referred
//   first-time visitor on /public/companies before they ever see /login.
//   MOVED into CHeader the same day: the four cabinets were missing them too,
//   and one header serves every shell.
//
// NO BACK BUTTON IN THE HEADER.
//   Public views do not pass `:show-back="true"` either. Browser back
//   handles the list <-> overview navigation. A deep-linked visitor
//   simply closes the tab. Adding a back arrow would clutter the
//   marketing surface without paying for itself.
//
// R22 STYLE-22-02 (preserved).
//   goToLogin() filters NavigationFailure types (duplicated /
//   cancelled / aborted) and logs anything else. Same pattern as
//   LoginView / RegisterView / useAuthWall.
// =============================================================================

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { useI18n } from 'vue-i18n'

import CHeader from '@/components/layout/CHeader.vue'
import CToast from '@/components/ui/CToast.vue'
import { useAuthStore } from '@/stores/auth'
import { getRoleDashboard } from '@/router/guards'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

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
  void safeNavigate(
    router.push({
      name: 'login',
      query: nextQuery.value ? { next: nextQuery.value } : undefined,
    }),
    '[PublicShell] to login',
  )
}

function goToRegister(): void {
  void safeNavigate(
    router.push({
      name: 'register',
      query: nextQuery.value ? { next: nextQuery.value } : undefined,
    }),
    '[PublicShell] to register',
  )
}

// A signed-in visitor sees the way into the cabinet in place of "Sign in".
function goToCabinet(): void {
  void safeNavigate(router.push(getRoleDashboard(authStore.role)), '[PublicShell] to cabinet')
}
</script>

<template>
  <div class="shell">
    <CHeader>
      <template #right>
        <button
          v-if="authStore.isAuthenticated"
          type="button"
          class="ds-button ds-button--primary"
          @click="goToCabinet"
        >
          {{ t('public.shell.cabinetButton') }}
        </button>
        <template v-else>
          <button type="button" class="ds-button ds-button--secondary" @click="goToRegister">
            {{ t('public.shell.registerButton') }}
          </button>
          <button type="button" class="ds-button ds-button--primary" @click="goToLogin">
            {{ t('public.shell.loginButton') }}
          </button>
        </template>
      </template>
    </CHeader>
    <main class="shell__content">
      <div class="shell__measure">
        <RouterView />
      </div>
    </main>
    <CToast />
  </div>
</template>

<style scoped>
/* PublicShell owns no rule of its own: its buttons are the system's Button
   (Sign in the primary action, Register the quieter one beside it), and `.shell`,
   `.shell__content` and `.shell__measure` are shared chrome in styles/shell.css.
   It deliberately does not carry `shell--tabbed`: the storefront has no tab bar
   and no side nav, so it gets no tier rules. */
</style>
