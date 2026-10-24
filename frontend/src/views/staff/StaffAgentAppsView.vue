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
import { CAvatar, CBadge, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
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
const page = useUrlPage()
const perPage = 20
const loading = ref(true)
const error = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

function goToPage(n: number): void {
  page.value = n
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
    <CAlert tone="info">
      {{ t('staff.agentApps2.hint') }}
    </CAlert>

    <!-- Loading -->
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadQueue">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.agentApps2.noQueue')">
      <template #icon>
        <FileText />
      </template>
    </CEmptyState>

    <!-- Queue (K23 rows) -->
    <ul v-else class="ds-rows">
      <li v-for="item in items" :key="item.id" class="ds-row">
        <CAvatar :name="item.applicant_name" :size="32" />
        <span class="ds-row__body">
          <span class="ds-row__title">{{ item.applicant_name }}</span>
          <span class="ds-row__meta app-item__detail">
            {{ item.applicant_email ?? '—' }} &bull;
            {{ new Date(item.created_at).toLocaleDateString() }}
          </span>
          <span class="ds-row__meta">
            {{ t('staff.agentApps2.kycStatus') }}
            <CBadge
              :variant="kycVariant(item.applicant_kyc_status)"
              :text="kycLabel(item.applicant_kyc_status)"
            />
          </span>
        </span>
        <span class="ds-row__trail">
          <button
            type="button"
            class="ds-button ds-button--primary ds-button--icon"
            data-size="sm"
            :aria-label="t('staff.agentApps2.approve')"
            :disabled="processingIds.has(item.id)"
            @click="handleApprove(item)"
          >
            <Check />
          </button>
          <button
            type="button"
            class="ds-button ds-button--secondary ds-button--icon"
            data-size="sm"
            :aria-label="t('staff.agentApps2.reject')"
            :disabled="processingIds.has(item.id)"
            @click="openReject(item)"
          >
            <X />
          </button>
        </span>
      </li>
    </ul>

    <!-- Pagination (K17) -->
    <CPager :page="page" :total-pages="totalPages" @update:page="goToPage" />

    <!-- Reject modal -->
    <CModal
      :open="showRejectModal"
      :title="t('staff.agentApps2.reject')"
      @close="showRejectModal = false"
    >
      <CInput
        v-model="rejectReason"
        :label="t('staff.agentApps2.rejectReason')"
        :placeholder="t('staff.agentApps2.rejectReason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showRejectModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          inline
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
/* The frame's main pads the screen and sets its measure; the screen only stacks its parts. */
.staff-apps {
  display: grid;
  gap: var(--space-4);
}
</style>
