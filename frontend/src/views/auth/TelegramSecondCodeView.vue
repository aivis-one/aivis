<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
// Telegram Mini App: the second code of a returning person whose account has
// two-factor on. The Telegram identity checked out and the server issued a
// pending token (kept in the auth store, memory only); no session exists until
// a live authenticator code, or an unused backup code, completes the sign-in
// through authStore.completeMfaLogin. The step follows the code-entry step of
// LoginView.
//
// The pending token is consumed on any outcome, so a wrong code ends this
// attempt: the person opens the app again for a fresh one.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import { CAlert, CInput } from '@/components/ui'
import { postEntryTarget } from '@/utils/postAuthReturn'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const mfaCode = ref('')
const useBackupCode = ref(false)
const error = ref('')
// The pending token was used up by a wrong code: nothing can continue here.
const ended = ref(false)

function toggleBackupCode(): void {
  useBackupCode.value = !useBackupCode.value
  mfaCode.value = ''
  error.value = ''
}

async function submitMfaCode(): Promise<void> {
  error.value = ''

  const token = authStore.telegramMfaToken
  if (!mfaCode.value.trim() || !token) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  try {
    await authStore.completeMfaLogin(token, mfaCode.value.trim())
    // safeNavigate is no-throw by contract -- a benign NavigationFailure must
    // not surface as an error after a successful sign-in.
    await safeNavigate(
      router.push(postEntryTarget(authStore.user?.onboarding_step)),
      '[TelegramSecondCodeView] post-auth to home',
    )
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 400) {
        // The pending token is consumed on ANY outcome (see api/auth.ts's
        // verifyTwoFactorLogin): a wrong code kills the whole token.
        authStore.clearTelegramEntry()
        ended.value = true
        return
      }
      error.value = err.status === 429 ? t('auth.error.rateLimited') : err.detail
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
  <AuthShell>
    <!-- The wrong code used up the pending token -->
    <template v-if="ended">
      <h1 class="ds-auth__title">
        {{ t('auth.telegramEntry.expiredTitle') }}
      </h1>
      <CAlert tone="danger">{{ t('auth.telegramEntry.secondCodeEnded') }}</CAlert>
    </template>

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

        <div class="ds-auth__foot">
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

        <CAlert v-if="error" tone="danger">{{ error }}</CAlert>

        <button
          class="ds-button ds-button--primary ds-button--block"
          :aria-busy="authStore.loading || undefined"
          :disabled="authStore.loading"
          @click="submitMfaCode"
        >
          <span v-if="authStore.loading" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.login.mfa.verifyBtn') }}</span>
        </button>
      </div>
    </template>
  </AuthShell>
</template>
