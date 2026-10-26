<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { ShieldAlert, ShieldCheck } from '@/components/ui/icons'
// =============================================================================
// AIVIS.ONE Frontend -- SetPasswordView: the first password (H44)
// =============================================================================
//
// Owner's rule: an account whose e-mail is confirmed and that has no password
// (UserResponse.password_required, computed by the server) chooses one before
// it goes anywhere -- in the Mini App and in the cabinet alike. globalGuard
// holds such an account here; there is no "skip". The person reached this
// screen with a live session, so the e-mail is proven and nothing is asked
// again: a password and its confirmation, both with the reveal control
// (CInput type="password"), the same limits as everywhere (utils/passwordRule).
// The confirmation is this screen's check; the server takes the password only.
//
// After the password is set the answer IS the user (password_required false):
// the store takes it and the screen leaves for the next entry step, as the
// e-mail code screen does. A 409 means the server already sees no reason for
// this screen (a password set elsewhere, the e-mail changed): the user is
// re-read and the guard decides.
// =============================================================================

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { setPassword } from '@/api/users'
import { safeNavigate } from '@/composables/safeNavigate'
import { CInput } from '@/components/ui'
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import { postEntryTarget } from '@/utils/postAuthReturn'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from '@/utils/passwordRule'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')

const userEmail = computed(() => authStore.user?.email ?? '')

/** What is wrong with the two fields, or '' when they can be sent. */
function formProblem(): string {
  if (!password.value || !confirmPassword.value) return t('auth.error.fillAllFields')
  if (password.value !== confirmPassword.value) return t('auth.error.passwordMismatch')
  if (password.value.length < PASSWORD_MIN_LENGTH) {
    return t('auth.setPassword.hint', { min: PASSWORD_MIN_LENGTH })
  }
  if (password.value.length > PASSWORD_MAX_LENGTH) {
    return t('auth.setPassword.tooLong', { max: PASSWORD_MAX_LENGTH })
  }
  return ''
}

async function leave(): Promise<void> {
  await safeNavigate(
    router.replace(postEntryTarget(authStore.user?.onboarding_step)),
    '[SetPasswordView] after the password',
  )
}

async function handleSubmit(): Promise<void> {
  if (loading.value) return
  error.value = formProblem()
  if (error.value) return

  loading.value = true
  try {
    authStore.user = await setPassword(password.value)
    await leave()
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 409) {
      try {
        await authStore.fetchMe()
      } catch {
        // Even the re-read failed: the person stays here, with the
        // server's words.
        error.value = err.detail
        return
      }
      await leave()
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
    <div class="ds-auth__icon">
      <ShieldCheck />
    </div>

    <h1 class="ds-auth__title">
      {{ t('auth.setPassword.title') }}
    </h1>
    <p class="ds-auth__subtitle">
      {{ t('auth.setPassword.subtitle') }}
      <template v-if="userEmail">
        <br />
        <strong>{{ userEmail }}</strong>
      </template>
    </p>

    <div class="ds-auth__form">
      <CInput
        v-model="password"
        :label="t('auth.setPassword.password')"
        :hint="t('auth.setPassword.hint', { min: PASSWORD_MIN_LENGTH })"
        type="password"
        :placeholder="t('auth.setPassword.passPlaceholder', { min: PASSWORD_MIN_LENGTH })"
        autocomplete="new-password"
        @keydown.enter="handleSubmit"
      />

      <CInput
        v-model="confirmPassword"
        :label="t('auth.setPassword.confirmPassword')"
        type="password"
        :placeholder="t('auth.setPassword.confirmPlaceholder')"
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
        type="button"
        :aria-busy="loading || undefined"
        :disabled="loading"
        @click="handleSubmit"
      >
        <span v-if="loading" class="ds-button__spinner" aria-hidden="true" />
        <span>{{ t('auth.setPassword.btn') }}</span>
      </button>

      <div class="ds-auth__foot">
        <AuthLogoutLink />
      </div>
    </div>
  </AuthShell>
</template>
