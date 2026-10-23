<script setup lang="ts">
// Staff integrator applications — the pending queue, paged, with approve/reject.
// GET /api/v1/staff/agent-applications (?page=, ?per_page=) → each row carries
//   the applicant's name, e-mail and identity-check status, so staff decide on
//   a person and not on an id.
// POST /api/v1/staff/agent-applications/{id}/approve → 204
// POST /api/v1/staff/agent-applications/{id}/reject → 204
//
// After the approval the person accepts the integrator agreement with one press
// and receives their one link; nothing of that is on this screen.

import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Check, X } from '@/components/ui/icons'
import { CAvatar, CBadge, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import {
  fetchAgentApplications,
  approveAgentApplication,
  rejectAgentApplication,
} from '@/api/admin'
import type { AgentApplicationQueueItem } from '@/api/admin'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<AgentApplicationQueueItem[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const error = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

function goToPrevPage(): void {
  page.value--
  void loadQueue()
}

function goToNextPage(): void {
  page.value++
  void loadQueue()
}

const kycVariant = (status: string) => {
  if (status === 'approved') return 'success'
  if (status === 'submitted') return 'warning'
  if (status === 'rejected' || status === 'revoked') return 'danger'
  return 'neutral'
}

function kycLabel(status: string): string {
  return tOrRaw(t, `staff.userDetail.kyc.filter.${status}`, status)
}

// Double-submit guard.
const processingIds = ref<Set<string>>(new Set())

// Reject modal.
const showRejectModal = ref(false)
const rejectTarget = ref<AgentApplicationQueueItem | null>(null)
const rejectReason = ref('')
const rejectLoading = ref(false)

async function loadQueue(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchAgentApplications({ page: page.value, per_page: perPage })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function handleApprove(item: AgentApplicationQueueItem): Promise<void> {
  if (processingIds.value.has(item.id)) return
  processingIds.value.add(item.id)
  try {
    await approveAgentApplication(item.id)
    showToast(t('staff.agentApps2.approved'), 'success')
    await settleAfterDecision()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(item.id)
  }
}

function openReject(item: AgentApplicationQueueItem): void {
  rejectTarget.value = item
  rejectReason.value = ''
  showRejectModal.value = true
}

async function handleReject(): Promise<void> {
  if (!rejectTarget.value || !rejectReason.value.trim()) return
  const id = rejectTarget.value.id
  if (processingIds.value.has(id)) return
  processingIds.value.add(id)
  rejectLoading.value = true
  try {
    await rejectAgentApplication(id, { reason: rejectReason.value })
    showToast(t('staff.agentApps2.rejected'), 'success')
    showRejectModal.value = false
    await settleAfterDecision()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(id)
    rejectLoading.value = false
  }
}

// A decided application leaves the queue, so the page is read again; when the
// decided one was the last of its page, the page before it is shown.
async function settleAfterDecision(): Promise<void> {
  if (items.value.length === 1 && page.value > 1) page.value--
  await loadQueue()
}

onMounted(loadQueue)
</script>

<template>
  <div class="staff-apps">
    <!-- Hint -->
    <div class="staff-apps__hint">
      <FileText :size="16" />
      {{ t('staff.agentApps2.hint') }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-apps__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-apps__center">
      <CButton variant="secondary" size="sm" @click="loadQueue">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.agentApps2.noQueue')">
      <template #icon>
        <FileText :size="40" />
      </template>
    </CEmptyState>

    <!-- Queue -->
    <div v-else class="apps-list">
      <div v-for="item in items" :key="item.id" class="app-item">
        <CAvatar :name="item.applicant_name" :size="40" />
        <div class="app-item__info">
          <div class="app-item__name">{{ item.applicant_name }}</div>
          <div class="app-item__detail">
            {{ item.applicant_email ?? '—' }} &bull;
            {{ new Date(item.created_at).toLocaleDateString() }}
          </div>
          <div class="app-item__kyc">
            <span class="app-item__kyc-label">{{ t('staff.agentApps2.kycStatus') }}</span>
            <CBadge
              :variant="kycVariant(item.applicant_kyc_status)"
              :text="kycLabel(item.applicant_kyc_status)"
            />
          </div>
        </div>
        <div class="app-item__actions">
          <button
            :aria-label="t('staff.agentApps2.approve')"
            class="app-btn app-btn--approve"
            :disabled="processingIds.has(item.id)"
            @click.stop="handleApprove(item)"
          >
            <Check :size="16" />
          </button>
          <button
            class="app-btn app-btn--reject"
            :aria-label="t('staff.agentApps2.reject')"
            :disabled="processingIds.has(item.id)"
            @click.stop="openReject(item)"
          >
            <X :size="16" />
          </button>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="apps-pagination">
      <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage()">
        &larr;
      </CButton>
      <span class="apps-pagination__page">{{ page }} / {{ totalPages }}</span>
      <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage()">
        &rarr;
      </CButton>
    </div>

    <!-- Reject modal -->
    <CModal :open="showRejectModal" @close="showRejectModal = false">
      <h3 class="reject__title">
        {{ t('staff.agentApps2.reject') }}
      </h3>
      <CInput
        v-model="rejectReason"
        :label="t('staff.agentApps2.rejectReason')"
        :placeholder="t('staff.agentApps2.rejectReason')"
      />
      <div class="reject__actions">
        <CButton variant="outline" size="sm" @click="showRejectModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          :loading="rejectLoading"
          :disabled="!rejectReason.trim()"
          @click="handleReject"
        >
          {{ t('staff.agentApps2.reject') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-apps {
  padding: var(--space-4);
}

.staff-apps__hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.staff-apps__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

.apps-list {
  display: flex;
  flex-direction: column;
}
.app-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
}
.app-item__info {
  flex: 1;
  min-width: 0;
}
.app-item__name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.app-item__detail {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  overflow-wrap: anywhere;
}
.app-item__kyc {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}
.app-item__kyc-label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.apps-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.apps-pagination__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
/* A5: the gap is 12px, not 4, and the reason is arithmetic rather than taste.
   These buttons are painted 32px and carry a 44px hit overlay; at a 4px gap
   the pitch was 36 and ADJACENT OVERLAYS OVERLAPPED BY 8px, so the upper one
   swallowed its neighbour's edge and half the row still failed a hit test.
   32 + 12 = 44 makes each target own its full area with nothing to spare. */
.app-item__actions {
  display: flex;
  gap: var(--space-3);
  flex-shrink: 0;
}

.app-btn {
  width: var(--size-md);
  height: var(--size-md);
  border-radius: var(--radius-sm);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: opacity 0.2s;
}
.app-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.app-btn--approve {
  background: var(--success);
  color: var(--on-success);
}
.app-btn--approve:hover:not(:disabled) {
  opacity: 0.9;
}
.app-btn--reject {
  background: var(--danger);
  color: var(--on-danger);
}
.app-btn--reject:hover:not(:disabled) {
  opacity: 0.9;
}

.reject__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}
.reject__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.staff-apps__hint {
  max-width: var(--maxw-prose);
}

/* A5: this control is deliberately 32px to sit right in its row, so the PAINTED
   box stays and the HIT AREA is expanded past it instead. The overlay is
   invisible, centred, and never smaller than the tap floor; clicks land on the
   button because the pseudo-element belongs to it. */
.app-btn {
  position: relative;
}
.app-btn::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: var(--tap-min);
  height: var(--tap-min);
  transform: translate(-50%, -50%);
}
</style>
