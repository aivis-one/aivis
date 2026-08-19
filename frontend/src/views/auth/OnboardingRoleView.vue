<script setup lang="ts">
// Role selection — 3 cards (investor, agent, company) from mockup.
// POST /api/v1/users/me/select-role { role }
// After success: fetchMe() → router.push('/') → guard redirects.

import { ref, computed } from 'vue'
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

type SelectableRole = 'investor' | 'agent' | 'company'

interface RoleOption {
  id: SelectableRole
  icon: string
  titleKey: string
  descKey: string
  features: string[]
}

const roles: RoleOption[] = [
  {
    id: 'investor',
    icon: '📊',
    titleKey: 'auth.role.investor',
    descKey: 'auth.role.investorDesc',
    features: [
      'auth.role.feat.portfolio',
      'auth.role.feat.installments',
      'auth.role.feat.balance',
      'auth.role.feat.documents',
    ],
  },
  {
    id: 'agent',
    icon: '🤝',
    titleKey: 'auth.role.agent',
    descKey: 'auth.role.agentDesc',
    features: [
      'auth.role.feat.referrals',
      'auth.role.feat.commissions',
      'auth.role.feat.leaderboard',
      'auth.role.feat.certification',
    ],
  },
  {
    id: 'company',
    icon: '🏢',
    titleKey: 'auth.role.company',
    descKey: 'auth.role.companyDesc',
    features: [
      'auth.role.feat.products',
      'auth.role.feat.analytics',
      'auth.role.feat.revenue',
      'auth.role.feat.documents',
    ],
  },
]

const selectedRole = ref<SelectableRole | null>(null)
const loading = ref(false)
const error = ref('')

const buttonText = computed(() => {
  if (!selectedRole.value) return t('auth.role.btn')
  return `${t('auth.role.continueAs')} ${t(`auth.role.${selectedRole.value}`)}`
})

function selectRole(role: SelectableRole): void {
  selectedRole.value = role
}

async function handleSubmit(): Promise<void> {
  if (!selectedRole.value) return
  error.value = ''
  loading.value = true

  try {
    await api.post<UserResponse>('/api/v1/users/me/select-role', {
      role: selectedRole.value,
    })
    await authStore.fetchMe()
    // Navigate to root — guard will redirect to the next onboarding step.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer role-error catch
    // and surface as a generic-error toast after successful role selection.
    await safeNavigate(router.push('/'), '[OnboardingRoleView] post-submit to home')
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
      <h1 class="auth-title">{{ t('auth.role.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.role.subtitle') }}</p>

      <div class="role-cards">
        <div
          v-for="role in roles"
          :key="role.id"
          class="role-card"
          :class="{ selected: selectedRole === role.id }"
          @click="selectRole(role.id)"
        >
          <div class="role-card-check">
            <span v-if="selectedRole === role.id">✓</span>
          </div>
          <div class="role-card-header">
            <span class="role-card-icon">{{ role.icon }}</span>
            <span class="role-card-title">{{ t(role.titleKey) }}</span>
          </div>
          <div class="role-card-desc">{{ t(role.descKey) }}</div>
          <div class="role-card-features">
            <span
              v-for="feat in role.features"
              :key="feat"
              class="role-feature"
            >
              {{ t(feat) }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="error" class="auth-error">{{ error }}</div>

      <div class="role-submit">
        <button
          class="btn btn-primary"
          type="button"
          :disabled="!selectedRole || loading"
          @click="handleSubmit"
        >
          <span v-if="loading" class="btn-spinner" />
          <span v-else>{{ buttonText }}</span>
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
  align-items: center;
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
.auth-error {
  font-size: var(--fs-xs-lg); color: var(--danger); text-align: center;
  margin: var(--space-4) 0; max-width: 400px;
}

.role-cards {
  display: flex; flex-direction: column; gap: var(--space-4);
  width: 100%; max-width: 400px;
}
.role-card {
  background: var(--bg-page); border: 2px solid var(--border-default);
  border-radius: var(--radius-lg); padding: var(--space-4-lg);
  cursor: pointer; transition: all 0.2s; position: relative;
}
.role-card:hover {
  transform: translateY(-2px); box-shadow: var(--shadow-3);
  border-color: var(--primary-hover);
}
.role-card.selected {
  border-color: var(--accent);
  background: var(--accent-subtle);
  box-shadow: var(--shadow-accent-focus);
}

.role-card-check {
  position: absolute; top: 16px; right: 16px;
  width: var(--size-xs); height: var(--size-xs); border-radius: 50%;
  border: 2px solid var(--border-default);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; font-size: var(--fs-sm); color: var(--on-accent);
}
.role-card.selected .role-card-check {
  background: var(--accent); border-color: var(--accent);
}

.role-card-header {
  display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3);
}
.role-card-icon { font-size: var(--fs-h3); }
.role-card-title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); }
.role-card-desc {
  font-size: var(--fs-xs-lg); color: var(--text-secondary);
  line-height: 1.5; margin-bottom: var(--space-3);
}

.role-card-features {
  display: flex; flex-wrap: wrap; gap: var(--space-2);
}
.role-feature {
  font-size: var(--fs-xs); font-weight: 500; padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm); background: var(--bg-surface);
  color: var(--primary);
}
.role-card.selected .role-feature {
  background: var(--accent-subtle); color: var(--accent);
}

.role-submit {
  width: 100%; max-width: 400px; margin-top: var(--space-5);
}
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
