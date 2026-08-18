<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- LoginView (iter 2.6 batch 2 + R22 STYLE-22-01 + STYLE-22-02)
// =============================================================================
//
// Email + password sign-in form.
//
// iter 2.6 batch 2 changes:
//
//   1. POST-AUTH REDIRECT honours `?next=` from the URL.
//      The query is set by:
//        - PublicShell's "Sign in" header CTA (the visitor was on a
//          /public/* page and explicitly wanted to sign in).
//        - useAuthWall().requireAuth() bouncing an anonymous visitor
//          off a CTA -- though that bouncer pushes to register, not
//          login; the register screen forwards `next` when the
//          visitor switches over.
//        - globalGuard redirecting an unauthenticated visitor away
//          from a protected URL.
//      We validate `next` to be a same-origin path (`startsWith('/')`
//      and NOT `startsWith('//')` -- the latter would let a malicious
//      link target an arbitrary protocol-relative URL through this
//      replace). On valid next we replace(); otherwise we fall back
//      to the original behaviour of `router.push('/')`, which
//      delegates to root.beforeEnter to pick the role dashboard.
//
//   2. CLEAR the referral key after successful sign-in.
//      Closes the hygiene gap from iter 2.5 where the referral code
//      lingered in sessionStorage after an existing user logged in
//      via a referral link. The referral is one-shot per browser
//      tab session (see FP-13); leaving stale codes around could
//      mis-attribute a subsequent registration in the same tab.
//
//   3. REGISTER LINK is router-driven instead of emit-driven.
//      Old code emitted 'go-register' to App.vue, which flipped a
//      local `authView` ref. iter 2.6 batch 2 removed that branch
//      entirely; LoginView now lives under the /login route and the
//      "Create account" footer button calls router.push({ name:
//      'register', query: route.query }) -- forwarding `?next=` so
//      the user's eventual sign-up returns to the same path they
//      were aiming for (via the LoginView fallback after they decide
//      they actually had an account).
//
// R22 STYLE-22-01:
//   The sessionStorage cleanup uses the shared `REFERRAL_KEY`
//   constant imported from stores/auth instead of an inline literal.
//   Eliminates the rename-miss-one trap that having three independent
//   `'aivis_referral_code'` literals enabled.
//
// R22 STYLE-22-02:
//   goToRegister() catches navigation rejections with the standard
//   NavigationFailure filter -- benign types (duplicated / cancelled
//   / aborted) stay silent, real issues log. Symmetry with
//   PublicShell / RegisterView / useAuthWall.
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')

/**
 * Pull a same-origin path out of `route.query.next` for the post-auth
 * redirect. Returns null if missing, malformed, or shaped like an
 * open-redirect target.
 *
 * - Must be a string (vue-router can return arrays for repeated keys).
 * - Must begin with `/` -- absolute URLs and bare hostnames are
 *   rejected.
 * - Must NOT begin with `//` -- protocol-relative URLs like
 *   `//evil.com/foo` are normalised to https://evil.com/foo by the
 *   browser and would let a crafted link redirect off our origin.
 */
function getValidatedNext(): string | null {
  const raw = route.query.next
  if (typeof raw !== 'string') return null
  if (!raw.startsWith('/')) return null
  if (raw.startsWith('//')) return null
  return raw
}

function goToRegister(): void {
  // Forward the entire `?next=...` query so the visitor's intended
  // destination survives the login <-> register pivot.
  void safeNavigate(
    router.push({ name: 'register', query: route.query }),
    '[LoginView] to register',
  )
}

async function handleLogin(): Promise<void> {
  error.value = ''

  if (!email.value || !password.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  try {
    await authStore.loginViaEmail(email.value, password.value)

    // Hygiene: clear any stale referral code lingering in this tab
    // (the visitor signed in to an existing account; FP-13's one-shot
    // guarantee applies to either terminal flow). The store also
    // clears it inside loginViaEmail; this is belt-and-braces for the
    // case where a future refactor moves the store-side cleanup, and
    // it's a free op when the slot is already empty.
    sessionStorage.removeItem(REFERRAL_KEY)

    // Post-auth redirect. If the visitor was bounced here from a
    // protected URL or from a public CTA, return them. Otherwise let
    // root.beforeEnter resolve the role dashboard.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer auth-error catch
    // and surface as a credentials/network error toast after a
    // successful login.
    const next = getValidatedNext()
    if (next !== null) {
      await safeNavigate(router.replace(next), '[LoginView] post-auth replace to next')
    } else {
      await safeNavigate(router.push('/'), '[LoginView] post-auth to home')
    }
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 401) {
        error.value = t('auth.error.invalidCredentials')
      } else {
        error.value = err.detail
      }
    } else if (err instanceof ApiNetworkError) {
      error.value = t('auth.error.networkError')
    } else if (err instanceof ApiTimeoutError) {
      error.value = t('auth.error.timeout')
    } else {
      error.value = t('common.error')
    }
  }
}
</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <CAppControls />
    </header>

    <div class="auth-content">
      <div class="auth-brand">
        <AivisLogo :height="64" />
      </div>

      <h1 class="auth-title">{{ t('auth.login.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.login.subtitle') }}</p>

      <div class="auth-form">
        <div class="form-group">
          <label class="form-label">{{ t('auth.login.email') }}</label>
          <input
            v-model="email"
            type="email"
            class="form-input"
            placeholder="name@example.com"
            autocomplete="email"
            @keydown.enter="handleLogin"
          />
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('auth.login.password') }}</label>
          <div class="input-wrapper">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="form-input"
              :placeholder="t('auth.login.passPlaceholder')"
              autocomplete="current-password"
              @keydown.enter="handleLogin"
            />
            <button
              type="button"
              class="toggle-password"
              @click="showPassword = !showPassword"
            >
              <svg
                v-if="!showPassword"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <svg
                v-else
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
                />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <button
          class="btn btn-primary"
          :disabled="authStore.loading"
          @click="handleLogin"
        >
          <span v-if="authStore.loading" class="btn-spinner" />
          <span v-else>{{ t('auth.login.btn') }}</span>
        </button>

        <div class="auth-footer">
          <span class="auth-footer-text">{{ t('auth.login.noAccount') }}</span>
          <button type="button" class="btn-link" @click="goToRegister">
            {{ t('auth.login.createAccount') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-screen {
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
}

.auth-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg-page);
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 24px;
  overflow-y: auto;
}

/* The entry screen leads with the BRAND, not a generic padlock glyph: the mark
   plus the drawn wordmark, at 64px. This is the first thing a user sees. */
.auth-brand {
  margin-bottom: 24px;
  display: flex;
  justify-content: center;
}

.auth-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
  text-align: center;
}

.auth-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 32px;
  text-align: center;
  line-height: 1.5;
}

.auth-form {
  width: 100%;
  max-width: 360px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-page);
  color: var(--text-primary);
  font-size: 15px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.form-input::placeholder {
  color: var(--text-tertiary);
}

.input-wrapper {
  position: relative;
}

.input-wrapper .form-input {
  padding-right: 48px;
}

.toggle-password {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  padding: 4px;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
}

.toggle-password svg {
  width: 20px;
  height: 20px;
}

.auth-error {
  padding: 12px 16px;
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: 13px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.btn {
  width: 100%;
  padding: 14px;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--primary);
  color: var(--on-primary);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-spinner {
  width: 20px;
  height: 20px;
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  border: 2px solid currentColor;
  opacity: 0.35;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.btn-link {
  background: none;
  border: none;
  color: var(--primary);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  padding: 0;
}

.btn-link:hover {
  text-decoration: underline;
}

.auth-footer {
  text-align: center;
  margin-top: 24px;
}

.auth-footer-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-right: 4px;
}
</style>
