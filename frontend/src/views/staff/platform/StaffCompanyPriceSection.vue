<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyPriceSection (iter 2.7 Block C / C2)
// =============================================================================
//
// The price of a part + the immutable history of the project's revaluations +
// edit modal. The price of a part is the project's valuation divided by
// 1,000,000,000, so each row of the history is a revaluation of the project;
// the screen says so under its title.
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
// FP-23 permission gate. The price change requires BOTH project_manage
// AND financial_operations server-side (narrowed from company_manage,
// TASK-30 §7). The edit CTA is therefore gated on canEdit = canManage
// && canFinancial (template guard), and the save handler re-checks
// defensively (console.warn + bail). Viewing the history needs only
// company_manage, which the parent route already enforces -- so a
// staffer without project_manage sees the price + history read-only,
// no edit button.
//
// Price is entered in dollars in the modal and converted to integer
// cents for the wire (UpdatePriceRequest.price_per_unit_cents). Display
// everywhere is dollars via formatPrice.
// =============================================================================

import { ref, onMounted, computed, watch, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState, CModal, CInput, CStatCard } from '@/components/ui'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { fetchStaffCompanyPriceHistory, updateStaffCompanyPrice } from '@/api/staff-companies'
import type { PriceHistoryResponse } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// FP-23: edit requires project_manage AND financial_operations.
const canManage = canDo('project_manage')
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
const currentPriceCents = ref<number | null>(ctx?.company.value?.price_per_unit_cents ?? null)

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
const page = useUrlPage()
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
    console.warn(
      '[StaffCompanyPriceSection] openEdit blocked: needs company_manage + financial_operations',
    )
    return
  }
  // Prefill with the current price in dollars (2dp), or empty if unknown.
  priceDraft.value =
    currentPriceCents.value !== null ? (currentPriceCents.value / 100).toFixed(2) : ''
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
    <!-- Current price (K46) + edit CTA -->
    <div class="scpr__current">
      <CStatCard
        :label="t('staff.platform.price.current')"
        :value="currentPriceCents !== null ? formatPrice(currentPriceCents) : '—'"
      />
      <CButton v-if="canEdit" variant="primary" size="sm" inline @click="openEdit">
        {{ t('staff.platform.price.editCta') }}
      </CButton>
    </div>

    <!-- History -->
    <section class="scpr__history">
      <h2 class="scpr__history-title">
        {{ t('staff.platform.price.historyTitle') }}
      </h2>
      <p class="scpr__history-caption">
        {{ t('staff.platform.price.historyCaption') }}
      </p>

      <CListSkeleton v-if="loading" />

      <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="loadHistory">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <CEmptyState v-else-if="!history.length" :title="t('staff.platform.price.historyEmpty')" />

      <template v-else>
        <!-- Two columns, so rows (K23): the price, and when it was set -->
        <ul class="ds-rows price-history">
          <li v-for="row in history" :key="row.id" class="ds-row price-history__row">
            <span class="ds-row__body">
              <span
                class="ds-row__title"
                :aria-label="`${t('staff.platform.price.colPrice')} ${formatPrice(row.price_per_unit_cents)}`"
                >{{ formatPrice(row.price_per_unit_cents) }}</span
              >
              <span class="ds-row__meta"
                >{{ t('staff.platform.price.colChangedAt') }}
                {{ formatDateTime(row.changed_at) }}</span
              >
            </span>
          </li>
        </ul>

        <!-- Pagination (K17) -->
        <CPager :page="page" :total-pages="totalPages" @update:page="(n: number) => (page = n)" />
      </template>
    </section>

    <!-- Edit modal -->
    <CModal :open="showEdit" :title="t('staff.platform.price.editTitle')" @close="showEdit = false">
      <p class="ds-dialog__text">
        {{ t('staff.platform.price.editHint') }}
      </p>
      <CInput
        v-model="priceDraft"
        type="number"
        :label="t('staff.platform.price.fieldPrice')"
        :placeholder="t('staff.platform.price.fieldPricePlaceholder')"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scpr {
  display: grid;
  gap: var(--space-5);
  align-content: start;
}

.scpr__current {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.scpr__history {
  display: grid;
  gap: var(--space-3);
}

.scpr__history-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.scpr__history-caption {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  max-inline-size: var(--maxw-prose);
}
</style>
