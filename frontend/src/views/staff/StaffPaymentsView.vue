<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffPaymentsView (Finance > Payments)
// =============================================================================
//
// Two blocks, one screen:
//
//   1. THE QUEUE OF TOP-UPS IN THEIR HOUR. A top-up is confirmed by itself
//      after the blockchain has confirmed it and an hour has passed. Until
//      then it is "frozen", and this block lists exactly those, each with the
//      time left, so a staff member can look at the transaction and reverse
//      it before the hour ends. A reversal takes the money the top-up brought
//      back out of the accounts it reached.
//   2. THE PAYMENT LIST, paged, with a status filter. A confirmed payment can
//      still be reversed (a chargeback); every status, type and label is
//      spoken in the interface language, never as a raw token.
//
// GET  /api/v1/staff/payments (?status=, ?user_id=, ?page=, ?per_page=)
// POST /api/v1/staff/payments/{id}/reverse   (frozen or confirmed)
// =============================================================================

import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CreditCard, Check } from '@/components/ui/icons'
import { CBadge, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import { fetchPayments, reversePayment } from '@/api/admin'
import { tOrRaw } from '@/utils/i18n'
import type { StaffPaymentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<StaffPaymentResponse[]>([])
const total = ref(0)
const page = useUrlPage()

function goToPage(n: number): void {
  page.value = n
  void loadPayments()
}
const perPage = 20
const statusFilter = ref('')
const loading = ref(true)
const error = ref(false)

// -- The queue of top-ups in their hour --
const queue = ref<StaffPaymentResponse[]>([])
const queueLoading = ref(true)
const queueError = ref(false)
// One read looks at up to a hundred; a longer queue says so.
const QUEUE_WINDOW = 100
const queueTotal = ref(0)

// The clock the "time left" is counted against, moved every half minute.
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null

// Reverse modal.
const showReverseModal = ref(false)
const reverseTarget = ref<StaffPaymentResponse | null>(null)
const reverseReason = ref('')
const reverseLoading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

const STATUSES = ['frozen', 'confirmed', 'reversed', 'failed'] as const

const statusVariant = (s: string) => {
  if (s === 'confirmed') return 'success'
  if (s === 'frozen') return 'warning'
  if (s === 'reversed') return 'danger'
  if (s === 'failed') return 'danger'
  return 'neutral'
}

function statusLabel(status: string): string {
  return tOrRaw(t, `staff.payments.statuses.${status}`, status)
}

function typeLabel(type: string): string {
  return tOrRaw(t, `staff.payments.types.${type}`, type)
}

function formatCents(cents: number, currency: string): string {
  return `${(cents / 100).toFixed(2)} ${currency.toUpperCase()}`
}

/** Whole minutes until the hour ends; null when the payment carries no end. */
function minutesLeft(item: StaffPaymentResponse): number | null {
  if (!item.frozen_until) return null
  const ms = new Date(item.frozen_until).getTime() - now.value
  return Math.max(0, Math.ceil(ms / 60000))
}

function timeLeftLabel(item: StaffPaymentResponse): string {
  const minutes = minutesLeft(item)
  if (minutes === null) return t('staff.payments.queue.noEnd')
  if (minutes === 0) return t('staff.payments.queue.confirming')
  return t('staff.payments.queue.minutesLeft', { n: minutes })
}

function serverReason(err: unknown, fallbackKey: string): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t(fallbackKey)
}

async function loadPayments(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchPayments({
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

async function loadQueue(): Promise<void> {
  queueLoading.value = true
  queueError.value = false
  try {
    const resp = await fetchPayments({ status: 'frozen', page: 1, per_page: QUEUE_WINDOW })
    // The soonest to confirm first: that is the one to look at next.
    queue.value = [...resp.items].sort(
      (a, b) =>
        new Date(a.frozen_until ?? a.created_at).getTime() -
        new Date(b.frozen_until ?? b.created_at).getTime(),
    )
    queueTotal.value = resp.total
  } catch {
    queueError.value = true
  } finally {
    queueLoading.value = false
  }
}

function openReverse(item: StaffPaymentResponse): void {
  reverseTarget.value = item
  reverseReason.value = ''
  showReverseModal.value = true
}

async function handleReverse(): Promise<void> {
  if (!reverseTarget.value) return
  reverseLoading.value = true
  try {
    await reversePayment(reverseTarget.value.id, {
      reason: reverseReason.value || undefined,
    })
    showToast(t('staff.payments.reversed'), 'success')
    showReverseModal.value = false
    await Promise.all([loadQueue(), loadPayments()])
  } catch (err) {
    showToast(serverReason(err, 'common.error'), 'error')
  } finally {
    reverseLoading.value = false
  }
}

function setStatusFilter(s: string): void {
  statusFilter.value = s
  page.value = 1
}

// A payment can be reversed while it is in its hour or after it was confirmed.
function canReverse(item: StaffPaymentResponse): boolean {
  return item.status === 'frozen' || item.status === 'confirmed'
}

watch([statusFilter], () => loadPayments())

onMounted(() => {
  void loadQueue()
  void loadPayments()
  clock = setInterval(() => {
    now.value = Date.now()
  }, 30_000)
})

onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})
</script>

<template>
  <div class="staff-pay">
    <!-- Hint -->
    <CAlert tone="info">
      {{ t('staff.payments.hint') }}
    </CAlert>

    <!-- The queue of top-ups in their hour -->
    <section class="staff-pay__section pay-queue" :aria-label="t('staff.payments.queue.title')">
      <h2 class="ds-section-title staff-pay__title">
        {{ t('staff.payments.queue.title') }}
        <CBadge v-if="!queueLoading && !queueError" variant="warning" :text="String(queueTotal)" />
      </h2>
      <CLoader v-if="queueLoading" centered />
      <CAlert v-else-if="queueError" tone="danger">
        {{ t('staff.payments.queue.error') }}
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="loadQueue">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CAlert>
      <p v-else-if="!queue.length" class="ds-note">
        {{ t('staff.payments.queue.empty') }}
      </p>
      <ul v-else class="ds-rows pay-list">
        <li v-for="item in queue" :key="item.id" class="ds-row pay-item">
          <span class="ds-row__body">
            <span class="ds-row__title">{{ typeLabel(item.payment_type) }}</span>
            <span class="ds-row__meta">
              {{ item.provider }} &bull; {{ new Date(item.created_at).toLocaleString() }}
            </span>
            <span class="ds-row__meta">
              {{ t('staff.payments.user') }}: {{ item.user_id.slice(0, 8) }}…
            </span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value">{{ formatCents(item.amount_cents, item.currency) }}</span>
            <CBadge variant="warning" :text="timeLeftLabel(item)" />
            <button
              type="button"
              class="ds-button ds-button--danger pay-item__reverse"
              data-size="sm"
              @click="openReverse(item)"
            >
              <span>{{ t('staff.payments.reverse') }}</span>
            </button>
          </span>
        </li>
      </ul>
      <p v-if="queueTotal > QUEUE_WINDOW" class="ds-note">
        {{ t('staff.payments.queue.more', { n: QUEUE_WINDOW }) }}
      </p>
    </section>

    <!-- All payments -->
    <section class="staff-pay__section">
      <h2 class="ds-section-title staff-pay__title">
        {{ t('staff.payments.listTitle') }}
      </h2>

      <!-- Status filters (K13) -->
      <div class="ds-chip-row" role="group" :aria-label="t('staff.payments.status')">
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
      <CListSkeleton v-if="loading" />

      <!-- Error -->
      <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="loadPayments">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <!-- Empty -->
      <CEmptyState v-else-if="!items.length" :title="t('staff.payments.noPayments')">
        <template #icon>
          <CreditCard />
        </template>
      </CEmptyState>

      <!-- Payment list (K23 rows) -->
      <template v-else>
        <ul class="ds-rows pay-list">
          <li v-for="item in items" :key="item.id" class="ds-row pay-item">
            <span class="ds-row__body">
              <span class="ds-row__title">{{ typeLabel(item.payment_type) }}</span>
              <span class="ds-row__meta">
                {{ item.provider }} &bull; {{ new Date(item.created_at).toLocaleDateString() }}
              </span>
              <span class="ds-row__meta">
                {{ t('staff.payments.user') }}: {{ item.user_id.slice(0, 8) }}…
              </span>
            </span>
            <span class="ds-row__trail">
              <span class="ds-row__value">{{ formatCents(item.amount_cents, item.currency) }}</span>
              <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
              <button
                v-if="canReverse(item)"
                type="button"
                class="ds-button ds-button--danger pay-item__reverse"
                data-size="sm"
                @click="openReverse(item)"
              >
                <span>{{ t('staff.payments.reverse') }}</span>
              </button>
            </span>
          </li>
        </ul>

        <!-- Pagination (K17) -->
        <CPager :page="page" :total-pages="totalPages" @update:page="goToPage" />
      </template>
    </section>

    <!-- Reverse modal -->
    <CModal
      :open="showReverseModal"
      :title="t('staff.payments.reverse')"
      @close="showReverseModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.payments.reverseConfirm') }}
      </p>
      <p v-if="reverseTarget" class="ds-amount" data-size="sm" data-tone="danger">
        {{ formatCents(reverseTarget.amount_cents, reverseTarget.currency) }}
      </p>
      <CInput
        v-model="reverseReason"
        :label="t('staff.payments.reason')"
        :placeholder="t('staff.payments.reason')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showReverseModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" inline :loading="reverseLoading" @click="handleReverse">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-pay {
  display: grid;
  gap: var(--space-5);
  align-content: start;
}

.staff-pay__section {
  display: grid;
  gap: var(--space-3);
}

.staff-pay__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
