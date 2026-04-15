// =============================================================================
// CBSHOME Frontend -- useAuth Composable
// =============================================================================
//
// Combines platform + auth store into a single init flow.
// Called once from App.vue onMounted.
//
// Module-level refs (isReady, isStandalone) are singletons shared
// across all components that call useAuth().
// =============================================================================

import { ref, watch } from 'vue'

import { platform } from '@/platform'
import { useAuthStore } from '@/stores/auth'

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
   *   2. Save referral code from URL ?ref= or platform.getStartParam()
   *   3. restoreSession() -- if saved token is valid, done
   *   4. Telegram: auto-login via initData
   *   5. Standalone with no token: user sees LoginView
   */
  async function initAuth(): Promise<void> {
    const authStore = useAuthStore()
    authError.value = null

    try {
      await platform.init()
      isStandalone.value = platform.name === 'standalone'

      // Persist referral code on first visit.
      _saveReferralCode()

      // Try restoring existing session.
      const restored = await authStore.restoreSession()
      if (restored) return

      // Telegram auto-login.
      if (!isStandalone.value) {
        const initData = platform.getInitData()
        if (initData) {
          const referralCode = sessionStorage.getItem('cbs_referral_code')
          await authStore.loginViaTelegram(initData, referralCode)
        } else {
          authError.value = 'Telegram initData not available'
        }
      }
      // Standalone with no token: isReady becomes true, App.vue shows LoginView.
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
// Internal helpers
// ---------------------------------------------------------------------------

/** Save referral code from URL query (?ref=) or Telegram start_param. */
function _saveReferralCode(): void {
  // Don't overwrite if already saved.
  if (sessionStorage.getItem('cbs_referral_code')) return

  const fromUrl = new URLSearchParams(window.location.search).get('ref')
  const fromPlatform = platform.getStartParam()
  const code = fromUrl || fromPlatform

  if (code) {
    sessionStorage.setItem('cbs_referral_code', code)
  }
}
