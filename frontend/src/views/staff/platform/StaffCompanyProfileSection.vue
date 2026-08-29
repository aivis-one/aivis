<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyProfileSection (iter 2.7 Block C)
// =============================================================================
//
// Company profile inspection, plus (TASK-30 ruling 12) a status
// control. Reads the company from the shared STAFF_COMPANY_KEY context
// (PERF-40-01) -- the parent detail view already loaded it for the
// header, so this section does not fire its own detail GET. Renders
// name, description, status, cover, price, supply, and the raw
// distribution_config.
//
// Editing most fields is out of MVP scope (R1 §4.3) -- this surface
// stays inspection-only for them. distribution_config is shown as
// pretty-printed JSON rather than a structured editor for the same
// reason.
//
// SUPPLY CONTROL (TASK-39 item 6 dilution ruling, owner, 2026-08-29).
//   total_supply now has a real mutating control too: PATCH
//   /api/v1/staff/companies/{id}/supply (update_supply() server-side),
//   gated on project_manage AND financial_operations -- same bar as the
//   price change in StaffCompanyPriceSection (FP-23), since this is
//   equally a financial operation and arguably a more consequential one
//   (it changes what existing investors own).
//
//   Unlike price, a total_supply change may or may not have a
//   consequence: it only recomputes something when the company HAS an
//   active option pool. So the edit modal fetches GET .../pool
//   (fetchStaffCompanyPool) when it opens: with no active pool, Save
//   commits directly (a plain field write, nothing to disclose); with
//   an active pool, a SEPARATE consequence-confirmation modal shows the
//   equity_percent move in numbers (X% -> Y%) before the PATCH fires --
//   the same two-step pattern CompanySettingsView.vue already uses for
//   its own price-change confirmation, and for the same reason: a
//   generic "are you sure?" is not this ruling's confirmation, a number
//   is. The preview percentage is computed client-side with plain
//   floating-point division for DISPLAY ONLY; the server (Decimal
//   arithmetic, pools/service.py::_compute_equity_percent) is the
//   authoritative value and the actual 100%-ceiling guard.
//
// STATUS CONTROL (TASK-30 ruling 12).
//   Unlike everything else on this surface, `status` now has a real
//   mutating control: PATCH /api/v1/staff/companies/{id} (update_company()
//   server-side), gated on project_manage -- the same permission that
//   gates the roadmap and attachment writes on the sibling sections
//   (StaffCompanyRoadmapSection, StaffCompanyDocumentsSection). Unlike
//   the price change (FP-23, gated on project_manage AND
//   financial_operations because it also touches distribution_config's
//   sibling money fields), status is project_manage alone --
//   update_company_endpoint only requires financial_operations when
//   `distribution_config` is present in the body, which it never is
//   here.
//
//   Staff is NOT restricted to one direction (unlike the project's own
//   ACTIVE -> HIDDEN-only self-service in CompanySettingsView): the
//   server validates against VALID_COMPANY_STATUS_TRANSITIONS (hidden
//   -> {active, archived}, active -> {hidden, archived}, archived -> {}
//   terminal). STATUS_TRANSITIONS below mirrors that table client-side
//   so the edit control only ever offers a legal target -- when the
//   current status is 'archived' there are none, so the edit CTA does
//   not render at all rather than opening a modal with an empty select.
//
// FP-25 self-hide: optional fields (description, cover) are omitted from
// the render when absent rather than showing empty rows.
// =============================================================================

import { inject, computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CLoader, CBadge, CButton, CEmptyState, CModal, CSelect, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import {
  updateStaffCompany,
  updateStaffCompanySupply,
  fetchStaffCompanyPool,
} from '@/api/staff-companies'
import { ApiResponseError } from '@/api/client'
import type { PoolResponse } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// project_manage only -- see STATUS CONTROL note above for why this
// does NOT also require financial_operations the way price does.
const canEditStatus = canDo('project_manage')

// SUPPLY CONTROL: project_manage AND financial_operations, same bar as
// StaffCompanyPriceSection's price edit (FP-23).
const canManageSupply = canDo('project_manage')
const canFinancialSupply = canDo('financial_operations')
const canEditSupply = computed<boolean>(
  () => canManageSupply.value && canFinancialSupply.value,
)

// PERF-40-01: read the company the parent detail view already loaded
// instead of firing a second GET /staff/companies/{id}. The injection
// is always present in practice -- sections only ever render inside
// StaffCompanyDetailView's <router-view>.
const ctx = inject(STAFF_COMPANY_KEY)

const company = computed(() => ctx?.company.value ?? null)
const loading = computed(() => ctx?.loading.value ?? false)
const error = computed(() => ctx?.error.value ?? false)

function reload(): void {
  void ctx?.reload()
}

const statusVariant = (s: string) => {
  if (s === 'active') return 'success'
  if (s === 'hidden') return 'warning'
  if (s === 'archived') return 'neutral'
  return 'neutral'
}

// ---------------------------------------------------------------------------
// Status control (TASK-30 ruling 12)
// ---------------------------------------------------------------------------

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// Mirrors backend/app/modules/companies/constants.py
// VALID_COMPANY_STATUS_TRANSITIONS -- kept in sync manually (small,
// stable table); the server is still the enforced source of truth,
// this only decides what the select offers.
const STATUS_TRANSITIONS: Record<string, string[]> = {
  hidden: ['active', 'archived'],
  active: ['hidden', 'archived'],
  archived: [],
}

function statusValueLabel(s: string): string {
  return t(`staff.platform.profile.statusValues.${s}`)
}

const availableTargets = computed<string[]>(() => {
  const current = company.value?.status
  if (!current) return []
  return STATUS_TRANSITIONS[current] ?? []
})

// The edit CTA only renders when there IS a legal target -- 'archived'
// is terminal, so a company in that state shows the badge with no
// button at all rather than an edit modal with an empty select.
const canShowStatusEdit = computed<boolean>(
  () => canEditStatus.value && availableTargets.value.length > 0,
)

const statusOptions = computed<{ value: string; label: string }[]>(() =>
  availableTargets.value.map((s) => ({ value: s, label: statusValueLabel(s) })),
)

const showStatusEdit = ref(false)
const statusDraft = ref('')
const savingStatus = ref(false)

function openStatusEdit(): void {
  if (!canShowStatusEdit.value) {
    console.warn(
      '[StaffCompanyProfileSection] openStatusEdit blocked: missing project_manage or no legal transition from the current status',
    )
    return
  }
  statusDraft.value = availableTargets.value[0] ?? ''
  showStatusEdit.value = true
}

async function handleStatusSave(): Promise<void> {
  if (!canEditStatus.value) {
    console.warn('[StaffCompanyProfileSection] handleStatusSave blocked: missing project_manage')
    return
  }
  const id = companyId.value
  const next = statusDraft.value
  if (!id || !next) return

  savingStatus.value = true
  try {
    await updateStaffCompany(id, { status: next })
    showStatusEdit.value = false
    showToast(t('staff.platform.profile.statusUpdated'), 'success')
    // Re-pull the detail through the shared context so every section
    // (this one included) sees the new status -- same pattern the
    // roadmap section uses after a mutation.
    await ctx?.reload()
  } catch (err) {
    const message = err instanceof ApiResponseError ? err.detail : t('common.error')
    showToast(message, 'error')
  } finally {
    savingStatus.value = false
  }
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

// ---------------------------------------------------------------------------
// Supply control (TASK-39 item 6 dilution ruling)
// ---------------------------------------------------------------------------

// Step 1: edit modal (draft input + pool lookup).
const showSupplyEdit = ref(false)
const supplyDraft = ref('') // as typed
const loadingPool = ref(false)
const activePool = ref<PoolResponse | null>(null)
// A FAILED pool lookup is NOT "no active pool" -- conflating the two
// (adversarial review finding) would let a transient network error
// silently skip the consequence-confirmation modal for a company that
// DOES have an active pool. Tracked separately so canSubmitSupply can
// block submission until a retry succeeds, rather than falling back to
// a plain-write path that assumes no dilution consequence exists.
const poolFetchFailed = ref(false)
const savingSupply = ref(false)

// Step 2: consequence-confirmation modal (only reachable when
// activePool is non-null -- see openSupplyEdit / handleSupplySave).
const showSupplyConfirm = ref(false)
const pendingTotalSupply = ref<number | null>(null)

async function loadPoolForSupplyEdit(): Promise<void> {
  loadingPool.value = true
  poolFetchFailed.value = false
  activePool.value = null
  try {
    activePool.value = await fetchStaffCompanyPool(companyId.value)
  } catch {
    // Do NOT fall back to "no active pool" here -- that would let a
    // transient network error silently skip the consequence-confirmation
    // modal for a company that DOES have one. canSubmitSupply blocks
    // submission entirely until a retry succeeds.
    poolFetchFailed.value = true
  } finally {
    loadingPool.value = false
  }
}

async function openSupplyEdit(): Promise<void> {
  if (!canEditSupply.value) {
    console.warn(
      '[StaffCompanyProfileSection] openSupplyEdit blocked: needs project_manage + financial_operations',
    )
    return
  }
  supplyDraft.value = company.value ? String(company.value.total_supply) : ''
  showSupplyEdit.value = true
  await loadPoolForSupplyEdit()
}

// Parse the draft into a positive integer. null blocks submission.
const draftTotalSupply = computed<number | null>(() => {
  const v = supplyDraft.value.trim()
  if (!v) return null
  const n = Number(v)
  if (!Number.isInteger(n) || n <= 0) return null
  return n
})

const canSubmitSupply = computed<boolean>(
  () =>
    draftTotalSupply.value !== null &&
    draftTotalSupply.value !== company.value?.total_supply &&
    !poolFetchFailed.value,
)

// Preview equity_percent for the confirmation modal. DISPLAY ONLY --
// see the module header note on why floating-point division is fine
// here but not on the server.
const previewEquityPercent = computed<number | null>(() => {
  const pool = activePool.value
  const newSupply = pendingTotalSupply.value
  if (!pool || newSupply === null || newSupply <= 0) return null
  return (pool.total_options / newSupply) * 100
})

const previewExceedsCeiling = computed<boolean>(
  () => previewEquityPercent.value !== null && previewEquityPercent.value > 100,
)

function formatPercent(pct: number): string {
  return `${pct.toFixed(4)}%`
}

async function handleSupplySave(): Promise<void> {
  if (!canEditSupply.value) {
    console.warn('[StaffCompanyProfileSection] handleSupplySave blocked: missing permission')
    return
  }
  const next = draftTotalSupply.value
  if (next === null || poolFetchFailed.value) return

  if (activePool.value === null) {
    // No active pool (a SUCCESSFUL lookup that found none, never a
    // failed one -- poolFetchFailed already blocked above): nothing
    // recomputes, so no consequence to confirm -- this is a plain
    // field write, matching the status control's own single-step save.
    await submitSupply(next)
    return
  }

  // Active pool: route through the consequence-confirmation modal
  // instead of saving directly.
  pendingTotalSupply.value = next
  showSupplyEdit.value = false
  showSupplyConfirm.value = true
}

async function handleConfirmSupply(): Promise<void> {
  const next = pendingTotalSupply.value
  if (next === null || previewExceedsCeiling.value) return
  // Only close the confirmation and discard the draft on a SUCCESSFUL
  // submit (adversarial review finding: submitSupply swallows its own
  // errors for its toast, so "it returned" is not "it succeeded" --
  // closing unconditionally here discarded a confirmed draft on a
  // failed PATCH with no way to retry from this screen).
  const ok = await submitSupply(next)
  if (ok) {
    showSupplyConfirm.value = false
    pendingTotalSupply.value = null
  }
}

function cancelSupplyConfirm(): void {
  showSupplyConfirm.value = false
  pendingTotalSupply.value = null
}

async function submitSupply(newTotalSupply: number): Promise<boolean> {
  savingSupply.value = true
  try {
    await updateStaffCompanySupply(companyId.value, { total_supply: newTotalSupply })
    showSupplyEdit.value = false
    showToast(t('staff.platform.profile.supplyUpdated'), 'success')
    // Re-pull the detail through the shared context so every section
    // sees the new total_supply, same pattern the status control uses.
    await ctx?.reload()
    return true
  } catch (err) {
    const message = err instanceof ApiResponseError ? err.detail : t('common.error')
    showToast(message, 'error')
    return false
  } finally {
    savingSupply.value = false
  }
}

// Pretty-print distribution_config for read-only inspection. It is a
// free-form JSONB on the backend, so we show it verbatim rather than
// assuming a fixed shape.
const distributionJson = computed<string>(() => {
  if (!company.value) return ''
  return JSON.stringify(company.value.distribution_config, null, 2)
})

// No local fetch -- the parent detail view owns the company load and
// provides it via STAFF_COMPANY_KEY. The retry button calls ctx.reload.
</script>

<template>
  <div class="scp">
    <!-- Loading -->
    <div v-if="loading" class="scp__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scp__center">
      <CButton variant="secondary" size="sm" @click="reload">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="company">
      <!-- Cover (FP-25 self-hide when absent) -->
      <div v-if="company.cover_url" class="scp__cover">
        <img :src="company.cover_url" :alt="company.name" class="scp__cover-img" />
      </div>

      <!-- Status + price + supply rows -->
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.status') }}</span>
        <div class="scp__status-cell">
          <CBadge :variant="statusVariant(company.status)" :text="company.status" />
          <CButton v-if="canShowStatusEdit" variant="outline" size="sm" @click="openStatusEdit">
            {{ t('staff.platform.profile.statusEditCta') }}
          </CButton>
        </div>
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.price') }}</span>
        <span class="scp__value">{{ formatPrice(company.price_per_unit_cents) }}</span>
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.totalSupply') }}</span>
        <div class="scp__status-cell">
          <span class="scp__value">{{ company.total_supply.toLocaleString() }}</span>
          <CButton v-if="canEditSupply" variant="outline" size="sm" @click="openSupplyEdit">
            {{ t('staff.platform.profile.supplyEditCta') }}
          </CButton>
        </div>
      </div>
      <div class="scp__row">
        <span class="scp__label">{{ t('staff.platform.profile.sharesPerOption') }}</span>
        <span class="scp__value">{{ company.shares_per_option }}</span>
      </div>

      <!-- Description (FP-25 self-hide when absent) -->
      <div v-if="company.description" class="scp__section">
        <h3 class="scp__section-title">
          {{ t('staff.platform.profile.description') }}
        </h3>
        <p class="scp__description">
          {{ company.description }}
        </p>
      </div>

      <!-- External links (FP-25 self-hide each when absent) -->
      <div
        v-if="company.logo_url || company.promo_video_url || company.presentation_url"
        class="scp__section"
      >
        <h3 class="scp__section-title">
          {{ t('staff.platform.profile.links') }}
        </h3>
        <ul class="scp__links">
          <li v-if="company.logo_url">
            <a :href="company.logo_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.logoUrl') }}
            </a>
          </li>
          <li v-if="company.promo_video_url">
            <a :href="company.promo_video_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.promoVideoUrl') }}
            </a>
          </li>
          <li v-if="company.presentation_url">
            <a :href="company.presentation_url" target="_blank" rel="noopener">
              {{ t('staff.platform.profile.presentationUrl') }}
            </a>
          </li>
        </ul>
      </div>

      <!-- distribution_config (raw JSON inspection) -->
      <div class="scp__section">
        <h3 class="scp__section-title">
          {{ t('staff.platform.profile.distributionConfig') }}
        </h3>
        <pre class="scp__json">{{ distributionJson }}</pre>
      </div>
    </template>

    <!-- Defensive empty (company null but no error/loading -- shouldn't happen) -->
    <CEmptyState v-else :title="t('common.noResults')" />

    <!-- Status edit modal (project_manage-gated) -->
    <CModal :open="showStatusEdit" @close="showStatusEdit = false">
      <h3 class="scp__modal-title">
        {{ t('staff.platform.profile.statusEditTitle') }}
      </h3>
      <p class="scp__modal-hint">
        {{ t('staff.platform.profile.statusEditHint') }}
      </p>
      <CSelect
        v-model="statusDraft"
        :label="t('staff.platform.profile.status')"
        :options="statusOptions"
      />
      <div class="scp__modal-actions">
        <CButton variant="outline" size="sm" @click="showStatusEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="savingStatus"
          :disabled="!statusDraft"
          @click="handleStatusSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Supply edit modal (project_manage + financial_operations) -->
    <CModal :open="showSupplyEdit" @close="showSupplyEdit = false">
      <h3 class="scp__modal-title">
        {{ t('staff.platform.profile.supplyEditTitle') }}
      </h3>
      <p class="scp__modal-hint">
        {{ t('staff.platform.profile.supplyEditHint') }}
      </p>
      <CInput
        v-model="supplyDraft"
        type="number"
        :label="t('staff.platform.profile.totalSupply')"
      />
      <p v-if="loadingPool" class="scp__modal-hint">
        {{ t('staff.platform.profile.supplyPoolLoading') }}
      </p>
      <template v-else-if="poolFetchFailed">
        <p class="scp__modal-error">
          {{ t('staff.platform.profile.supplyPoolLoadError') }}
        </p>
        <CButton variant="outline" size="sm" @click="loadPoolForSupplyEdit">
          {{ t('common.retry') }}
        </CButton>
      </template>
      <p v-else-if="activePool" class="scp__modal-hint">
        {{ t('staff.platform.profile.supplyPoolActiveHint') }}
      </p>
      <div class="scp__modal-actions">
        <CButton variant="outline" size="sm" @click="showSupplyEdit = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="savingSupply"
          :disabled="!canSubmitSupply || loadingPool"
          @click="handleSupplySave"
        >
          {{ activePool ? t('common.next') : t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Supply-change consequence confirmation (only when an active pool
         exists -- see the SUPPLY CONTROL header note). -->
    <CModal :open="showSupplyConfirm" @close="cancelSupplyConfirm">
      <h3 class="scp__modal-title">
        {{ t('staff.platform.profile.supplyConfirmTitle') }}
      </h3>
      <p v-if="activePool && pendingTotalSupply !== null" class="scp__modal-hint">
        {{
          t('staff.platform.profile.supplyConfirmBody', {
            oldPct: formatPercent(Number(activePool.equity_percent)),
            newPct:
              previewEquityPercent !== null ? formatPercent(previewEquityPercent) : '—',
          })
        }}
      </p>
      <p v-if="previewExceedsCeiling" class="scp__modal-error">
        {{ t('staff.platform.profile.supplyConfirmCeilingError') }}
      </p>
      <div class="scp__modal-actions">
        <CButton variant="outline" size="sm" @click="cancelSupplyConfirm">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="savingSupply"
          :disabled="previewExceedsCeiling"
          @click="handleConfirmSupply"
        >
          {{ t('staff.platform.profile.supplyConfirmSubmit') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scp {
  padding: var(--space-4);
}

.scp__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-md);
  gap: var(--space-4);
}

.scp__cover {
  margin-bottom: var(--space-4);
}
.scp__cover-img {
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: var(--radius-md);
  display: block;
}

.scp__row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}
.scp__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.scp__value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.scp__status-cell {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.scp__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.scp__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.scp__modal-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  margin: 0 0 var(--space-4);
}
.scp__modal-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

.scp__section {
  margin-top: var(--space-4-lg);
}
.scp__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.scp__description {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
}
.scp__links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.scp__links a {
  font-size: var(--fs-sm);
  color: var(--primary);
  text-decoration: underline;
  word-break: break-all;
}

.scp__json {
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  color: var(--text-primary);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  overflow-x: auto;
  margin: 0;
  white-space: pre;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.scp__description {
  max-width: var(--maxw-prose);
}
</style>
