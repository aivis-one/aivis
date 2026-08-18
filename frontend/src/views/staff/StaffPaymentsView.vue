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
      <CreditCard :size="12" />
      {{ t('staff.payments.hint') }}
    </div>

    <!-- Status filters -->
    <div class="staff-pay__filters">
      <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatusFilter('')">All</button>
      <button
        v-for="s in ['frozen', 'confirmed', 'reversed', 'failed']"
        :key="s"
        class="filter-chip" :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >{{ s }}</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-pay__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-pay__center">
      <CButton variant="secondary" size="sm" @click="loadPayments">{{ t('common.retry') }}</CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.payments.noPayments')">
      <template #icon><CreditCard :size="40" /></template>
    </CEmptyState>

    <!-- Payment list -->
    <template v-else>
      <div class="pay-list">
        <div
          v-for="item in items"
          :key="item.id"
          class="pay-item"
        >
          <div class="pay-item__info">
            <div class="pay-item__amount">{{ formatCents(item.amount_cents, item.currency) }}</div>
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
            >{{ t('staff.payments.reverse') }}</button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="staff-pay__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--; loadPayments()">&larr;</CButton>
        <span class="staff-pay__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++; loadPayments()">&rarr;</CButton>
      </div>
    </template>

    <!-- Reverse modal -->
    <CModal :open="showReverseModal" @close="showReverseModal = false">
      <h3 class="modal__title">{{ t('staff.payments.reverse') }}</h3>
      <p class="modal__text">{{ t('staff.payments.reverseConfirm') }}</p>
      <p v-if="reverseTarget" class="modal__amount">
        {{ formatCents(reverseTarget.amount_cents, reverseTarget.currency) }}
      </p>
      <CInput
        v-model="reverseReason"
        :label="t('staff.payments.reason')"
        :placeholder="t('staff.payments.reason')"
      />
      <div class="modal__actions">
        <CButton variant="outline" size="sm" @click="showReverseModal = false">{{ t('common.cancel') }}</CButton>
        <CButton variant="danger" size="sm" :loading="reverseLoading" @click="handleReverse">{{ t('common.confirm') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-pay { padding: 16px; }

.staff-pay__hint {
  display: flex; align-items: center; gap: 8px;
  padding: 12px; background: var(--bg-surface, var(--bg-subtle)); border-radius: var(--radius-md);
  margin-bottom: 16px; font-size: 12px; color: var(--text-secondary);
}

.staff-pay__filters {
  display: flex; gap: 8px; overflow-x: auto; margin-bottom: 16px; padding-bottom: 4px;
}
.filter-chip {
  padding: 6px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-page); color: var(--text-secondary); font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap; text-transform: capitalize;
}
.filter-chip.active { background: var(--primary); color: white; border-color: var(--primary); }

.staff-pay__center {
  display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 200px; gap: 16px;
}

.pay-list { display: flex; flex-direction: column; }
.pay-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 0;
  border-bottom: 1px solid var(--border-default);
}
.pay-item__info { flex: 1; min-width: 0; }
.pay-item__amount { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.pay-item__detail { font-size: 12px; color: var(--text-tertiary); }
.pay-item__user { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; font-family: monospace; }
.pay-item__right { text-align: right; flex-shrink: 0; display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
.pay-item__reverse {
  font-size: 11px; font-weight: 600; color: var(--danger); background: none; border: none;
  cursor: pointer; padding: 2px 0; text-decoration: underline;
}

.staff-pay__pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px;
}
.staff-pay__page { font-size: 13px; color: var(--text-secondary); }

.modal__title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 8px; }
.modal__text { font-size: 14px; color: var(--text-secondary); margin: 0 0 8px; }
.modal__amount { font-size: 16px; font-weight: 700; color: var(--danger); margin: 0 0 16px; }
.modal__actions { display: flex; gap: 8px; margin-top: 16px; }
</style>
