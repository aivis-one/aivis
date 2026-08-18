<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- BalanceView (Phase F4.3 B2 + F4.4 B2 store rename)
// =============================================================================
//
// Investor balance screen. Shows the active ledger balance and a
// paginated payment-history feed. The "Deposit" CTA pushes to the
// dedicated /investor/balance/deposit screen (InvestorDepositView).
//
// State split:
//   - balance figures live in the Pinia `dashboard` store, sourced
//     from GET /api/v1/dashboard/summary. The store exposes the
//     full DashboardSummaryResponse and is shared with the F4.4
//     InvestorDashboardView / PurchaseView / InstallmentView, so
//     balance never desyncs across views in one session. This view
//     only reads `activeBalance` (a computed getter over
//     `summary?.active_balance`) -- the portfolio aggregate fields
//     are ignored here.
//   - payment history lives in a local ref on this view. There is
//     no reuse across screens, no filters, and the list is only
//     consumed by this component -- a dedicated Pinia store would
//     be ceremony without upside.
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
//
// Error strategy:
//   Balance card errors surface inline with a retry button.
//   Payment history errors surface inline under the balance card.
//   No toasts -- this is a passive read-only screen, a toast would
//   vanish before the user notices it on mount.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDownToLine, CreditCard } from 'lucide-vue-next'
import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useDashboardStore } from '@/stores/dashboard'
import { listPaymentHistory } from '@/api/payments'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { PaymentResponse } from '@/api/types'

const PER_PAGE = 20

const router = useRouter()
const { t } = useI18n()
const dashboardStore = useDashboardStore()

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

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
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
  void safeNavigate(
    router.push({ name: 'investor-deposit' }),
    '[BalanceView] to deposit',
  )
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

// If the user deposits and returns here via router.back(), the
// BalanceView instance is already mounted and onMounted will NOT
// rerun. Watching the route name wouldn't help since we stay on
// the same name. A fresh refresh is driven by DepositView pushing
// a toast + the user glancing back -- acceptable for F4.3; if
// stickiness bites, F4.4 can add a store-level subscription.
watch(
  () => dashboardStore.error,
  (err) => {
    // Surface as inline banner, no toast (see header comment).
    void err
  },
)
</script>

<template>
  <div class="bv">
    <div class="bv__header">
      <h1 class="bv__title">{{ t('inv.balance.title') }}</h1>
    </div>

    <!-- Active balance card -->
    <section class="bv__card bv__balance">
      <h2 class="bv__card-title">{{ t('inv.balance.active') }}</h2>

      <div v-if="dashboardStore.loading && dashboardStore.activeBalance.confirmed === 0 && dashboardStore.activeBalance.frozen === 0" class="bv__balance-loading">
        <CLoader :size="20" />
      </div>

      <template v-else>
        <div class="bv__balance-main">
          {{ formatPrice(dashboardStore.activeBalance.confirmed) }}
        </div>

        <div
          v-if="hasFrozen"
          class="bv__balance-frozen"
        >
          <span class="bv__balance-frozen-label">
            {{ t('inv.balance.frozen') }}
          </span>
          <span class="bv__balance-frozen-value">
            {{ formatPrice(dashboardStore.activeBalance.frozen) }}
          </span>
        </div>

        <div
          v-if="dashboardStore.error"
          class="bv__balance-error"
        >
          <span>{{ t('inv.balance.refreshFailed') }}</span>
          <CButton variant="outline" size="sm" @click="reload">
            {{ t('common.retry') }}
          </CButton>
        </div>

        <CButton
          variant="primary"
          class="bv__deposit"
          @click="goDeposit"
        >
          <ArrowDownToLine :size="16" />
          {{ t('inv.balance.deposit') }}
        </CButton>
      </template>
    </section>

    <!-- Payment history -->
    <section class="bv__history">
      <h2 class="bv__card-title bv__history-title">
        {{ t('inv.balance.history') }}
      </h2>

      <!-- Initial load spinner (no items yet, fetching) -->
      <div
        v-if="loadingHistory && items.length === 0 && !historyError"
        class="bv__history-center"
      >
        <CLoader :size="24" />
      </div>

      <!-- Error (first-page failure) -->
      <div
        v-else-if="historyError && items.length === 0"
        class="bv__history-center"
      >
        <CEmptyState
          :title="t('inv.balance.historyError.title')"
          :description="t('inv.balance.historyError.desc')"
        />
        <CButton variant="outline" size="sm" @click="fetchFirstPage">
          {{ t('common.retry') }}
        </CButton>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="!loadingHistory && items.length === 0"
        class="bv__history-center"
      >
        <CEmptyState :title="t('inv.balance.historyEmpty')">
          <template #icon>
            <CreditCard :size="32" />
          </template>
        </CEmptyState>
      </div>

      <!-- List -->
      <ul v-else class="bv__list">
        <li
          v-for="item in items"
          :key="item.id"
          class="bv__item"
        >
          <div class="bv__item-icon">
            <CreditCard :size="18" />
          </div>
          <div class="bv__item-body">
            <div class="bv__item-line">
              <span class="bv__item-type">
                {{ typeLabel(item.payment_type) }}
              </span>
              <span class="bv__item-amount">
                {{ formatPrice(item.amount_cents, item.currency) }}
              </span>
            </div>
            <div class="bv__item-line bv__item-line--sub">
              <span class="bv__item-date">
                {{ formatDate(item.created_at) }}
              </span>
              <CBadge
                :variant="statusVariant(item.status)"
                :text="statusLabel(item.status)"
              />
            </div>
          </div>
        </li>
      </ul>

      <!-- Infinite scroll sentinel (only when we already have items) -->
      <div
        v-if="items.length > 0"
        ref="sentinelRef"
        class="bv__sentinel"
      >
        <CLoader v-if="loadingHistory" :size="20" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.bv {
  display: flex;
  flex-direction: column;
  padding-bottom: 24px;
}

/* Page header (inline, not CHeader -- shell already renders CHeader) */
.bv__header {
  padding: 16px 16px 0;
}
.bv__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

/* Card base */
.bv__card {
  padding: 20px;
  background: var(--bg-secondary, var(--surface));
  border-radius: var(--radius-md, 12px);
  margin: 16px 16px 0;
}

.bv__card-title {
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Active balance */
.bv__balance {
  display: flex;
  flex-direction: column;
}

.bv__balance-loading {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.bv__balance-main {
  font-size: 32px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1.1;
  margin-bottom: 8px;
  word-break: break-word;
}

.bv__balance-frozen {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  font-size: 13px;
  color: var(--text-secondary);
}
.bv__balance-frozen-label {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.bv__balance-frozen-value {
  font-weight: 600;
  color: var(--text-secondary);
}

.bv__balance-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--danger-subtle);
  color: var(--danger);
  font-size: 12px;
}

.bv__deposit {
  margin-top: 16px;
}

/* History */
.bv__history {
  padding: 20px 16px 0;
}

.bv__history-title {
  padding: 0 4px;
}

.bv__history-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
}

.bv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bv__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-secondary, var(--surface));
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.06));
}

.bv__item-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.bv__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bv__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.bv__item-line--sub {
  font-size: 12px;
  color: var(--text-tertiary);
}

.bv__item-type {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}
.bv__item-amount {
  font-size: 14px;
  font-weight: 700;
  color: var(--success);
  white-space: nowrap;
}
.bv__item-date {
  color: var(--text-tertiary);
}

.bv__sentinel {
  display: flex;
  justify-content: center;
  padding: 16px 0 0;
  min-height: 32px;
}
</style>
