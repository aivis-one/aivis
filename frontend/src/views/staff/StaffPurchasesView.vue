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
// be cancelled after the page it was granted from is closed. An active purchase
// that is not an installment tranche carries Reverse for a member who may review payments: a reason is required,
// the server takes the whole purchase back and returns its parts to the pool.
//
// GET  /api/v1/staff/purchases   (financial_operations; ?status= ?company_id= ?buyer_id= ?page= ?per_page=)
// POST /api/v1/staff/purchases/gifts/{id}/cancel   (financial_operations)
// POST /api/v1/staff/purchases/{id}/reverse   (payment_review)
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShoppingBag } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CModal, CSelect } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import UserPicker from '@/components/staff/UserPicker.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { ApiResponseError } from '@/api/client'
import { cancelGift, fetchStaffPurchases, reversePurchase } from '@/api/admin'
import { listProducts } from '@/api/products'
import { fetchStaffCompanies } from '@/api/staff-companies'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'
import type { StaffPurchaseItem } from '@/api/generated'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'
import { useUrlUserFilter } from '@/composables/useUrlUserFilter'

const { t, locale } = useI18n()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

const canCancel = canDo('financial_operations')
const canListProjects = canDo('company_manage')
const canReverse = canDo('payment_review')

const STATUSES = ['active', 'pending_acceptance', 'reversed', 'cancelled'] as const

// -- The list -----------------------------------------------------------------

const items = ref<StaffPurchaseItem[]>([])
const total = ref(0)
const page = useUrlPage()
const perPage = 20
const loading = ref(true)
const error = ref(false)
// An answer that arrives after a newer request was sent is dropped.
let epoch = 0

const statusFilter = ref('')
const projectFilter = ref('')
// The buyer is also read from the address (?buyer_id=), so the user card can open the list narrowed.
const buyerFilter = useUrlUserFilter('buyer_id')

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

function goToPage(n: number): void {
  page.value = n
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

// -- Reverse ----------------------------------------------------------------------

const REASON_MAX = 500
const reverseTarget = ref<StaffPurchaseItem | null>(null)
const reverseReason = ref('')
const reverseLoading = ref(false)
const reverseError = ref('')

/** An active purchase of a member who may review payments; an installment tranche is refused by the server, so it is not offered. */
function reversible(row: StaffPurchaseItem): boolean {
  return canReverse.value && row.status === 'active' && row.legal_basis !== 'installment_tranche'
}

function openReverse(row: StaffPurchaseItem): void {
  reverseTarget.value = row
  reverseReason.value = ''
  reverseError.value = ''
}

function closeReverse(): void {
  if (reverseLoading.value) return
  reverseTarget.value = null
}

async function handleReverse(): Promise<void> {
  const target = reverseTarget.value
  if (!target || reverseLoading.value) return
  const reason = reverseReason.value.trim()
  if (!reason) {
    reverseError.value = t('staff.purchases.reverseReasonRequired')
    return
  }
  reverseLoading.value = true
  reverseError.value = ''
  try {
    await reversePurchase(target.id, { reason })
    showToast(t('staff.purchases.reversedToast'), 'success')
    reverseTarget.value = null
    await load()
  } catch (err) {
    reverseError.value =
      err instanceof ApiResponseError && err.detail ? err.detail : t('staff.purchases.reverseError')
  } finally {
    reverseLoading.value = false
  }
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => load())

onMounted(() => {
  void load()
  void loadProjects()
})
</script>

<template>
  <div class="purch">
    <CAlert tone="info">
      {{ t('staff.purchases.hint') }}
    </CAlert>

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
      <UserPicker
        v-model="buyerFilter"
        class="purch__buyer"
        :label="t('staff.purchases.filterBuyer')"
      />
    </div>

    <CListSkeleton v-if="loading" />

    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState v-else-if="!items.length" :title="t('staff.purchases.empty')">
      <template #icon>
        <ShoppingBag />
      </template>
    </CEmptyState>

    <ul v-else class="ds-rows purch__list">
      <li v-for="row in items" :key="row.id" class="ds-row purch__row">
        <span class="ds-row__body">
          <span class="ds-row__title">{{ buyerLabel(row) }}</span>
          <span class="ds-row__meta">
            {{ formatDate(row.created_at, locale) }} &bull; {{ row.company_name }} &mdash;
            {{ row.product_name }}
          </span>
          <span class="ds-row__meta">
            {{ t('staff.purchases.partsCount', { n: formatNumber(row.units, locale) }) }}
            &bull; {{ formatPrice(row.paid_cents, 'USD') }}
          </span>
        </span>
        <span class="ds-row__trail">
          <span class="purch__kind">{{ kindLabel(row.kind) }}</span>
          <CBadge :variant="statusVariant(row.status)" :text="statusLabel(row.status)" />
          <button
            v-if="cancellable(row)"
            type="button"
            class="ds-button ds-button--secondary purch__cancel"
            data-size="sm"
            :disabled="cancellingId === row.id"
            @click="handleCancel(row)"
          >
            <span>{{ t('staff.gifts.cancel') }}</span>
          </button>
          <button
            v-if="reversible(row)"
            type="button"
            class="ds-button ds-button--danger purch__reverse"
            data-size="sm"
            @click="openReverse(row)"
          >
            <span>{{ t('staff.purchases.reverse') }}</span>
          </button>
        </span>
      </li>
    </ul>

    <!-- Pagination (K17) -->
    <CPager
      v-if="!loading && !error"
      :page="page"
      :total-pages="totalPages"
      @update:page="goToPage"
    />

    <!-- Reverse: a reason is required -->
    <CModal
      :open="reverseTarget !== null"
      :title="t('staff.purchases.reverse')"
      @close="closeReverse"
    >
      <p class="ds-dialog__text">
        {{ t('staff.purchases.reverseConfirm') }}
      </p>
      <p v-if="reverseTarget" class="ds-amount" data-size="sm" data-tone="danger">
        {{ formatPrice(reverseTarget.paid_cents, 'USD') }}
      </p>
      <CInput
        v-model="reverseReason"
        :label="t('staff.purchases.reverseReason')"
        :maxlength="REASON_MAX"
        :error="reverseError || undefined"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeReverse">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" inline :loading="reverseLoading" @click="handleReverse">
          {{ t('staff.purchases.reverse') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.purch {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  align-content: start;
}

.purch__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
}

.purch__buyer {
  min-inline-size: var(--center-md);
}

.purch__kind {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}
</style>
