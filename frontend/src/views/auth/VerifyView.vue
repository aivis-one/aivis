<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CButton from '@/components/ui/CButton.vue'
import CbsLogo from '@/components/ui/CbsLogo.vue'
import { useAuth } from '@/composables/useAuth'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuth()
const authStore = useAuthStore()

const codeDigits = reactive(['', '', '', '', '', ''])
const codeRefs = ref<HTMLInputElement[]>([])
const isCodeComplete = computed(() => codeDigits.every((d) => d !== ''))
const verifying = ref(false)
const verifyError = ref<string | null>(null)

function onCodeInput(index: number) {
  if (codeDigits[index] && index < 5) {
    codeRefs.value[index + 1]?.focus()
  }
}

function onCodeDelete(index: number) {
  if (!codeDigits[index] && index > 0) {
    codeRefs.value[index - 1]?.focus()
  }
}

function onCodePaste(event: ClipboardEvent) {
  const text = event.clipboardData?.getData('text') || ''
  const digits = text.replace(/\D/g, '').slice(0, 6)
  for (let i = 0; i < 6; i++) {
    codeDigits[i] = digits[i] || ''
  }
  if (digits.length > 0) {
    codeRefs.value[Math.min(digits.length, 5)]?.focus()
  }
  event.preventDefault()
}

async function handleVerify() {
  if (!isCodeComplete.value) return
  verifying.value = true
  verifyError.value = null
  try {
    // Verification endpoint will be implemented when backend supports it
    // For now, redirect to dashboard after "verification"
    auth.redirectByRole()
  } catch (e: unknown) {
    verifyError.value = e instanceof Error ? e.message : t('common.error')
  } finally {
    verifying.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-container">
      <CbsLogo />

      <div class="auth-header">
        <h1 class="auth-title">
          {{ t('auth.verify.title') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.verify.subtitle') }}
        </p>
      </div>

      <div class="code-inputs">
        <input
          v-for="(_, i) in codeDigits"
          :key="i"
          ref="codeRefs"
          v-model="codeDigits[i]"
          type="text"
          inputmode="numeric"
          maxlength="1"
          class="code-input"
          @input="onCodeInput(i)"
          @keydown.delete="onCodeDelete(i)"
          @paste="onCodePaste"
        />
      </div>

      <CButton
        variant="primary"
        :loading="verifying"
        :disabled="!isCodeComplete"
        @click="handleVerify"
      >
        {{ t('auth.verify.btn') }}
      </CButton>

      <p v-if="verifyError || authStore.error" class="auth-error">
        {{ verifyError || authStore.error }}
      </p>

      <p class="auth-footer">
        {{ t('auth.verify.noCode') }}
        <button class="resend-btn" :disabled="authStore.loading" @click="handleVerify">
          {{ t('auth.verify.resend') }}
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-md);
  background: var(--bg);
}

.auth-container {
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.auth-header {
  text-align: center;
}

.auth-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.auth-subtitle {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin: var(--space-xs) 0 0;
}

.code-inputs {
  display: flex;
  gap: var(--space-sm);
  justify-content: center;
}

.code-input {
  width: 48px;
  height: 56px;
  text-align: center;
  font-size: var(--text-2xl);
  font-weight: 700;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  outline: none;
  transition: border-color 0.2s;
}

.code-input:focus {
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.auth-footer {
  text-align: center;
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.resend-btn {
  background: none;
  border: none;
  color: var(--primary);
  font-weight: 600;
  cursor: pointer;
  font-size: inherit;
  font-family: var(--font);
  padding: 0;
}

.resend-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.auth-error {
  color: var(--error);
  font-size: var(--text-caption);
  text-align: center;
}
</style>
