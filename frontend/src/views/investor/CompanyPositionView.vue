<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanyPositionView (Phase F4.4 B3)
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
//     2. Purchase list -- one row per PurchaseItemResponse with a
//        "Certificate" button that opens CertificateSheet.
//     3. Infinite scroll sentinel at the bottom.
//     4. loadMore error banner + Retry when currentLoadMoreErrored.
//
// 404 behaviour.
//   Backend 404s when the caller has no active purchases in the
//   requested company. The store flips currentErrored; the template
//   renders a NOT-FOUND state with a "back to portfolio" CTA.
//
// CERTIFICATE FLOW.
//   Tapping "Certificate" on a purchase row sets selectedPurchaseId
//   and opens CertificateSheet. The sheet owns the fetch via
//   useCertificateBlob; this view only tracks which row is active.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { CalendarClock, FileText, Gift, ShoppingCart } from 'lucide-vue-next'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import CertificateSheet from '@/components/shared/CertificateSheet.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
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
// Certificate sheet selection
// ---------------------------------------------------------------------------

const selectedPurchaseId = ref<string | null>(null)
const certificateSheetOpen = computed<boolean>(
  () => selectedPurchaseId.value !== null,
)

function openCertificate(p: PurchaseItemResponse): void {
  selectedPurchaseId.value = p.id
}
function closeCertificate(): void {
  selectedPurchaseId.value = null
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
  if (router.options.history.state.back) {
    router.back()
    return
  }
  router.push({ name: portfolioRouteName.value })
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
    <CHeader
      :show-back="true"
      :show-logo="false"
      :title="headerTitle"
      @back="goBack"
    />

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
            <li
              v-for="p in currentPurchases"
              :key="p.id"
              class="cp__item"
            >
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
                  <span
                    v-if="p.legal_basis !== 'gift'"
                    class="cp__item-stat"
                  >
                    {{ formatPrice(p.paid_cents) }}
                  </span>
                </div>
              </div>
              <div class="cp__item-actions">
                <CButton
                  variant="outline"
                  size="sm"
                  @click="openCertificate(p)"
                >
                  <FileText :size="14" />
                  {{ t('inv.companyPosition.purchases.certificate') }}
                </CButton>
              </div>
            </li>
          </ul>

          <!-- Infinite scroll sentinel (only when we have items) -->
          <div
            v-if="currentPurchases.length > 0"
            ref="sentinelRef"
            class="cp__sentinel"
          >
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

    <!-- Certificate sheet -->
    <CertificateSheet
      :open="certificateSheetOpen"
      :purchase-id="selectedPurchaseId"
      @close="closeCertificate"
    />
  </div>
</template>

<style scoped>
.cp {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
}

.cp__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 240px;
  padding: 24px;
}
.cp__center--small {
  min-height: 120px;
  padding: 12px;
}

.cp__body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 16px;
}

/* Aggregate block */
.cp__aggregate {
  padding: 18px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  color: var(--on-primary, #fff);
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}
.cp__agg-value {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.1;
}
.cp__agg-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;
}
.cp__agg-label {
  font-size: 11px;
  opacity: 0.85;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 2px;
}
.cp__agg-val {
  font-size: 15px;
  font-weight: 700;
}

/* Purchases list */
.cp__section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: 8px 0 10px;
}

.cp__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cp__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
}

.cp__item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cp__item-icon--sale {
  background: var(--primary-dim, var(--bg-subtle));
  color: var(--primary);
}
.cp__item-icon--gift {
  background: var(--success-dim, var(--bg-subtle));
  color: var(--success);
}
.cp__item-icon--installment {
  background: var(--warning-dim, var(--bg-subtle));
  color: var(--warning, var(--accent));
}

.cp__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cp__item-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.cp__item-kind {
  font-weight: 700;
  color: var(--text);
}
.cp__item-date {
  color: var(--text-tertiary);
  font-size: 12px;
}
.cp__item-stats {
  display: flex;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.cp__item-actions {
  flex-shrink: 0;
}

/* Sentinel */
.cp__sentinel {
  display: flex;
  justify-content: center;
  padding: 16px 0 0;
  min-height: 32px;
}

/* loadMore error banner */
.cp__loadmore-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--danger-dim);
  color: var(--danger);
  font-size: 13px;
}
.cp__loadmore-error-text {
  flex: 1;
  min-width: 0;
}
</style>
