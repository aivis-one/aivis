<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PortfolioView (Phase F4.4 B3)
// =============================================================================
//
// Investor portfolio screen. Rendered by InvestorShell (and AgentShell
// for the agent-side duplicate) at /investor/portfolio. Shell already
// paints CHeader + CTabBar -- this view is a plain content column,
// matching the CompanyListView top-level-tab pattern.
//
// Data source:
//   usePortfolioStore (B1). `fetchPortfolio()` populates positions[].
//   The endpoint is not paginated on the backend (companies per
//   investor are few), so the whole list arrives in one shot. No
//   infinite scroll here -- CompanyPositionView has scroll on the
//   per-purchase list instead.
//
// Hero card:
//   Mirrors the visual in mockups/investor-shell/mockup.html screen-
//   portfolio: gradient full-width card with total value + three stat
//   columns (Products, Units, Profit%). Total value is current value
//   across all positions; profit% is a CLIENT-side calc
//   `(current - paid) / paid * 100`. See TD-F11d comment below:
//   backend does not emit profit yet, and switching to a server-side
//   figure later will shift tiny cents due to rounding differences,
//   so this number is an estimate until the backend settles it.
//
// Position cards:
//   One card per company position (PortfolioPositionResponse). Tap
//   routes to CompanyPositionView via role-aware route name. Visual
//   from the mockup .portfolio-item: company name + per-company
//   profit%, followed by three stats (Units / Avg. price / Value).
//
// Empty state:
//   CTA to companies catalogue. If the investor has zero companies
//   in positions[], the list renders the empty state block with a
//   button to navigate to /investor/companies (or /agent/companies).
//
// Loading / error states:
//   Same taxonomy as CompanyListView -- centered spinner during first
//   load, CEmptyState + retry on error. Silent refresh on return.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, ChevronRight, Store } from 'lucide-vue-next'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { usePortfolioStore } from '@/stores/portfolio'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
import type { PortfolioPositionResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = usePortfolioStore()

// ---------------------------------------------------------------------------
// Derived state
// ---------------------------------------------------------------------------

const hasPositions = computed<boolean>(
  () => store.positions.length > 0,
)

// Aggregate rollups for the hero card. Sum across positions instead
// of a second round-trip to /dashboard/summary -- dashboardStore may
// not be refreshed when the user lands here by deep-link.
const totalCurrentValue = computed<number>(() =>
  store.positions.reduce((acc, p) => acc + p.current_value_cents, 0),
)
const totalInvested = computed<number>(() =>
  store.positions.reduce((acc, p) => acc + p.total_paid_cents, 0),
)
const totalUnits = computed<number>(() =>
  store.positions.reduce((acc, p) => acc + p.total_units, 0),
)
const productsCount = computed<number>(() => store.positions.length)

// Profit % across the whole portfolio. Guard against divide-by-zero
// when an investor only holds gift units (invested === 0). Returns
// null to skip the profit column in that case.
//
// TD-F11d: client-side profit calc. When the backend emits a
// portfolio-level profit field, drop this computed and read from
// PortfolioResponse directly. The switch will shift displayed values
// by sub-cent amounts due to rounding -- callers should not compare
// against cached figures.
const totalProfitPercent = computed<number | null>(() => {
  if (totalInvested.value <= 0) return null
  const diff = totalCurrentValue.value - totalInvested.value
  return (diff / totalInvested.value) * 100
})

// ---------------------------------------------------------------------------
// Per-position helpers
// ---------------------------------------------------------------------------

function positionProfitPercent(p: PortfolioPositionResponse): number | null {
  if (p.total_paid_cents <= 0) return null
  const diff = p.current_value_cents - p.total_paid_cents
  return (diff / p.total_paid_cents) * 100
}

function profitClass(pct: number | null): string {
  if (pct === null) return ''
  if (pct >= 0) return 'pv__profit--up'
  return 'pv__profit--down'
}

function formatProfitPercent(pct: number | null): string {
  if (pct === null) return '—'
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

const positionRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-company-position' : 'investor-company-position',
)

const marketRouteName = computed<string>(() =>
  // iter 2.6.x hotfix: market routes removed in iter 2.5 batch 9,
  // catalogue moved to *-companies (CompanyListView). Computed name
  // kept as `marketRouteName` -- internal label, no rename to keep
  // hotfix scope minimal.
  isAgentShell(route) ? 'agent-companies' : 'investor-companies',
)

function openPosition(p: PortfolioPositionResponse): void {
  void safeNavigate(
    router.push({
      name: positionRouteName.value,
      params: { id: p.company_id },
    }),
    '[PortfolioView] to company position',
  )
}

function goMarket(): void {
  void safeNavigate(
    router.push({ name: marketRouteName.value }),
    '[PortfolioView] to companies list',
  )
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  // Always refresh on mount -- stale positions in a long-lived SPA
  // session shouldn't misrepresent current value. The store's epoch
  // guard makes this safe against navigation-away races.
  void store.fetchPortfolio()
})
</script>

<template>
  <div class="pv">
    <!-- Header -->
    <div class="pv__header">
      <h1 class="pv__title">{{ t('inv.portfolio.title') }}</h1>
      <p class="pv__subtitle">{{ t('inv.portfolio.subtitle') }}</p>
    </div>

    <!-- Initial load spinner (no positions yet, fetching) -->
    <div
      v-if="store.positionsLoading && !store.positionsLoaded && !store.positionsErrored"
      class="pv__center"
    >
      <CLoader :size="28" />
    </div>

    <!-- Error (first load failed) -->
    <div
      v-else-if="store.positionsErrored && !store.positionsLoaded"
      class="pv__center"
    >
      <CEmptyState :title="t('inv.portfolio.errorTitle')" />
      <CButton variant="outline" size="sm" @click="store.fetchPortfolio()">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!store.positionsLoading && !hasPositions"
      class="pv__center"
    >
      <CEmptyState
        :title="t('inv.portfolio.empty.title')"
        :description="t('inv.portfolio.empty.description')"
      />
      <CButton variant="primary" size="sm" @click="goMarket">
        <Store :size="16" />
        {{ t('inv.portfolio.empty.cta') }}
      </CButton>
    </div>

    <!-- Populated: hero + position list -->
    <template v-else>
      <!-- Hero card -->
      <div class="pv__hero">
        <div class="pv__hero-label">
          {{ t('inv.portfolio.totalValue') }}
        </div>
        <div class="pv__hero-value">
          {{ formatPrice(totalCurrentValue) }}
        </div>
        <div class="pv__hero-row">
          <div class="pv__hero-stat">
            <div class="pv__hero-stat-label">
              {{ t('inv.portfolio.products') }}
            </div>
            <div class="pv__hero-stat-value">
              {{ formatNumber(productsCount, locale) }}
            </div>
          </div>
          <div class="pv__hero-stat">
            <div class="pv__hero-stat-label">
              {{ t('inv.portfolio.units') }}
            </div>
            <div class="pv__hero-stat-value">
              {{ formatNumber(totalUnits, locale) }}
            </div>
          </div>
          <div v-if="totalProfitPercent !== null" class="pv__hero-stat">
            <div class="pv__hero-stat-label">
              {{ t('inv.portfolio.profit') }}
            </div>
            <div
              class="pv__hero-stat-value"
              :class="profitClass(totalProfitPercent)"
            >
              {{ formatProfitPercent(totalProfitPercent) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Position cards -->
      <ul class="pv__list">
        <li
          v-for="p in store.positions"
          :key="p.company_id"
          class="pv__item"
          tabindex="0"
          role="button"
          @click="openPosition(p)"
          @keyup.enter="openPosition(p)"
          @keyup.space.prevent="openPosition(p)"
        >
          <div class="pv__item-head">
            <span class="pv__item-company">
              <Building :size="16" />
              {{ p.company_name }}
            </span>
            <span class="pv__item-head-right">
              <span
                class="pv__profit"
                :class="profitClass(positionProfitPercent(p))"
              >
                {{ formatProfitPercent(positionProfitPercent(p)) }}
              </span>
              <ChevronRight :size="16" class="pv__item-chev" />
            </span>
          </div>
          <div class="pv__item-stats">
            <div class="pv__item-stat">
              <div class="pv__item-stat-label">
                {{ t('inv.portfolio.position.units') }}
              </div>
              <div class="pv__item-stat-value">
                {{ formatNumber(p.total_units, locale) }}
              </div>
            </div>
            <div class="pv__item-stat">
              <div class="pv__item-stat-label">
                {{ t('inv.portfolio.position.avgPrice') }}
              </div>
              <div class="pv__item-stat-value">
                {{ formatPrice(p.avg_price_cents) }}
              </div>
            </div>
            <div class="pv__item-stat">
              <div class="pv__item-stat-label">
                {{ t('inv.portfolio.position.value') }}
              </div>
              <div class="pv__item-stat-value">
                {{ formatPrice(p.current_value_cents) }}
              </div>
            </div>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.pv {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pv__header { display: flex; flex-direction: column; gap: 4px; }
.pv__title {
  font-size: 20px; font-weight: 700;
  color: var(--text-primary); margin: 0;
}
.pv__subtitle {
  font-size: 14px; color: var(--text-secondary); margin: 0;
}

.pv__center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 16px;
  min-height: 240px;
  padding: 24px;
}

/* Hero card */
.pv__hero {
  padding: 20px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: var(--on-primary);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pv__hero-label {
  font-size: 13px;
  opacity: 0.9;
}
.pv__hero-value {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.1;
}
.pv__hero-row {
  display: flex;
  gap: 24px;
  margin-top: 4px;
}
.pv__hero-stat-label {
  font-size: 11px;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 2px;
}
.pv__hero-stat-value {
  font-size: 16px;
  font-weight: 700;
}

/* Position cards */
.pv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pv__item {
  padding: 14px 16px;
  border-radius: var(--radius);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: border-color 0.15s;
}
.pv__item:hover { border-color: var(--primary); }
.pv__item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.pv__item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.pv__item-company {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pv__item-head-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.pv__item-chev { color: var(--text-tertiary); }

.pv__item-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.pv__item-stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: 2px;
}
.pv__item-stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Profit chip */
.pv__profit {
  font-size: 12px;
  font-weight: 700;
}
.pv__profit--up { color: var(--success); }
.pv__profit--down { color: var(--danger); }
</style>
