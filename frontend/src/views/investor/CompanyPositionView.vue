<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanyPositionView
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
//     1a. Ownership certificate row -- two buttons (view / email)
//         for the company-level ownership document (iter 2.5 R2 §5.5
//         batch 7).
//     2. Purchase list -- one row per PurchaseItemResponse with two
//        per-row buttons: view (legal-basis-labelled) + email. Both
//        share the page-level email cooldown.
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
//       sandboxed iframe; tap email -> POST /agreement/email with a
//       shared cooldown lock.
//     - Per-company ownership certificate (mode='ownership'): tap the
//       header's view button -> a SECOND AgreementSheet instance
//       renders the ownership HTML; tap email -> POST
//       /ownership-certificate/email under the same cooldown lock.
//   Two sheet instances because their fetcher closures are pinned at
//   setup time -- one composable per surface, epoch counters do not
//   interfere with each other.
//
// EMAIL COOLDOWN (page-level).
//   Backend rate-limits the two email endpoints (5/60s per user, R2
//   §5.3). The UI adds a local 3s cooldown after any successful send
//   so a rapid tap on the next row doesn't burn another quota second.
//   The cooldown is page-level (shared across all email buttons) --
//   per-purchase per-button locks would over-engineer for a flow where
//   the user typically sends one document at a time, and a global lock
//   reads as more honest UX ("you just sent something, wait a beat")
//   than per-row "this one button is locked, but that one isn't".
//
// ERROR MAPPING (R2 §5.3 + §5.6 ERR-11-01).
//   429 -> "Too many requests" toast (rateLimited).
//   500 -> "Document temporarily unavailable" toast (unavailable).
//   Everything else -> generic emailError toast.
//   404 on email is impossible from this UI (the user is the buyer
//   per route guard; the rows came from the user's own portfolio).
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import {
  CalendarClock,
  FileSignature,
  FileText,
  Gift,
  Mail,
  ShoppingCart,
} from 'lucide-vue-next'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import AgreementSheet from '@/components/shared/AgreementSheet.vue'
import { ApiResponseError } from '@/api/client'
import {
  emailAgreement,
  emailOwnershipCertificate,
} from '@/api/agreements'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { usePortfolioStore } from '@/stores/portfolio'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { PurchaseItemResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = usePortfolioStore()
const { showToast } = useToast()

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
const certificateSheetOpen = computed<boolean>(
  () => selectedPurchaseId.value !== null,
)

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
// instances each own their own useAgreementBlob -- epoch counters are
// per-instance, so loading one doesn't superseded the other.
const ownershipSheetOpen = ref<boolean>(false)

function openOwnership(): void {
  ownershipSheetOpen.value = true
}
function closeOwnership(): void {
  ownershipSheetOpen.value = false
}

// ---------------------------------------------------------------------------
// Email cooldown (page-level, shared across all email buttons)
// ---------------------------------------------------------------------------
//
// One in-flight flag and one cooldown timestamp serve both ownership
// and per-purchase email sends. Rationale: backend rate-limits both
// endpoints per-user (R2 §5.3, 5/60s), a successful send fills one
// quota slot, and the next send should wait a beat regardless of
// which document type it is. Per-button locks would let a fast-fingered
// user burn through both endpoints' quotas in parallel and hit 429s.
//
// EMAIL_COOLDOWN_MS sits below the backend 60s window -- the UI just
// keeps the user from oscillating "send -> send -> 429" within a
// second; the backend window remains the real ceiling.

const EMAIL_COOLDOWN_MS = 3_000

const emailSending = ref<boolean>(false)
const emailLockedUntil = ref<number>(0)
// We track which target the current pending email belongs to so the
// affected button can show "sending" while peers stay enabled-but-not-
// firing (until the in-flight one resolves). Null = nothing sending.
const emailPendingTarget = ref<'ownership' | string | null>(null)

function emailDisabled(target: 'ownership' | string): boolean {
  if (emailSending.value) return true
  if (Date.now() < emailLockedUntil.value) return true
  // Defensive guard: per-purchase email needs a real purchase id; the
  // ownership target is always valid once currentDetail is loaded.
  if (target !== 'ownership' && !target) return true
  return false
}

function emailIsThisTargetSending(target: 'ownership' | string): boolean {
  return emailSending.value && emailPendingTarget.value === target
}

/**
 * Map a thrown error from emailAgreement / emailOwnershipCertificate
 * onto the right toast. R2 §5.3 makes 429 and 500 first-class semantic
 * outcomes -- 429 is "user pushed too fast", 500 is "template_id NULL
 * or PDF render failed, broken infra, not user's fault" -- so they
 * each get their own user-facing copy.
 */
function emailErrorToast(err: unknown): void {
  if (err instanceof ApiResponseError) {
    if (err.status === 429) {
      showToast(t('inv.agreement.rateLimited'), 'error')
      return
    }
    if (err.status >= 500) {
      showToast(t('inv.agreement.unavailable'), 'error')
      return
    }
  }
  showToast(t('inv.agreement.emailError'), 'error')
}

async function onEmailOwnership(): Promise<void> {
  if (emailDisabled('ownership')) return
  emailSending.value = true
  emailPendingTarget.value = 'ownership'
  try {
    await emailOwnershipCertificate(companyId.value)
    showToast(t('inv.agreement.emailSuccess'), 'success')
    emailLockedUntil.value = Date.now() + EMAIL_COOLDOWN_MS
  } catch (err) {
    emailErrorToast(err)
  } finally {
    emailSending.value = false
    emailPendingTarget.value = null
  }
}

async function onEmailPurchase(p: PurchaseItemResponse): Promise<void> {
  if (emailDisabled(p.id)) return
  emailSending.value = true
  emailPendingTarget.value = p.id
  try {
    await emailAgreement(p.id)
    showToast(t('inv.agreement.emailSuccess'), 'success')
    emailLockedUntil.value = Date.now() + EMAIL_COOLDOWN_MS
  } catch (err) {
    emailErrorToast(err)
  } finally {
    emailSending.value = false
    emailPendingTarget.value = null
  }
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

          <!--
            Ownership certificate row (iter 2.5 R2 §5.5 batch 7).
            Lives inside the aggregate section because the document is
            scoped to the (caller, company) pair -- it's a position-
            level summary, not a per-purchase artifact.

            Both buttons are page-level-cooldown-aware via
            emailDisabled('ownership') and emailIsThisTargetSending.
          -->
          <div class="cp__ownership-actions">
            <CButton
              variant="outline"
              size="sm"
              @click="openOwnership"
            >
              <FileSignature :size="14" />
              {{ t('inv.companyPosition.ownership.viewCertificate') }}
            </CButton>
            <CButton
              variant="outline"
              size="sm"
              :disabled="emailDisabled('ownership')"
              @click="onEmailOwnership"
            >
              <Mail :size="14" />
              {{
                emailIsThisTargetSending('ownership')
                  ? t('inv.companyPosition.ownership.sending')
                  : t('inv.companyPosition.ownership.emailCertificate')
              }}
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
                  {{ viewLabelForLegalBasis(p.legal_basis) }}
                </CButton>
                <CButton
                  variant="outline"
                  size="sm"
                  :disabled="emailDisabled(p.id)"
                  @click="onEmailPurchase(p)"
                >
                  <Mail :size="14" />
                  {{
                    emailIsThisTargetSending(p.id)
                      ? t('inv.agreement.emailSending')
                      : t('inv.agreement.emailSend')
                  }}
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
      :open="certificateSheetOpen"
      mode="agreement"
      :id="selectedPurchaseId"
      :legal-basis="selectedLegalBasis ?? undefined"
      @close="closeCertificate"
    />
    <AgreementSheet
      :open="ownershipSheetOpen"
      mode="ownership"
      :id="companyId"
      @close="closeOwnership"
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
  /* Two buttons stacked vertically on narrow screens so a long
     "Installment subcontract" label doesn't push them off the row. */
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

/*
 * Ownership-certificate action row (iter 2.5 batch 7).
 *
 * Sits inside .cp__aggregate beneath the agg-grid. Horizontal flex
 * keeps the two buttons (view + email) side-by-side on mobile; both
 * are size="sm" so they fit comfortably under the stat grid without
 * dominating the visual hierarchy of the aggregate header.
 */
.cp__ownership-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
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
