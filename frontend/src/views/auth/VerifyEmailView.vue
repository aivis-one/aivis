<script setup lang="ts">
// Email verification — 6 individual digit inputs with auto-focus.
// POST /api/v1/auth/verify-email { code }
// POST /api/v1/auth/verify-email/resend → 204
// After success: fetchMe() → router.push('/') → guard redirects.

import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import type { UserResponse } from '@/api/types'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const CODE_LENGTH = 6
const RESEND_COOLDOWN = 60

const digits = ref<string[]>(Array(CODE_LENGTH).fill(''))
const inputRefs = ref<HTMLInputElement[]>([])
const loading = ref(false)
const error = ref('')
const resendCooldown = ref(0)
let cooldownTimer: ReturnType<typeof setInterval> | null = null

const code = computed(() => digits.value.join(''))
const isCodeComplete = computed(() => code.value.length === CODE_LENGTH)
const userEmail = computed(() => authStore.user?.email ?? '')

// Start cooldown on mount (code was just sent during registration).
onMounted(() => {
  startCooldown()
  nextTick(() => inputRefs.value[0]?.focus())
})

function setInputRef(el: unknown, index: number): void {
  if (el instanceof HTMLInputElement) {
    inputRefs.value[index] = el
  }
}

function handleInput(index: number, event: Event): void {
  const target = event.target as HTMLInputElement
  const value = target.value.replace(/\D/g, '')

  // Handle paste of full code.
  if (value.length > 1) {
    const chars = value.slice(0, CODE_LENGTH).split('')
    chars.forEach((ch, i) => {
      if (i < CODE_LENGTH) digits.value[i] = ch
    })
    const focusIndex = Math.min(chars.length, CODE_LENGTH - 1)
    inputRefs.value[focusIndex]?.focus()
    return
  }

  digits.value[index] = value.slice(0, 1)

  // Auto-focus next input.
  if (value && index < CODE_LENGTH - 1) {
    inputRefs.value[index + 1]?.focus()
  }
}

function handleKeydown(index: number, event: KeyboardEvent): void {
  // Backspace: clear current or move to previous.
  if (event.key === 'Backspace') {
    if (!digits.value[index] && index > 0) {
      digits.value[index - 1] = ''
      inputRefs.value[index - 1]?.focus()
      event.preventDefault()
    }
  }
}

async function handleVerify(): Promise<void> {
  if (!isCodeComplete.value) return
  error.value = ''
  loading.value = true

  try {
    await api.post<UserResponse>('/api/v1/auth/verify-email', {
      code: code.value,
    })
    await authStore.fetchMe()
    // Navigate to root — guard will redirect to the next onboarding step.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer verify-error
    // catch and surface as a generic-error toast after successful verify.
    await safeNavigate(router.push('/'), '[VerifyEmailView] post-verify to home')
  } catch (err) {
    if (err instanceof ApiResponseError) {
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

function startCooldown(): void {
  resendCooldown.value = RESEND_COOLDOWN
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = setInterval(() => {
    resendCooldown.value--
    if (resendCooldown.value <= 0 && cooldownTimer) {
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

async function handleResend(): Promise<void> {
  if (resendCooldown.value > 0) return
  error.value = ''

  try {
    await api.post<void>('/api/v1/auth/verify-email/resend')
    startCooldown()
    // Clear inputs for new code.
    digits.value = Array(CODE_LENGTH).fill('')
    nextTick(() => inputRefs.value[0]?.focus())
  } catch (err) {
    if (err instanceof ApiResponseError) {
      error.value = err.detail
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
      <CAppControls />
    </header>

    <div class="auth-content">
      <div class="verify-icon">
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
        {{ t('auth.verify.title') }}
      </h1>
      <p class="auth-subtitle">
        {{ t('auth.verify.subtitle') }}
        <br />
        <strong class="verify-email">{{ userEmail }}</strong>
      </p>

      <div class="code-inputs">
        <input
          v-for="(_, index) in CODE_LENGTH"
          :key="index"
          :ref="(el) => setInputRef(el, index)"
          type="text"
          inputmode="numeric"
          maxlength="6"
          class="code-input"
          :aria-label="t('common.codeDigit', { n: index + 1, total: CODE_LENGTH })"
          :value="digits[index]"
          @input="handleInput(index, $event)"
          @keydown="handleKeydown(index, $event)"
          @keydown.enter="handleVerify"
        />
      </div>

      <div v-if="error" class="auth-error">
        {{ error }}
      </div>

      <div class="auth-form">
        <button
          class="btn btn-primary"
          type="button"
          :disabled="!isCodeComplete || loading"
          @click="handleVerify"
        >
          <span v-if="loading" class="btn-spinner" />
          <span v-else>{{ t('auth.verify.btn') }}</span>
        </button>

        <div class="resend-section">
          <span class="resend-label">{{ t('auth.verify.noCode') }}</span>
          <button v-if="resendCooldown <= 0" type="button" class="btn-link" @click="handleResend">
            {{ t('auth.verify.resend') }}
          </button>
          <span v-else class="resend-timer">
            {{ t('auth.verify.resendIn', { seconds: resendCooldown }) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
}
.auth-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) var(--space-5);
}
.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
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
.auth-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  text-align: center;
  margin-bottom: var(--space-4);
  max-width: var(--maxw-form);
}

.verify-icon {
  display: flex;
  justify-content: center;
  margin-bottom: var(--space-5);
}
.verify-email {
  color: var(--text-primary);
}

.code-inputs {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}
.code-input {
  width: var(--size-3xl);
  height: var(--size-4xl);
  text-align: center;
  font-size: var(--fs-h3);
  font-weight: 700;
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-page);
  color: var(--text-primary);
  font-family: inherit;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}
.code-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.btn {
  width: 100%;
}
.btn-primary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 600;
  font-size: var(--fs-sm);
  font-family: inherit;
  border: none;
  cursor: pointer;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-spinner {
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  width: var(--size-2xs);
  height: var(--size-2xs);
  border: 2px solid currentColor;
  opacity: 0.35;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.resend-section {
  text-align: center;
  margin-top: var(--space-4-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
}
.resend-label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.resend-timer {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}
.btn-link {
  position: relative;
  font-size: var(--fs-sm);
  color: var(--primary);
  font-weight: 600;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
}

/* A5: the PAINTED box stays this size on purpose; the HIT AREA is expanded past
   it with a centred overlay. Growing the box itself would move the text this
   control sits inside or beside. max() so an already-large box never shrinks. */
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
</style>
