<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyPriceSection (iter 2.7 Block C / C2)
// =============================================================================
//
// Current unit price + immutable price-history table + edit modal.
//
// Sources:
//   GET   /staff/companies/{id}/price-history (iter 2.6c B3) -- paginated,
//         newest-first.
//   GET   /staff/companies/{id}            -- current price (from the
//         company detail; the history head is NOT authoritative for
//         "current" because a fresh company has a price but no history
//         row yet).
//   PATCH /staff/companies/{id}/price      -- change price. Cascades to
//         products + appends a history row server-side.
//
// FP-23 permission gate. The price change requires BOTH company_manage
// AND financial_operations server-side. The edit CTA is therefore gated
// on canEdit = canManage && canFinancial (template guard), and the save
// handler re-checks defensively (console.warn + bail). Viewing the
// history needs only company_manage, which the parent route already
// enforces -- so a company_manage staffer without financial_operations
// sees the price + history read-only, no edit button.
//
// Price is entered in dollars in the modal and converted to integer
// cents for the wire (UpdatePriceRequest.price_per_unit_cents). Display
// everywhere is dollars via formatPrice.
// =============================================================================

import { ref, onMounted, computed, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import {
  fetchStaffCompanyPriceHistory,
  updateStaffCompanyPrice,
} from '@/api/staff-companies'
import type { PriceHistoryResponse } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// FP-23: edit requires company_manage AND financial_operations.
const canManage = canDo('company_manage')
const canFinancial = canDo('financial_operations')
const canEdit = computed<boolean>(() => canManage.value && canFinancial.value)

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// Current price (cents). Seeded from the company the parent detail
// view already loaded (PERF-40-01 -- no duplicate detail GET here),
// then kept as a local ref so a price change updates it from the
// PATCH response without round-tripping the parent. The header does
// not show price, so a brief divergence from the injected company is
// harmless.
const ctx = inject(STAFF_COMPANY_KEY)
const currentPriceCents = ref<number | null>(
  ctx?.company.value?.price_per_unit_cents ?? null,
)

// The parent may still be loading when this section mounts; sync the
// price once the injected company resolves (or changes).
watch(
  () => ctx?.company.value,
  (c) => {
    if (c) currentPriceCents.value = c.price_per_unit_cents
  },
)

// History table.
const history = ref<PriceHistoryResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const error = ref(false)

// Edit modal.
const showEdit = ref(false)
const priceDraft = ref('') // dollars, as typed
const saving = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

async function loadHistory(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffCompanyPriceHistory(id, {
      page: page.value,
      per_page: perPage,
    })
    history.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  // Price comes from the injected company; only the history is
  // this section's own fetch.
  await loadHistory()
}

// -- Edit --

function openEdit(): void {
  if (!canEdit.value) {
    console.warn('[StaffCompanyPriceSection] openEdit blocked: needs company_manage + financial_operations')
    return
  }
  // Prefill with the current price in dollars (2dp), or empty if unknown.
  priceDraft.value =
    currentPriceCents.value !== null
      ? (currentPriceCents.value / 100).toFixed(2)
      : ''
  showEdit.value = true
}

// Parse the dollar draft into integer cents. Returns null when the input
// is not a positive number -- canSubmit blocks the save in that case.
const draftCents = computed<number | null>(() => {
  const v = priceDraft.value.trim()
  if (!v) return null
  const dollars = Number(v)
  if (Number.isNaN(dollars) || dollars <= 0) return null
  return Math.round(dollars * 100)
})

const canSubmit = computed<boolean>(() => draftCents.value !== null)

async function handleSave(): Promise<void> {
  if (!canEdit.value) {
    console.warn('[StaffCompanyPriceSection] handleSave blocked: missing permission')
    return
  }
  const cents = draftCents.value
  if (cents === null) return

  saving.value = true
  try {
    const updated = await updateStaffCompanyPrice(companyId.value, {
      price_per_unit_cents: cents,
    })
    currentPriceCents.value = updated.price_per_unit_cents
    showToast(t('staff.platform.price.updated'), 'success')
    showEdit.value = false
    // A new history row was appended server-side; refetch page 1 to show
    // it at the top (newest-first).
    if (page.value !== 1) {
      page.value = 1 // page watcher reloads history
    } else {
      await loadHistory()
    }
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    saving.value = false
  }
}

watch(page, () => loadHistory())
watch(companyId, () => reload())
onMounted(reload)
</script>

<template>
  <div class="scpr">
    <!-- Current price + edit CTA -->
    <div class="scpr__current">
      <div class="scpr__current-info">
        <span class="scpr__current-label">{{ t('staff.platform.price.current') }}</span>
        <span class="scpr__current-value">
          {{ currentPriceCents !== null ? formatPrice(currentPriceCents) : '—' }}
        </span>
      </div>
      <CButton
        v-if="canEdit"
        variant="primary"
        size="sm"
        @click="openEdit"
      >{{ t('staff.platform.price.editCta') }}</CButton>
    </div>

    <!-- History -->
    <h3 class="scpr__history-title">{{ t('staff.platform.price.historyTitle') }}</h3>

    <div v-if="loading" class="scpr__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error" class="scpr__center">
      <CButton variant="secondary" size="sm" @click="loadHistory">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <CEmptyState
      v-else-if="!history.length"
      :title="t('staff.platform.price.historyEmpty')"
    />

    <template v-else>
      <div class="price-history">
        <div class="price-history__head">
          <span class="price-history__col-price">{{ t('staff.platform.price.colPrice') }}</span>
          <span class="price-history__col-date">{{ t('staff.platform.price.colChangedAt') }}</span>
        </div>
        <div
          v-for="row in history"
          :key="row.id"
          class="price-history__row"
        >
          <span class="price-history__col-price">{{ formatPrice(row.price_per_unit_cents) }}</span>
          <span class="price-history__col-date">{{ formatDateTime(row.changed_at) }}</span>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="scpr__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">&larr;</CButton>
        <span class="scpr__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">&rarr;</CButton>
      </div>
    </template>

    <!-- Edit modal -->
    <CModal :open="showEdit" @close="showEdit = false">
      <h3 class="scpr__modal-title">{{ t('staff.platform.price.editTitle') }}</h3>
      <p class="scpr__modal-hint">{{ t('staff.platform.price.editHint') }}</p>
      <CInput
        v-model="priceDraft"
        type="number"
        :label="t('staff.platform.price.fieldPrice')"
        :placeholder="t('staff.platform.price.fieldPricePlaceholder')"
      />
      <div class="scpr__modal-actions">
        <CButton variant="outline" size="sm" @click="showEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >{{ t('common.save') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scpr { padding: var(--space-4); }

.scpr__current {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px; background: var(--bg-subtle); border-radius: var(--radius-md);
  margin-bottom: 20px;
}
.scpr__current-info { display: flex; flex-direction: column; gap: 4px; }
.scpr__current-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
.scpr__current-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }

.scpr__history-title { font-size: 14px; font-weight: 700; color: var(--text-primary); margin: 0 0 8px; }

.scpr__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: 140px; gap: 16px;
}

.price-history { display: flex; flex-direction: column; }
.price-history__head {
  display: flex; padding: 8px 0; border-bottom: 2px solid var(--border-default);
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.price-history__row {
  display: flex; padding: 12px 0; border-bottom: 1px solid var(--border-default);
  font-size: 14px; color: var(--text-primary);
}
.price-history__col-price { flex: 0 0 40%; font-weight: 600; }
.price-history__col-date { flex: 1; color: var(--text-secondary); }

.scpr__pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 12px; margin-top: 16px;
}
.scpr__page { font-size: 13px; color: var(--text-secondary); }

.scpr__modal-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 8px; }
.scpr__modal-hint { font-size: 13px; color: var(--text-secondary); margin: 0 0 16px; }
.scpr__modal-actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }
</style>
