<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import { MailCheck, ShieldAlert } from '@/components/ui/icons'
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
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import { postEntryTarget } from '@/utils/postAuthReturn'

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
    await safeNavigate(
      router.push(postEntryTarget(authStore.user?.onboarding_step)),
      '[VerifyEmailView] post-verify to home',
    )
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
  <AuthShell>
    <div class="ds-auth__icon">
      <MailCheck />
    </div>

    <h1 class="ds-auth__title">
      {{ t('auth.verify.title') }}
    </h1>
    <p class="ds-auth__subtitle">
      {{ t('auth.verify.subtitle') }}
      <br />
      <strong>{{ userEmail }}</strong>
    </p>

    <div
      class="ds-field ds-otp"
      role="group"
      aria-labelledby="verify-code-label"
      :aria-busy="loading || undefined"
    >
      <span id="verify-code-label" class="ds-field__label">{{ t('common.codeGroup') }}</span>
      <div class="ds-otp__cells">
        <input
          v-for="(_, index) in CODE_LENGTH"
          :key="index"
          :ref="(el) => setInputRef(el, index)"
          type="text"
          inputmode="numeric"
          maxlength="6"
          class="ds-otp__cell"
          :data-filled="!!digits[index]"
          :aria-invalid="error ? 'true' : undefined"
          :autocomplete="index === 0 ? 'one-time-code' : 'off'"
          :aria-label="t('common.codeDigit', { n: index + 1, total: CODE_LENGTH })"
          :value="digits[index]"
          @input="handleInput(index, $event)"
          @keydown="handleKeydown(index, $event)"
          @keydown.enter="handleVerify"
        />
      </div>
    </div>

    <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
      <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ error }}</p>
      </div>
    </div>

    <div class="ds-auth__form">
      <button
        class="ds-button ds-button--primary ds-button--block"
        :aria-busy="loading || undefined"
        type="button"
        :disabled="!isCodeComplete || loading"
        @click="handleVerify"
      >
        <span v-if="loading" class="ds-button__spinner" aria-hidden="true" />
        <span>{{ t('auth.verify.btn') }}</span>
      </button>

      <div class="ds-auth__foot">
        <span>{{ t('auth.verify.noCode') }}</span>
        <button
          v-if="resendCooldown <= 0"
          type="button"
          class="ds-button ds-button--ghost"
          data-size="sm"
          @click="handleResend"
        >
          {{ t('auth.verify.resend') }}
        </button>
        <span v-else>
          {{ t('auth.verify.resendIn', { seconds: resendCooldown }) }}
        </span>
      </div>

      <div class="entry-logout">
        <AuthLogoutLink />
      </div>
    </div>
  </AuthShell>
</template>

<style scoped>
.entry-logout {
  display: flex;
  justify-content: center;
  margin-block-start: var(--space-5);
}
</style>
