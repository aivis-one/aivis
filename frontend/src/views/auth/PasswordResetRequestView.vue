<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { MailCheck, ShieldAlert } from '@/components/ui/icons'
// =============================================================================
// AIVIS.ONE Frontend -- PasswordResetRequestView
// =============================================================================
//
// Step 1 of account recovery: email in, generic "check your email" out.
// POST /api/v1/auth/password-reset/request { email } -> always 200 with
// the SAME fixed body (backend anti-enumeration, auth/router.py
// PasswordResetRequestResponse) whether or not the email matched a real
// account.
//
// This view mirrors that discipline on the frontend: a successful
// response of ANY shape flips to the success panel unconditionally.
// There is no "email not found" error state to accidentally add here --
// doing so would leak exactly what the backend refuses to. The only
// error states shown are genuine client-side problems (network,
// timeout, rate limit, malformed email) that say nothing about whether
// the account exists.
//
// Unauthenticated route (meta.public, see router/index.ts) -- this is
// the entry point for someone who is LOCKED OUT and has no session.
// =============================================================================

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import { CInput } from '@/components/ui'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const email = ref('')
const error = ref('')
const loading = ref(false)
const submitted = ref(false)

function goToLogin(): void {
  void safeNavigate(
    router.push({ name: 'login', query: route.query }),
    '[PasswordResetRequestView] to login',
  )
}

async function handleSubmit(): Promise<void> {
  error.value = ''

  if (!email.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  loading.value = true
  try {
    // Response body is deliberately not read for branching -- ANY 2xx
    // here means "show the generic success panel", full stop. See file
    // header: reading/branching on the body would defeat the backend's
    // anti-enumeration guarantee for no benefit (the body never varies).
    await api.post('/api/v1/auth/password-reset/request', { email: email.value })
    submitted.value = true
  } catch (err) {
    if (err instanceof ApiResponseError) {
      if (err.status === 429) {
        error.value = t('auth.error.rateLimited')
      } else if (err.status === 422) {
        // Malformed email -- schema validation, not an enumeration
        // signal (it fires before the backend ever looks the email up).
        error.value = err.detail
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
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell>
    <template v-if="!submitted">
      <h1 class="ds-auth__title">
        {{ t('auth.passwordReset.requestTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.passwordReset.requestSubtitle') }}
      </p>

      <div class="ds-auth__form">
        <CInput
          v-model="email"
          :label="t('auth.passwordReset.email')"
          type="email"
          placeholder="name@example.com"
          autocomplete="email"
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
          <span>{{ t('auth.passwordReset.requestBtn') }}</span>
        </button>

        <div class="ds-auth__foot">
          <button
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="goToLogin"
          >
            {{ t('auth.passwordReset.backToLogin') }}
          </button>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="ds-auth__icon">
        <MailCheck />
      </div>

      <h1 class="ds-auth__title">
        {{ t('auth.passwordReset.requestSuccessTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('auth.passwordReset.requestSuccessText') }}
      </p>

      <div class="ds-auth__form">
        <button class="ds-button ds-button--primary ds-button--block" @click="goToLogin">
          {{ t('auth.passwordReset.backToLogin') }}
        </button>
      </div>
    </template>
  </AuthShell>
</template>
