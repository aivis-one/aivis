<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { MailCheck, ShieldAlert } from '@/components/ui/icons'
// =============================================================================
// AIVIS.ONE Frontend -- PasswordResetConfirmView
// =============================================================================
//
// Step 2 of account recovery: reads `?token=` from the URL (the link
// _request_password_reset_email built -- see auth/service.py --
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
import { CInput } from '@/components/ui'
import { PASSWORD_MIN_LENGTH } from '@/utils/passwordRule'

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

  if (newPassword.value.length < PASSWORD_MIN_LENGTH) {
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
  <AuthShell>
    <template v-if="linkMissing || tokenRejected">
      <h1 class="ds-auth__title">
        {{ t('auth.passwordReset.invalidLinkTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.passwordReset.invalidLinkText') }}
      </p>

      <div class="ds-auth__form">
        <button class="ds-button ds-button--primary ds-button--block" @click="goToRequest">
          {{ t('auth.passwordReset.requestNewLink') }}
        </button>
      </div>
    </template>

    <template v-else-if="done">
      <div class="ds-auth__icon">
        <MailCheck />
      </div>

      <h1 class="ds-auth__title">
        {{ t('auth.passwordReset.confirmSuccessTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.passwordReset.confirmSuccessText') }}
      </p>

      <div class="ds-auth__form">
        <button class="ds-button ds-button--primary ds-button--block" @click="goToLogin">
          {{ t('auth.passwordReset.signInBtn') }}
        </button>
      </div>
    </template>

    <template v-else>
      <h1 class="ds-auth__title">
        {{ t('auth.passwordReset.confirmTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.passwordReset.confirmSubtitle') }}
      </p>

      <div class="ds-auth__form">
        <CInput
          v-model="newPassword"
          :label="t('auth.passwordReset.newPassword')"
          :hint="t('auth.passwordReset.newPasswordHint')"
          type="password"
          :placeholder="t('auth.passwordReset.newPassPlaceholder')"
          autocomplete="new-password"
          @keydown.enter="handleSubmit"
        />

        <CInput
          v-model="confirmPassword"
          :label="t('auth.passwordReset.confirmPassword')"
          type="password"
          :placeholder="t('auth.passwordReset.confirmPassPlaceholder')"
          autocomplete="new-password"
          @keydown.enter="handleSubmit"
        />

        <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ error }}</p>
          </div>
        </div>

        <button
          class="ds-button ds-button--primary ds-button--block"
          :aria-busy="loading || undefined"
          :disabled="loading"
          @click="handleSubmit"
        >
          <span v-if="loading" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.passwordReset.confirmBtn') }}</span>
        </button>
      </div>
    </template>
  </AuthShell>
</template>
