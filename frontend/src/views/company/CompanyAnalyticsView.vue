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
//   1. Page header     -- the frame's header (useScreenHeader).
//
//   2. Top metrics card (big primary value with two
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
//      secondary curiosity in the table beside the chart).
//
//      No charting library. The system's bar chart (K37): an svg of
//      rects in a viewBox of N columns by 100 rows, and the same
//      numbers as a table beside it (the text alternative, in place
//      of the per-bar hover tooltip).
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

import { Download } from '@/components/ui/icons'

import { CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getCompanyAnalytics } from '@/api/company'
import { formatNumber, formatPrice } from '@/utils/format'
import type { CompanyAnalyticsResponse, SalesByMonthEntry, SalesByProductEntry } from '@/api/types'

const { t, locale } = useI18n()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('comp.analytics.title'),
  lead: () => t('comp.analytics.subtitle'),
})

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

const totalRevenue = computed<number>(() => analytics.value?.total_revenue_cents ?? 0)
const revenueThisMonth = computed<number>(() => analytics.value?.revenue_this_month_cents ?? 0)
const totalOptionsSold = computed<number>(() => analytics.value?.total_options_sold ?? 0)

// The period of the chart and of the export: the last 3, 6 or 12 months.
type Period = 3 | 6 | 12
const PERIODS: readonly Period[] = [3, 6, 12]
const period = ref<Period>(12)

/** "YYYY-MM" of the first month inside the chosen period (this month counts). */
const periodStart = computed<string>(() => {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - (period.value - 1))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
})

const salesByMonth = computed<SalesByMonthEntry[]>(() =>
  (analytics.value?.sales_by_month ?? []).filter((m) => m.month >= periodStart.value),
)

function csvCell(value: string | number): string {
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function usd(cents: number): string {
  return (cents / 100).toFixed(2)
}

/** Saves the sales by month of the chosen period and the lifetime sales by product, as one CSV file. */
function exportCsv(): void {
  const lines: string[] = [
    ['month', 'parts_sales_usd', 'parts_sold'].join(','),
    ...salesByMonth.value.map((m) => [m.month, usd(m.revenue_cents), m.options_sold].join(',')),
    '',
    ['product', 'parts_sales_usd_lifetime', 'parts_sold_lifetime'].join(','),
    ...(analytics.value?.sales_by_product ?? []).map((p) =>
      [csvCell(p.product_name), usd(p.revenue_cents), p.options_sold].join(','),
    ),
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'sales.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

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
 * Long month label for the table rows and the range caption,
 * e.g. "April 2026". Carries the year so a row in isolation is
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
  const range = start === end ? start : t('comp.analytics.chart.range', { start, end })
  // K37: the range line names the peak in words, so the darker bar is never the
  // only mark of it.
  if (!peakMonth.value) return range
  const peak = t('comp.analytics.chart.peak', { month: longMonthLabel(peakMonth.value) })
  return `${range}, ${peak}`
})

/** The month of the highest bar (the first one on a tie), or '' when nothing sold. */
const peakMonth = computed<string>(() => {
  const peak = salesByMonth.value.find(
    (m) => m.revenue_cents > 0 && m.revenue_cents === maxRevenue.value,
  )
  return peak ? peak.month : ''
})

/**
 * Per-bar height in rows of the chart (K37: the plot is N columns by 100 rows).
 * Bounded [0, 100] so a malformed payload can't break the layout; a value above
 * zero is at least one row, so a small month is never lost under the baseline.
 */
function barHeightPercent(entry: SalesByMonthEntry): number {
  if (entry.revenue_cents <= 0) return 0
  const pct = (entry.revenue_cents / maxRevenue.value) * 100
  if (pct > 100) return 100
  if (pct < 1) return 1
  return pct
}

/** The plot's width in columns: ten units a month, the bar inside it eight wide. */
const chartWidth = computed<number>(() => salesByMonth.value.length * 10)

// ---------------------------------------------------------------------------
// B2 -- sales_by_product table
// ---------------------------------------------------------------------------

const salesByProduct = computed<SalesByProductEntry[]>(
  () => analytics.value?.sales_by_product ?? [],
)

const hasProductData = computed<boolean>(() => salesByProduct.value.length > 0)

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
  <!-- Initial loading -->
  <CLoader v-if="initialLoading" centered extent="page" />

  <!-- Error -->
  <CEmptyState v-else-if="errored" tone="danger" :title="t('comp.analytics.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="refresh">
        {{ t('comp.analytics.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else>
    <!-- The top figures -->
    <div class="ds-stats">
      <CStatCard
        :label="t('comp.analytics.metrics.totalRevenue')"
        :value="formatPrice(totalRevenue)"
      />
      <CStatCard
        :label="t('comp.analytics.metrics.thisMonth')"
        :value="formatPrice(revenueThisMonth)"
      />
      <CStatCard
        :label="t('comp.analytics.metrics.optionsSold')"
        :value="formatNumber(totalOptionsSold, locale)"
      />
    </div>

    <!-- The period of the chart, and the export -->
    <div class="ds-shell__toolbar">
      <div class="ds-shell__filters">
        <fieldset class="ds-segmented" data-size="sm">
          <legend class="ds-sr-only">{{ t('comp.analytics.period.label') }}</legend>
          <label v-for="p in PERIODS" :key="p" class="ds-segmented__option">
            <input
              class="ds-segmented__input"
              type="radio"
              name="analytics-period"
              :value="p"
              :checked="period === p"
              @change="period = p"
            />
            {{ t('comp.analytics.period.months', { n: p }) }}
          </label>
        </fieldset>
      </div>
      <div class="ds-shell__primary">
        <CButton variant="outline" size="sm" inline @click="exportCsv">
          <Download size="sm" />
          {{ t('comp.analytics.export') }}
        </CButton>
      </div>
    </div>

    <!-- Sales by month: the bar chart with its text alternative (K37) -->
    <p v-if="!hasChartData" class="ds-barchart__empty">{{ t('comp.analytics.chart.empty') }}</p>

    <figure v-else class="ds-barchart">
      <div class="ds-barchart__head">
        <h2 id="canl-chart-title" class="ds-barchart__title">
          {{ t('comp.analytics.chart.title') }}
        </h2>
        <span v-if="rangeCaption" id="canl-chart-range" class="ds-barchart__range">
          {{ rangeCaption }}
        </span>
      </div>
      <div class="ds-barchart__plot">
        <svg
          class="ds-barchart__svg"
          role="img"
          :aria-labelledby="rangeCaption ? 'canl-chart-title canl-chart-range' : 'canl-chart-title'"
          :viewBox="`0 0 ${chartWidth} 100`"
          preserveAspectRatio="none"
          focusable="false"
        >
          <line
            v-for="y in [25, 50, 75]"
            :key="y"
            class="ds-barchart__grid"
            x1="0"
            :x2="chartWidth"
            :y1="y"
            :y2="y"
          />
          <rect
            v-for="(entry, i) in salesByMonth"
            :key="entry.month"
            class="ds-barchart__bar"
            :x="i * 10 + 1"
            :y="100 - barHeightPercent(entry)"
            width="8"
            :height="barHeightPercent(entry)"
            :data-peak="entry.month === peakMonth ? '' : undefined"
          />
        </svg>
        <ul class="ds-barchart__labels" aria-hidden="true">
          <li v-for="entry in salesByMonth" :key="entry.month">
            {{ shortMonthLabel(entry.month) }}
          </li>
        </ul>
      </div>
      <details class="ds-barchart__alt" open>
        <summary>{{ t('comp.analytics.chart.table') }}</summary>
        <div
          class="ds-table-wrap"
          role="region"
          :aria-label="t('comp.analytics.chart.title')"
          tabindex="0"
        >
          <table class="ds-table">
            <thead>
              <tr>
                <th scope="col">{{ t('comp.analytics.period.label') }}</th>
                <th scope="col" class="ds-table__num">
                  {{ t('comp.analytics.metrics.optionsSold') }}
                </th>
                <th scope="col" class="ds-table__num">
                  {{ t('comp.analytics.metrics.totalRevenue') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in salesByMonth" :key="entry.month">
                <th scope="row">{{ longMonthLabel(entry.month) }}</th>
                <td class="ds-table__num">{{ formatNumber(entry.options_sold, locale) }}</td>
                <td class="ds-table__num">{{ formatPrice(entry.revenue_cents) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </figure>

    <!-- B2: sales by product breakdown -->
    <section class="canl__section" aria-labelledby="canl-products">
      <h2 id="canl-products" class="ds-section-title">
        {{ t('comp.analytics.byProduct.title') }}
      </h2>

      <CEmptyState
        v-if="!hasProductData"
        framed
        :description="t('comp.analytics.byProduct.empty')"
      />

      <ul v-else class="ds-rows">
        <li v-for="entry in salesByProduct" :key="entry.product_id" class="ds-row">
          <span class="ds-row__body">
            <span class="ds-row__title">{{ entry.product_name }}</span>
            <span class="ds-row__meta">{{ unitsLabelFor(entry) }}</span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value">{{ formatPrice(entry.revenue_cents) }}</span>
          </span>
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
/* A section: its heading over its rows, on the frame's rhythm. */
.canl__section {
  display: grid;
  gap: var(--space-3);
}
</style>
