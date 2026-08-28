<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InstallmentPlansView (TASK-39 item 1)
// =============================================================================
//
// List of the authenticated buyer's installment plans, newest first.
// Reached from the "Installment plans" tile in InvestorMoreView /
// AgentMoreView (see those files' TILES arrays) and mounted under both
// /investor/installments and /agent/installments via role-distinct
// route names -- same "shared component lives physically under
// views/investor/, other shells' routes import it directly" convention
// already used for PortfolioView / NotificationsInboxView (see router
// comments at each *-installment-plans route).
//
// NOT to be confused with InstallmentView.vue (routes *-installment,
// path installment/:id where :id is a PRODUCT id) -- that is the plan
// CREATION/confirmation screen. This view lists ALREADY-CREATED plans
// (GET /api/v1/installments/me), which no screen consumed before this
// (TASK-39's measured gap).
//
// STATUS SOURCE OF TRUTH: backend/app/modules/installments/constants.py
//   InstallmentPlanStatus: active | completed | defaulted | cancelled
// `defaulted` is the only failure state visible on the LIST payload --
// InstallmentPlanResponse (the list item shape) carries no tranche
// data, so a per-tranche OVERDUE state on an otherwise `active` plan
// is NOT knowable here without an N+1 fetch per row. That is a real
// backend-contract limitation (see task report), not an oversight;
// the DETAIL view (InstallmentPlanDetailView.vue) is where a single
// plan's OVERDUE tranches become visible, via GET /installments/{id}
// which does include the tranche list.
//
// PAGINATION: page/per_page (NOT cursor -- installments/me is a plain
// offset-paginated endpoint, unlike comms' inbox). Mirrors BalanceView's
// payment-history pattern: local page/total refs, a stale-fetch epoch
// guard shared between fetchFirstPage/loadMore, and
// composables/usePagination's useInfiniteScroll on a bottom sentinel.
//
// LOADING / ERROR / EMPTY TAXONOMY (matches PortfolioView /
// NotificationsInboxView): first-load spinner while items.length === 0
// and no error yet; error state (CEmptyState + retry) when the first
// load failed; empty state (CEmptyState + CTA to the companies
// catalogue) when the load succeeded with zero plans. Populated state
// renders the list plus the infinite-scroll sentinel/load-more-error
// row underneath, identical shape to BalanceView's payment history.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CalendarClock, CreditCard } from 'lucide-vue-next'
import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { listMyPlans } from '@/api/installments'
import { formatDateTime, formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { InstallmentPlanResponse } from '@/api/types'

const PER_PAGE = 20

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()

const items = ref<InstallmentPlanResponse[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loaded = ref(false)
const errored = ref(false)
const loadMoreErrored = ref(false)

const sentinelRef = ref<HTMLElement | null>(null)

// Stale-epoch guard -- same pattern as BalanceView payment history /
// stores/products.ts: a fresh fetchFirstPage invalidates any
// in-flight loadMore from a previous visit to this screen.
let fetchEpoch = 0

const hasMore = computed(() => items.value.length < total.value)
// `loaded` alone is NOT enough: it stays true after a FAILED first
// load, so during a retry (which resets `errored` to false before
// the request resolves) an isEmpty that ignored `loading` would
// briefly render the empty state -- "no plans yet" + a CTA away
// from the screen -- while the user's plans were still loading.
// BalanceView's history list avoids this by having no `loaded`
// flag at all and gating purely on loading/items.
const isEmpty = computed(
  () => loaded.value && !loading.value && !errored.value && items.value.length === 0,
)

// ---------------------------------------------------------------------------
// Status presentation
// ---------------------------------------------------------------------------

function planStatusVariant(status: string): 'success' | 'warning' | 'danger' | 'primary' | 'neutral' {
  if (status === 'completed') return 'success'
  if (status === 'defaulted') return 'danger'
  if (status === 'cancelled') return 'neutral'
  return 'primary' // active
}

function planStatusLabel(status: string): string {
  // TD-F08c-style fall-through: an unrecognised future status renders
  // as its raw token instead of a blank badge.
  return tOrRaw(t, `inv.installmentPlans.status.plan.${status}`, status)
}

function shortId(id: string): string {
  return id.slice(0, 8)
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

const detailRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-installment-plan-detail' : 'investor-installment-plan-detail',
)

const companiesRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-companies' : 'investor-companies',
)

function openPlan(plan: InstallmentPlanResponse): void {
  void safeNavigate(
    router.push({ name: detailRouteName.value, params: { id: plan.id } }),
    '[InstallmentPlansView] to plan detail',
  )
}

function goCompanies(): void {
  void safeNavigate(
    router.push({ name: companiesRouteName.value }),
    '[InstallmentPlansView] to companies list',
  )
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function fetchFirstPage(): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  try {
    const resp = await listMyPlans({ page: 1, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = resp.items
    total.value = resp.total
    page.value = 1
    loaded.value = true
  } catch {
    if (epoch !== fetchEpoch) return
    errored.value = true
    loaded.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

async function loadMore(): Promise<void> {
  if (loading.value || !hasMore.value) return
  const epoch = ++fetchEpoch
  loading.value = true
  loadMoreErrored.value = false
  try {
    const nextPage = page.value + 1
    const resp = await listMyPlans({ page: nextPage, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = [...items.value, ...resp.items]
    total.value = resp.total
    page.value = nextPage
  } catch {
    if (epoch !== fetchEpoch) return
    // Non-destructive: keep already-loaded pages visible, surface a
    // retry row instead (same brake as BalanceView withdrawals).
    loadMoreErrored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

function retryLoadMore(): void {
  loadMoreErrored.value = false
  void loadMore()
}

useInfiniteScroll(sentinelRef, hasMore, loadMore, loadMoreErrored)

onMounted(() => {
  void fetchFirstPage()
})
</script>

<template>
  <div class="ipl">
    <div class="ipl__header">
      <h1 class="ipl__title">
        {{ t('inv.installmentPlans.list.title') }}
      </h1>
      <p class="ipl__subtitle">
        {{ t('inv.installmentPlans.list.subtitle') }}
      </p>
    </div>

    <!-- Initial load spinner -->
    <div v-if="loading && items.length === 0" class="ipl__center">
      <CLoader :size="28" />
    </div>

    <!-- Error (first load failed) -->
    <div v-else-if="errored && items.length === 0" class="ipl__center">
      <CEmptyState :title="t('inv.installmentPlans.list.errorTitle')" />
      <CButton variant="outline" size="sm" @click="fetchFirstPage">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <div v-else-if="isEmpty" class="ipl__center">
      <CEmptyState
        :title="t('inv.installmentPlans.list.empty.title')"
        :description="t('inv.installmentPlans.list.empty.description')"
      >
        <template #icon>
          <CreditCard :size="32" />
        </template>
      </CEmptyState>
      <CButton variant="primary" size="sm" @click="goCompanies">
        {{ t('inv.installmentPlans.list.empty.cta') }}
      </CButton>
    </div>

    <!-- Populated -->
    <template v-else>
      <ul class="ipl__list">
        <li v-for="plan in items" :key="plan.id">
          <button
            type="button"
            class="ipl__item"
            :class="{ 'ipl__item--danger': plan.status === 'defaulted' }"
            @click="openPlan(plan)"
          >
            <div class="ipl__item-head">
              <span class="ipl__item-label">
                {{ t('inv.installmentPlans.list.item.label', { id: shortId(plan.id) }) }}
              </span>
              <CBadge :variant="planStatusVariant(plan.status)" :text="planStatusLabel(plan.status)" />
            </div>
            <div class="ipl__item-stats">
              <div class="ipl__item-stat">
                <div class="ipl__item-stat-label">
                  {{ t('inv.installmentPlans.list.item.totalPrice') }}
                </div>
                <div class="ipl__item-stat-value">
                  {{ formatPrice(plan.total_price_cents) }}
                </div>
              </div>
              <div class="ipl__item-stat">
                <div class="ipl__item-stat-label">
                  {{ t('inv.installmentPlans.list.item.units') }}
                </div>
                <div class="ipl__item-stat-value">
                  {{ formatNumber(plan.total_units, locale) }}
                </div>
              </div>
            </div>
            <div class="ipl__item-foot">
              <CalendarClock :size="14" class="ipl__item-foot-icon" />
              <span>
                {{ t('inv.installmentPlans.list.item.created') }}
                {{ formatDateTime(plan.created_at, locale) }}
              </span>
            </div>
          </button>
        </li>
      </ul>

      <!-- Infinite scroll sentinel -->
      <div ref="sentinelRef" class="ipl__sentinel">
        <CLoader v-if="loading" :size="20" />
      </div>

      <div v-if="loadMoreErrored && !loading" class="ipl__loadmore-error">
        <span>{{ t('inv.installmentPlans.list.loadMoreError') }}</span>
        <CButton variant="outline" size="sm" @click="retryLoadMore">
          {{ t('common.retry') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ipl {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ipl__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.ipl__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.ipl__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
  max-width: var(--maxw-prose);
}

.ipl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.ipl__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ipl__item {
  appearance: none;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius);
  margin: 0;
  padding: var(--space-4);
  font: inherit;
  color: inherit;
  text-align: start;
  width: 100%;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition: border-color 0.15s;
}
.ipl__item:hover {
  border-color: var(--primary);
}
.ipl__item:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Defaulted plans must be unmistakable in the list, not just via the
   badge colour -- a tinted surface + accent border reads at a glance
   even before the badge text is parsed. */
.ipl__item--danger {
  background: var(--danger-subtle);
  border-color: var(--danger);
}
.ipl__item--danger:hover {
  border-color: var(--danger);
}

.ipl__item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.ipl__item-label {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.ipl__item-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
}
.ipl__item-stat-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--space-1);
}
.ipl__item-stat-value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.ipl__item-foot {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.ipl__item-foot-icon {
  flex-shrink: 0;
}

.ipl__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

.ipl__loadmore-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  margin-top: var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}
</style>
