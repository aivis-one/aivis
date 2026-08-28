<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PasswordResetConfirmView
// =============================================================================
//
// Step 2 of account recovery: reads `?token=` from the URL (the link
// _send_password_reset_email built -- see auth/service.py --
// f"{frontend_base_url}/password-reset/confirm?token={token}"), takes a
// new password, and POSTs both to /api/v1/auth/password-reset/confirm.
//
// Unlike the request step, this endpoint's response DOES legitimately
// reveal whether the token was valid (400 vs 204) -- that is not an
// enumeration leak (see auth/router.py docstring): the token is a
// 256-bit secret only the recipient of the email ever saw, nothing
// about the underlying email address is exposed by a 400 here.
//
// No session exists yet at this point -- this view does NOT touch
// authStore. A successful reset invalidates every session server-side
// (delete_all_sessions in auth/service.py::confirm_password_reset), so
// even if the browser somehow still held a stale token none would work
// afterward; the user signs in fresh via LoginView.
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CInput } from '@/components/ui'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)
// Separate from `linkMissing` below: this flips only after the backend
// actually rejects the token (400), as opposed to the URL never
// carrying one in the first place. Both render the same invalid-link
// panel today (see linkMissing's comment).
const tokenRejected = ref(false)

// vue-router can return an array for a repeated query key -- only a
// single well-formed string counts as a token here.
const token = computed(() => {
  const raw = route.query.token
  return typeof raw === 'string' && raw.length > 0 ? raw : null
})

// A missing token means this URL was opened without going through the
// emailed link (typo, truncated share, bookmark of the bare route). It
// is a DIFFERENT case from a token the backend rejects (expired/used) --
// tracked separately so the copy can eventually differ, though today
// both render the same invalid-link panel.
const linkMissing = computed(() => token.value === null)

function goToLogin(): void {
  void safeNavigate(router.push({ name: 'login' }), '[PasswordResetConfirmView] to login')
}

function goToRequest(): void {
  void safeNavigate(
    router.push({ name: 'password-reset-request' }),
    '[PasswordResetConfirmView] to request',
  )
}

async function handleSubmit(): Promise<void> {
  error.value = ''

  if (!newPassword.value || !confirmPassword.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    error.value = t('auth.error.passwordMismatch')
    return
  }

  if (newPassword.value.length < 8) {
    error.value = t('auth.passwordReset.newPasswordHint')
    return
  }

  if (token.value === null) {
    // Defensive -- the submit button is not reachable in this state
    // (v-if gates the whole form on linkMissing), but a stale token
    // ref during a route transition is not impossible.
    return
  }

  loading.value = true
  try {
    await api.post('/api/v1/auth/password-reset/confirm', {
      token: token.value,
      new_password: newPassword.value,
    })
    done.value = true
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 400) {
      // Invalid / expired / already-used token -- switch to the
      // invalid-link panel instead of an inline error, since there is
      // nothing more the user can do here but request a fresh link.
      tokenRejected.value = true
    } else if (err instanceof ApiResponseError && err.status === 429) {
      error.value = t('auth.error.rateLimited')
    } else if (err instanceof ApiResponseError) {
      error.value = err.detail
    } else if (err instanceof ApiNetworkError) {
      error.value = t('auth.error.networkError')
    } else if (err instanceof ApiTimeoutError) {
      error.value = t('auth.error.timeout')
    } else {
      error.value = t('common.error')
    }
  } finally {
    loading.value = false
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

      <template v-if="linkMissing || tokenRejected">
        <h1 class="auth-title">
          {{ t('auth.passwordReset.invalidLinkTitle') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.passwordReset.invalidLinkText') }}
        </p>

        <div class="auth-form">
          <button class="btn btn-primary" @click="goToRequest">
            {{ t('auth.passwordReset.requestNewLink') }}
          </button>
        </div>
      </template>

      <template v-else-if="done">
        <div class="success-icon">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--primary)"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            width="64"
            height="64"
          >
            <path
              d="M22 13V6.5C22 5.4 21.1 4.5 20 4.5H4C2.9 4.5 2 5.4 2 6.5V17.5C2 18.6 2.9 19.5 4 19.5H13"
            />
            <polyline points="22 7 13.5 12.5 2 7" />
            <polyline points="16 19 18 21 22 17" />
          </svg>
        </div>

        <h1 class="auth-title">
          {{ t('auth.passwordReset.confirmSuccessTitle') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.passwordReset.confirmSuccessText') }}
        </p>

        <div class="auth-form">
          <button class="btn btn-primary" @click="goToLogin">
            {{ t('auth.passwordReset.signInBtn') }}
          </button>
        </div>
      </template>

      <template v-else>
        <h1 class="auth-title">
          {{ t('auth.passwordReset.confirmTitle') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.passwordReset.confirmSubtitle') }}
        </p>

        <div class="auth-form">
          <div class="form-group">
            <CInput
              v-model="newPassword"
              class="form-group__field"
              :label="t('auth.passwordReset.newPassword')"
              type="password"
              :placeholder="t('auth.passwordReset.newPassPlaceholder')"
              autocomplete="new-password"
              @keydown.enter="handleSubmit"
            />
            <div class="form-hint">
              {{ t('auth.passwordReset.newPasswordHint') }}
            </div>
          </div>

          <CInput
            v-model="confirmPassword"
            :label="t('auth.passwordReset.confirmPassword')"
            type="password"
            :placeholder="t('auth.passwordReset.confirmPassPlaceholder')"
            autocomplete="new-password"
            @keydown.enter="handleSubmit"
          />

          <div v-if="error" class="auth-error">
            {{ error }}
          </div>

          <button class="btn btn-primary" :disabled="loading" @click="handleSubmit">
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.passwordReset.confirmBtn') }}</span>
          </button>
        </div>
      </template>
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

.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-6) var(--space-5);
  overflow-y: auto;
}

.auth-brand {
  margin-bottom: var(--space-5);
  display: flex;
  justify-content: center;
}

.success-icon {
  display: flex;
  justify-content: center;
  margin-bottom: var(--space-5);
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
</style>
