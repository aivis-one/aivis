<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { ShieldAlert } from '@/components/ui/icons'
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
//
// TASK-38 (2FA):
//   handleLogin() now branches on authStore.loginViaEmail()'s
//   discriminated result. `mfaRequired: false` runs the EXACT same
//   post-auth redirect this view already had. `mfaRequired: true`
//   does NOT redirect -- no session exists yet -- it switches the form
//   into a second step (mfaStep) asking for a live TOTP code or an
//   unused backup code, then calls authStore.completeMfaLogin() with
//   the returned mfa_token. On THAT success, completeLoginRedirect()
//   (the redirect logic factored out of handleLogin so both paths
//   share it) runs identically to a normal login.
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import { CInput } from '@/components/ui'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const error = ref('')

// -- TASK-38: 2FA code-entry step --
const mfaStep = ref(false)
const mfaToken = ref('')
const mfaCode = ref('')
const useBackupCode = ref(false)
const mfaError = ref('')

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

function goToPasswordReset(): void {
  void safeNavigate(
    router.push({ name: 'password-reset-request' }),
    '[LoginView] to password reset',
  )
}

function goToRegister(): void {
  // Forward the entire `?next=...` query so the visitor's intended
  // destination survives the login <-> register pivot.
  void safeNavigate(
    router.push({ name: 'register', query: route.query }),
    '[LoginView] to register',
  )
}

/**
 * Post-auth redirect -- shared by a normal login AND a 2FA-completed
 * login (submitMfaCode below). Extracted so the two paths cannot drift
 * apart on redirect behaviour.
 */
async function completeLoginRedirect(): Promise<void> {
  // Hygiene: clear any stale referral code lingering in this tab
  // (the visitor signed in to an existing account; FP-13's one-shot
  // guarantee applies to either terminal flow). The store also
  // clears it inside loginViaEmail/completeMfaLogin; this is
  // belt-and-braces for the case where a future refactor moves the
  // store-side cleanup, and it's a free op when the slot is already
  // empty.
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
}

async function handleLogin(): Promise<void> {
  error.value = ''

  if (!email.value || !password.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  try {
    const result = await authStore.loginViaEmail(email.value, password.value)

    if (result.mfaRequired) {
      // Password checked out, but no session exists yet -- switch to
      // the code-entry step instead of redirecting anywhere.
      mfaToken.value = result.mfaToken
      mfaCode.value = ''
      mfaError.value = ''
      useBackupCode.value = false
      mfaStep.value = true
      return
    }

    await completeLoginRedirect()
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

// ---------------------------------------------------------------------------
// TASK-38: 2FA code-entry step
// ---------------------------------------------------------------------------

function backToPassword(): void {
  mfaStep.value = false
  mfaToken.value = ''
  mfaCode.value = ''
  mfaError.value = ''
}

function toggleBackupCode(): void {
  useBackupCode.value = !useBackupCode.value
  mfaCode.value = ''
  mfaError.value = ''
}

async function submitMfaCode(): Promise<void> {
  mfaError.value = ''

  if (!mfaCode.value.trim()) {
    mfaError.value = t('auth.error.fillAllFields')
    return
  }

  try {
    await authStore.completeMfaLogin(mfaToken.value, mfaCode.value.trim())
    await completeLoginRedirect()
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 400) {
        // The pending token is consumed on ANY outcome, success or
        // failure (see api/auth.ts's verifyTwoFactorLogin docstring) --
        // a wrong code here means the whole mfa_token is now dead, not
        // just this one guess. Sending the visitor back to re-enter
        // their password (which mints a fresh token) is the only way
        // forward, not a "try again" retry on the same step -- so the
        // message is shown on the PASSWORD screen (`error`, not
        // `mfaError`, which backToPassword() clears) after the reset.
        backToPassword()
        error.value = t('auth.login.mfa.errorInvalidCode')
        return
      }
      if (err.status === 429) {
        mfaError.value = t('auth.error.rateLimited')
      } else {
        mfaError.value = err.detail
      }
    } else if (err instanceof ApiNetworkError) {
      mfaError.value = t('auth.error.networkError')
    } else if (err instanceof ApiTimeoutError) {
      mfaError.value = t('auth.error.timeout')
    } else {
      mfaError.value = t('common.error')
    }
  }
}
</script>

<template>
  <AuthShell>
    <template v-if="!mfaStep">
      <h1 class="ds-auth__title">
        {{ t('auth.login.title') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.login.tagline') }}<br />{{ t('auth.login.subtitle') }}
      </p>

      <div class="ds-auth__form">
        <CInput
          v-model="email"
          :label="t('auth.login.email')"
          type="email"
          placeholder="name@example.com"
          autocomplete="email"
          @keydown.enter="handleLogin"
        />

        <CInput
          v-model="password"
          :label="t('auth.login.password')"
          type="password"
          :placeholder="t('auth.login.passPlaceholder')"
          autocomplete="current-password"
          @keydown.enter="handleLogin"
        />

        <div class="forgot-row">
          <button
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="goToPasswordReset"
          >
            {{ t('auth.login.forgot') }}
          </button>
        </div>

        <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ error }}</p>
          </div>
        </div>

        <button
          class="ds-button ds-button--primary ds-button--block"
          :aria-busy="authStore.loading || undefined"
          :disabled="authStore.loading"
          @click="handleLogin"
        >
          <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.login.btn') }}</span>
        </button>

        <div class="ds-auth__foot">
          <span>{{ t('auth.login.noAccount') }}</span>
          <button
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="goToRegister"
          >
            {{ t('auth.login.createAccount') }}
          </button>
        </div>
      </div>
    </template>

    <!-- TASK-38: 2FA code-entry step, shown after loginViaEmail resolves
           with mfaRequired=true. No email/password fields here -- those
           already succeeded; this step exists purely to complete the
           second factor via authStore.completeMfaLogin(). -->
    <template v-else>
      <h1 class="ds-auth__title">
        {{ t('auth.login.mfa.title') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.login.mfa.subtitle') }}
      </p>

      <div class="ds-auth__form">
        <CInput
          v-model="mfaCode"
          :label="
            useBackupCode ? t('auth.login.mfa.backupCodeLabel') : t('auth.login.mfa.codeLabel')
          "
          type="text"
          :inputmode="useBackupCode ? 'text' : 'numeric'"
          autocomplete="one-time-code"
          :maxlength="useBackupCode ? 20 : 6"
          :placeholder="
            useBackupCode
              ? t('auth.login.mfa.backupCodePlaceholder')
              : t('auth.login.mfa.codePlaceholder')
          "
          @keydown.enter="submitMfaCode"
        />

        <div class="forgot-row">
          <button
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="toggleBackupCode"
          >
            {{
              useBackupCode
                ? t('auth.login.mfa.useCodeInstead')
                : t('auth.login.mfa.useBackupCodeInstead')
            }}
          </button>
        </div>

        <div v-if="mfaError" class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ mfaError }}</p>
          </div>
        </div>

        <button
          class="ds-button ds-button--primary ds-button--block"
          :aria-busy="authStore.loading || undefined"
          :disabled="authStore.loading"
          @click="submitMfaCode"
        >
          <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.login.mfa.verifyBtn') }}</span>
        </button>

        <div class="ds-auth__foot">
          <button
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="backToPassword"
          >
            {{ t('auth.login.mfa.backToPassword') }}
          </button>
        </div>
      </div>
    </template>
  </AuthShell>
</template>

<style scoped>
.forgot-row {
  display: flex;
  justify-content: flex-end;
}
</style>
