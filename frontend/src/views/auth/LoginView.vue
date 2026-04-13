<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, EyeOff } from 'lucide-vue-next'
import CButton from '@/components/ui/CButton.vue'
import CInput from '@/components/ui/CInput.vue'
import CbsLogo from '@/components/ui/CbsLogo.vue'
import { useForm } from '@/composables/useForm'
import { useAuth } from '@/composables/useAuth'
import { useAuthStore } from '@/stores/auth'
import { platform } from '@/platform'

const { t } = useI18n()
const auth = useAuth()
const authStore = useAuthStore()

const showPassword = ref(false)
const showTelegramAuth = platform.type === 'telegram'

const { values, errors, submitting, submitError, handleSubmit } = useForm({
  initialValues: { email: '', password: '' },
  validate(v) {
    const errs: Record<string, string> = {}
    if (!v.email) errs.email = t('validation.required')
    if (!v.password) errs.password = t('validation.required')
    return errs
  },
  async onSubmit(v) {
    await auth.login(v.email as string, v.password as string)
  },
})

async function handleTelegramAuth() {
  try {
    await authStore.telegramAuth()
    auth.redirectByRole()
  } catch {
    // Error is set in store
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-container">
      <CbsLogo />

      <div class="auth-header">
        <h1 class="auth-title">
          {{ t('auth.login.title') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.login.subtitle') }}
        </p>
      </div>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <CInput
          v-model="values.email"
          type="email"
          :label="t('auth.login.email')"
          :placeholder="t('auth.login.email')"
          :error="errors.email"
        />

        <div class="password-field">
          <CInput
            v-model="values.password"
            :type="showPassword ? 'text' : 'password'"
            :label="t('auth.login.password')"
            :placeholder="t('auth.login.passPlaceholder')"
            :error="errors.password"
          />
          <button type="button" class="password-toggle" @click="showPassword = !showPassword">
            <component :is="showPassword ? EyeOff : Eye" :size="20" />
          </button>
        </div>

        <CButton type="submit" variant="primary" :loading="submitting">
          {{ t('auth.login.btn') }}
        </CButton>

        <p v-if="submitError" class="auth-error">
          {{ submitError }}
        </p>
      </form>

      <div class="auth-divider">
        <span>{{ t('auth.login.or') }}</span>
      </div>

      <CButton v-if="showTelegramAuth" variant="secondary" @click="handleTelegramAuth">
        {{ t('auth.login.telegram') }}
      </CButton>

      <p class="auth-footer">
        {{ t('auth.login.noAccount') }}
        <router-link to="/auth/register">
          {{ t('auth.login.createAccount') }}
        </router-link>
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

.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.password-field {
  position: relative;
}

.password-toggle {
  position: absolute;
  inset-inline-end: var(--space-sm);
  bottom: var(--space-sm);
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: var(--space-xs);
  display: flex;
  align-items: center;
}

.auth-divider {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.auth-divider span {
  font-size: var(--text-base);
  color: var(--text-tertiary);
}

.auth-footer {
  text-align: center;
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.auth-footer a {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}

.auth-error {
  color: var(--error);
  font-size: var(--text-caption);
  text-align: center;
}
</style>
