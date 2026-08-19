<script setup lang="ts">
// Profile setup — first name, last name, phone, country, language.
// PATCH /api/v1/users/me { profile: {...}, language }
// After success: fetchMe() → router.push('/') → guard redirects.

import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import type { UserResponse } from '@/api/types'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CInput, CSelect } from '@/components/ui'

const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()

const firstName = ref('')
const lastName = ref('')
const phone = ref('')
const country = ref('')
const language = ref(locale.value)
const loading = ref(false)
const error = ref('')

const countries = [
  { value: 'DE', label: 'Deutschland' },
  { value: 'CH', label: 'Schweiz' },
  { value: 'AT', label: 'Österreich' },
  { value: 'RU', label: 'Россия' },
  { value: 'OTHER', label: 'Other' },
]

// Derived from SUPPORTED_LOCALES so adding a new language requires
// only one change (the config file + its JSON) and the picker picks
// it up automatically.
const languages = SUPPORTED_LOCALES.map((l) => ({
  value: l.code,
  label: l.label,
}))

// Pre-fill from existing profile if available (e.g. Telegram user).
onMounted(() => {
  const profile = authStore.user?.profile
  if (profile && typeof profile === 'object') {
    firstName.value = (profile.first_name as string) ?? ''
    lastName.value = (profile.last_name as string) ?? ''
    phone.value = (profile.phone as string) ?? ''
    country.value = (profile.country as string) ?? ''
  }
  language.value = authStore.user?.language ?? locale.value
})

async function handleSubmit(): Promise<void> {
  error.value = ''

  if (!firstName.value.trim() || !lastName.value.trim() || !country.value) {
    error.value = t('auth.error.fillAllFields')
    return
  }

  loading.value = true

  try {
    await api.patch<UserResponse>('/api/v1/users/me', {
      profile: {
        first_name: firstName.value.trim(),
        last_name: lastName.value.trim(),
        phone: phone.value.trim() || undefined,
        country: country.value,
      },
      language: language.value,
    })
    await authStore.fetchMe()
    // Navigate to root — guard will redirect to the next onboarding step.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer profile-error
    // catch and surface as a generic-error toast after successful submission.
    await safeNavigate(router.push('/'), '[OnboardingProfileView] post-submit to home')
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

</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <CAppControls />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.profile.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.profile.subtitle') }}</p>

      <div class="auth-form">
        <div class="form-row">
          <CInput
            v-model="firstName"
            class="form-row__col"
            :label="t('auth.profile.firstName')"
            type="text"
            autocomplete="given-name"
            @keydown.enter="handleSubmit"
          />
          <CInput
            v-model="lastName"
            class="form-row__col"
            :label="t('auth.profile.lastName')"
            type="text"
            autocomplete="family-name"
            @keydown.enter="handleSubmit"
          />
        </div>

        <CInput
          v-model="phone"
          :label="t('auth.profile.phone')"
          type="tel"
          placeholder="+49 XXX XXXXXXXX"
          autocomplete="tel"
          @keydown.enter="handleSubmit"
        />

        <CSelect
          v-model="country"
          :label="t('auth.profile.country')"
          :options="countries"
          placeholder="—"
        />

        <CSelect
          v-model="language"
          :label="t('auth.profile.language')"
          :options="languages"
        />

        <div v-if="error" class="auth-error">{{ error }}</div>

        <button
          class="btn btn-primary"
          type="button"
          :disabled="loading"
          @click="handleSubmit"
        >
          <span v-if="loading" class="btn-spinner" />
          <span v-else>{{ t('auth.profile.btn') }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex; flex-direction: column;
  min-height: 100vh; min-height: 100dvh;
  background: var(--bg-page);
}
.auth-header {
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-4) var(--space-5);
}
.auth-content {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: var(--space-5); overflow-y: auto;
}
.auth-title {
  font-size: var(--fs-h3); font-weight: 700; color: var(--text-primary);
  margin-bottom: var(--space-2); text-align: center;
}
.auth-subtitle {
  font-size: var(--fs-sm); color: var(--text-secondary);
  margin-bottom: var(--space-6); text-align: center; line-height: 1.5;
}
.auth-form { width: 100%; max-width: var(--maxw-form); }
.auth-error {
  font-size: var(--fs-xs); color: var(--danger); text-align: center;
  margin-bottom: var(--space-4);
}

.form-row {
  display: flex; gap: var(--space-3);
}
/* The two name fields share the row equally. This targeted `.form-group`,
   the class the raw markup carried; the CInput root is `.c-input-group`, so
   the rule needed its own hook rather than a class the components do not use. */
.form-row__col { flex: 1; }

.btn { width: 100%; }
.btn-primary {
  display: flex; align-items: center; justify-content: center; gap: var(--space-2);
  padding: var(--space-4); border-radius: var(--radius-md);
  background: var(--primary); color: var(--on-primary);
  font-weight: 600; font-size: var(--fs-sm); font-family: inherit;
  border: none; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  width: var(--size-2xs); height: var(--size-2xs); border: 2px solid currentColor; opacity: 0.35;
  border-top-color: currentColor; border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
