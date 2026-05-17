// =============================================================================
// CBSHOME Frontend -- useAuth Composable (iter 2.6 batch 2 + R22 STYLE-22-01)
// =============================================================================
//
// Combines platform + auth store into a single init flow.
// Called once from App.vue onMounted.
//
// Module-level refs (isReady, isStandalone) are singletons shared
// across all components that call useAuth().
//
// iter 2.6 batch 2 changes:
//
//   1. _saveReferralCode() now recognises three sources, not two:
//        (a) URL query: `?ref=<code>` -- unchanged.
//        (b) Telegram start_param via platform.getStartParam() -- unchanged.
//        (c) URL path: `/r/<code>` (R1 referral patch §A6) -- NEW.
//      The path match is a sibling source: the visitor types
//      cbshome.org/r/AGENT_CODE in their browser, captureReferralFromPath()
//      is called from the /r/:code beforeEnter and also from this
//      initAuth-time scan to cover the case where the app hot-reloads
//      on the /r/... URL before the router boots.
//      FIRST-WINS guard (FP-13) is preserved: an existing
//      sessionStorage code blocks all three sources.
//
//   2. captureReferralFromPath(code) is exported so router.index.ts
//      can call it from the /r/:code beforeEnter hook. The export is
//      a thin wrapper around the same sessionStorage write with the
//      first-wins guard -- single source of truth, no risk of the
//      hook and the initAuth scan disagreeing on the storage shape.
//
// iter 2.6 R22 STYLE-22-01:
//   REFERRAL_KEY now lives in stores/auth.ts and is imported here.
//   The store is the natural owner -- three of the four sessionStorage
//   call-sites (one per login flow) live there. Importing here also
//   avoids a circular dependency: this module already imports
//   useAuthStore from stores/auth, so an additional named import from
//   the same module is a straight DAG edge, not a cycle.
// =============================================================================

import { ref, watch } from 'vue'

import { platform } from '@/platform'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'

// Marketing referral path: `/r/AGENT_CODE`. Matches the route
// registered as `referral-link` in router/index.ts; the regex is the
// authoritative source for what counts as a valid code character set.
// The router uses the same character class as a path constraint
// (`/r/:code([A-Za-z0-9_-]+)`) so the two stay in sync.
const REFERRAL_PATH_RE = /^\/r\/([A-Za-z0-9_-]+)\/?$/

// ---------------------------------------------------------------------------
// Singleton refs (shared across all consumers)
// ---------------------------------------------------------------------------

const isReady = ref(false)
const isStandalone = ref(true)
const authError = ref<string | null>(null)

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useAuth() {
  /**
   * Initialize authentication. Called once from App.vue onMounted.
   *
   * Flow:
   *   1. platform.init()
   *   2. Save referral code from URL path (/r/<code>), URL query
   *      (?ref=<code>), or Telegram start_param.
   *   3. restoreSession() -- if saved token is valid, done
   *   4. Telegram: auto-login via initData
   *   5. Standalone with no token: user sees /login (router-driven)
   */
  async function initAuth(): Promise<void> {
    const authStore = useAuthStore()
    authError.value = null

    try {
      await platform.init()
      isStandalone.value = platform.name === 'standalone'

      // Persist referral code on first visit. Source order is
      // immaterial because of first-wins: whichever scan checks
      // first against an empty key wins, and the others no-op.
      _saveReferralCode()

      // Try restoring existing session.
      const restored = await authStore.restoreSession()
      if (restored) return

      // Telegram auto-login.
      if (!isStandalone.value) {
        const initData = platform.getInitData()
        if (initData) {
          const referralCode = sessionStorage.getItem(REFERRAL_KEY)
          await authStore.loginViaTelegram(initData, referralCode)
        } else {
          authError.value = 'Telegram initData not available'
        }
      }
      // Standalone with no token: isReady becomes true, /login is
      // reached via root.beforeEnter -> getRoleDashboard(null).
    } catch (err) {
      authError.value = err instanceof Error ? err.message : 'Authentication failed'
      console.error('[useAuth] initAuth failed:', err)
    } finally {
      isReady.value = true
    }
  }

  /** Retry auth initialization (e.g. after Telegram failure). */
  async function retryAuth(): Promise<void> {
    isReady.value = false
    await initAuth()
  }

  /**
   * Wait until auth initialization completes.
   * Used by router guards to delay navigation until ready.
   * Rejects after 10 seconds timeout.
   */
  function waitUntilReady(): Promise<void> {
    if (isReady.value) return Promise.resolve()

    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        unwatch()
        reject(new Error('Auth init timeout (10s)'))
      }, 10_000)

      const unwatch = watch(isReady, (ready) => {
        if (ready) {
          clearTimeout(timer)
          unwatch()
          resolve()
        }
      })
    })
  }

  return {
    initAuth,
    retryAuth,
    isReady,
    isStandalone,
    authError,
    waitUntilReady,
  }
}

// ---------------------------------------------------------------------------
// Referral capture helpers (iter 2.6 batch 2)
// ---------------------------------------------------------------------------

/**
 * Save a referral code to sessionStorage if no code is already
 * stored. First-wins per FP-13: once a tab has been credited to an
 * agent, subsequent referral links in the same session do not
 * overwrite.
 *
 * Exported so router.index.ts can invoke it from the /r/:code
 * beforeEnter hook -- the route handler doesn't need to know the
 * sessionStorage key or the first-wins policy; it just hands us the
 * code parsed from the URL params.
 */
export function captureReferralFromPath(code: string): void {
  if (!code) return
  // First-wins: defer to the existing stored code if any.
  if (sessionStorage.getItem(REFERRAL_KEY)) return
  sessionStorage.setItem(REFERRAL_KEY, code)
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Save referral code from URL path (/r/<code>), URL query (?ref=), or
 * Telegram start_param. Called once on initAuth -- first-wins means
 * subsequent reruns are no-ops.
 */
function _saveReferralCode(): void {
  // Don't overwrite if already saved (FP-13 first-wins).
  if (sessionStorage.getItem(REFERRAL_KEY)) return

  // Path-based: /r/<code>. Match here as well as in router.beforeEnter
  // so an app boot that lands directly on /r/<code> (cold reload)
  // captures even if the router's beforeEnter has not run yet at the
  // moment of initAuth. The regex is permissive on a trailing slash.
  const pathMatch = REFERRAL_PATH_RE.exec(window.location.pathname)
  const fromPath = pathMatch ? pathMatch[1] : null

  const fromUrl = new URLSearchParams(window.location.search).get('ref')
  const fromPlatform = platform.getStartParam()

  // Order is irrelevant because of first-wins above; this picks the
  // first non-empty in path -> query -> platform priority. Anyone of
  // them suffices to credit the visit.
  const code = fromPath || fromUrl || fromPlatform

  if (code) {
    sessionStorage.setItem(REFERRAL_KEY, code)
  }
}
