<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PortfolioView (Phase F4.4 B3)
// =============================================================================
//
// Investor portfolio screen. Rendered by InvestorShell (and AgentShell
// for the agent-side duplicate) at /investor/portfolio. The frame's header
// (K25) holds the title and the line under it -- this view is a plain content
// column, matching the CompanyListView top-level-tab pattern.
//
// Data source:
//   usePortfolioStore (B1). `fetchPortfolio()` populates positions[].
//   The endpoint is not paginated on the backend (companies per
//   investor are few), so the whole list arrives in one shot. No
//   infinite scroll here -- CompanyPositionView has scroll on the
//   per-purchase list instead.
//
// Hero card:
//   The system's brand card (K07): total value + three stats
//   (Products, Units, Profit%). Total value is current value
//   across all positions; profit% is a CLIENT-side calc
//   `(current - paid) / paid * 100`. See TD-F11d comment below:
//   backend does not emit profit yet, and switching to a server-side
//   figure later will shift tiny cents due to rounding differences,
//   so this number is an estimate until the backend settles it.
//
// Position cards:
//   One interactive card (K07) per company position (PortfolioPositionResponse);
//   its title is the one link, to CompanyPositionView by a role-aware route
//   name. It shows the company name + per-company profit%, followed by three
//   facts (Units / Avg. price / Value) as a key-value list (K49).
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
import { CalendarClock, ChevronRight, Store } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import PendingGifts from '@/components/shared/PendingGifts.vue'
import { usePortfolioStore } from '@/stores/portfolio'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
import type { PortfolioPositionResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = usePortfolioStore()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('inv.portfolio.title'),
  lead: () => t('inv.portfolio.subtitle'),
})

// ---------------------------------------------------------------------------
// Derived state
// ---------------------------------------------------------------------------

const hasPositions = computed<boolean>(() => store.positions.length > 0)

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

// The tone of a profit or loss in a card head (K07 .ds-card__delta data-tone): the
// sign is written in the text, the tone repeats it.
function profitTone(pct: number | null): 'success' | 'danger' | undefined {
  if (pct === null) return undefined
  return pct >= 0 ? 'success' : 'danger'
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

// The instalment plans: no tab holds them (the side menu's second list is gone),
// so they are reached from this row.
const plansRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-installment-plans' : 'investor-installment-plans',
)

const marketRouteName = computed<string>(() =>
  // iter 2.6.x hotfix: market routes removed in iter 2.5 batch 9,
  // catalogue moved to *-companies (CompanyListView). Computed name
  // kept as `marketRouteName` -- internal label, no rename to keep
  // hotfix scope minimal.
  isAgentShell(route) ? 'agent-companies' : 'investor-companies',
)

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
    <!-- Gifts waiting for acceptance -->
    <PendingGifts @accepted="store.fetchPortfolio()" />

    <!-- The instalment plans (K23 row) -->
    <ul class="ds-rows">
      <li class="ds-row">
        <span class="ds-row__lead"><CalendarClock size="sm" /></span>
        <span class="ds-row__body">
          <RouterLink class="ds-row__link" :to="{ name: plansRouteName }">
            <span class="ds-row__title">{{ t('tab.installments') }}</span>
          </RouterLink>
        </span>
        <span class="ds-row__trail"><ChevronRight size="sm" /></span>
      </li>
    </ul>

    <!-- Initial load spinner (no positions yet, fetching) -->
    <CLoader v-if="store.positionsLoading && !store.positionsLoaded && !store.positionsErrored" />

    <!-- Error (first load failed) -->
    <CEmptyState
      v-else-if="store.positionsErrored && !store.positionsLoaded"
      tone="danger"
      :title="t('inv.portfolio.errorTitle')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="store.fetchPortfolio()">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty state -->
    <CEmptyState
      v-else-if="!store.positionsLoading && !hasPositions"
      :title="t('inv.portfolio.empty.title')"
      :description="t('inv.portfolio.empty.description')"
    >
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="goMarket">
          <Store size="sm" />
          {{ t('inv.portfolio.empty.cta') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Populated: hero + position list -->
    <template v-else>
      <!-- Hero card: the brand card (K07); a figure on it takes --on-primary with its sign in the text -->
      <article class="ds-card ds-card--brand">
        <p class="ds-card__label">
          {{ t('inv.portfolio.totalValue') }}
        </p>
        <p class="ds-card__figure">
          {{ formatPrice(totalCurrentValue) }}
        </p>
        <div class="pv__hero-row">
          <div>
            <p class="ds-card__label">
              {{ t('inv.portfolio.products') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(productsCount, locale) }}
            </p>
          </div>
          <div>
            <p class="ds-card__label">
              {{ t('inv.portfolio.units') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(totalUnits, locale) }}
            </p>
          </div>
          <div v-if="totalProfitPercent !== null">
            <p class="ds-card__label">
              {{ t('inv.portfolio.profit') }}
            </p>
            <p class="ds-card__delta">
              {{ formatProfitPercent(totalProfitPercent) }}
            </p>
          </div>
        </div>
      </article>

      <!-- Position cards: the title is the one link -->
      <ul class="pv__list">
        <li v-for="p in store.positions" :key="p.company_id">
          <article class="ds-card ds-card--interactive">
            <header class="ds-card__head">
              <h3 class="ds-card__title">
                <RouterLink
                  class="ds-card__link"
                  :to="{ name: positionRouteName, params: { id: p.company_id } }"
                >
                  {{ p.company_name }}
                </RouterLink>
              </h3>
              <p class="ds-card__delta" :data-tone="profitTone(positionProfitPercent(p))">
                {{ formatProfitPercent(positionProfitPercent(p)) }}
              </p>
            </header>
            <dl class="ds-kv">
              <div class="ds-kv__row">
                <dt>{{ t('inv.portfolio.position.units') }}</dt>
                <dd>{{ formatNumber(p.total_units, locale) }}</dd>
              </div>
              <div class="ds-kv__row">
                <dt>{{ t('inv.portfolio.position.avgPrice') }}</dt>
                <dd>{{ formatPrice(p.avg_price_cents) }}</dd>
              </div>
              <div class="ds-kv__row">
                <dt>{{ t('inv.portfolio.position.value') }}</dt>
                <dd>{{ formatPrice(p.current_value_cents) }}</dd>
              </div>
            </dl>
          </article>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.pv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.pv__hero-row {
  display: flex;
  gap: var(--space-5);
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

/* TILE CEILING — past a point the extra room should be whitespace, not wider
   furniture. Only the ceiling is added, so nothing reflows. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 880px) {
  .pv__list {
    max-inline-size: calc(3 * var(--tile-max));
  }
}
</style>
