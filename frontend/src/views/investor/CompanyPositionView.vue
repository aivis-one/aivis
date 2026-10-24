<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyPositionView
//                       (Phase F4.4 B3 + iter 2.5 batch 2 + batch 7)
// =============================================================================
//
// Per-company investor position detail. Sub-route under the portfolio
// tree: /investor/portfolio/:id and /agent/portfolio/:id. Not a
// top-level tab -- the frame's header (K25, `useScreenHeader`) holds the company
// name as the title and a back control that pops the history entry.
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
//   Top: the frame's header with the company name as title + back control.
//   Body, scrollable:
//     1. Aggregate block -- the brand card (K07): the current value and a
//        two-column grid of facts (total units / avg price / invested /
//        purchased / gifted).
//     1a. Ownership certificate action -- one button that opens the
//         AgreementSheet (mode='ownership') for the company-level
//         ownership document (iter 2.5 R2 §5.5 batch 7).
//     2. Purchase list -- one Booking card (KN1) per PurchaseItemResponse: the
//        kind and its badge, the booked date, the units and the amount paid
//        (a gift has none; the price of a part is never shown, decided by the
//        owner, 2026-10-23), and one view button labelled by legal_basis
//        (Purchase agreement / Gift certificate / Installment subcontract).
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
//
// DOCUMENT LINK (P-106).
//   A document email lands here with the document named in the query
//   (`?doc=ownership`, `?doc=agreement&purchase=<id>`; the shape and
//   its parser live in router/documentLink.ts). The named sheet opens
//   once the position has loaded -- not before, so a link to a company
//   the reader holds nothing in shows the NOT-FOUND state alone rather
//   than a document floating over it. An agreement's title comes from
//   its row when that row is on the first page; a purchase further
//   down the list opens under the generic "Document" title (accepted
//   by the owner). Closing the sheet drops `doc` / `purchase` from the
//   URL, so neither refresh nor history reopens a document the reader
//   has already closed.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import {
  AlertTriangle,
  CalendarClock,
  FileSignature,
  FileText,
  Gift,
  ShoppingCart,
} from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import AgreementSheet from '@/components/shared/AgreementSheet.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { usePortfolioStore } from '@/stores/portfolio'
import { isAgentShell } from '@/router/helpers'
import { parseDocumentQuery } from '@/router/documentLink'
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
  dropLinkedDocument()
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
  dropLinkedDocument()
}

// Document named by an email link -- see DOCUMENT LINK in the header.
const linkedDocument = computed(() => parseDocumentQuery(route.query))

watch(
  [currentDetail, linkedDocument],
  ([detail, request]) => {
    if (detail === null || request === null) return
    if (request.kind === 'ownership') {
      ownershipSheetOpen.value = true
      return
    }
    const row = currentPurchases.value.find((p) => p.id === request.purchaseId)
    selectedPurchaseId.value = request.purchaseId
    selectedLegalBasis.value = row?.legal_basis ?? null
  },
  { immediate: true },
)

function dropLinkedDocument(): void {
  if (route.query.doc === undefined && route.query.purchase === undefined) return
  const query = { ...route.query }
  delete query.doc
  delete query.purchase
  void safeNavigate(router.replace({ query }), '[CompanyPositionView] drop document link')
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

// The frame's header: the company name and the back control. Prefer the
// history step so the PortfolioView scroll/state restore for free; a
// deep-link into this view goes to the portfolio.
useScreenHeader({
  title: headerTitle,
  back: () => (window.history.state?.back ? true : { name: portfolioRouteName.value }),
})

function goBack(): void {
  // The not-found state's own button: same rule as the header's back control.
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
    return new Date(iso).toLocaleDateString(locale.value, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function basisIcon(basis: string) {
  if (basis === 'gift') return Gift
  if (basis === 'installment_tranche') return CalendarClock
  return ShoppingCart
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
    <CLoader v-if="currentLoading && currentDetail === null && !currentErrored" />

    <!-- Error (covers both backend failure and 404 no-position) -->
    <CEmptyState
      v-else-if="currentErrored"
      tone="danger"
      :title="t('inv.companyPosition.notFound.title')"
      :description="t('inv.companyPosition.notFound.description')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="goBack">
          {{ t('common.back') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else-if="currentDetail">
      <!-- Aggregate: the brand card (K07); a figure on it takes --on-primary -->
      <section class="ds-card ds-card--brand">
        <p class="ds-card__figure">
          {{ formatPrice(currentDetail.current_value_cents) }}
        </p>
        <div class="cp__agg-grid">
          <div>
            <p class="ds-card__label">
              {{ t('inv.companyPosition.aggregate.totalUnits') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(currentDetail.total_units, locale) }}
            </p>
          </div>
          <div>
            <p class="ds-card__label">
              {{ t('inv.companyPosition.aggregate.avgPrice') }}
            </p>
            <p class="ds-card__delta">
              {{ formatPrice(currentDetail.avg_price_cents) }}
            </p>
          </div>
          <div>
            <p class="ds-card__label">
              {{ t('inv.companyPosition.aggregate.invested') }}
            </p>
            <p class="ds-card__delta">
              {{ formatPrice(currentDetail.total_paid_cents) }}
            </p>
          </div>
          <div>
            <p class="ds-card__label">
              {{ t('inv.companyPosition.aggregate.saleUnits') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(currentDetail.sale_units, locale) }}
            </p>
          </div>
          <div v-if="currentDetail.gift_units > 0">
            <p class="ds-card__label">
              {{ t('inv.companyPosition.aggregate.giftUnits') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(currentDetail.gift_units, locale) }}
            </p>
          </div>
        </div>

        <!--
          Ownership certificate action (iter 2.5 R2 §5.5 batch 7).
          Lives inside the aggregate card because the document is
          scoped to the (caller, company) pair -- it's a position-
          level summary, not a per-purchase artifact.

          Email-me is intentionally absent here -- AgreementSheet
          carries its own email action inside the preview UI, so
          duplicating it as a row-level button would be redundant.
        -->
        <footer class="ds-card__foot">
          <CButton variant="outline" size="sm" inline @click="openOwnership">
            <FileSignature size="sm" />
            {{ t('inv.companyPosition.ownership.viewCertificate') }}
          </CButton>
        </footer>
      </section>

      <!-- Purchases -->
      <section class="cp__purchases" aria-labelledby="cp-purchases">
        <h2 id="cp-purchases" class="cp__section-title">
          {{ t('inv.companyPosition.purchases.title') }}
        </h2>

        <!-- Empty (happens only when total > 0 but current page
             somehow arrived empty -- a race edge, not the normal
             case. Keep a graceful message rather than a dead
             silence.) -->
        <CEmptyState
          v-if="currentPurchases.length === 0 && !currentLoading"
          :title="t('inv.companyPosition.purchases.empty')"
        />

        <ul v-else class="cp__list">
          <li v-for="p in currentPurchases" :key="p.id">
            <!-- One purchase: the Booking card (KN1) -->
            <article class="ds-card ds-booking" :aria-labelledby="`cp-purchase-${p.id}`">
              <header class="ds-booking__head">
                <span class="ds-booking__icon" aria-hidden="true">
                  <component :is="basisIcon(p.legal_basis)" size="sm" />
                </span>
                <h3 :id="`cp-purchase-${p.id}`" class="ds-booking__title">
                  {{ viewLabelForLegalBasis(p.legal_basis) }}
                </h3>
                <span class="ds-badge ds-badge--info">{{ legalBasisLabel(p.legal_basis) }}</span>
              </header>
              <dl class="ds-booking__facts">
                <div>
                  <dt>{{ t('inv.installmentPlans.list.item.created') }}</dt>
                  <dd>{{ formatDate(p.created_at) }}</dd>
                </div>
                <div>
                  <dt>{{ t('inv.companyPosition.purchases.units') }}</dt>
                  <dd>{{ formatNumber(p.units, locale) }}</dd>
                </div>
                <div v-if="p.legal_basis !== 'gift'">
                  <dt>{{ t('inv.companyPosition.purchases.paid') }}</dt>
                  <dd>{{ formatPrice(p.paid_cents) }}</dd>
                </div>
              </dl>
              <ul class="ds-booking__docs">
                <li class="ds-row ds-docrow">
                  <span class="ds-row__lead"><FileText size="sm" /></span>
                  <span class="ds-row__body">
                    <button
                      type="button"
                      class="ds-button ds-button--ghost"
                      data-size="sm"
                      @click="openCertificate(p)"
                    >
                      {{ viewLabelForLegalBasis(p.legal_basis) }}
                    </button>
                  </span>
                </li>
              </ul>
            </article>
          </li>
        </ul>

        <!-- Infinite scroll sentinel (only when we have items) -->
        <div v-if="currentPurchases.length > 0" ref="sentinelRef" class="cp__sentinel">
          <CLoader v-if="currentLoading" :size="20" />
        </div>

        <!-- loadMore error banner (FP-16 retry-storm brake) -->
        <div
          v-if="currentPurchases.length > 0 && currentLoadMoreErrored && !currentLoading"
          class="ds-alert ds-alert--danger"
          role="alert"
        >
          <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ t('inv.companyPosition.errorTitle') }}</p>
            <div class="ds-alert__actions">
              <CButton variant="outline" size="sm" inline @click="retryLoadMore">
                {{ t('common.retry') }}
              </CButton>
            </div>
          </div>
        </div>
      </section>
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
      :company-name="currentDetail?.company_name"
      @close="closeCertificate"
    />
    <AgreementSheet
      :id="companyId"
      :open="ownershipSheetOpen"
      mode="ownership"
      :company-name="currentDetail?.company_name"
      @close="closeOwnership"
    />
  </div>
</template>

<style scoped>
.cp {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Aggregate facts: two columns, as before */
.cp__agg-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3) var(--space-4);
}

/* Purchases list */
.cp__purchases {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.cp__section-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.cp__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Sentinel */
.cp__sentinel {
  display: flex;
  justify-content: center;
  min-block-size: var(--size-md);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a desktop it stretches its contents to fill. Past a point the
   extra room should be whitespace, not wider furniture. The COLUMN COUNT IS
   DELIBERATELY UNCHANGED; only the ceiling is added. Mobile-first, so this is
   a min-width and the phone is untouched. */
@media (min-width: 880px) {
  .cp__agg-grid {
    max-inline-size: calc(2 * var(--tile-max));
  }
}
</style>
