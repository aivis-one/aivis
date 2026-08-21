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
              <Building :size="16" class="pv__item-company-icon" />
              <span class="pv__item-company-name">{{ p.company_name }}</span>
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
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.pv__header { display: flex; flex-direction: column; gap: var(--space-1); }
.pv__title {
  font-size: var(--fs-lg); font-weight: 700;
  color: var(--text-primary); margin: 0;
}
.pv__subtitle {
  font-size: var(--fs-sm); color: var(--text-secondary); margin: 0;
}

.pv__center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

/* Hero card */
.pv__hero {
  padding: var(--space-4-lg);
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: var(--on-primary);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.pv__hero-label {
  font-size: var(--fs-xs);
  opacity: 0.9;
}
.pv__hero-value {
  font-size: var(--fs-3xl);
  font-weight: 700;
  line-height: 1.1;
}
.pv__hero-row {
  display: flex;
  gap: var(--space-5);
  margin-top: var(--space-1);
}
.pv__hero-stat-label {
  font-size: var(--fs-xs);
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: var(--space-1);
}
.pv__hero-stat-value {
  font-size: var(--fs-body);
  font-weight: 700;
}

/* Position cards */
.pv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.pv__item {
  padding: var(--space-4) var(--space-4);
  border-radius: var(--radius);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
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
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
/* The ellipsis belongs to the NAME TEXT, never to this flex container. On the
   container it is INERT -- text-overflow acts on inline content in a BLOCK, not
   on a flex container's anonymous text item -- so at 390 the name was cut dead
   at 263px with 283px hidden and NO ellipsis, while overflow:hidden crushed the
   non-shrinking icon to zero width instead. Identical mechanism and identical
   repair to .lb__nametext in LeaderboardView, whose fix landed on one file and
   left this twin untouched. Found by the 2026-08-19 sweep; renders in BOTH the
   investor and agent cabinets, phone tier only. */
.pv__item-company {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.pv__item-company-icon {
  flex-shrink: 0;
}
.pv__item-company-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pv__item-head-right {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}
.pv__item-chev { color: var(--text-tertiary); }

.pv__item-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}
.pv__item-stat-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--space-1);
}
.pv__item-stat-value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

/* Profit chip */
.pv__profit {
  font-size: var(--fs-xs);
  font-weight: 700;
}
.pv__profit--up { color: var(--success); }
.pv__profit--down { color: var(--danger); }

/* A6: --success and --danger are tuned against --bg-page. `.pv__hero` is a
   saturated azure gradient carrying --on-primary, and on it these two measure
   1.35 / 1.08 in light and 1.04 / 1.23 in dark -- the figure telling an
   investor whether they are up or down was effectively invisible on the one
   panel that leads the screen, in BOTH themes and BOTH directions.
   formatProfitPercent() already prefixes an explicit + or -, so the direction
   is carried by the text and nothing is lost by taking the panel's own colour
   here. (WCAG 1.4.1 wants that anyway: not by colour alone.)
   The list rows below the hero sit on --bg-page and keep green and red. */
.pv__hero .pv__profit--up,
.pv__hero .pv__profit--down {
  color: var(--on-primary);
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
  .pv__item-stats { max-width: calc(3 * var(--tile-max)); }
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.pv__subtitle { max-width: var(--maxw-prose); }
</style>
