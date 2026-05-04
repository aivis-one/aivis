<script setup lang="ts">
// Login screen — email + password form.
// Emits 'go-register' to switch to RegisterView in App.vue auth gate.
//
// Post-login navigation:
//   loginViaEmail succeeds → router.push('/') → root.beforeEnter
//   resolves the role-specific dashboard → globalGuard runs and either
//   passes through (onboarding_complete) or redirects to the next
//   onboarding step. Without this push, App.vue's reactive switch from
//   <LoginView> to <RouterView /> mounts RouterView at URL=/login and
//   renders LoginView again -- no navigation event fires, so the guard
//   is never invoked. Mirrors the pattern in VerifyEmailView and every
//   onboarding view; LoginView was the only handler missing the call.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import CbsLogo from '@/components/ui/CbsLogo.vue'

const emit = defineEmits<{
  'go-register': []
}>()

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')

async function handleLogin(): Promise<void> {
  error.value = ''

  if (!email.value || !password.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  try {
    await authStore.loginViaEmail(email.value, password.value)
    // Trigger a navigation event so globalGuard fires; it routes to
    // the role's dashboard or to the correct onboarding step.
    await router.push('/')
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
      <CbsLogo :height="28" />
    </header>

    <div class="auth-content">
      <div class="auth-icon">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--primary)"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
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
          <button type="button" class="btn-link" @click="emit('go-register')">
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
  background: var(--bg);
  display: flex;
  flex-direction: column;
}

.auth-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--bg);
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
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

.auth-icon {
  margin-bottom: 24px;
}

.auth-icon svg {
  width: 48px;
  height: 48px;
}

.auth-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
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
  color: var(--text);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius-md, 8px);
  background: var(--bg);
  color: var(--text);
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
  background: var(--error-dim);
  border: 1px solid var(--error);
  border-radius: var(--radius-md, 8px);
  color: var(--error);
  font-size: 13px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.btn {
  width: 100%;
  padding: 14px;
  border-radius: var(--radius-md, 8px);
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
  background: var(--accent);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
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
