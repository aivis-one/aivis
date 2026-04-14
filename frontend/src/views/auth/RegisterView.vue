<script setup lang="ts">
// Register screen — email + password + confirmation.
// Reads referral code from sessionStorage on submit.
// Emits 'go-login' to switch back to LoginView in App.vue auth gate.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import CbsLogo from '@/components/ui/CbsLogo.vue'

const emit = defineEmits<{
  'go-login': []
}>()

const { t } = useI18n()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const showConfirmPassword = ref(false)
const error = ref('')

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

  const referralCode = sessionStorage.getItem('cbs_referral_code')

  try {
    await authStore.registerViaEmail(email.value, password.value, referralCode)
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
      <CbsLogo :height="28" />
      <button type="button" class="btn-link btn-back" @click="emit('go-login')">
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
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.register.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.register.subtitle') }}</p>

      <div class="auth-form">
        <div class="form-group">
          <label class="form-label">{{ t('auth.register.email') }}</label>
          <input
            v-model="email"
            type="email"
            class="form-input"
            placeholder="name@example.com"
            autocomplete="email"
            @keydown.enter="handleRegister"
          />
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('auth.register.password') }}</label>
          <div class="input-wrapper">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="form-input"
              :placeholder="t('auth.register.passPlaceholder')"
              autocomplete="new-password"
              @keydown.enter="handleRegister"
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
          <div class="form-hint">{{ t('auth.register.passwordHint') }}</div>
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('auth.register.confirmPassword') }}</label>
          <div class="input-wrapper">
            <input
              v-model="confirmPassword"
              :type="showConfirmPassword ? 'text' : 'password'"
              class="form-input"
              :placeholder="t('auth.register.confirmPlaceholder')"
              autocomplete="new-password"
              @keydown.enter="handleRegister"
            />
            <button
              type="button"
              class="toggle-password"
              @click="showConfirmPassword = !showConfirmPassword"
            >
              <svg
                v-if="!showConfirmPassword"
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
          @click="handleRegister"
        >
          <span v-if="authStore.loading" class="btn-spinner" />
          <span v-else>{{ t('auth.register.btn') }}</span>
        </button>

        <div class="auth-footer">
          <span class="auth-footer-text">{{ t('auth.register.hasAccount') }}</span>
          <button type="button" class="btn-link" @click="emit('go-login')">
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

.btn-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
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
  padding: 32px 24px;
  overflow-y: auto;
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

.form-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
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
