<script setup lang="ts">
// Staff withdrawals — paginated withdrawal list with status filter +
// confirm/reject actions. Closes the discovery gap: confirm/reject
// endpoints already existed (Sprint 6.3) but staff had no list to find
// a pending withdrawal_id against. Structural template: StaffPaymentsView.vue.
//
// WHERE THE MONEY GOES is shown as the network and the wallet, two labelled
// lines (utils/payoutDetails.ts), in the list row and in the confirmation --
// never as the raw payout object.
// GET /api/v1/staff/withdrawals (?status=, ?user_id=, ?page=, ?per_page=)
// POST /api/v1/staff/withdrawals/{id}/confirm
// POST /api/v1/staff/withdrawals/{id}/reject

import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Banknote, Check } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import StaffAlert from '@/components/staff/StaffAlert.vue'
import StaffListSkeleton from '@/components/staff/StaffListSkeleton.vue'
import StaffPager from '@/components/staff/StaffPager.vue'
import { useUrlPage } from '@/components/staff/useUrlPage'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { payoutLines } from '@/utils/payoutDetails'
import { ApiResponseError } from '@/api/client'
import { fetchWithdrawalsStaff, confirmWithdrawal, rejectWithdrawal } from '@/api/admin'
import type { WithdrawalResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<WithdrawalResponse[]>([])
const total = ref(0)
const page = useUrlPage()

function goToPage(n: number): void {
  page.value = n
  void loadWithdrawals()
}
const perPage = 20
const statusFilter = ref('')
const loading = ref(true)
const error = ref(false)

// 'confirmed' is deliberately excluded: confirm_withdrawal() transitions
// pending -> confirmed -> processing within one call, so 'confirmed' is
// never an externally observable persisted status -- that filter chip
// would always return zero rows.
const STATUSES = ['pending', 'processing', 'completed', 'rejected', 'failed']

// Confirm modal.
const showConfirmModal = ref(false)
const confirmTarget = ref<WithdrawalResponse | null>(null)
const confirmLoading = ref(false)

// Reject modal.
const showRejectModal = ref(false)
const rejectTarget = ref<WithdrawalResponse | null>(null)
const rejectReason = ref('')
const rejectLoading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

const statusVariant = (s: string) => {
  if (s === 'completed' || s === 'processing') return 'success'
  if (s === 'pending' || s === 'confirmed') return 'warning'
  if (s === 'rejected' || s === 'failed') return 'danger'
  return 'neutral'
}

function formatCents(cents: number): string {
  return `${(cents / 100).toFixed(2)} ${t('staff.withdrawals.currency')}`
}

function statusLabel(status: string): string {
  return tOrRaw(t, `staff.withdrawals.statuses.${status}`, status)
}

function payoutLabel(key: string): string {
  return tOrRaw(t, `staff.withdrawals.payout.${key}`, key)
}

function serverReason(err: unknown, fallbackKey: string): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t(fallbackKey)
}

async function loadWithdrawals(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchWithdrawalsStaff({
      status: statusFilter.value || undefined,
      page: page.value,
      per_page: perPage,
    })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function openConfirm(item: WithdrawalResponse): void {
  confirmTarget.value = item
  showConfirmModal.value = true
}

async function handleConfirm(): Promise<void> {
  if (!confirmTarget.value) return
  confirmLoading.value = true
  try {
    await confirmWithdrawal(confirmTarget.value.id)
    showToast(t('staff.withdrawals.confirmed'), 'success')
    showConfirmModal.value = false
    await loadWithdrawals()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    confirmLoading.value = false
  }
}

function openReject(item: WithdrawalResponse): void {
  rejectTarget.value = item
  rejectReason.value = ''
  showRejectModal.value = true
}

async function handleReject(): Promise<void> {
  if (!rejectTarget.value) return
  if (!rejectReason.value.trim()) {
    showToast(t('staff.withdrawals.reasonRequired'), 'error')
    return
  }
  rejectLoading.value = true
  try {
    await rejectWithdrawal(rejectTarget.value.id, { reason: rejectReason.value })
    showToast(t('staff.withdrawals.rejected'), 'success')
    showRejectModal.value = false
    await loadWithdrawals()
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    rejectLoading.value = false
  }
}

function setStatusFilter(s: string): void {
  statusFilter.value = s
  page.value = 1
}

watch([statusFilter], () => loadWithdrawals())

onMounted(loadWithdrawals)
</script>

<template>
  <div class="staff-wd">
    <!-- Hint -->
    <StaffAlert tone="info">
      {{ t('staff.withdrawals.hint') }}
    </StaffAlert>

    <!-- Status filters (K13) -->
    <div class="ds-chip-row" role="group" :aria-label="t('staff.withdrawals.title')">
      <button
        class="ds-chip"
        :aria-pressed="!statusFilter"
        @click="setStatusFilter('')"
        type="button"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ t('common.all') }}</span>
      </button>
      <button
        v-for="s in STATUSES"
        :key="s"
        class="ds-chip"
        :aria-pressed="statusFilter === s"
        @click="setStatusFilter(s)"
        type="button"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ statusLabel(s) }}</span>
      </button>
    </div>

    <!-- Loading -->
    <StaffListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadWithdrawals">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.withdrawals.noWithdrawals')">
      <template #icon>
        <Banknote :size="40" />
      </template>
    </CEmptyState>

    <!-- Withdrawal list (K23 rows) -->
    <template v-else>
      <ul class="ds-rows wd-list">
        <li v-for="item in items" :key="item.id" class="ds-row wd-item">
          <span class="ds-row__body">
            <span class="ds-row__title">
              {{ t('staff.withdrawals.user') }}: {{ item.user_id.slice(0, 8) }}…
            </span>
            <span class="ds-row__meta">
              {{ new Date(item.created_at).toLocaleDateString() }}
            </span>
            <dl class="ds-kv wd-item__payout">
              <div
                v-for="line in payoutLines(item.payout_details_snapshot)"
                :key="line.key"
                class="ds-kv__row"
              >
                <dt>{{ payoutLabel(line.key) }}</dt>
                <dd>{{ line.value }}</dd>
              </div>
            </dl>
            <span v-if="item.status === 'processing'" class="ds-row__meta">
              {{ t('staff.withdrawals.processingNote') }}
            </span>
            <span v-if="item.rejection_reason" class="ds-row__meta">
              {{ t('staff.withdrawals.reason') }}: {{ item.rejection_reason }}
            </span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value">{{ formatCents(item.amount_cents) }}</span>
            <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
            <template v-if="item.status === 'pending'">
              <button
                type="button"
                class="ds-button ds-button--primary wd-item__confirm"
                data-size="sm"
                @click="openConfirm(item)"
              >
                <span>{{ t('staff.withdrawals.confirm') }}</span>
              </button>
              <button
                type="button"
                class="ds-button ds-button--secondary wd-item__reject"
                data-size="sm"
                @click="openReject(item)"
              >
                <span>{{ t('staff.withdrawals.reject') }}</span>
              </button>
            </template>
          </span>
        </li>
      </ul>

      <!-- Pagination (K17) -->
      <StaffPager :page="page" :total-pages="totalPages" @update:page="goToPage" />
    </template>

    <!-- Confirm modal -->
    <CModal
      :open="showConfirmModal"
      :title="t('staff.withdrawals.confirm')"
      @close="showConfirmModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.withdrawals.confirmConfirm') }}
      </p>
      <p v-if="confirmTarget" class="staff-wd__amount">
        {{ formatCents(confirmTarget.amount_cents) }}
      </p>
      <template v-if="confirmTarget">
        <p class="staff-wd__label">{{ t('staff.withdrawals.payoutDetails') }}</p>
        <dl class="ds-kv">
          <div
            v-for="line in payoutLines(confirmTarget.payout_details_snapshot)"
            :key="line.key"
            class="ds-kv__row"
          >
            <dt>{{ payoutLabel(line.key) }}</dt>
            <dd>{{ line.value }}</dd>
          </div>
        </dl>
      </template>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showConfirmModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="confirmLoading" @click="handleConfirm">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Reject modal -->
    <CModal
      :open="showRejectModal"
      :title="t('staff.withdrawals.reject')"
      @close="showRejectModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.withdrawals.rejectConfirm') }}
      </p>
      <p v-if="rejectTarget" class="staff-wd__amount">
        {{ formatCents(rejectTarget.amount_cents) }}
      </p>
      <CInput
        v-model="rejectReason"
        :label="t('staff.withdrawals.reason')"
        :placeholder="t('staff.withdrawals.reason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showRejectModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" inline :loading="rejectLoading" @click="handleReject">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-wd {
  display: grid;
  gap: var(--space-4);
  align-content: start;
}

.staff-wd__amount {
  margin: 0;
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--text-primary);
}

.staff-wd__label {
  margin: 0;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--text-secondary);
}
</style>
