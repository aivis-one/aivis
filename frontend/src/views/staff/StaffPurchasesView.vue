<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffPurchasesView (Finance > Purchases)
// =============================================================================
//
// The list of the platform's purchases, read-only: one row per purchase with its
// date, buyer, project, product, parts, amount, type (paid / installment /
// gift / bonus) and status. Paged, newest first, filtered by status, project and
// buyer. There is no contract to upload here: the buyer accepts the buyer's
// agreement with a click, the purchase agreement is generated, and a gift has
// its certificate.
//
// A gift that the recipient has not accepted yet carries Cancel, so a gift can
// be cancelled after the page it was granted from is closed. An accepted gift is
// reversed through the payments, not here.
//
// GET  /api/v1/staff/purchases   (financial_operations; ?status= ?company_id= ?buyer_id= ?page= ?per_page=)
// POST /api/v1/staff/purchases/gifts/{id}/cancel   (financial_operations)
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShoppingBag } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CLoader, CSelect } from '@/components/ui'
import UserPicker from '@/components/staff/UserPicker.vue'
import { ApiResponseError } from '@/api/client'
import { cancelGift, fetchStaffPurchases } from '@/api/admin'
import { listProducts } from '@/api/products'
import { fetchStaffCompanies } from '@/api/staff-companies'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'
import type { StaffPurchaseItem } from '@/api/generated'

const { t, locale } = useI18n()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

const canCancel = canDo('financial_operations')
const canListProjects = canDo('company_manage')

const STATUSES = ['active', 'pending_acceptance', 'reversed', 'cancelled'] as const

// -- The list -----------------------------------------------------------------

const items = ref<StaffPurchaseItem[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const error = ref(false)
// An answer that arrives after a newer request was sent is dropped.
let epoch = 0

const statusFilter = ref('')
const projectFilter = ref('')
const buyerFilter = ref('')

const totalPages = computed(() => Math.ceil(total.value / perPage))

async function load(): Promise<void> {
  const mine = ++epoch
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffPurchases({
      status: statusFilter.value || undefined,
      company_id: projectFilter.value || undefined,
      buyer_id: buyerFilter.value || undefined,
      page: page.value,
      per_page: perPage,
    })
    if (mine !== epoch) return
    items.value = resp.items
    total.value = resp.total
  } catch {
    if (mine !== epoch) return
    error.value = true
  } finally {
    if (mine === epoch) loading.value = false
  }
}

function goToPrevPage(): void {
  page.value--
  void load()
}

function goToNextPage(): void {
  page.value++
  void load()
}

// A new filter starts again from the first page.
watch([statusFilter, projectFilter, buyerFilter], () => {
  page.value = 1
  void load()
})

// -- The project filter -------------------------------------------------------
//
// A member with company_manage picks from every project; any other reads the
// projects that have products on sale (the storefront's list, which needs no
// right). A failed read leaves the filter empty and the list unfiltered.

const projectOptions = ref<{ value: string; label: string }[]>([])

async function loadProjects(): Promise<void> {
  try {
    if (canListProjects.value) {
      const resp = await fetchStaffCompanies({ per_page: 100 })
      projectOptions.value = resp.items.map((c) => ({ value: c.id, label: c.name }))
      return
    }
    const resp = await listProducts({ per_page: 100 })
    const seen = new Map<string, string>()
    for (const p of resp.items) seen.set(p.company_id, p.company_name)
    projectOptions.value = [...seen].map(([value, label]) => ({ value, label }))
  } catch {
    projectOptions.value = []
  }
}

const statusOptions = computed(() => STATUSES.map((s) => ({ value: s, label: statusLabel(s) })))

// -- Row words ------------------------------------------------------------------

function statusLabel(status: string): string {
  return tOrRaw(t, `staff.purchases.statuses.${status}`, status)
}

function kindLabel(kind: string): string {
  return tOrRaw(t, `staff.purchases.kinds.${kind}`, kind)
}

function statusVariant(status: string): 'success' | 'warning' | 'neutral' | 'danger' {
  if (status === 'active') return 'success'
  if (status === 'pending_acceptance') return 'warning'
  if (status === 'reversed') return 'danger'
  return 'neutral'
}

function buyerLabel(row: StaffPurchaseItem): string {
  return row.buyer_name || row.buyer_email || row.buyer_id.slice(0, 8)
}

/** A staff gift the recipient has not accepted yet: the only row with Cancel. */
function cancellable(row: StaffPurchaseItem): boolean {
  return canCancel.value && row.kind === 'gift' && row.status === 'pending_acceptance'
}

// -- Cancel -----------------------------------------------------------------------

const cancellingId = ref<string | null>(null)

async function handleCancel(row: StaffPurchaseItem): Promise<void> {
  if (cancellingId.value) return
  cancellingId.value = row.id
  try {
    await cancelGift(row.id)
    showToast(t('staff.gifts.cancelled'), 'success')
    await load()
  } catch (err) {
    const reason =
      err instanceof ApiResponseError && err.detail ? err.detail : t('staff.gifts.cancelError')
    showToast(reason, 'error')
  } finally {
    cancellingId.value = null
  }
}

onMounted(() => {
  void load()
  void loadProjects()
})
</script>

<template>
  <div class="purch">
    <p class="purch__hint">{{ t('staff.purchases.hint') }}</p>

    <div class="purch__filters">
      <CSelect
        v-model="statusFilter"
        :label="t('staff.purchases.filterStatus')"
        :placeholder="t('staff.purchases.filterAll')"
        :options="statusOptions"
      />
      <CSelect
        v-if="projectOptions.length"
        v-model="projectFilter"
        :label="t('staff.purchases.filterProject')"
        :placeholder="t('staff.purchases.filterAll')"
        :options="projectOptions"
      />
      <div class="purch__buyer">
        <span class="purch__label">{{ t('staff.purchases.filterBuyer') }}</span>
        <UserPicker v-model="buyerFilter" />
      </div>
    </div>

    <div v-if="loading" class="purch__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error" class="purch__center">
      <p class="purch__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <CEmptyState v-else-if="!items.length" :title="t('staff.purchases.empty')">
      <template #icon>
        <ShoppingBag :size="40" />
      </template>
    </CEmptyState>

    <ul v-else class="purch__list">
      <li v-for="row in items" :key="row.id" class="purch__row">
        <div class="purch__main">
          <div class="purch__top">
            <span class="purch__buyer-name">{{ buyerLabel(row) }}</span>
            <span class="purch__date">{{ formatDate(row.created_at, locale) }}</span>
          </div>
          <div class="purch__sub">{{ row.company_name }} &mdash; {{ row.product_name }}</div>
          <div class="purch__sub">
            {{ t('staff.purchases.partsCount', { n: formatNumber(row.units, locale) }) }}
            &bull; {{ formatPrice(row.paid_cents, 'USD') }}
          </div>
        </div>
        <div class="purch__side">
          <span class="purch__kind">{{ kindLabel(row.kind) }}</span>
          <CBadge :variant="statusVariant(row.status)" :text="statusLabel(row.status)" />
          <button
            v-if="cancellable(row)"
            type="button"
            class="purch__cancel"
            :disabled="cancellingId === row.id"
            @click="handleCancel(row)"
          >
            {{ t('staff.gifts.cancel') }}
          </button>
        </div>
      </li>
    </ul>

    <div v-if="!loading && !error && totalPages > 1" class="purch__pagination">
      <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage()">
        &larr;
      </CButton>
      <span class="purch__page">{{ page }} / {{ totalPages }}</span>
      <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage()">
        &rarr;
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.purch {
  padding: var(--space-4);
}

.purch__hint {
  margin: 0 0 var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-inline-size: var(--maxw-prose);
}

.purch__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
  margin-block-end: var(--space-4);
}

.purch__buyer {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-inline-size: 14rem;
}

.purch__label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.purch__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-sm);
  gap: var(--space-3);
}

.purch__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.purch__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.purch__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-block-end: thin solid var(--border-default);
}

.purch__main {
  flex: 1;
  min-inline-size: 0;
}

.purch__top {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
}

.purch__buyer-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.purch__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.purch__sub {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.purch__side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
  flex-shrink: 0;
}

.purch__kind {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.purch__cancel {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--danger);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) 0;
  text-decoration: underline;
}
.purch__cancel:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.purch__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-block-start: var(--space-4);
}

.purch__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
</style>
