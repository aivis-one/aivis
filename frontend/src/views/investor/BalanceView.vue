<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- BalanceView (Phase F4.3 B2 + F4.4 B2 store rename)
// =============================================================================
//
// Investor balance screen: the ONE account of the buyer, the deposit, the way
// into the full list of operations, and the holder's accruals and payouts.
// The "Deposit" CTA pushes to the dedicated /investor/balance/deposit screen
// (InvestorDepositView).
//
// THE BUYER ACCOUNT is the account the buyer tops up. It is spent on parts of
// AIVIS and comes back only through support, so the screen has no withdrawal
// sheet and no payout-details editor: an investor asks for none, and the
// server refuses one from the role.
//
// THE HOLDER has accruals and payouts and no balance of their own. AIVIS pays
// the accruals itself, once a quarter, so the screen carries the rule in words
// and shows no figure a person could mistake for money to spend or withdraw.
//
// State split:
//   - balance figures live in the Pinia `dashboard` store, sourced
//     from GET /api/v1/dashboard/summary. The store exposes the
//     full DashboardSummaryResponse and is shared with the F4.4
//     InvestorDashboardView / PurchaseView / InstallmentView, so
//     balance never desyncs across views in one session. This view
//     only reads `activeBalance` (a computed getter over
//     `summary?.active_balance`).
//   - payment history lives in a local ref on this view. There is
//     no reuse across screens, no filters, and the list is only
//     consumed by this component.
//
// Pagination:
//   Infinite scroll via useInfiniteScroll on a sentinel div. Uses
//   the same stale-epoch guard pattern as stores/products.ts: a
//   counter bumped on every network-touching path so resolves from
//   older fetches can't overwrite newer state.
//
// Formatting:
//   - formatPrice with `undefined` currency -- BalanceResponse and
//     PaymentResponse both lack the field on the backend (TD-F08a).
//     formatPrice falls back to USD, which is correct for today's
//     single-currency platform.
//   - dates are formatted in the language of the cabinet.
//
// Error strategy:
//   Balance card errors surface inline with a retry button.
//   Payment history errors surface inline under the balance card.
//   No toasts -- this is a passive read-only screen, a toast would
//   vanish before the user notices it on mount.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ArrowDownToLine,
  CreditCard,
  ListChecks,
  Wallet,
} from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CLoader, CListSkeleton } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useDashboardStore } from '@/stores/dashboard'
import { listPaymentHistory } from '@/api/payments'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDateTime, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { PaymentResponse } from '@/api/types'

const PER_PAGE = 20

const router = useRouter()
const { t, locale } = useI18n()
const dashboardStore = useDashboardStore()

useScreenHeader({ title: () => t('inv.balance.title') })

// -- Payment history local state --
const items = ref<PaymentResponse[]>([])
const total = ref(0)
const page = ref(1)
const loadingHistory = ref(false)
const historyError = ref(false)

const sentinelRef = ref<HTMLElement | null>(null)

// Stale-epoch guard -- see stores/products.ts notes. Shared between
// fetchFirstPage and loadMore so a fresh first-page call invalidates
// any in-flight loadMore from a previous visit to this screen.
let fetchEpoch = 0

const hasMore = computed(() => items.value.length < total.value)

const hasFrozen = computed<boolean>(() => {
  return dashboardStore.activeBalance.frozen > 0
})

// Map backend payment status onto a CBadge variant. Mirrors the
// staff-side mapping in StaffPaymentsView -- keep the two in sync
// if a new status shows up.
function statusVariant(s: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (s === 'confirmed') return 'success'
  if (s === 'frozen' || s === 'created') return 'warning'
  if (s === 'reversed' || s === 'failed') return 'danger'
  return 'neutral'
}

function statusLabel(s: string): string {
  // TD-F08c-style fall-through: if the backend adds a status we
  // haven't i18n'd yet, show the raw token rather than blanking.
  return tOrRaw(t, `inv.balance.status.${s}`, s)
}

function typeLabel(type: string): string {
  return tOrRaw(t, `inv.balance.type.${type}`, type)
}

async function fetchFirstPage(): Promise<void> {
  const epoch = ++fetchEpoch
  loadingHistory.value = true
  historyError.value = false
  try {
    const resp = await listPaymentHistory({ page: 1, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = resp.items
    total.value = resp.total
    page.value = 1
  } catch {
    if (epoch !== fetchEpoch) return
    historyError.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loadingHistory.value = false
    }
  }
}

async function loadMore(): Promise<void> {
  if (loadingHistory.value || !hasMore.value) return
  const epoch = ++fetchEpoch
  loadingHistory.value = true
  try {
    const nextPage = page.value + 1
    const resp = await listPaymentHistory({
      page: nextPage,
      per_page: PER_PAGE,
    })
    if (epoch !== fetchEpoch) return
    items.value = [...items.value, ...resp.items]
    total.value = resp.total
    page.value = nextPage
  } catch {
    // Non-destructive: silent swallow keeps the already-loaded pages
    // visible; the user can scroll back up and tap Retry on the
    // empty-state if first-page itself had failed.
  } finally {
    if (epoch === fetchEpoch) {
      loadingHistory.value = false
    }
  }
}

function goDeposit(): void {
  void safeNavigate(router.push({ name: 'investor-deposit' }), '[BalanceView] to deposit')
}

// "All operations" opens the full journal of the account's operations.
function goOperations(): void {
  void safeNavigate(router.push({ name: 'investor-transactions' }), '[BalanceView] to operations')
}

async function reload(): Promise<void> {
  await Promise.all([dashboardStore.refresh(), fetchFirstPage()])
}

// Wire up the infinite scroll sentinel.
useInfiniteScroll(sentinelRef, hasMore, loadMore)

// If the balance store was populated by another view (purchase
// confirm probe, etc.) there's no need to reset it; refresh will
// overwrite. We don't reset on unmount because the store is shared
// with F4.4 screens and clearing on nav would cause a flash there.
onMounted(() => {
  void dashboardStore.refresh()
  void fetchFirstPage()
})
</script>

<template>
  <div class="bv">
    <!-- The buyer account: a summary card (K07) -->
    <section class="ds-card" aria-labelledby="bv-active">
      <header class="ds-card__head">
        <h2 id="bv-active" class="ds-card__title">
          {{ t('inv.balance.active') }}
        </h2>
      </header>

      <div
        v-if="
          dashboardStore.loading &&
          dashboardStore.activeBalance.confirmed === 0 &&
          dashboardStore.activeBalance.frozen === 0
        "
        class="ds-card__body"
      >
        <CLoader :size="20" />
      </div>

      <template v-else>
        <div class="ds-card__body bv__body">
          <p class="ds-card__figure">
            {{ formatPrice(dashboardStore.activeBalance.confirmed) }}
          </p>

          <dl v-if="hasFrozen" class="ds-kv">
            <div class="ds-kv__row">
              <dt>{{ t('inv.balance.frozen') }}</dt>
              <dd>{{ formatPrice(dashboardStore.activeBalance.frozen) }}</dd>
            </div>
          </dl>

          <div v-if="dashboardStore.error" class="ds-alert ds-alert--danger" role="alert">
            <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
            <div class="ds-alert__content">
              <p class="ds-alert__text">{{ t('inv.balance.refreshFailed') }}</p>
              <div class="ds-alert__actions">
                <CButton variant="outline" size="sm" inline @click="reload">
                  {{ t('common.retry') }}
                </CButton>
              </div>
            </div>
          </div>

          <p class="ds-note ds-note--xs">
            {{ t('inv.balance.accountNote') }}
          </p>
        </div>

        <footer class="ds-card__foot bv__actions">
          <CButton variant="primary" @click="goDeposit">
            <ArrowDownToLine size="sm" />
            {{ t('inv.balance.deposit') }}
          </CButton>
          <CButton variant="outline" @click="goOperations">
            <ListChecks size="sm" />
            {{ t('inv.balance.allOperations') }}
          </CButton>
        </footer>
      </template>
    </section>

    <!-- The holder: accruals and payouts, no balance -->
    <section class="ds-card ds-card--flat" aria-labelledby="bv-holder">
      <header class="ds-card__head">
        <h2 id="bv-holder" class="ds-card__title bv__holder-title">
          <Wallet size="sm" />
          <span>{{ t('inv.balance.holder.title') }}</span>
        </h2>
      </header>
      <div class="ds-card__body bv__body">
        <p class="ds-note ds-note--xs">
          {{ t('inv.balance.holder.rule') }}
        </p>
        <p class="ds-note ds-note--xs">
          {{ t('inv.balance.holder.small') }}
        </p>
      </div>
    </section>

    <!-- Payment history -->
    <section class="bv__history" aria-labelledby="bv-history">
      <h2 id="bv-history" class="ds-section-title">
        {{ t('inv.balance.history') }}
      </h2>

      <!-- Initial load: the placeholder rows of the list that will arrive (K19) -->
      <CListSkeleton v-if="loadingHistory && items.length === 0 && !historyError" :rows="3" />

      <!-- Error (first-page failure) -->
      <CEmptyState
        v-else-if="historyError && items.length === 0"
        tone="danger"
        :title="t('inv.balance.historyError.title')"
        :description="t('inv.balance.historyError.desc')"
      >
        <template #actions>
          <CButton variant="outline" size="sm" inline @click="fetchFirstPage">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <!-- Empty state -->
      <CEmptyState
        v-else-if="!loadingHistory && items.length === 0"
        :title="t('inv.balance.historyEmpty')"
      >
        <template #icon>
          <CreditCard />
        </template>
      </CEmptyState>

      <!-- List -->
      <ul v-else class="ds-rows">
        <li v-for="item in items" :key="item.id" class="ds-row">
          <span class="ds-row__lead"><CreditCard size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ typeLabel(item.payment_type) }}</span>
            <span class="ds-row__meta">{{ formatDateTime(item.created_at, locale) }}</span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value" data-tone="success">
              {{ formatPrice(item.amount_cents, item.currency) }}
            </span>
            <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
          </span>
        </li>
      </ul>

      <!-- Infinite scroll sentinel (only when we already have items) -->
      <div v-if="items.length > 0" ref="sentinelRef" class="bv__sentinel">
        <CLoader v-if="loadingHistory" :size="20" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.bv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.bv__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.bv__actions {
  flex-direction: column;
}

.bv__holder-title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.bv__history {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.bv__sentinel {
  display: flex;
  justify-content: center;
  min-block-size: var(--size-md);
}
</style>
