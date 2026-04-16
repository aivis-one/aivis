<script setup lang="ts">
// Staff KYC queue — pending KYC applications.
// GET /api/v1/staff/kyc/queue → KYCQueueItem[]
// POST /api/v1/staff/kyc/{id}/approve → 204
// POST /api/v1/staff/kyc/{id}/reject → 204

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldAlert, Check, X } from 'lucide-vue-next'
import { CAvatar, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { fetchKYCQueue, approveKYC, rejectKYC } from '@/api/admin'
import type { KYCQueueItem } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<KYCQueueItem[]>([])
const loading = ref(true)
const error = ref(false)

// Double-submit guard: track IDs being processed.
const processingIds = ref<Set<string>>(new Set())

// Reject modal state.
const showRejectModal = ref(false)
const rejectTarget = ref<KYCQueueItem | null>(null)
const rejectReason = ref('')
const rejectLoading = ref(false)

function fullName(item: KYCQueueItem): string {
  const parts = [item.first_name, item.last_name].filter(Boolean)
  return parts.length ? parts.join(' ') : '—'
}

async function loadQueue(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    items.value = await fetchKYCQueue()
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function handleApprove(item: KYCQueueItem): Promise<void> {
  if (processingIds.value.has(item.id)) return
  processingIds.value.add(item.id)
  try {
    await approveKYC(item.id)
    showToast(t('staff.kyc.approved'), 'success')
    items.value = items.value.filter(i => i.id !== item.id)
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(item.id)
  }
}

function openReject(item: KYCQueueItem): void {
  rejectTarget.value = item
  rejectReason.value = ''
  showRejectModal.value = true
}

async function handleReject(): Promise<void> {
  if (!rejectTarget.value) return
  const id = rejectTarget.value.id
  if (processingIds.value.has(id)) return
  processingIds.value.add(id)
  rejectLoading.value = true
  try {
    await rejectKYC(id, { reason: rejectReason.value || undefined })
    showToast(t('staff.kyc.rejected'), 'success')
    items.value = items.value.filter(i => i.id !== id)
    showRejectModal.value = false
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(id)
    rejectLoading.value = false
  }
}

onMounted(loadQueue)
</script>

<template>
  <div class="staff-kyc">
    <!-- Hint banner -->
    <div class="staff-kyc__hint">
      <ShieldAlert :size="12" />
      {{ t('staff.kyc.hint') }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-kyc__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-kyc__center">
      <CButton variant="secondary" size="sm" @click="loadQueue">{{ t('common.retry') }}</CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.kyc.noQueue')">
      <template #icon><ShieldAlert :size="40" /></template>
    </CEmptyState>

    <!-- Queue list -->
    <div v-else class="kyc-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="kyc-item"
      >
        <CAvatar :name="fullName(item)" :size="40" />
        <div class="kyc-item__info">
          <div class="kyc-item__name">{{ fullName(item) }}</div>
          <div class="kyc-item__detail">
            {{ item.email ?? '—' }} &bull;
            {{ t('staff.kyc.submitted') }} {{ new Date(item.created_at).toLocaleDateString() }}
          </div>
        </div>
        <div class="kyc-item__actions">
          <button
            class="kyc-btn kyc-btn--approve"
            :disabled="processingIds.has(item.id)"
            @click.stop="handleApprove(item)"
          >
            <Check :size="12" />
          </button>
          <button
            class="kyc-btn kyc-btn--reject"
            :disabled="processingIds.has(item.id)"
            @click.stop="openReject(item)"
          >
            <X :size="12" />
          </button>
        </div>
      </div>
    </div>

    <!-- Reject modal -->
    <CModal :open="showRejectModal" @close="showRejectModal = false">
      <h3 class="reject__title">{{ t('staff.kyc.reject') }}</h3>
      <p v-if="rejectTarget" class="reject__user">{{ fullName(rejectTarget) }}</p>
      <CInput
        v-model="rejectReason"
        :label="t('staff.kyc.rejectReason')"
        :placeholder="t('staff.kyc.rejectReason')"
      />
      <div class="reject__actions">
        <CButton variant="outline" size="sm" @click="showRejectModal = false">{{ t('common.cancel') }}</CButton>
        <CButton variant="danger" size="sm" :loading="rejectLoading" @click="handleReject">{{ t('staff.kyc.reject') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-kyc { padding: 16px; }

.staff-kyc__hint {
  display: flex; align-items: center; gap: 8px;
  padding: 12px; background: var(--warning-dim); border-radius: var(--radius-md);
  margin-bottom: 16px; font-size: 12px; color: var(--text-secondary);
}

.staff-kyc__center {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px; gap: 16px;
}

.kyc-list { display: flex; flex-direction: column; }
.kyc-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 0;
  border-bottom: 1px solid var(--border);
}
.kyc-item__info { flex: 1; min-width: 0; }
.kyc-item__name { font-size: 14px; font-weight: 600; color: var(--text); }
.kyc-item__detail { font-size: 12px; color: var(--text-tertiary); }
.kyc-item__actions { display: flex; gap: 4px; flex-shrink: 0; }

.kyc-btn {
  width: 32px; height: 32px; border-radius: var(--radius-sm); border: none;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  transition: opacity 0.2s; color: white;
}
.kyc-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.kyc-btn--approve { background: var(--success); }
.kyc-btn--approve:hover:not(:disabled) { opacity: 0.9; }
.kyc-btn--reject { background: var(--danger); }
.kyc-btn--reject:hover:not(:disabled) { opacity: 0.9; }

.reject__title { font-size: 18px; font-weight: 700; color: var(--text); margin: 0 0 8px; }
.reject__user { font-size: 14px; color: var(--text-secondary); margin: 0 0 16px; }
.reject__actions { display: flex; gap: 8px; margin-top: 16px; }
</style>
