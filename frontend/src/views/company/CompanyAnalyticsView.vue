<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyAnalyticsView (Phase F5.2 B1)
// =============================================================================
//
// Analytics tab inside CompanyShell. CompanyShell paints the global
// CHeader and CTabBar -- this view renders only the content column
// with an inline page-header (mirrors the dashboard / products /
// settings views).
//
// SCOPE -- B1 + B2.
//   This file now ships top metrics, the sales_by_month bar chart
//   (B1), and the sales_by_product breakdown table (B2). All three
//   render from a single getCompanyAnalytics() round trip -- the
//   payload contract puts the table data into sales_by_product[]
//   alongside the time series.
//
//   sales_by_product semantics (per backend Sprint 4.3 B5):
//     "ALL products of the company including archived and zero-sales,
//      sorted by revenue_cents DESC". The point of showing zero-sales
//      rows is so the company sees what isn't selling -- so we render
//      them, do not dim them, and label units as "No sales yet" instead
//      of "0 units" to make the message explicit.
//
// LAYOUT, in render order:
//
//   1. Page header     -- title + subtitle, no data call.
//
//   2. Top metrics card (mockup style: big primary value with two
//      sub-metrics underneath, NOT three equal tiles). The dashboard
//      already shows three tiles for the same role; the analytics
//      view leans more "report-like" with one headline figure.
//        - Primary: total_revenue_cents (formatPrice)
//        - Sub left: revenue_this_month_cents (formatPrice)
//        - Sub right: total_options_sold (formatNumber)
//
//   3. Bar chart -- sales_by_month, oldest first, height proportional
//      to revenue_cents (per the F5.2 B1 design decision: revenue is
//      the primary business metric for the company; units are a
//      secondary curiosity in the hover tooltip).
//
//      No charting library. The mockup uses a CSS bar chart
//      (`.chart-bars` / `.chart-bar { height: % }`); the native
//      `title=` attribute carries the per-bar tooltip. We follow the
//      same pattern -- adding a charting dep (~50KB gzip for recharts
//      etc.) for one chart is poor leverage at this stage.
//
//      Bar height policy:
//        - Empty data: render the empty placeholder, no chart.
//        - All zero revenues (theoretical -- the backend would skip
//          such months, but defensive): every bar 0% -> visually
//          collapses to a baseline; the placeholder is a better UX
//          but skipping the bars at runtime would be a contract
//          violation. We take the visual baseline.
//        - Otherwise: bar.height = revenue / max(revenue) * 100%.
//          One outlier month flattens the rest by design -- this is
//          how the magnitude story reads correctly for the
//          dashboard reader.
//
//      Range caption above the chart spells out start / end month
//      explicitly so the reader doesn't have to interpolate from
//      the abbreviated bar labels.
//
// DATA SOURCE.
//   Local `ref<CompanyAnalyticsResponse | null>` -- no Pinia store.
//   Analytics is single-screen, single-fetch; a store would only
//   add boilerplate. If a future scope needs cross-view sharing
//   (e.g. notifications driven by sales deltas), introducing a
//   store at that point is a clean refactor.
//
//   getCompanyAnalytics() (api/company.ts, F5.1 B0) returns the
//   full payload in one round trip -- top metrics, sales_by_month,
//   sales_by_product. We do NOT reuse companyDashboard cache for
//   the top metrics: revenue_this_month_cents only lives in the
//   analytics endpoint, so we have to fetch anyway.
//
//   Epoch guard mirrors the FP-17 pattern from companyDashboard /
//   transactions / portfolio: every fetch captures a counter, only
//   the latest publishes; a Retry click that lands while a previous
//   fetch is still in flight cannot regress the UI.
//
// RENDER POLICY -- ALL OR NOTHING.
//   - initialLoading: spinner. Holds until analytics resolves once.
//   - hasError:        full-screen empty-state + Retry. Either
//                      profile error (we do not depend on profile,
//                      but include it defensively) or analytics
//                      error routes here.
//   - loaded:          metrics + chart.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { getCompanyAnalytics } from '@/api/company'
import { formatNumber, formatPrice } from '@/utils/format'
import type {
  CompanyAnalyticsResponse,
  SalesByMonthEntry,
  SalesByProductEntry,
} from '@/api/types'

const { t, locale } = useI18n()

// ---------------------------------------------------------------------------
// State + epoch guard
// ---------------------------------------------------------------------------

const analytics = ref<CompanyAnalyticsResponse | null>(null)
const loading = ref<boolean>(false)
const errored = ref<boolean>(false)

// Plain `let` inside <script setup> is fine -- the module-scoped
// closure lives for the component's lifetime. Mirrors the pattern
// from stores/products.ts and stores/companyDashboard.ts.
let fetchEpoch = 0

async function refresh(): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  try {
    const resp = await getCompanyAnalytics()
    if (epoch !== fetchEpoch) return
    analytics.value = resp
  } catch {
    if (epoch !== fetchEpoch) return
    errored.value = true
  } finally {
    if (epoch === fetchEpoch) loading.value = false
  }
}

onMounted(() => {
  void refresh()
})

// ---------------------------------------------------------------------------
// Derived state
// ---------------------------------------------------------------------------

const initialLoading = computed<boolean>(() => {
  if (errored.value) return false
  return analytics.value === null
})

const totalRevenue = computed<number>(
  () => analytics.value?.total_revenue_cents ?? 0,
)
const revenueThisMonth = computed<number>(
  () => analytics.value?.revenue_this_month_cents ?? 0,
)
const totalOptionsSold = computed<number>(
  () => analytics.value?.total_options_sold ?? 0,
)

const salesByMonth = computed<SalesByMonthEntry[]>(
  () => analytics.value?.sales_by_month ?? [],
)

const hasChartData = computed<boolean>(() => salesByMonth.value.length > 0)

/**
 * Maximum revenue across the visible bars. Used as the denominator
 * for bar heights. Falls back to 1 to avoid a divide-by-zero render
 * (theoretical: backend skips zero-revenue months, but the guard
 * keeps the template branchless).
 */
const maxRevenue = computed<number>(() => {
  const values = salesByMonth.value.map((m) => m.revenue_cents)
  if (values.length === 0) return 1
  const max = Math.max(...values)
  return max > 0 ? max : 1
})

/**
 * Parse "YYYY-MM" into a Date anchored on the first of that month
 * in local time. Used as the source for month-name formatting.
 * Returns null on a malformed input -- callers fall back to the
 * raw string.
 */
function parseYearMonth(ym: string): Date | null {
  const m = /^(\d{4})-(\d{2})$/.exec(ym)
  if (!m) return null
  const year = Number(m[1])
  const month = Number(m[2]) - 1
  if (Number.isNaN(year) || Number.isNaN(month)) return null
  return new Date(year, month, 1)
}

/**
 * Short month label for a bar's x-axis label, e.g. "Apr". Locale-aware
 * via toLocaleDateString. The year is intentionally absent here -- it
 * lives in the chart range caption above the bars to avoid clutter
 * on a 12-month axis.
 */
function shortMonthLabel(ym: string): string {
  const d = parseYearMonth(ym)
  if (!d) return ym
  return d.toLocaleDateString(locale.value, { month: 'short' })
}

/**
 * Long month label for the hover tooltip and the range caption,
 * e.g. "April 2026". Carries the year so a tooltip in isolation is
 * unambiguous.
 */
function longMonthLabel(ym: string): string {
  const d = parseYearMonth(ym)
  if (!d) return ym
  return d.toLocaleDateString(locale.value, {
    month: 'long',
    year: 'numeric',
  })
}

/**
 * Tooltip string per bar: "April 2026 · $12,345.00 · 100 units".
 * Native browser tooltip via the `title=` attribute -- enough at
 * this scope; a custom hover popover would need pointer / focus
 * handling we don't need yet.
 */
function tooltipFor(entry: SalesByMonthEntry): string {
  const month = longMonthLabel(entry.month)
  const revenue = formatPrice(entry.revenue_cents)
  const units = t('comp.analytics.chart.tooltipUnits', {
    units: formatNumber(entry.options_sold, locale.value),
  })
  return `${month} · ${revenue} · ${units}`
}

/**
 * Chart range caption above the bars: "Apr 2025 — Apr 2026". Uses
 * the long format so the year is explicit. Hidden when the chart
 * is empty (no months to range over).
 */
const rangeCaption = computed<string>(() => {
  const entries = salesByMonth.value
  if (entries.length === 0) return ''
  const first = entries[0]
  const last = entries[entries.length - 1]
  const start = longMonthLabel(first.month)
  const end = longMonthLabel(last.month)
  // For a single month, just show that month rather than "X — X".
  if (start === end) return start
  return t('comp.analytics.chart.range', { start, end })
})

/**
 * Per-bar height as a percentage of the chart area. Bounded [0, 100]
 * so a malformed payload can't break the layout. Floor at a small
 * sliver so a bar with revenue > 0 is always visible even when the
 * max bar dwarfs it -- otherwise tiny months render as a pixel and
 * disappear under the baseline.
 */
function barHeightPercent(entry: SalesByMonthEntry): number {
  if (entry.revenue_cents <= 0) return 0
  const pct = (entry.revenue_cents / maxRevenue.value) * 100
  if (pct > 100) return 100
  if (pct < 4) return 4
  return pct
}

// ---------------------------------------------------------------------------
// B2 -- sales_by_product table
// ---------------------------------------------------------------------------

const salesByProduct = computed<SalesByProductEntry[]>(
  () => analytics.value?.sales_by_product ?? [],
)

const hasProductData = computed<boolean>(
  () => salesByProduct.value.length > 0,
)

/**
 * Sub-line label for each row. Zero-sales products show "No sales yet"
 * instead of "0 units" -- explicit about the situation rather than
 * leaving the reader to translate a numeric zero. Backend includes
 * zero-sales rows on purpose (Sprint 4.3 B5) so the company sees what
 * isn't moving; the label has to carry that intent in plain English
 * (and locale equivalents in B7 i18n catchup).
 */
function unitsLabelFor(entry: SalesByProductEntry): string {
  if (entry.options_sold <= 0) {
    return t('comp.analytics.byProduct.noSales')
  }
  return t('comp.analytics.byProduct.units', {
    n: formatNumber(entry.options_sold, locale.value),
  })
}
</script>

<template>
  <div class="canl">
    <!-- Page header -->
    <div class="canl__header">
      <h1 class="canl__title">{{ t('comp.analytics.title') }}</h1>
      <p class="canl__subtitle">{{ t('comp.analytics.subtitle') }}</p>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="canl__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="canl__center">
      <CEmptyState :title="t('comp.analytics.errorTitle')" />
      <CButton variant="outline" size="sm" @click="refresh">
        {{ t('comp.analytics.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Top metrics card: big primary + two sub-metrics row -->
      <section class="canl__metrics">
        <div class="canl__metrics-label">
          {{ t('comp.analytics.metrics.totalRevenue') }}
        </div>
        <div class="canl__metrics-value">
          {{ formatPrice(totalRevenue) }}
        </div>
        <div class="canl__metrics-row">
          <div class="canl__metrics-sub">
            <div class="canl__metrics-sub-label">
              {{ t('comp.analytics.metrics.thisMonth') }}
            </div>
            <div class="canl__metrics-sub-value">
              {{ formatPrice(revenueThisMonth) }}
            </div>
          </div>
          <div class="canl__metrics-sub">
            <div class="canl__metrics-sub-label">
              {{ t('comp.analytics.metrics.optionsSold') }}
            </div>
            <div class="canl__metrics-sub-value">
              {{ formatNumber(totalOptionsSold, locale) }}
            </div>
          </div>
        </div>
      </section>

      <!-- Sales by month chart -->
      <section class="canl__chart-section">
        <div class="canl__chart-header">
          <h2 class="canl__chart-title">
            {{ t('comp.analytics.chart.title') }}
          </h2>
          <span v-if="rangeCaption" class="canl__chart-range">
            {{ rangeCaption }}
          </span>
        </div>

        <!-- Empty state -->
        <p v-if="!hasChartData" class="canl__chart-empty">
          {{ t('comp.analytics.chart.empty') }}
        </p>

        <!-- Bars -->
        <div v-else class="canl__chart">
          <div class="canl__chart-bars">
            <div
              v-for="entry in salesByMonth"
              :key="entry.month"
              class="canl__chart-col"
            >
              <div class="canl__chart-bar-wrap">
                <div
                  class="canl__chart-bar"
                  :style="{ height: barHeightPercent(entry) + '%' }"
                  :title="tooltipFor(entry)"
                />
              </div>
              <div class="canl__chart-month">
                {{ shortMonthLabel(entry.month) }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- B2: sales by product breakdown -->
      <section class="canl__table-section">
        <div class="canl__chart-header">
          <h2 class="canl__chart-title">
            {{ t('comp.analytics.byProduct.title') }}
          </h2>
        </div>

        <p v-if="!hasProductData" class="canl__chart-empty">
          {{ t('comp.analytics.byProduct.empty') }}
        </p>

        <ul v-else class="canl__table">
          <li
            v-for="entry in salesByProduct"
            :key="entry.product_id"
            class="canl__row"
          >
            <div class="canl__row-body">
              <div class="canl__row-name">{{ entry.product_name }}</div>
              <div class="canl__row-sub">{{ unitsLabelFor(entry) }}</div>
            </div>
            <div class="canl__row-revenue">
              {{ formatPrice(entry.revenue_cents) }}
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.canl {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Page header */
.canl__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.canl__title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.canl__subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Whole-screen states */
.canl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: calc(100vh - 240px);
  min-height: calc(100dvh - 240px);
  padding: 24px;
  text-align: center;
}

/*
 * Top metrics card -- inspired by the mockup balance-card:
 * gradient background with the primary value as the headline and a
 * row of two sub-metrics underneath. The gradient uses --primary as
 * the anchor; --primary-dark falls back to --primary so themes that
 * only define one tone still render.
 */
.canl__metrics {
  padding: 18px 18px 16px;
  border-radius: var(--radius);
  background: linear-gradient(
    135deg,
    var(--primary),
    var(--primary-active)
  );
  color: var(--on-primary);
}
.canl__metrics-label {
  font-size: 12px;
  font-weight: 600;
  opacity: 0.85;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.canl__metrics-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
}
.canl__metrics-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}
.canl__metrics-sub-label {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}
.canl__metrics-sub-value {
  font-size: 16px;
  font-weight: 700;
}

/* Chart section */
.canl__chart-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.canl__chart-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.canl__chart-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.canl__chart-range {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.canl__chart-empty {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px dashed var(--border-default);
  text-align: center;
}

/* Chart container */
.canl__chart {
  padding: 16px 12px 8px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}

.canl__chart-bars {
  display: flex;
  align-items: stretch;
  gap: 6px;
  height: 160px;
}

/*
 * Each column carries the bar (top, flexes to fill the tallest area
 * available) and a month label below. column-reverse on the wrapper
 * anchors the bar to the bottom of the chart area regardless of its
 * height percentage.
 */
.canl__chart-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  min-width: 0;
}

.canl__chart-bar-wrap {
  flex: 1;
  display: flex;
  flex-direction: column-reverse;
  min-height: 0;
}

.canl__chart-bar {
  width: 100%;
  background: var(--primary);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  transition: height 0.3s ease, opacity 0.15s;
  cursor: default;
  min-height: 1px;
}
.canl__chart-bar:hover {
  opacity: 0.8;
}

.canl__chart-month {
  font-size: 10px;
  color: var(--text-tertiary);
  text-align: center;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* B2 -- sales by product table */
.canl__table-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.canl__table {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.canl__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}

.canl__row-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.canl__row-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.canl__row-sub {
  font-size: 12px;
  color: var(--text-secondary);
}

.canl__row-revenue {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
  white-space: nowrap;
}
</style>
