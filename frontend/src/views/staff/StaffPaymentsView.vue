<script setup lang="ts">
// Staff payments — paginated payment list with status filter + chargeback reversal.
// GET /api/v1/staff/payments (?status=, ?user_id=, ?page=, ?per_page=)
// POST /api/v1/staff/payments/{id}/reverse

import { ref, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CreditCard } from 'lucide-vue-next'
import { CBadge, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { fetchPayments, reversePayment } from '@/api/admin'
import type { StaffPaymentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<StaffPaymentResponse[]>([])
const total = ref(0)
const page = ref(1)

// Pagination steps are a NAMED CALL, not a two-statement inline expression.
// `@click="page--; loadPayments()"` is two statements in a template
// expression; prettier reflows it across lines and drops the semicolon, and
// Vue's expression parser cannot read the result -- the build fails outright.
// Measured on 2026-08-25, not predicted.
function goToPrevPage(): void {
  page.value--
  void loadPayments()
}

function goToNextPage(): void {
  page.value++
  void loadPayments()
}
const perPage = 20
const statusFilter = ref('')
const loading = ref(true)
const error = ref(false)

// Reverse modal.
const showReverseModal = ref(false)
const reverseTarget = ref<StaffPaymentResponse | null>(null)
const reverseReason = ref('')
const reverseLoading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

const statusVariant = (s: string) => {
  if (s === 'confirmed') return 'success'
  if (s === 'frozen') return 'warning'
  if (s === 'reversed') return 'danger'
  if (s === 'failed') return 'danger'
  return 'neutral'
}

function formatCents(cents: number, currency: string): string {
  return `${(cents / 100).toFixed(2)} ${currency.toUpperCase()}`
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
    await loadPayments()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    reverseLoading.value = false
  }
}

function setStatusFilter(s: string): void {
  statusFilter.value = s
  page.value = 1
}

watch([statusFilter], () => loadPayments())

onMounted(loadPayments)
</script>

<template>
  <div class="staff-pay">
    <!-- Hint -->
    <div class="staff-pay__hint">
      <CreditCard :size="16" />
      {{ t('staff.payments.hint') }}
    </div>

    <!-- Status filters -->
    <div class="staff-pay__filters">
      <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatusFilter('')">
        All
      </button>
      <button
        v-for="s in ['frozen', 'confirmed', 'reversed', 'failed']"
        :key="s"
        class="filter-chip"
        :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >
        {{ s }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-pay__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-pay__center">
      <CButton variant="secondary" size="sm" @click="loadPayments">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.payments.noPayments')">
      <template #icon>
        <CreditCard :size="40" />
      </template>
    </CEmptyState>

    <!-- Payment list -->
    <template v-else>
      <div class="pay-list">
        <div v-for="item in items" :key="item.id" class="pay-item">
          <div class="pay-item__info">
            <div class="pay-item__amount">
              {{ formatCents(item.amount_cents, item.currency) }}
            </div>
            <div class="pay-item__detail">
              {{ item.payment_type }} &bull; {{ item.provider }} &bull;
              {{ new Date(item.created_at).toLocaleDateString() }}
            </div>
            <div class="pay-item__user">User: {{ item.user_id.slice(0, 8) }}…</div>
          </div>
          <div class="pay-item__right">
            <CBadge :variant="statusVariant(item.status)" :text="item.status" />
            <button
              v-if="item.status === 'confirmed'"
              class="pay-item__reverse"
              @click.stop="openReverse(item)"
            >
              {{ t('staff.payments.reverse') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="staff-pay__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage()">
          &larr;
        </CButton>
        <span class="staff-pay__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage()">
          &rarr;
        </CButton>
      </div>
    </template>

    <!-- Reverse modal -->
    <CModal :open="showReverseModal" @close="showReverseModal = false">
      <h3 class="modal__title">
        {{ t('staff.payments.reverse') }}
      </h3>
      <p class="modal__text">
        {{ t('staff.payments.reverseConfirm') }}
      </p>
      <p v-if="reverseTarget" class="modal__amount">
        {{ formatCents(reverseTarget.amount_cents, reverseTarget.currency) }}
      </p>
      <CInput
        v-model="reverseReason"
        :label="t('staff.payments.reason')"
        :placeholder="t('staff.payments.reason')"
      />
      <div class="modal__actions">
        <CButton variant="outline" size="sm" @click="showReverseModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="reverseLoading" @click="handleReverse">
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-pay {
  padding: var(--space-4);
}

.staff-pay__hint {
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

.staff-pay__filters {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-1);
}
.filter-chip {
  position: relative;
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-transform: capitalize;
}

/* A5: the PAINTED box stays this size on purpose -- growing it would move the
   text beside it. The HIT AREA is expanded past it with a centred overlay, the
   pattern CInput.vue established and this codebase already uses ten times.
   max() so an already-large box never shrinks. Added 2026-08-25 after the first
   HIT TEST (elementFromPoint) rather than a bounding-box census: a pseudo-element
   is not in getBoundingClientRect(), so no box-based count here could ever see
   an overlay, and every A5 figure this project published measured the wrong
   quantity. */
.filter-chip::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}
.filter-chip.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.staff-pay__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

.pay-list {
  display: flex;
  flex-direction: column;
}
.pay-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
}
.pay-item__info {
  flex: 1;
  min-width: 0;
}
.pay-item__amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.pay-item__detail {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.pay-item__user {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
  font-family: var(--font-mono);
}
.pay-item__right {
  text-align: right;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  align-items: flex-end;
}
.pay-item__reverse {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--danger);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) 0;
  text-decoration: underline;
}

.staff-pay__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.staff-pay__page {
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
}
.modal__amount {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--danger);
  margin: 0 0 var(--space-4);
}
.modal__actions {
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
.modal__text {
  max-width: var(--maxw-prose);
}
.staff-pay__hint {
  max-width: var(--maxw-prose);
}
</style>
