<script setup lang="ts">
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
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
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
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <CAppControls />
    </header>

    <div class="auth-content">
      <div class="auth-brand">
        <AivisLogo :height="64" />
      </div>

      <template v-if="!submitted">
        <h1 class="auth-title">
          {{ t('auth.passwordReset.requestTitle') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.passwordReset.requestSubtitle') }}
        </p>

        <div class="auth-form">
          <CInput
            v-model="email"
            :label="t('auth.passwordReset.email')"
            type="email"
            placeholder="name@example.com"
            autocomplete="email"
            @keydown.enter="handleSubmit"
          />

          <div v-if="error" class="auth-error">
            {{ error }}
          </div>

          <button class="btn btn-primary" :disabled="loading" @click="handleSubmit">
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.passwordReset.requestBtn') }}</span>
          </button>

          <div class="auth-footer">
            <button type="button" class="btn-link" @click="goToLogin">
              {{ t('auth.passwordReset.backToLogin') }}
            </button>
          </div>
        </div>
      </template>

      <template v-else>
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
          {{ t('auth.passwordReset.requestSuccessTitle') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.passwordReset.requestSuccessText') }}
        </p>

        <div class="auth-form">
          <button class="btn btn-primary" @click="goToLogin">
            {{ t('auth.passwordReset.backToLogin') }}
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

.btn-link {
  position: relative;
  background: none;
  border: none;
  color: var(--primary);
  font-weight: 600;
  font-size: var(--fs-sm);
  cursor: pointer;
  padding: 0;
}

.btn-link::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}

.btn-link:hover {
  text-decoration: underline;
}

.auth-footer {
  text-align: center;
  margin-top: var(--space-5);
}
</style>
