<script setup lang="ts">
// Role selection — 3 cards (investor, agent, company) from mockup.
// POST /api/v1/users/me/select-role { role }
// After success: fetchMe() → router.push('/') → guard redirects.

import { ref, computed } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import type { UserResponse } from '@/api/types'
import CbsLogo from '@/components/ui/CbsLogo.vue'

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
    //
    // The .catch filter must NOT rethrow -- a benign NavigationFailure
    // rethrown here would be caught by the outer role-error `catch`
    // below and surface as a generic-error toast despite a successful
    // role selection.
    await router.push('/').catch((navErr: unknown) => {
      if (
        isNavigationFailure(navErr, NavigationFailureType.duplicated)
        || isNavigationFailure(navErr, NavigationFailureType.cancelled)
        || isNavigationFailure(navErr, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error('[OnboardingRoleView] post-submit navigation to home failed:', navErr)
    })
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
      <CbsLogo :height="28" />
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
  background: var(--bg);
}
.auth-header {
  display: flex; align-items: center; justify-content: center;
  padding: 16px 24px;
}
.auth-content {
  flex: 1; display: flex; flex-direction: column;
  align-items: center;
  padding: 24px; overflow-y: auto;
}
.auth-title {
  font-size: 24px; font-weight: 700; color: var(--text);
  margin-bottom: 8px; text-align: center;
}
.auth-subtitle {
  font-size: 14px; color: var(--text-secondary);
  margin-bottom: 32px; text-align: center; line-height: 1.5;
}
.auth-error {
  font-size: 13px; color: var(--danger); text-align: center;
  margin: 16px 0; max-width: 400px;
}

.role-cards {
  display: flex; flex-direction: column; gap: 16px;
  width: 100%; max-width: 400px;
}
.role-card {
  background: var(--bg); border: 2px solid var(--border);
  border-radius: var(--radius-lg); padding: 20px;
  cursor: pointer; transition: all 0.2s; position: relative;
}
.role-card:hover {
  transform: translateY(-2px); box-shadow: var(--shadow-lg);
  border-color: var(--primary-light);
}
.role-card.selected {
  border-color: var(--accent);
  background: rgba(232, 101, 26, 0.04);
  box-shadow: var(--shadow-accent-focus);
}

.role-card-check {
  position: absolute; top: 16px; right: 16px;
  width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; font-size: 14px; color: white;
}
.role-card.selected .role-card-check {
  background: var(--accent); border-color: var(--accent);
}

.role-card-header {
  display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
}
.role-card-icon { font-size: 24px; }
.role-card-title { font-size: 18px; font-weight: 700; color: var(--text); }
.role-card-desc {
  font-size: 13px; color: var(--text-secondary);
  line-height: 1.5; margin-bottom: 12px;
}

.role-card-features {
  display: flex; flex-wrap: wrap; gap: 6px;
}
.role-feature {
  font-size: 11px; font-weight: 500; padding: 4px 10px;
  border-radius: var(--radius-sm); background: var(--bg-elevated);
  color: var(--primary);
}
.role-card.selected .role-feature {
  background: rgba(232, 101, 26, 0.1); color: var(--accent);
}

.role-submit {
  width: 100%; max-width: 400px; margin-top: 24px;
}
.btn { width: 100%; }
.btn-primary {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 14px; border-radius: var(--radius-md);
  background: var(--accent); color: white;
  font-weight: 600; font-size: 15px; font-family: inherit;
  border: none; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white; border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
