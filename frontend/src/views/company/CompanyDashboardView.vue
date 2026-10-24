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
// THE POOL. The project's pool is a fixed 10 percent of the gross receipts
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

import { CAvatar, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
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

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('comp.dashboard.title'),
  lead: () => t('comp.dashboard.subtitle'),
})

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

const companyName = computed<string>(() => profileStore.profile?.name ?? '')
const logoUrl = computed<string | null>(() => profileStore.profile?.logo_url ?? null)

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

/** The project's pool: 10 percent of the product's gross receipts. None is recorded in 1.0, so zero. */
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

/** The lead box's tone: a credit is green, a debit red; the signed amount says the same in text. */
function amountTone(amountCents: number): 'success' | 'danger' | undefined {
  if (amountCents > 0) return 'success'
  if (amountCents < 0) return 'danger'
  return undefined
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
  <!-- The project's identity (shown whenever the profile is read) -->
  <ul v-if="profileStore.profile" class="ds-rows">
    <li class="ds-row">
      <CAvatar :name="companyName" :url="logoUrl ?? undefined" :size="56" />
      <span class="ds-row__body">
        <span class="ds-row__title">{{ companyName }}</span>
      </span>
    </li>
  </ul>

  <!-- The summary is loading -->
  <div v-if="summaryLoading" aria-busy="true">
    <CLoader />
  </div>

  <!-- The summary failed: only its blocks give way, with a retry in their place -->
  <CEmptyState v-else-if="summaryFailed" tone="danger" :title="t('comp.dashboard.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="loadAll">
        {{ t('comp.dashboard.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <template v-else>
    <!-- Five figures, each a link to the screen that holds its detail -->
    <div class="ds-stats">
      <!-- Balance -> the balance screen -->
      <div class="ds-stat ds-stat--interactive">
        <span class="ds-stat__icon"><Wallet /></span>
        <p class="ds-stat__label">
          <RouterLink class="ds-stat__link" to="/company/balance">
            {{ t('comp.dashboard.balance.title') }}
          </RouterLink>
        </p>
        <p class="ds-stat__value">{{ formatPrice(passiveConfirmed) }}</p>
        <p v-if="hasFrozen" class="ds-stat__sub">
          {{ t('comp.dashboard.balance.frozen') }}: {{ formatPrice(passiveFrozen) }}
        </p>
      </div>

      <!-- The project's pool: a share of the gross receipts, zero until a sale -->
      <div class="ds-stat ds-stat--interactive">
        <span class="ds-stat__icon"><Layers /></span>
        <p class="ds-stat__label">
          <RouterLink class="ds-stat__link" to="/company/analytics">
            {{ t('comp.dashboard.pool.title') }}
          </RouterLink>
        </p>
        <p class="ds-stat__value">{{ formatPrice(poolCents) }}</p>
        <p class="ds-stat__sub">
          {{ t('comp.dashboard.pool.note', { percent: POOL_PERCENT }) }}
        </p>
      </div>

      <div class="ds-stat ds-stat--interactive">
        <span class="ds-stat__icon"><TrendingUp /></span>
        <p class="ds-stat__label">
          <RouterLink class="ds-stat__link" to="/company/analytics">
            {{ t('comp.dashboard.metrics.revenue') }}
          </RouterLink>
        </p>
        <p class="ds-stat__value">{{ formatPrice(partSales) }}</p>
      </div>

      <div class="ds-stat ds-stat--interactive">
        <span class="ds-stat__icon"><Package /></span>
        <p class="ds-stat__label">
          <RouterLink class="ds-stat__link" to="/company/analytics">
            {{ t('comp.dashboard.metrics.optionsSold') }}
          </RouterLink>
        </p>
        <p class="ds-stat__value">{{ formatNumber(partsSold, locale) }}</p>
      </div>

      <div class="ds-stat ds-stat--interactive">
        <span class="ds-stat__icon"><Layers /></span>
        <p class="ds-stat__label">
          <RouterLink class="ds-stat__link" to="/company/products">
            {{ t('comp.dashboard.metrics.products') }}
          </RouterLink>
        </p>
        <p class="ds-stat__value">{{ formatNumber(productsCount, locale) }}</p>
      </div>
    </div>

    <!-- Recent operations, and the way to all of them -->
    <section class="dash__recent" aria-labelledby="dash-recent">
      <h2 id="dash-recent" class="ds-section-title">
        {{ t('comp.dashboard.recent.title') }}
      </h2>

      <CEmptyState
        v-if="recentTransactions.length === 0"
        framed
        :description="t('comp.dashboard.recent.empty')"
      />

      <ul v-else class="ds-rows">
        <li v-for="tx in recentTransactions" :key="tx.id" class="ds-row">
          <span class="ds-row__lead" :data-tone="amountTone(tx.amount_cents)">
            <component :is="iconForType(tx.type)" size="sm" />
          </span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ typeLabel(tx.type) }}</span>
            <span class="ds-row__meta">{{ formatDateTime(tx.created_at, locale) }}</span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value">
              {{ formatSignedPrice(tx.amount_cents, tx.currency) }}
            </span>
          </span>
        </li>
      </ul>

      <RouterLink
        to="/company/balance/transactions"
        class="ds-button ds-button--ghost dash__all"
        data-size="sm"
      >
        <span>{{ t('comp.dashboard.recent.all') }}</span>
        <ChevronRight size="sm" />
      </RouterLink>
    </section>
  </template>
</template>

<style scoped>
/* The recent operations: a heading over its rows, on the frame's rhythm. */
.dash__recent {
  display: grid;
  gap: var(--space-3);
}
.dash__all {
  justify-self: start;
}
</style>
