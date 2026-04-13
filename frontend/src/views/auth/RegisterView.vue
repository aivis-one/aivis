<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Eye, EyeOff } from 'lucide-vue-next'
import CButton from '@/components/ui/CButton.vue'
import CInput from '@/components/ui/CInput.vue'
import CbsLogo from '@/components/ui/CbsLogo.vue'
import { useForm } from '@/composables/useForm'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const showPassword = ref(false)
const showConfirmPassword = ref(false)

const { values, errors, submitting, submitError, handleSubmit } = useForm({
  initialValues: {
    email: '',
    password: '',
    passwordConfirmation: '',
    terms: false,
  },
  validate(v) {
    const errs: Record<string, string> = {}
    if (!v.email) errs.email = t('validation.required')
    if (!v.password) errs.password = t('validation.required')
    if (v.password && (v.password as string).length < 8) {
      errs.password = t('validation.minLength', { min: 8 })
    }
    if (v.password !== v.passwordConfirmation) {
      errs.passwordConfirmation = t('validation.passwordMismatch')
    }
    if (!v.terms) errs.terms = t('validation.termsRequired')
    return errs
  },
  async onSubmit(v) {
    await authStore.register(v.email as string, v.password as string)
    router.push('/auth/verify')
  },
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-container">
      <button class="back-button" @click="router.push('/auth/login')">
        <ArrowLeft :size="20" />
        {{ t('auth.back') }}
      </button>

      <CbsLogo />

      <div class="auth-header">
        <h1 class="auth-title">
          {{ t('auth.register.title') }}
        </h1>
        <p class="auth-subtitle">
          {{ t('auth.register.subtitle') }}
        </p>
      </div>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <CInput
          v-model="values.email"
          type="email"
          :label="t('auth.register.email')"
          :placeholder="t('auth.register.email')"
          :error="errors.email"
        />

        <div class="password-field">
          <CInput
            v-model="values.password"
            :type="showPassword ? 'text' : 'password'"
            :label="t('auth.register.password')"
            :placeholder="t('auth.register.passPlaceholder')"
            :error="errors.password"
          />
          <button type="button" class="password-toggle" @click="showPassword = !showPassword">
            <component :is="showPassword ? EyeOff : Eye" :size="20" />
          </button>
        </div>
        <p class="field-hint">
          {{ t('auth.register.passwordHint') }}
        </p>

        <div class="password-field">
          <CInput
            v-model="values.passwordConfirmation"
            :type="showConfirmPassword ? 'text' : 'password'"
            :label="t('auth.register.confirmPassword')"
            :placeholder="t('auth.register.confirmPlaceholder')"
            :error="errors.passwordConfirmation"
          />
          <button
            type="button"
            class="password-toggle"
            @click="showConfirmPassword = !showConfirmPassword"
          >
            <component :is="showConfirmPassword ? EyeOff : Eye" :size="20" />
          </button>
        </div>

        <label class="terms-checkbox">
          <input v-model="values.terms" type="checkbox" />
          <span>{{ t('auth.register.terms') }}</span>
        </label>
        <p v-if="errors.terms" class="field-error">
          {{ errors.terms }}
        </p>

        <CButton type="submit" variant="primary" :loading="submitting">
          {{ t('auth.register.btn') }}
        </CButton>

        <p v-if="submitError" class="auth-error">
          {{ submitError }}
        </p>
      </form>

      <p class="auth-footer">
        {{ t('auth.register.hasAccount') }}
        <router-link to="/auth/login">
          {{ t('auth.register.loginLink') }}
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

.back-button {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-base);
  cursor: pointer;
  padding: 0;
  align-self: flex-start;
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

.field-hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-top: calc(-1 * var(--space-sm));
}

.terms-checkbox {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  font-size: var(--text-caption);
  color: var(--text-secondary);
  cursor: pointer;
}

.terms-checkbox input {
  margin-top: 2px;
  accent-color: var(--primary);
}

.field-error {
  font-size: var(--text-sm);
  color: var(--error);
  margin-top: calc(-1 * var(--space-sm));
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
