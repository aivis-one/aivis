<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- RegisterView (iter 2.6 batch 2 + R22 STYLE-22-02)
// =============================================================================
//
// Email + password + confirmation registration form. Reads the
// referral code from sessionStorage on submit (FP-13, first-wins per
// tab session), passes it to authStore.registerViaEmail, which clears
// the key after a successful response.
//
// iter 2.6 batch 2 changes:
//
//   1. LOGIN LINKS are router-driven instead of emit-driven.
//      The header back-button and the footer "Sign in" link both used
//      to emit('go-login') to App.vue's authView ref. App.vue's
//      standalone-flow branch is gone (router-driven content now);
//      both buttons call router.push({ name: 'login', query:
//      route.query }) instead. Forwarding `?next=` keeps the visitor's
//      intended destination alive across the register <-> login pivot.
//
//   2. `next` IS DELIBERATELY NOT HONOURED here on success.
//      A successful registration kicks off multi-step onboarding
//      (verify -> profile -> role -> KYC -> docs). Carrying `next`
//      through five hops, persisting it across page reloads during
//      onboarding, and racing the user's attention is overkill for
//      this scale of usage. After onboarding completes the user
//      lands on their role dashboard via the existing globalGuard
//      flow; they can navigate back to the public page via the
//      browser back stack or the URL bar. If a real UX pain point
//      surfaces, we can wire it later. See iter 2.6 plan §A4.
//
// R22 STYLE-22-02:
//   goToLogin() catches navigation rejections with the standard
//   NavigationFailure filter -- benign types (duplicated / cancelled
//   / aborted) stay silent, real issues log. Matches the pattern
//   established by useAuthWall (R20 STYLE-20-01) and now applied
//   across all router.push() call-sites that branch on user action.
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { REFERRAL_KEY, useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CInput } from '@/components/ui'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')

function goToLogin(): void {
  // Forward `?next=...` so the eventual sign-in returns the visitor
  // to the same public page they were aiming for.
  void safeNavigate(
    router.push({ name: 'login', query: route.query }),
    '[RegisterView] to login',
  )
}

async function handleRegister(): Promise<void> {
  error.value = ''

  if (!email.value || !password.value || !confirmPassword.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  if (password.value !== confirmPassword.value) {
    error.value = t('auth.error.passwordMismatch')
    return
  }

  if (password.value.length < 8) {
    error.value = t('auth.register.passwordHint')
    return
  }

  const referralCode = sessionStorage.getItem(REFERRAL_KEY)

  try {
    await authStore.registerViaEmail(email.value, password.value, referralCode)
    // BUG-07 fix: after registration the user is at onboarding_step=registered.
    // Push straight to /verify (meta.skipOnboarding=true) -- going through /
    // would bounce us via root.beforeEnter + globalGuard for no reason.
    //
    // iter 2.6 batch 2: deliberately NOT forwarding `?next=` here --
    // see file header for the rationale.
    //
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer registration-error
    // catch and surface as a generic-error toast after successful registration.
    await safeNavigate(
      router.push({ name: 'verify' }),
      '[RegisterView] post-register to verify',
    )
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 409) {
        error.value = t('auth.error.emailTaken')
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
      <button type="button" class="btn-link btn-back" @click="goToLogin">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
        {{ t('auth.back') }}
      </button>
      <CAppControls />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.register.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.register.subtitle') }}</p>

      <div class="auth-form">
        <CInput
          v-model="email"
          :label="t('auth.register.email')"
          type="email"
          placeholder="name@example.com"
          autocomplete="email"
          @keydown.enter="handleRegister"
        />

        <!-- The hint belongs to the field, 4px under it, so the pair is wrapped
             and the field's own bottom margin is dropped; the wrapper carries
             the spacing that used to sit on .form-group. -->
        <div class="form-group">
          <CInput
            v-model="password"
            class="form-group__field"
            :label="t('auth.register.password')"
            type="password"
            :placeholder="t('auth.register.passPlaceholder')"
            autocomplete="new-password"
            @keydown.enter="handleRegister"
          />
          <div class="form-hint">{{ t('auth.register.passwordHint') }}</div>
        </div>

        <CInput
          v-model="confirmPassword"
          :label="t('auth.register.confirmPassword')"
          type="password"
          :placeholder="t('auth.register.confirmPlaceholder')"
          autocomplete="new-password"
          @keydown.enter="handleRegister"
        />

        <div v-if="error" class="auth-error">{{ error }}</div>

        <button
          class="btn btn-primary"
          :disabled="authStore.loading"
          @click="handleRegister"
        >
          <span v-if="authStore.loading" class="btn-spinner" />
          <span v-else>{{ t('auth.register.btn') }}</span>
        </button>

        <div class="auth-footer">
          <span class="auth-footer-text">{{ t('auth.register.hasAccount') }}</span>
          <button type="button" class="btn-link" @click="goToLogin">
            {{ t('auth.register.loginLink') }}
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
  padding: var(--space-4) var(--space-4-lg);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--fs-sm);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-6) var(--space-5);
  overflow-y: auto;
}

.auth-title {
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
  text-align: center;
}

.auth-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-6);
  text-align: center;
  line-height: 1.5;
}

.auth-form {
  width: 100%;
  max-width: var(--maxw-form);
}

.form-group {
  margin-bottom: var(--space-4);
}

/* The field inside a hint pair gives up its own margin to the wrapper. */
.form-group__field {
  margin-bottom: 0;
}

.form-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.auth-error {
  padding: var(--space-3) var(--space-4);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: var(--fs-xs);
  margin-bottom: var(--space-4);
  line-height: 1.5;
}

.btn {
  width: 100%;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--fs-sm);
  font-weight: 600;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
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
  width: var(--size-2xs);
  height: var(--size-2xs);
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
  font-size: var(--fs-sm);
  cursor: pointer;
  padding: 0;
}

.btn-link:hover {
  text-decoration: underline;
}

.auth-footer {
  text-align: center;
  margin-top: var(--space-5);
}

.auth-footer-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-right: var(--space-1);
}
</style>
