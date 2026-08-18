<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyDashboardView (Phase F5.1 B2 + B3)
// =============================================================================
//
// Company home screen. Rendered by CompanyShell at /company/dashboard
// (the "home" tab). Shell already paints CHeader + CTabBar, so this
// view is a plain content column -- no embedded CHeader (mirrors
// MarketView / InvestorDashboardView convention for top-level tab views).
//
// WIDGETS, in render order:
//
//   1. Page header -- title + subtitle, no data call.
//
//   2. Hero card -- company identity. Logo with initials fallback +
//      company name. Non-clickable: Settings (where the company can
//      view its profile in read-only) lands in F5.2 B5; routing it
//      from here today would lead to the stub.
//
//   3. Balance card -- passive_balance.confirmed (large) plus an
//      "On hold" hint for frozen > 0. Non-clickable in B2 -- the
//      Balance view is a stub until F5.2 B3.
//
//   4. Pool widget (B3) -- only when summary.pool is non-null.
//      consumed / total progress bar + equity_percent + remaining
//      caption. The pool is created by staff during company setup;
//      a freshly-created company without a pool is a legitimate
//      transient state, not an error -- so we hide the widget
//      entirely instead of rendering a placeholder. Non-clickable:
//      pool management is a staff-side concern.
//
//   5. Metrics row -- three CStatCard tiles: total revenue, options
//      sold (sale + installment_tranche, Sprint 4.6 hotfix on the
//      backend), products count.
//
//   6. Recent transactions (B3) -- list of summary.recent_transactions
//      (last 20, embedded in the dashboard payload by the backend).
//      Read-only feed: no detail-sheet click in B3 -- the full
//      transactions view for the company role is a future scope item.
//      MUST NOT issue a separate /transactions fetch -- the embed is
//      the contract.
//
// DEFERRED.
//   i18n JSON keys (`comp.dashboard.*`) + null-state polish = B4.
//   Until B4 lands, vue-i18n's missing-key fallback echoes the raw
//   key for static labels; for transaction TYPE labels we use
//   tOrRaw so the bare type token (e.g. "purchase:completed")
//   shows instead of the dotted i18n path -- considerably more
//   readable while we wait for the catalogue.
//
// DATA FLOW.
//   onMounted fires Promise.all over loadIfMissing() (profile,
//   cache-first) and refresh() (dashboard, always re-fetches because
//   balances and counters move with every purchase / withdrawal).
//   The two probes are independent on the network but coupled in
//   the UI: see RENDER POLICY.
//
// RENDER POLICY -- ALL OR NOTHING.
//   The view has three top-level states:
//     - initialLoading: full-screen CLoader. Holds until BOTH stores
//                       have populated (or one errors). Avoids the
//                       fast-store / slow-store flash where balance
//                       briefly shows $0 because passive_balance is
//                       defaulted via `?? 0` while the dashboard
//                       fetch is still running.
//     - hasError:       full-screen CEmptyState + Retry. Any error
//                       on either store routes here -- a partial
//                       dashboard with a working hero but a broken
//                       balance card would be confusingly broken
//                       rather than obviously broken.
//     - loaded:         the actual content. Both stores are
//                       guaranteed non-null and error-free.
//
// AUTH ASSUMPTIONS.
//   CompanyShell sits behind the auth + role guard (meta.roles =
//   ['company']), so this component can assume an authenticated
//   company-role user. Backend serves /companies/me + /company/dashboard
//   behind get_current_company_profile, returning 403 to anyone
//   without a CompanyProfile -- which the route guard already
//   prevents from reaching here.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowUpRight,
  CreditCard,
  Layers,
  Package,
  RefreshCw,
  Repeat,
  ShoppingBag,
  TrendingUp,
  Wallet,
} from 'lucide-vue-next'
import type { Component } from 'vue'

import {
  CButton,
  CEmptyState,
  CLoader,
  CProgressBar,
  CStatCard,
} from '@/components/ui'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import type { CompanyTransactionResponse, PoolEmbedResponse } from '@/api/types'
import { formatNumber, formatPrice, formatSignedPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'

const { t, locale } = useI18n()
const profileStore = useCompanyProfileStore()
const dashboardStore = useCompanyDashboardStore()

// ---------------------------------------------------------------------------
// Hero -- profile-derived
// ---------------------------------------------------------------------------

const companyName = computed<string>(
  () => profileStore.profile?.name ?? '',
)
const logoUrl = computed<string | null>(
  () => profileStore.profile?.logo_url ?? null,
)

/**
 * Initials fallback when logo_url is null. Takes the first letter of
 * up to two whitespace-separated chunks: "Test Company" -> "TC",
 * "Acme" -> "A". Always uppercase. Falls back to a single 'C' on the
 * theoretically-impossible empty-name case so the avatar tile never
 * renders blank.
 */
const initials = computed<string>(() => {
  const name = companyName.value.trim()
  if (!name) return 'C'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
})

// ---------------------------------------------------------------------------
// Balance + metrics + pool -- dashboard-derived
//
// These computed fields default to 0 / null via `?? 0` / `?? null` so the
// template never needs a null guard on summary itself. The
// all-or-nothing render policy guarantees they are not read until
// summary is non-null, so the defaults never actually surface to the
// user -- they exist to keep the type narrow.
// ---------------------------------------------------------------------------

const passiveConfirmed = computed<number>(
  () => dashboardStore.summary?.passive_balance.confirmed ?? 0,
)
const passiveFrozen = computed<number>(
  () => dashboardStore.summary?.passive_balance.frozen ?? 0,
)
const hasFrozen = computed<boolean>(() => passiveFrozen.value > 0)

const totalRevenue = computed<number>(
  () => dashboardStore.summary?.total_revenue_cents ?? 0,
)
const totalOptionsSold = computed<number>(
  () => dashboardStore.summary?.total_options_sold ?? 0,
)
const productsCount = computed<number>(
  () => dashboardStore.summary?.products_count ?? 0,
)

// pool is `PoolEmbedResponse | null | undefined` on the wire; coerce
// the undefined case to null so the template's v-if check is clean.
const pool = computed<PoolEmbedResponse | null>(
  () => dashboardStore.summary?.pool ?? null,
)

// recent_transactions is required (non-optional) on the response
// schema, but we still default to [] so the v-for is safe in the
// (impossible) interim state where summary is non-null but the field
// somehow isn't.
const recentTransactions = computed<CompanyTransactionResponse[]>(
  () => dashboardStore.summary?.recent_transactions ?? [],
)

// ---------------------------------------------------------------------------
// Transaction row helpers (B3)
//
// Mirrors the investor-side TransactionsView icon + label + signed-
// amount pattern. We deliberately reuse the `inv.transactions.type.*`
// catalogue for typeLabel because the type strings themselves are
// identical (purchase:completed, withdrawal:completed, etc.) -- the
// row of a withdrawal looks the same to a company seeing money leave
// as it does to an investor seeing money leave. B4 may rename to a
// shared `tx.type.*` namespace; the tOrRaw fallback covers both
// futures without breaking today.
// ---------------------------------------------------------------------------

/**
 * Pick a lucide icon for a transaction type. Match by prefix so any
 * future ":completed" / ":pending" / ":failed" suffix variant routes
 * to the same icon without an exhaustive allow-list.
 */
function iconForType(type: string): Component {
  if (type.startsWith('purchase:')) return ShoppingBag
  if (type.startsWith('installment:')) return Repeat
  if (type.startsWith('withdrawal:')) return ArrowUpRight
  if (type.startsWith('reversal:') || type.startsWith('refund:')) {
    return RefreshCw
  }
  return CreditCard
}

/**
 * Translate the type token. Falls back to the bare token (e.g.
 * "purchase:completed") rather than the i18n dotted path so the
 * pre-B4 view is readable.
 */
function typeLabel(type: string): string {
  return tOrRaw(t, `inv.transactions.type.${type}`, type)
}

/**
 * CSS modifier class for amount colour. Positive = revenue (credit,
 * green), negative = withdrawal / refund (debit, red), zero = neutral.
 */
function amountClass(amountCents: number): string {
  if (amountCents > 0) return 'dash__tx-amount--credit'
  if (amountCents < 0) return 'dash__tx-amount--debit'
  return ''
}

/**
 * Format a transaction timestamp. Short locale-aware date + time --
 * the recent feed is contextual (last 20), so a minute-precise
 * timestamp helps the operator scan it.
 */
function formatTxDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// View states (see RENDER POLICY in the file header)
// ---------------------------------------------------------------------------

const hasError = computed<boolean>(
  () => profileStore.error !== null || dashboardStore.error !== null,
)

const initialLoading = computed<boolean>(() => {
  // Errors take priority over loading -- otherwise an errored fetch
  // that left its store ref null would loop in the loader forever.
  if (hasError.value) return false
  return (
    profileStore.profile === null
    || dashboardStore.summary === null
  )
})

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

/**
 * Run both probes in parallel. Used by onMounted and by the Retry
 * button in the error state.
 *
 * loadIfMissing() is cache-first -- if the profile is already loaded
 * from a previous visit to this view (or to a F5.2 view that also
 * needs the profile), the second call is a no-op. refresh() always
 * re-fetches because balances / counters move with every purchase
 * and withdrawal.
 */
async function loadAll(): Promise<void> {
  await Promise.all([
    profileStore.loadIfMissing(),
    dashboardStore.refresh(),
  ])
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="dash">
    <!-- Initial loading -- both stores empty, no error yet -->
    <div v-if="initialLoading" class="dash__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -- whole-screen, retry both stores -->
    <div v-else-if="hasError" class="dash__center">
      <CEmptyState :title="t('comp.dashboard.errorTitle')" />
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('comp.dashboard.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Page header -->
      <div class="dash__header">
        <h1 class="dash__title">{{ t('comp.dashboard.title') }}</h1>
        <p class="dash__subtitle">{{ t('comp.dashboard.subtitle') }}</p>
      </div>

      <!-- Hero -- company identity (logo + name) -->
      <div class="dash__hero">
        <div class="dash__hero-logo">
          <img
            v-if="logoUrl"
            :src="logoUrl"
            :alt="companyName"
            class="dash__hero-logo-img"
          />
          <div v-else class="dash__hero-logo-fallback">
            {{ initials }}
          </div>
        </div>
        <div class="dash__hero-text">
          <div class="dash__hero-name">{{ companyName }}</div>
        </div>
      </div>

      <!-- Balance card (passive ledger) -->
      <div class="dash__balance">
        <div class="dash__balance-head">
          <span class="dash__balance-label">
            <Wallet :size="16" />
            {{ t('comp.dashboard.balance.title') }}
          </span>
        </div>
        <div class="dash__balance-value">
          {{ formatPrice(passiveConfirmed) }}
        </div>
        <div v-if="hasFrozen" class="dash__balance-frozen">
          {{ t('comp.dashboard.balance.frozen') }}:
          {{ formatPrice(passiveFrozen) }}
        </div>
      </div>

      <!-- Pool widget (B3) -- hidden when staff hasn't created a pool -->
      <div v-if="pool" class="dash__pool">
        <div class="dash__pool-head">
          <span class="dash__pool-label">
            <Layers :size="16" />
            {{ t('comp.dashboard.pool.title') }}
          </span>
          <span class="dash__pool-equity">
            {{ pool.equity_percent }}%
            {{ t('comp.dashboard.pool.equity') }}
          </span>
        </div>
        <CProgressBar
          :value="pool.consumed"
          :max="pool.total_options"
        />
        <div class="dash__pool-stats">
          <span>
            {{ formatNumber(pool.consumed, locale) }}
            /
            {{ formatNumber(pool.total_options, locale) }}
            {{ t('comp.dashboard.pool.consumed') }}
          </span>
          <span>
            {{ formatNumber(pool.remaining, locale) }}
            {{ t('comp.dashboard.pool.remaining') }}
          </span>
        </div>
      </div>

      <!-- Metrics row -- 3 stat tiles -->
      <div class="dash__metrics">
        <CStatCard
          :value="formatPrice(totalRevenue)"
          :label="t('comp.dashboard.metrics.revenue')"
        >
          <template #icon>
            <TrendingUp :size="20" />
          </template>
        </CStatCard>
        <CStatCard
          :value="formatNumber(totalOptionsSold, locale)"
          :label="t('comp.dashboard.metrics.optionsSold')"
        >
          <template #icon>
            <Package :size="20" />
          </template>
        </CStatCard>
        <CStatCard
          :value="formatNumber(productsCount, locale)"
          :label="t('comp.dashboard.metrics.products')"
        >
          <template #icon>
            <Layers :size="20" />
          </template>
        </CStatCard>
      </div>

      <!-- Recent transactions (B3) -- embedded list, no extra fetch -->
      <div class="dash__recent">
        <h2 class="dash__recent-title">
          {{ t('comp.dashboard.recent.title') }}
        </h2>

        <p
          v-if="recentTransactions.length === 0"
          class="dash__recent-empty"
        >
          {{ t('comp.dashboard.recent.empty') }}
        </p>

        <ul v-else class="dash__tx-list">
          <li
            v-for="tx in recentTransactions"
            :key="tx.id"
            class="dash__tx-item"
          >
            <div class="dash__tx-icon">
              <component :is="iconForType(tx.type)" :size="16" />
            </div>
            <div class="dash__tx-body">
              <div class="dash__tx-line">
                <span class="dash__tx-type">
                  {{ typeLabel(tx.type) }}
                </span>
                <span
                  class="dash__tx-amount"
                  :class="amountClass(tx.amount_cents)"
                >
                  {{ formatSignedPrice(tx.amount_cents, tx.currency) }}
                </span>
              </div>
              <div class="dash__tx-date">
                {{ formatTxDate(tx.created_at) }}
              </div>
            </div>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dash {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Whole-screen states (loading / error) */
.dash__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: calc(100vh - 200px);
  min-height: calc(100dvh - 200px);
  padding: 24px;
  text-align: center;
}

/* Header */
.dash__header { display: flex; flex-direction: column; gap: 4px; }
.dash__title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.dash__subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Hero -- company identity, no CTA */
.dash__hero {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__hero-logo {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dash__hero-logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.dash__hero-logo-fallback {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
  letter-spacing: 0.5px;
}
.dash__hero-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.dash__hero-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

/* Balance card -- mirrors investor balance card; non-clickable in B2 */
.dash__balance {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}
.dash__balance-head {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__balance-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dash__balance-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}
.dash__balance-frozen {
  font-size: 12px;
  color: var(--warning);
}

/* Pool widget (B3) */
.dash__pool {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__pool-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.dash__pool-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.dash__pool-equity {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__pool-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

/* Metrics row */
.dash__metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
@media (max-width: 480px) {
  .dash__metrics {
    grid-template-columns: 1fr;
  }
}

/* Recent transactions (B3) */
.dash__recent {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dash__recent-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 4px 0 0 0;
}
.dash__recent-empty {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px dashed var(--border-default);
  text-align: center;
}

/* Transaction list -- compact two-line rows */
.dash__tx-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dash__tx-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__tx-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--bg-page);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.dash__tx-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dash__tx-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.dash__tx-type {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dash__tx-amount {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
}
.dash__tx-amount--credit { color: var(--success); }
.dash__tx-amount--debit  { color: var(--danger); }
.dash__tx-date {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
