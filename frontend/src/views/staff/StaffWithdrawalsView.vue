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
import { Banknote } from '@/components/ui/icons'
import { CBadge, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
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
const page = ref(1)

// Named calls, not inline `page--; loadWithdrawals()` template expressions --
// see StaffPaymentsView.vue's goToPrevPage/goToNextPage for why (prettier
// reflows a two-statement template expression across lines and drops the
// semicolon; Vue's expression parser then fails the build).
function goToPrevPage(): void {
  page.value--
  void loadWithdrawals()
}

function goToNextPage(): void {
  page.value++
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
    <div class="staff-wd__hint">
      <Banknote :size="16" />
      {{ t('staff.withdrawals.hint') }}
    </div>

    <!-- Status filters -->
    <div class="staff-wd__filters">
      <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatusFilter('')">
        {{ t('common.all') }}
      </button>
      <button
        v-for="s in STATUSES"
        :key="s"
        class="filter-chip"
        :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >
        {{ statusLabel(s) }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-wd__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-wd__center">
      <p class="wd-item__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="loadWithdrawals">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.withdrawals.noWithdrawals')">
      <template #icon>
        <Banknote :size="40" />
      </template>
    </CEmptyState>

    <!-- Withdrawal list -->
    <template v-else>
      <div class="wd-list">
        <div v-for="item in items" :key="item.id" class="wd-item">
          <div class="wd-item__info">
            <div class="wd-item__amount">
              {{ formatCents(item.amount_cents) }}
            </div>
            <div class="wd-item__detail">
              {{ new Date(item.created_at).toLocaleDateString() }}
            </div>
            <div class="wd-item__user">{{ t('staff.withdrawals.user') }}: {{ item.user_id.slice(0, 8) }}…</div>
            <div class="wd-item__payout">
              <template v-for="line in payoutLines(item.payout_details_snapshot)" :key="line.key">
                <span class="wd-item__payout-key">{{ payoutLabel(line.key) }}</span>
                <span class="wd-item__payout-value">{{ line.value }}</span>
              </template>
            </div>
            <div v-if="item.status === 'processing'" class="wd-item__note">
              {{ t('staff.withdrawals.processingNote') }}
            </div>
            <div v-if="item.rejection_reason" class="wd-item__note">
              {{ t('staff.withdrawals.reason') }}: {{ item.rejection_reason }}
            </div>
          </div>
          <div class="wd-item__right">
            <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
            <div v-if="item.status === 'pending'" class="wd-item__actions">
              <button class="wd-item__confirm" @click.stop="openConfirm(item)">
                {{ t('staff.withdrawals.confirm') }}
              </button>
              <button class="wd-item__reject" @click.stop="openReject(item)">
                {{ t('staff.withdrawals.reject') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="staff-wd__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage()">
          &larr;
        </CButton>
        <span class="staff-wd__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage()">
          &rarr;
        </CButton>
      </div>
    </template>

    <!-- Confirm modal -->
    <CModal :open="showConfirmModal" @close="showConfirmModal = false">
      <h3 class="modal__title">
        {{ t('staff.withdrawals.confirm') }}
      </h3>
      <p class="modal__text">
        {{ t('staff.withdrawals.confirmConfirm') }}
      </p>
      <p v-if="confirmTarget" class="modal__amount">
        {{ formatCents(confirmTarget.amount_cents) }}
      </p>
      <template v-if="confirmTarget">
        <p class="modal__label">{{ t('staff.withdrawals.payoutDetails') }}</p>
        <dl class="modal__payout">
          <template v-for="line in payoutLines(confirmTarget.payout_details_snapshot)" :key="line.key">
            <dt>{{ payoutLabel(line.key) }}</dt>
            <dd>{{ line.value }}</dd>
          </template>
        </dl>
      </template>
      <div class="modal__actions">
        <CButton variant="outline" size="sm" @click="showConfirmModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" :loading="confirmLoading" @click="handleConfirm">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>

    <!-- Reject modal -->
    <CModal :open="showRejectModal" @close="showRejectModal = false">
      <h3 class="modal__title">
        {{ t('staff.withdrawals.reject') }}
      </h3>
      <p class="modal__text">
        {{ t('staff.withdrawals.rejectConfirm') }}
      </p>
      <p v-if="rejectTarget" class="modal__amount">
        {{ formatCents(rejectTarget.amount_cents) }}
      </p>
      <CInput
        v-model="rejectReason"
        :label="t('staff.withdrawals.reason')"
        :placeholder="t('staff.withdrawals.reason')"
      />
      <div class="modal__actions">
        <CButton variant="outline" size="sm" @click="showRejectModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="rejectLoading" @click="handleReject">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-wd {
  padding: var(--space-4);
}

.staff-wd__hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  margin-block-end: var(--space-4);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-inline-size: var(--maxw-prose);
}

.staff-wd__filters {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  margin-block-end: var(--space-4);
  padding-block-end: var(--space-1);
}
.filter-chip {
  position: relative;
  /* A5: pointer target floor. */
  min-block-size: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: thin solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-transform: capitalize;
}

/* A5: painted box stays the same size; hit area is expanded past it with a
   centred pseudo-element overlay -- same pattern as StaffPaymentsView.vue's
   .filter-chip::after (and CInput.vue before it). */
.filter-chip::after {
  content: '';
  position: absolute;
  inset-inline-start: 50%;
  inset-block-start: 50%;
  transform: translate(-50%, -50%);
  inline-size: max(100%, var(--tap-min));
  block-size: max(100%, var(--tap-min));
}
.filter-chip.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.staff-wd__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-md);
  gap: var(--space-4);
}

.wd-list {
  display: flex;
  flex-direction: column;
}
.wd-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-block-end: thin solid var(--border-default);
}
.wd-item__info {
  flex: 1;
  min-inline-size: 0;
}
.wd-item__amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.wd-item__detail {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.wd-item__user {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-block-start: var(--space-1);
  font-family: var(--font-mono);
}
.wd-item__note {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin-block-start: var(--space-1);
  max-inline-size: var(--maxw-prose);
}
.wd-item__right {
  text-align: end;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  align-items: flex-end;
}
.wd-item__actions {
  display: flex;
  gap: var(--space-3);
}
.wd-item__confirm {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--success);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) 0;
  text-decoration: underline;
}
.wd-item__reject {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--danger);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) 0;
  text-decoration: underline;
}

.staff-wd__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-block-start: var(--space-4);
}
.staff-wd__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.modal__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.modal__text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-2);
  max-inline-size: var(--maxw-prose);
}
.modal__amount {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}
.modal__label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 var(--space-1);
}
.modal__payout {
  font-size: var(--fs-xs);
  color: var(--text-primary);
  background: var(--bg-page);
  border: thin solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin: 0 0 var(--space-4);
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-3);
  word-break: break-word;
  max-block-size: 200px;
  overflow-y: auto;
}
.modal__actions {
  display: flex;
  gap: var(--space-2);
  margin-block-start: var(--space-4);
}

.modal__payout dt {
  color: var(--text-secondary);
}
.modal__payout dd {
  margin: 0;
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}
.wd-item__payout {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0 var(--space-3);
  margin-block-start: var(--space-1);
  font-size: var(--fs-xs);
}
.wd-item__payout-key {
  color: var(--text-tertiary);
}
.wd-item__payout-value {
  color: var(--text-primary);
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}
.wd-item__error {
  font-size: var(--fs-sm);
  color: var(--danger);
  margin: 0;
}
</style>
