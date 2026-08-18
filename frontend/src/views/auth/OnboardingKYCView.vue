<script setup lang="ts">
// KYC verification — submit application, show status, continue immediately.
// POST /api/v1/kyc/submit  → KYCSubmitResponse
// GET  /api/v1/kyc/status  → KYCStatusResponse
// POST /api/v1/kyc/advance → 204 (iter 2.7 onboarding-advance hotfix)
//
// KYC does NOT block onboarding. After submit, user clicks "Got it" and
// proceeds to the next step. Verification runs in background.
//
// iter 2.7 onboarding-advance hotfix.
//   The original handleContinue() just called fetchMe() and navigated
//   to /, trusting the onboarding guard to forward the user to the
//   next step. That works only when onboarding_step has been advanced
//   past KYC server-side -- which submit_kyc() does on the happy
//   path. For re-entry scenarios (kyc_status already
//   submitted/approved/rejected, but onboarding_step still
//   role_selected -- e.g. from a DB seed, a manual edit, or a prior
//   submit that crashed before the advancement landed) the guard
//   sees role_selected and redirects back to /onboarding/kyc.
//   Silent infinite loop because safeNavigate's no-throw contract
//   swallows the redirect with no console trace.
//
//   The fix: before navigating, call POST /api/v1/kyc/advance which
//   delegates to the idempotent backend helper
//   advance_onboarding_after_kyc(). Happy-path users see a no-op
//   204; stuck users get their step advanced before the guard
//   evaluates. fetchMe() is then guaranteed to read the post-advance
//   value, and the subsequent navigation reaches the right place.
//
//   We call advance from BOTH the submitted-branch handleContinue
//   and the approved-branch handleContinue (same handler today,
//   but the rejected-branch handleRetry path is unchanged because
//   it goes through submit again).

import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import type { KYCStatusResponse } from '@/api/types'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

const kycStatus = ref<string>('not_started')
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  await fetchStatus()
})

async function fetchStatus(): Promise<void> {
  try {
    const data = await api.get<KYCStatusResponse>('/api/v1/kyc/status')
    kycStatus.value = data.kyc_status
  } catch {
    // Silently ignore — show not_started state.
  }
}

async function handleSubmit(): Promise<void> {
  error.value = ''
  loading.value = true

  try {
    await api.post<unknown>('/api/v1/kyc/submit')
    kycStatus.value = 'submitted'
    // Backend advances onboarding_step to kyc_done immediately.
    await authStore.fetchMe()
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

async function handleContinue(): Promise<void> {
  loading.value = true
  // iter 2.7 hotfix: kick the idempotent advance endpoint before
  // navigating. Backend no-ops if the user is already past the KYC
  // step; advances them if they are stuck on role_selected with a
  // non-not_started kyc_status. Errors swallowed -- the worst case
  // is the user lands back here and tries again, which is no worse
  // than the pre-fix behaviour.
  try {
    await api.post<unknown>('/api/v1/kyc/advance')
  } catch {
    // Intentionally silent: this is a best-effort unstick.
  }
  await authStore.fetchMe()
  loading.value = false
  // Navigate to root — guard will redirect to the next onboarding step.
  // No outer try/catch here -- safeNavigate's no-throw contract prevents
  // an unhandled promise rejection from reaching the Vue global handler.
  await safeNavigate(router.push('/'), '[OnboardingKYCView] continue to home')
}

async function handleRetry(): Promise<void> {
  kycStatus.value = 'not_started'
  await handleSubmit()
}
</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <CAppControls />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.kyc.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.kyc.subtitle') }}</p>

      <!-- Not started -->
      <template v-if="kycStatus === 'not_started'">
        <div class="kyc-icon">
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
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <div class="kyc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading"
            @click="handleSubmit"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.kyc.submit') }}</span>
          </button>
        </div>
      </template>

      <!-- Submitted (pending) — non-blocking, user can proceed -->
      <template v-else-if="kycStatus === 'submitted'">
        <div class="kyc-status-card pending">
          <div class="kyc-card-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--warning)"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              width="48"
              height="48"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div class="kyc-card-title" style="color: var(--warning);">
            {{ t('auth.kyc.pending') }}
          </div>
          <div class="kyc-card-text">{{ t('auth.kyc.pendingText') }}</div>
        </div>

        <div class="kyc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading"
            @click="handleContinue"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.kyc.continue') }}</span>
          </button>
        </div>
      </template>

      <!-- Approved -->
      <template v-else-if="kycStatus === 'approved'">
        <div class="kyc-status-card approved">
          <div class="kyc-card-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--success)"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              width="48"
              height="48"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
          </div>
          <div class="kyc-card-title" style="color: var(--success);">
            {{ t('auth.kyc.approved') }}
          </div>
          <div class="kyc-card-text">{{ t('auth.kyc.approvedText') }}</div>
        </div>

        <div class="kyc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading"
            @click="handleContinue"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.kyc.continue') }}</span>
          </button>
        </div>
      </template>

      <!-- Rejected -->
      <template v-else-if="kycStatus === 'rejected'">
        <div class="kyc-status-card rejected">
          <div class="kyc-card-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--danger)"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              width="48"
              height="48"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <div class="kyc-card-title" style="color: var(--danger);">
            {{ t('auth.kyc.rejected') }}
          </div>
          <div class="kyc-card-text">{{ t('auth.kyc.rejectedText') }}</div>
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <div class="kyc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="loading"
            @click="handleRetry"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>{{ t('auth.kyc.redo') }}</span>
          </button>
        </div>
      </template>

      <!-- Status legend -->
      <div class="kyc-statuses">
        <div class="kyc-statuses-title">{{ t('auth.kyc.statusesTitle') }}</div>
        <div class="kyc-status-item">
          <span class="kyc-status-dot warning" />
          <span>{{ t('auth.kyc.statusPending') }}</span>
        </div>
        <div class="kyc-status-item">
          <span class="kyc-status-dot success" />
          <span>{{ t('auth.kyc.statusApproved') }}</span>
        </div>
        <div class="kyc-status-item">
          <span class="kyc-status-dot danger" />
          <span>{{ t('auth.kyc.statusRejected') }}</span>
        </div>
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
  padding: 16px 24px;
}
.auth-content {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 24px; overflow-y: auto;
}
.auth-title {
  font-size: var(--fs-h3); font-weight: 700; color: var(--text-primary);
  margin-bottom: 8px; text-align: center;
}
.auth-subtitle {
  font-size: var(--fs-sm); color: var(--text-secondary);
  margin-bottom: 32px; text-align: center; line-height: 1.5;
}
.auth-error {
  font-size: var(--fs-xs-lg); color: var(--danger); text-align: center;
  margin-bottom: 16px; max-width: 360px;
}

.kyc-icon { display: flex; justify-content: center; margin-bottom: 32px; }

.kyc-status-card {
  width: 100%; max-width: 360px; border-radius: var(--radius-lg);
  padding: 32px 24px; text-align: center; margin-bottom: 24px;
}
.kyc-status-card.pending {
  background: var(--warning-subtle); border: 1px solid rgba(245, 158, 11, 0.3);
}
.kyc-status-card.approved {
  background: var(--success-subtle); border: 1px solid rgba(34, 197, 94, 0.3);
}
.kyc-status-card.rejected {
  background: var(--danger-subtle); border: 1px solid rgba(239, 68, 68, 0.3);
}

.kyc-card-icon { display: flex; justify-content: center; margin-bottom: 16px; }
.kyc-card-title { font-size: var(--fs-lg); font-weight: 700; margin-bottom: 8px; }
.kyc-card-text { font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.5; }

.kyc-actions { width: 100%; max-width: 360px; }

.kyc-statuses {
  margin-top: 32px; width: 100%; max-width: 360px;
  padding: 16px; background: var(--bg-surface);
  border-radius: var(--radius-md);
}
.kyc-statuses-title {
  font-size: var(--fs-xs-lg); font-weight: 600; color: var(--text-primary);
  margin-bottom: 8px;
}
.kyc-status-item {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-xs-lg); color: var(--text-secondary);
  margin-bottom: 6px;
}
.kyc-status-item:last-child { margin-bottom: 0; }
.kyc-status-dot {
  width: 10px; height: 10px; min-width: 10px;
  border-radius: 50%;
}
.kyc-status-dot.warning { background: var(--warning); }
.kyc-status-dot.success { background: var(--success); }
.kyc-status-dot.danger { background: var(--danger); }

.btn { width: 100%; }
.btn-primary {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 14px; border-radius: var(--radius-md);
  background: var(--primary); color: var(--on-primary);
  font-weight: 600; font-size: var(--fs-sm); font-family: inherit;
  border: none; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  width: 18px; height: 18px; border: 2px solid currentColor; opacity: 0.35;
  border-top-color: currentColor; border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
