<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSupportStats (H41)
// =============================================================================
//
// The "Statistics" tab of the support screen (StaffSupportView): support
// over a period of APPEALS -- the tickets created between two days of the
// operator's own calendar, both included. Their edges are this browser's
// local midnights (supportPeople.dayEdges), sent as instants with their
// zone: the backend refuses an edge without one, and a period that ends
// before it starts.
//
// What it shows is the backend's own (GET /api/v1/staff/support/stats):
//   - the six categories, spam left out: appeals, how many were rated, the
//     average and the share of 4-5 -- a category nobody rated shows a dash,
//     not a zero;
//   - the total of the six -- the same count as the list without spam for
//     the same days;
//   - spam: the spam tickets still there plus those the bin took;
//   - by operator: the ratings by the operator each one is about.
// Opens on today.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState, CInput, CLoader } from '@/components/ui'
import { useSupportStore } from '@/stores/support'
import type { SupportStatsFigures } from '@/api/support'
import { dayEdges, personName } from './supportPeople'

const { t, locale } = useI18n()
const support = useSupportStore()

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const from = ref(today())
const to = ref(today())

// The period as instants: the first day's midnight to the midnight after
// the last day. null when a day is missing or the last precedes the first --
// nothing is asked then, and the screen says why.
const period = computed<{ from: string; to: string } | null>(() => {
  const first = dayEdges(from.value)
  const last = dayEdges(to.value)
  if (first === null || last === null) return null
  if (last.to <= first.from) return null
  return { from: first.from, to: last.to }
})

function load(): void {
  const p = period.value
  if (p !== null) void support.fetchStats(p.from, p.to)
}

watch(period, load)
onMounted(load)

const numberFormat = computed(() => new Intl.NumberFormat(locale.value))
const percentFormat = computed(
  () => new Intl.NumberFormat(locale.value, { style: 'percent', maximumFractionDigits: 0 }),
)

function average(f: SupportStatsFigures): string {
  return f.average === null
    ? t('staff.support.stats.noValue')
    : new Intl.NumberFormat(locale.value, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 2,
      }).format(f.average)
}

function share(f: SupportStatsFigures): string {
  return f.share_4_5 === null
    ? t('staff.support.stats.noValue')
    : percentFormat.value.format(f.share_4_5)
}

function count(n: number): string {
  return numberFormat.value.format(n)
}

function errorMessage(): string {
  const err = support.statsError
  if (!err) return ''
  if (err.status === 502 || err.status === 504) return t('staff.support.errorUnavailable')
  return t('staff.support.errorGeneric')
}
</script>

<template>
  <section class="sstat" :aria-label="t('staff.support.stats.title')">
    <div class="sstat__period">
      <CInput v-model="from" type="date" :label="t('staff.support.stats.from')" />
      <CInput v-model="to" type="date" :label="t('staff.support.stats.to')" />
    </div>
    <p v-if="period === null" class="ds-field__error">{{ t('staff.support.stats.badPeriod') }}</p>

    <CLoader v-else-if="support.statsLoading && support.stats === null" centered />

    <CEmptyState v-else-if="support.statsError" tone="danger" :description="errorMessage()">
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else-if="support.stats !== null">
      <div class="sstat__scroll">
        <table class="sstat__table">
          <caption class="ds-sr-only">
            {{
              t('staff.support.stats.byCategory')
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ t('staff.support.category') }}</th>
              <th scope="col">{{ t('staff.support.stats.tickets') }}</th>
              <th scope="col">{{ t('staff.support.stats.rated') }}</th>
              <th scope="col">{{ t('staff.support.stats.average') }}</th>
              <th scope="col">{{ t('staff.support.stats.share45') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in support.stats.categories" :key="row.category">
              <th scope="row">{{ t(`staff.support.categories.${row.category}`) }}</th>
              <td>{{ count(row.tickets) }}</td>
              <td>{{ count(row.rated) }}</td>
              <td>{{ average(row) }}</td>
              <td>{{ share(row) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="sstat__total">
              <th scope="row">{{ t('staff.support.stats.total') }}</th>
              <td>{{ count(support.stats.total.tickets) }}</td>
              <td>{{ count(support.stats.total.rated) }}</td>
              <td>{{ average(support.stats.total) }}</td>
              <td>{{ share(support.stats.total) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p class="sstat__spam">
        {{ t('staff.support.stats.spam', { n: count(support.stats.spam.tickets) }) }}
        <span v-if="support.stats.spam.deleted > 0" class="ds-note">
          {{ t('staff.support.stats.spamDeleted', { n: count(support.stats.spam.deleted) }) }}
        </span>
      </p>

      <h3 class="ds-section-title">{{ t('staff.support.stats.byOperator') }}</h3>
      <p v-if="support.stats.resolvers.length === 0" class="ds-note">
        {{ t('staff.support.stats.noRatings') }}
      </p>
      <div v-else class="sstat__scroll">
        <table class="sstat__table">
          <thead>
            <tr>
              <th scope="col">{{ t('staff.support.stats.operator') }}</th>
              <th scope="col">{{ t('staff.support.stats.rated') }}</th>
              <th scope="col">{{ t('staff.support.stats.average') }}</th>
              <th scope="col">{{ t('staff.support.stats.share45') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in support.stats.resolvers"
              :key="row.operator?.user_id ?? personName(row.operator)"
            >
              <th scope="row">{{ personName(row.operator) }}</th>
              <td>{{ count(row.rated) }}</td>
              <td>{{ average(row) }}</td>
              <td>{{ share(row) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.sstat {
  display: grid;
  gap: var(--space-4);
  min-inline-size: 0;
}
.sstat__period {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: var(--space-3);
}
.sstat__scroll {
  overflow-x: auto;
}
.sstat__table {
  inline-size: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
.sstat__table th,
.sstat__table td {
  padding: var(--space-2);
  text-align: start;
  border-block-end: 1px solid var(--border-default);
  white-space: nowrap;
}
.sstat__table td {
  text-align: end;
  font-variant-numeric: tabular-nums;
}
.sstat__total th,
.sstat__total td {
  font-weight: 600;
}
.sstat__spam {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
