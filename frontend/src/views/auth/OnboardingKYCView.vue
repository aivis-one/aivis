<script setup lang="ts">
// KYC verification — submit application, poll status, show result.
// POST /api/v1/kyc/submit → KYCSubmitResponse
// GET  /api/v1/kyc/status → KYCStatusResponse
// States: not_started → submitted (polling) → approved/rejected.
// After approved: fetchMe() → guard redirects to /onboarding/docs.

import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import type { KYCStatusResponse } from '@/api/types'
import CbsLogo from '@/components/ui/CbsLogo.vue'

const { t } = useI18n()
const authStore = useAuthStore()

const POLL_INTERVAL = 10_000

const kycStatus = ref<string>('not_started')
const loading = ref(false)
const error = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await fetchStatus()
})

onUnmounted(() => {
  stopPolling()
})

async function fetchStatus(): Promise<void> {
  try {
    const data = await api.get<KYCStatusResponse>('/api/v1/kyc/status')
    kycStatus.value = data.kyc_status

    // Start polling if submitted (waiting for webhook).
    if (data.kyc_status === 'submitted') {
      startPolling()
    } else {
      stopPolling()
    }
  } catch {
    // Silently ignore — status will be retried.
  }
}

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    const data = await api.get<KYCStatusResponse>('/api/v1/kyc/status')
    kycStatus.value = data.kyc_status
    if (data.kyc_status !== 'submitted') {
      stopPolling()
      // Sync auth store so guards can redirect automatically.
      if (data.kyc_status === 'approved') {
        await authStore.fetchMe()
      }
    }
  }, POLL_INTERVAL)
}

function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function handleSubmit(): Promise<void> {
  error.value = ''
  loading.value = true

  try {
    await api.post<unknown>('/api/v1/kyc/submit')
    kycStatus.value = 'submitted'
    startPolling()
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
  await authStore.fetchMe()
  loading.value = false
  // Guard will redirect to /onboarding/docs.
}

async function handleRetry(): Promise<void> {
  kycStatus.value = 'not_started'
  await handleSubmit()
}
</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <CbsLogo :height="28" />
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
            stroke-width="1.5"
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

      <!-- Submitted (pending) -->
      <template v-else-if="kycStatus === 'submitted'">
        <div class="kyc-status-card pending">
          <div class="kyc-card-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--warning)"
              stroke-width="1.5"
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
          <div class="kyc-polling-indicator">
            <span class="kyc-dot" />
          </div>
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
              stroke-width="1.5"
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
              stroke-width="1.5"
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
  background: var(--bg);
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
  font-size: 24px; font-weight: 700; color: var(--text);
  margin-bottom: 8px; text-align: center;
}
.auth-subtitle {
  font-size: 14px; color: var(--text-secondary);
  margin-bottom: 32px; text-align: center; line-height: 1.5;
}
.auth-error {
  font-size: 13px; color: var(--danger); text-align: center;
  margin-bottom: 16px; max-width: 360px;
}

.kyc-icon { display: flex; justify-content: center; margin-bottom: 32px; }

.kyc-status-card {
  width: 100%; max-width: 360px; border-radius: var(--radius-lg);
  padding: 32px 24px; text-align: center; margin-bottom: 24px;
}
.kyc-status-card.pending {
  background: var(--warning-dim); border: 1px solid rgba(245, 158, 11, 0.3);
}
.kyc-status-card.approved {
  background: var(--success-dim); border: 1px solid rgba(34, 197, 94, 0.3);
}
.kyc-status-card.rejected {
  background: var(--danger-dim); border: 1px solid rgba(239, 68, 68, 0.3);
}

.kyc-card-icon { display: flex; justify-content: center; margin-bottom: 16px; }
.kyc-card-title { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
.kyc-card-text { font-size: 14px; color: var(--text-secondary); line-height: 1.5; }

.kyc-polling-indicator {
  display: flex; justify-content: center; margin-top: 16px;
}
.kyc-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--warning); animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.5); }
}

.kyc-actions { width: 100%; max-width: 360px; }

.kyc-statuses {
  margin-top: 32px; width: 100%; max-width: 360px;
  padding: 16px; background: var(--bg-elevated);
  border-radius: var(--radius-md);
}
.kyc-statuses-title {
  font-size: 13px; font-weight: 600; color: var(--text);
  margin-bottom: 8px;
}
.kyc-status-item {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--text-secondary);
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
