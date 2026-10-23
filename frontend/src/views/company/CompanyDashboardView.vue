<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyDashboardView (the project account's Home tab)
// =============================================================================
//
// What the project sees first: the balance, the project's pool, three figures
// and the recent operations. Every block is a link to the screen that holds its
// detail (the balance, the operations, the analytics, the products), and every
// block stands on its own: a failed request removes only the blocks it feeds
// and leaves a retry in their place.
//
// THE POOL. The project's pool is a fixed 15 percent of the gross receipts
// from sales of the project's product. The money buyers pay for parts is
// never gross receipts, and the Cabinet records no sale of a product in 1.0,
// so the pool is zero until the product sells.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowUpRight,
  ChevronRight,
  CreditCard,
  Layers,
  Package,
  RefreshCw,
  Repeat,
  ShoppingBag,
  TrendingUp,
  Wallet,
} from '@/components/ui/icons'
import type { Component } from 'vue'

import { CButton, CLoader, CStatCard } from '@/components/ui'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import type { CompanyTransactionResponse } from '@/api/types'
import { formatDateTime, formatNumber, formatPrice, formatSignedPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'

// The share of the gross receipts that forms the project's pool, in percent.
const POOL_PERCENT = 15

const { t, locale } = useI18n()
const profileStore = useCompanyProfileStore()
const dashboardStore = useCompanyDashboardStore()

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

const companyName = computed<string>(() => profileStore.profile?.name ?? '')
const logoUrl = computed<string | null>(() => profileStore.profile?.logo_url ?? null)

/** Initials when there is no logo: the first letters of up to two words. */
const initials = computed<string>(() => {
  const name = companyName.value.trim()
  if (!name) return 'P'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
})

// ---------------------------------------------------------------------------
// Summary blocks
// ---------------------------------------------------------------------------

const summary = computed(() => dashboardStore.summary)

const passiveConfirmed = computed<number>(() => summary.value?.passive_balance.confirmed ?? 0)
const passiveFrozen = computed<number>(() => summary.value?.passive_balance.frozen ?? 0)
const hasFrozen = computed<boolean>(() => passiveFrozen.value > 0)

const partSales = computed<number>(() => summary.value?.total_revenue_cents ?? 0)
const partsSold = computed<number>(() => summary.value?.total_options_sold ?? 0)
const productsCount = computed<number>(() => summary.value?.products_count ?? 0)

/** The project's pool: 15 percent of the product's gross receipts. None is recorded in 1.0, so zero. */
const poolCents = computed<number>(() => 0)

const recentTransactions = computed<CompanyTransactionResponse[]>(
  () => summary.value?.recent_transactions ?? [],
)

const summaryFailed = computed<boolean>(
  () => dashboardStore.error !== null && summary.value === null,
)
const summaryLoading = computed<boolean>(() => summary.value === null && !summaryFailed.value)

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

/** An icon per operation group, matched by prefix. */
function iconForType(type: string): Component {
  if (type.startsWith('purchase:')) return ShoppingBag
  if (type.startsWith('installment:')) return Repeat
  if (type.startsWith('withdrawal:')) return ArrowUpRight
  if (type.startsWith('reversal:') || type.startsWith('refund:')) return RefreshCw
  return CreditCard
}

/** The project's own wording: a purchase by a buyer is a sale for the project. */
function typeLabel(type: string): string {
  return tOrRaw(t, `comp.operations.type.${type}`, tOrRaw(t, `inv.transactions.type.${type}`, type))
}

function amountClass(amountCents: number): string {
  if (amountCents > 0) return 'dash__tx-amount--credit'
  if (amountCents < 0) return 'dash__tx-amount--debit'
  return ''
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

async function loadAll(): Promise<void> {
  await Promise.all([profileStore.loadIfMissing(), dashboardStore.refresh()])
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="dash">
    <!-- Page header -->
    <div class="dash__header">
      <h1 class="dash__title">
        {{ t('comp.dashboard.title') }}
      </h1>
      <p class="dash__subtitle">
        {{ t('comp.dashboard.subtitle') }}
      </p>
    </div>

    <!-- Hero -- the project's identity (shown whenever the profile is read) -->
    <div v-if="profileStore.profile" class="dash__hero">
      <div class="dash__hero-logo">
        <img v-if="logoUrl" :src="logoUrl" :alt="companyName" class="dash__hero-logo-img" />
        <div v-else class="dash__hero-logo-fallback">
          {{ initials }}
        </div>
      </div>
      <div class="dash__hero-text">
        <div class="dash__hero-name">
          {{ companyName }}
        </div>
      </div>
    </div>

    <!-- The summary is loading -->
    <div v-if="summaryLoading" class="dash__center">
      <CLoader :size="28" />
    </div>

    <!-- The summary failed: only its blocks give way, with a retry in their place -->
    <div v-else-if="summaryFailed" class="dash__failed">
      <span>{{ t('comp.dashboard.errorTitle') }}</span>
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('comp.dashboard.errorRetry') }}
      </CButton>
    </div>

    <template v-else>
      <!-- Balance -> the balance screen -->
      <RouterLink to="/company/balance" class="dash__balance dash__link">
        <div class="dash__balance-head">
          <span class="dash__balance-label">
            <Wallet :size="16" />
            {{ t('comp.dashboard.balance.title') }}
          </span>
          <ChevronRight :size="16" />
        </div>
        <div class="dash__balance-value">
          {{ formatPrice(passiveConfirmed) }}
        </div>
        <div v-if="hasFrozen" class="dash__balance-frozen">
          {{ t('comp.dashboard.balance.frozen') }}:
          {{ formatPrice(passiveFrozen) }}
        </div>
      </RouterLink>

      <!-- The project's pool: a share of the gross receipts, zero until a sale -->
      <RouterLink to="/company/analytics" class="dash__pool dash__link">
        <div class="dash__pool-head">
          <span class="dash__pool-label">
            <Layers :size="16" />
            {{ t('comp.dashboard.pool.title') }}
          </span>
          <ChevronRight :size="16" />
        </div>
        <div class="dash__pool-value">
          {{ formatPrice(poolCents) }}
        </div>
        <p class="dash__pool-note">
          {{ t('comp.dashboard.pool.note', { percent: POOL_PERCENT }) }}
        </p>
      </RouterLink>

      <!-- Three figures, each a link to its screen -->
      <div class="dash__metrics">
        <RouterLink to="/company/analytics" class="dash__link dash__link--tile">
          <CStatCard
            :value="formatPrice(partSales)"
            :label="t('comp.dashboard.metrics.revenue')"
          >
            <template #icon>
              <TrendingUp :size="20" />
            </template>
          </CStatCard>
        </RouterLink>
        <RouterLink to="/company/analytics" class="dash__link dash__link--tile">
          <CStatCard
            :value="formatNumber(partsSold, locale)"
            :label="t('comp.dashboard.metrics.optionsSold')"
          >
            <template #icon>
              <Package :size="20" />
            </template>
          </CStatCard>
        </RouterLink>
        <RouterLink to="/company/products" class="dash__link dash__link--tile">
          <CStatCard
            :value="formatNumber(productsCount, locale)"
            :label="t('comp.dashboard.metrics.products')"
          >
            <template #icon>
              <Layers :size="20" />
            </template>
          </CStatCard>
        </RouterLink>
      </div>

      <!-- Recent operations, and the way to all of them -->
      <div class="dash__recent">
        <div class="dash__recent-head">
          <h2 class="dash__recent-title">
            {{ t('comp.dashboard.recent.title') }}
          </h2>
          <RouterLink to="/company/balance/transactions" class="dash__recent-all">
            {{ t('comp.dashboard.recent.all') }}
            <ChevronRight :size="14" />
          </RouterLink>
        </div>

        <p v-if="recentTransactions.length === 0" class="dash__recent-empty">
          {{ t('comp.dashboard.recent.empty') }}
        </p>

        <ul v-else class="dash__tx-list">
          <li v-for="tx in recentTransactions" :key="tx.id" class="dash__tx-item">
            <div class="dash__tx-icon">
              <component :is="iconForType(tx.type)" :size="16" />
            </div>
            <div class="dash__tx-body">
              <div class="dash__tx-line">
                <span class="dash__tx-type">
                  {{ typeLabel(tx.type) }}
                </span>
                <span class="dash__tx-amount" :class="amountClass(tx.amount_cents)">
                  {{ formatSignedPrice(tx.amount_cents, tx.currency) }}
                </span>
              </div>
              <div class="dash__tx-date">
                {{ formatDateTime(tx.created_at, locale) }}
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
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Whole-screen states (loading / error) */
.dash__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: calc(100vh - 200px);
  min-height: calc(100dvh - 200px);
  padding: var(--space-5);
  text-align: center;
}

/* Header */
.dash__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.dash__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.dash__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

/* Hero -- company identity, no CTA */
.dash__hero {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__hero-logo {
  width: var(--size-4xl);
  height: var(--size-4xl);
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
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--primary);
  letter-spacing: 0.5px;
}
.dash__hero-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}
.dash__hero-name {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

/* Balance card -- mirrors investor balance card; non-clickable in B2 */
.dash__balance {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
}
.dash__balance-head {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__balance-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.dash__balance-value {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.dash__balance-frozen {
  font-size: var(--fs-xs);
  color: var(--warning);
}

/* Pool widget (B3) */
.dash__pool {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__pool-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.dash__pool-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}
.dash__pool-equity {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__pool-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

/* Metrics row */
.dash__metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
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
  gap: var(--space-3);
}
.dash__recent-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0 0 0;
}
.dash__recent-empty {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius-md);
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
  gap: var(--space-1);
}
.dash__tx-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.dash__tx-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-md);
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
  gap: var(--space-1);
}
.dash__tx-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.dash__tx-type {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dash__tx-amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
}
.dash__tx-amount--credit {
  color: var(--success);
}
.dash__tx-amount--debit {
  color: var(--danger);
}
.dash__tx-date {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

/* Blocks that are links */
.dash__link {
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s;
}
.dash__link:hover {
  border-color: var(--primary);
}
.dash__link--tile {
  display: block;
  border-radius: var(--radius-md);
}
.dash__balance-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.dash__pool-value {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.dash__pool-note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}
.dash__failed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-default);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.dash__recent-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}
.dash__recent-all {
  display: inline-flex;
  align-items: center;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--primary);
  text-decoration: none;
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
@media (min-width: 880px) {
  .dash__metrics {
    max-width: calc(3 * var(--tile-max));
  }
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.dash__subtitle {
  max-width: var(--maxw-prose);
}
</style>
