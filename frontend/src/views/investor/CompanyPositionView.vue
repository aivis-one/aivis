<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyPositionView
//                       (Phase F4.4 B3 + iter 2.5 batch 2 + batch 7)
// =============================================================================
//
// Per-company investor position detail. Sub-route under the portfolio
// tree: /investor/portfolio/:id and /agent/portfolio/:id. Not a
// top-level tab -- renders CHeader with a back button that pops the
// history entry (matching the InvestorDepositView pattern).
//
// DATA.
//   usePortfolioStore (B1-post): setCompanyId(id) kicks a first-page
//   fetch and publishes into currentDetail / currentPurchases.
//   loadMorePurchases drives the infinite scroll. currentLoadMoreErrored
//   feeds the useInfiniteScroll paused param (FP-16, the retry-storm
//   brake from B1-post). clearCurrent is invoked on unmount so a
//   subsequent visit to a different position doesn't briefly flash
//   the previous company's data.
//
// LAYOUT.
//   Top: CHeader with company name as title + back button.
//   Body, scrollable:
//     1. Aggregate block -- two-column stat grid (total units / avg
//        price / invested / current value / purchased / gifted).
//     1a. Ownership certificate action -- one button that opens the
//         AgreementSheet (mode='ownership') for the company-level
//         ownership document (iter 2.5 R2 §5.5 batch 7).
//     2. Purchase list -- one row per PurchaseItemResponse with a
//        single view button labelled by legal_basis (Purchase agreement
//        / Gift certificate / Installment subcontract).
//     3. Infinite scroll sentinel at the bottom.
//     4. loadMore error banner + Retry when currentLoadMoreErrored.
//
// 404 behaviour.
//   Backend 404s when the caller has no active purchases in the
//   requested company. The store flips currentErrored; the template
//   renders a NOT-FOUND state with a "back to portfolio" CTA.
//
// DOCUMENT FLOW (iter 2.5 batch 7).
//   Two surfaces live in this view:
//     - Per-purchase agreement (mode='agreement'): tap a row's view
//       button -> AgreementSheet renders the agreement HTML in a
//       sandboxed iframe. The sheet owns its own email-me action,
//       so this view does NOT duplicate it as a row-level button.
//     - Per-company ownership certificate (mode='ownership'): tap the
//       header's view button -> a SECOND AgreementSheet instance
//       renders the ownership HTML; same rule -- email lives inside
//       the sheet, not as a header-level button.
//   Two sheet instances because their fetcher closures are pinned at
//   setup time -- one composable per surface, epoch counters do not
//   interfere with each other.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { CalendarClock, FileSignature, FileText, Gift, ShoppingCart } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import AgreementSheet from '@/components/shared/AgreementSheet.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { usePortfolioStore } from '@/stores/portfolio'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { PurchaseItemResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = usePortfolioStore()

// storeToRefs preserves reactivity on the refs used by
// useInfiniteScroll's paused param. The method references
// (setCompanyId / loadMorePurchases / ...) stay on `store`.
const {
  currentDetail,
  currentPurchases,
  currentLoading,
  currentErrored,
  currentLoadMoreErrored,
  hasMoreCurrentPurchases,
} = storeToRefs(store)

const companyId = computed<string>(() => route.params.id as string)

// ---------------------------------------------------------------------------
// Sheet selection
// ---------------------------------------------------------------------------

// Per-purchase sheet: selectedPurchaseId pins both the open-state and
// the id+legalBasis we feed AgreementSheet. legalBasis is captured
// alongside the id so a row tap freezes the title that will render
// inside the sheet (the watch on props.id inside the sheet uses these
// together).
const selectedPurchaseId = ref<string | null>(null)
const selectedLegalBasis = ref<string | null>(null)
const certificateSheetOpen = computed<boolean>(() => selectedPurchaseId.value !== null)

function openCertificate(p: PurchaseItemResponse): void {
  selectedPurchaseId.value = p.id
  selectedLegalBasis.value = p.legal_basis
}
function closeCertificate(): void {
  selectedPurchaseId.value = null
  selectedLegalBasis.value = null
}

// Per-company ownership sheet: independent state from the per-purchase
// sheet so both can co-exist without prop churn. The two AgreementSheet
// instances each own their own useAgreementBlob composable instance
// with an independent epoch counter. Loading one doesn't supersede
// the other.
const ownershipSheetOpen = ref<boolean>(false)

function openOwnership(): void {
  ownershipSheetOpen.value = true
}
function closeOwnership(): void {
  ownershipSheetOpen.value = false
}

// ---------------------------------------------------------------------------
// Infinite scroll on purchases
// ---------------------------------------------------------------------------

const sentinelRef = ref<HTMLElement | null>(null)

useInfiniteScroll(
  sentinelRef,
  hasMoreCurrentPurchases,
  store.loadMorePurchases,
  currentLoadMoreErrored,
)

function retryLoadMore(): void {
  store.clearLoadMoreError()
  void store.loadMorePurchases()
}

// ---------------------------------------------------------------------------
// Navigation / header
// ---------------------------------------------------------------------------

const portfolioRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-portfolio' : 'investor-portfolio',
)

const headerTitle = computed<string>(() => {
  return currentDetail.value?.company_name ?? t('inv.companyPosition.title')
})

function goBack(): void {
  // Prefer router.back() so the PortfolioView scroll/state restore
  // for free. Fall back to explicit push when there's no prior
  // history (deep-link into this view).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: portfolioRouteName.value }),
    '[CompanyPositionView] to portfolio',
  )
}

// ---------------------------------------------------------------------------
// Derived display helpers
// ---------------------------------------------------------------------------

function legalBasisLabel(basis: string): string {
  // server-driven enum -> tOrRaw per FP-15
  return tOrRaw(t, `inv.companyPosition.purchases.legalBasis.${basis}`, basis)
}

function legalBasisClass(basis: string): string {
  if (basis === 'gift') return 'cp__item-icon--gift'
  if (basis === 'installment_tranche') return 'cp__item-icon--installment'
  return 'cp__item-icon--sale'
}

/**
 * Map a Purchase.legal_basis to the localised label for the per-row
 * VIEW button (iter 2.5 batch 7).
 *
 * Replaces the legacy generic "Certificate" label. The mapping mirrors
 * AgreementSheet's title resolver, so the row button and the sheet
 * heading agree on the document name -- a sale row shows "Purchase
 * agreement" both on the button and inside the sheet's CHeader.
 *
 * Unknown values fall through to the generic "document" label rather
 * than the raw token so a future legal_basis (e.g. a fourth kind
 * landing before the i18n catalogue catches up) still reads
 * naturally. This is a deliberate divergence from the FP-15 raw-token
 * fallback used by `legalBasisLabel` (which is a CHIP, not a button
 * label) -- "Document" on a button is fine, "installment_tranche" on
 * a button is not.
 */
function viewLabelForLegalBasis(basis: string): string {
  switch (basis) {
    case 'sale':
      return t('inv.agreement.title.purchaseAgreement')
    case 'gift':
      return t('inv.agreement.title.giftCertificate')
    case 'installment_tranche':
      return t('inv.agreement.title.installmentSubcontract')
    default:
      return t('inv.agreement.title.document')
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void store.setCompanyId(companyId.value)
})

// If the user tapped a different company in PortfolioView while this
// view was mounted, vue-router reuses the component (same route
// record). Watch the id and re-run setCompanyId so the detail swaps
// in place.
watch(
  () => route.params.id,
  (nextId) => {
    if (typeof nextId !== 'string') return
    if (nextId === store.currentCompanyId) return
    void store.setCompanyId(nextId)
  },
)

onUnmounted(() => {
  // Drop per-company state + bump currentEpoch so any in-flight fetch
  // resolves into a no-op. Positions list on PortfolioView is
  // untouched -- it lives on portfolioEpoch.
  store.clearCurrent()
})
</script>

<template>
  <div class="cp">
    <!-- Initial load -->
    <div v-if="currentLoading && currentDetail === null && !currentErrored" class="cp__center">
      <CLoader :size="28" />
    </div>

    <!-- Error (covers both backend failure and 404 no-position) -->
    <div v-else-if="currentErrored" class="cp__center">
      <CEmptyState
        :title="t('inv.companyPosition.notFound.title')"
        :description="t('inv.companyPosition.notFound.description')"
      />
      <CButton variant="outline" size="sm" @click="goBack">
        {{ t('common.back') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="currentDetail">
      <!-- iter 2.7 batch B2: inline page-header replaces view-CHeader.
           Company name (resolved by headerTitle) goes here as the <h1>;
           back-link reuses the existing history-aware goBack(). B3:
           button shape extracted to CBackLink; .cp__page-header padding
           already handles spacing so no extra wrapper is needed. -->
      <div class="cp__page-header">
        <CBackLink :label="t('inv.companyPosition.backLink')" @click="goBack" />
        <h1 class="cp__page-title">
          {{ headerTitle }}
        </h1>
      </div>

      <div class="cp__body">
        <!-- Aggregate -->
        <section class="cp__aggregate">
          <div class="cp__agg-value">
            {{ formatPrice(currentDetail.current_value_cents) }}
          </div>
          <div class="cp__agg-grid">
            <div class="cp__agg-stat">
              <div class="cp__agg-label">
                {{ t('inv.companyPosition.aggregate.totalUnits') }}
              </div>
              <div class="cp__agg-val">
                {{ formatNumber(currentDetail.total_units, locale) }}
              </div>
            </div>
            <div class="cp__agg-stat">
              <div class="cp__agg-label">
                {{ t('inv.companyPosition.aggregate.avgPrice') }}
              </div>
              <div class="cp__agg-val">
                {{ formatPrice(currentDetail.avg_price_cents) }}
              </div>
            </div>
            <div class="cp__agg-stat">
              <div class="cp__agg-label">
                {{ t('inv.companyPosition.aggregate.invested') }}
              </div>
              <div class="cp__agg-val">
                {{ formatPrice(currentDetail.total_paid_cents) }}
              </div>
            </div>
            <div class="cp__agg-stat">
              <div class="cp__agg-label">
                {{ t('inv.companyPosition.aggregate.saleUnits') }}
              </div>
              <div class="cp__agg-val">
                {{ formatNumber(currentDetail.sale_units, locale) }}
              </div>
            </div>
            <div v-if="currentDetail.gift_units > 0" class="cp__agg-stat">
              <div class="cp__agg-label">
                {{ t('inv.companyPosition.aggregate.giftUnits') }}
              </div>
              <div class="cp__agg-val">
                {{ formatNumber(currentDetail.gift_units, locale) }}
              </div>
            </div>
          </div>

          <!--
            Ownership certificate action (iter 2.5 R2 §5.5 batch 7).
            Lives inside the aggregate section because the document is
            scoped to the (caller, company) pair -- it's a position-
            level summary, not a per-purchase artifact.

            Email-me is intentionally absent here -- AgreementSheet
            carries its own email action inside the preview UI, so
            duplicating it as a row-level button would be redundant.
          -->
          <div class="cp__ownership-actions">
            <CButton variant="outline" size="sm" @click="openOwnership">
              <FileSignature :size="16" />
              {{ t('inv.companyPosition.ownership.viewCertificate') }}
            </CButton>
          </div>
        </section>

        <!-- Purchases -->
        <section class="cp__purchases">
          <h2 class="cp__section-title">
            {{ t('inv.companyPosition.purchases.title') }}
          </h2>

          <!-- Empty (happens only when total > 0 but current page
               somehow arrived empty -- a race edge, not the normal
               case. Keep a graceful message rather than a dead
               silence.) -->
          <div
            v-if="currentPurchases.length === 0 && !currentLoading"
            class="cp__center cp__center--small"
          >
            <CEmptyState :title="t('inv.companyPosition.purchases.empty')" />
          </div>

          <ul v-else class="cp__list">
            <li v-for="p in currentPurchases" :key="p.id" class="cp__item">
              <div class="cp__item-icon" :class="legalBasisClass(p.legal_basis)">
                <Gift v-if="p.legal_basis === 'gift'" :size="16" />
                <CalendarClock v-else-if="p.legal_basis === 'installment_tranche'" :size="16" />
                <ShoppingCart v-else :size="16" />
              </div>
              <div class="cp__item-body">
                <div class="cp__item-line">
                  <span class="cp__item-kind">
                    {{ legalBasisLabel(p.legal_basis) }}
                  </span>
                  <span class="cp__item-date">
                    {{ formatDate(p.created_at) }}
                  </span>
                </div>
                <div class="cp__item-stats">
                  <span class="cp__item-stat">
                    {{ formatNumber(p.units, locale) }}
                    {{ t('inv.companyPosition.purchases.units') }}
                  </span>
                  <span v-if="p.legal_basis !== 'gift'" class="cp__item-stat">
                    {{ formatPrice(p.paid_cents) }}
                  </span>
                </div>
              </div>
              <div class="cp__item-actions">
                <CButton variant="outline" size="sm" @click="openCertificate(p)">
                  <FileText :size="16" />
                  {{ viewLabelForLegalBasis(p.legal_basis) }}
                </CButton>
              </div>
            </li>
          </ul>

          <!-- Infinite scroll sentinel (only when we have items) -->
          <div v-if="currentPurchases.length > 0" ref="sentinelRef" class="cp__sentinel">
            <CLoader v-if="currentLoading" :size="20" />
          </div>

          <!-- loadMore error banner (FP-16 retry-storm brake) -->
          <div
            v-if="currentPurchases.length > 0 && currentLoadMoreErrored && !currentLoading"
            class="cp__loadmore-error"
          >
            <span class="cp__loadmore-error-text">
              {{ t('inv.companyPosition.errorTitle') }}
            </span>
            <CButton variant="outline" size="sm" @click="retryLoadMore">
              {{ t('common.retry') }}
            </CButton>
          </div>
        </section>
      </div>
    </template>

    <!--
      Document sheets (iter 2.5 batch 7).

      Two AgreementSheet instances co-exist on this view -- one per
      surface. They share the AgreementSheet component but pin
      different fetchers at setup time via the `mode` prop, and each
      owns its own useAgreementBlob composable instance with an
      independent epoch counter. Loading the per-purchase sheet does
      not interrupt an in-flight per-company fetch (and vice versa).

      Per-purchase sheet (mode='agreement'):
        - open when selectedPurchaseId is set;
        - `legal-basis` prop drives the sheet title via
          inv.agreement.title.<basis>, matching the row's view button
          label produced by viewLabelForLegalBasis().
      Per-company ownership sheet (mode='ownership'):
        - open when ownershipSheetOpen is true;
        - id pinned to the active companyId; the sheet ignores
          legal-basis in ownership mode and always renders
          inv.agreement.title.ownership.
    -->
    <AgreementSheet
      :id="selectedPurchaseId"
      :open="certificateSheetOpen"
      mode="agreement"
      :legal-basis="selectedLegalBasis ?? undefined"
      @close="closeCertificate"
    />
    <AgreementSheet
      :id="companyId"
      :open="ownershipSheetOpen"
      mode="ownership"
      @close="closeOwnership"
    />
  </div>
</template>

<style scoped>
.cp {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.cp__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}
.cp__center--small {
  min-height: var(--center-sm);
  padding: var(--space-3);
}

/* iter 2.7 batch B2 -- inline page-header (back-link + title) replaces
   the previous view-CHeader. No hero on this view, so the title lives
   inside a header block at the top of the loaded branch. */
.cp__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4) var(--space-2);
}
.cp__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.cp__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: 0 var(--space-4);
}

/* Aggregate block */
.cp__aggregate {
  padding: var(--space-4);
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: var(--on-primary);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-3);
}

/* A6: `.cp__aggregate` is the azure gradient carrying --on-primary, but a
   CButton keeps its own variant colours -- `outline` paints --text-secondary
   text on a --border-default border, both tuned against --bg-page. Measured on
   the gradient: 1.02 in dark, 1.15 in light. --on-primary gives 5.85 / 8.48.
   Third instance of one shape: a semantic colour placed on a coloured panel.
   Scoped to this hero so the variant is unchanged everywhere else. */
.cp__aggregate .c-btn--outline {
  color: var(--on-primary);
  border-color: currentColor;
}
.cp__agg-value {
  font-size: var(--fs-3xl);
  font-weight: 700;
  line-height: 1.1;
}
.cp__agg-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3) var(--space-4);
}
.cp__agg-label {
  font-size: var(--fs-xs);
  opacity: 0.85;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: var(--space-1);
}
.cp__agg-val {
  font-size: var(--fs-sm);
  font-weight: 700;
}

/* Purchases list */
.cp__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-2) 0 var(--space-3);
}

.cp__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.cp__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
}

.cp__item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-md);
  border-radius: 50%;
  flex-shrink: 0;
}
.cp__item-icon--sale {
  background: var(--primary-dim);
  color: var(--primary);
}
.cp__item-icon--gift {
  background: var(--success-subtle);
  color: var(--success);
}
.cp__item-icon--installment {
  background: var(--warning-subtle);
  color: var(--warning);
}

.cp__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.cp__item-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
}
.cp__item-kind {
  font-weight: 700;
  color: var(--text-primary);
}
.cp__item-date {
  color: var(--text-tertiary);
  font-size: var(--fs-xs);
}
.cp__item-stats {
  display: flex;
  gap: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
}

.cp__item-actions {
  flex-shrink: 0;
}

/*
 * Ownership-certificate action (iter 2.5 batch 7).
 *
 * Sits inside .cp__aggregate beneath the agg-grid. Single button --
 * email-me lives inside the AgreementSheet preview, not here.
 */
.cp__ownership-actions {
  display: flex;
  margin-top: var(--space-4);
}

/* Sentinel */
.cp__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

/* loadMore error banner */
.cp__loadmore-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--danger-subtle);
  color: var(--danger);
  font-size: var(--fs-xs);
}
.cp__loadmore-error-text {
  flex: 1;
  min-width: 0;
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 820px) {
  .cp__agg-grid {
    max-width: calc(2 * var(--tile-max));
  }
}
</style>
