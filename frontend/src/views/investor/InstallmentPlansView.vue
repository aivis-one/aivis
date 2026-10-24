<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InstallmentPlansView (TASK-39 item 1)
// =============================================================================
//
// List of the authenticated buyer's installment plans, newest first.
// Reached from the "Installment plans" line of the web side menu and from
// the portfolio, and mounted under both
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
// The title and the line under it are the frame's header (K25); the plans are
// the system's Row list (K23), each row one link on its title.
//
// LOADING / ERROR / EMPTY TAXONOMY (matches PortfolioView /
// NotificationsInboxView): first-load skeleton while items.length === 0
// and no error yet; error state (CEmptyState + retry) when the first
// load failed; empty state (CEmptyState + CTA to the companies
// catalogue) when the load succeeded with zero plans. Populated state
// renders the list plus the infinite-scroll sentinel/load-more-error
// row underneath, identical shape to BalanceView's payment history.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, CalendarClock, CreditCard } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CLoader, CListSkeleton } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
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

useScreenHeader({
  title: () => t('inv.installmentPlans.list.title'),
  lead: () => t('inv.installmentPlans.list.subtitle'),
})

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

function planStatusVariant(
  status: string,
): 'success' | 'warning' | 'danger' | 'primary' | 'neutral' {
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
    <!-- Initial load: the placeholder rows of the list that will arrive (K19) -->
    <CListSkeleton v-if="loading && items.length === 0" :rows="3" />

    <!-- Error (first load failed) -->
    <CEmptyState
      v-else-if="errored && items.length === 0"
      tone="danger"
      :title="t('inv.installmentPlans.list.errorTitle')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="fetchFirstPage">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState
      v-else-if="isEmpty"
      :title="t('inv.installmentPlans.list.empty.title')"
      :description="t('inv.installmentPlans.list.empty.description')"
    >
      <template #icon>
        <CreditCard />
      </template>
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="goCompanies">
          {{ t('inv.installmentPlans.list.empty.cta') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Populated -->
    <template v-else>
      <ul class="ds-rows">
        <li v-for="plan in items" :key="plan.id" class="ds-row">
          <!-- A defaulted plan is unmistakable: the lead is toned, the badge says it in words. -->
          <span
            class="ds-row__lead"
            :data-tone="plan.status === 'defaulted' ? 'danger' : undefined"
          >
            <CalendarClock size="sm" />
          </span>
          <span class="ds-row__body">
            <RouterLink
              class="ds-row__link"
              :to="{ name: detailRouteName, params: { id: plan.id } }"
            >
              <span class="ds-row__title">
                {{ t('inv.installmentPlans.list.item.label', { id: shortId(plan.id) }) }}
              </span>
            </RouterLink>
            <span class="ds-row__meta">
              {{ t('inv.installmentPlans.list.item.units') }}:
              {{ formatNumber(plan.total_units, locale) }}
            </span>
            <span class="ds-row__meta">
              {{ t('inv.installmentPlans.list.item.created') }}
              {{ formatDateTime(plan.created_at, locale) }}
            </span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-row__value">{{ formatPrice(plan.total_price_cents) }}</span>
            <CBadge
              :variant="planStatusVariant(plan.status)"
              :text="planStatusLabel(plan.status)"
            />
          </span>
        </li>
      </ul>

      <!-- Infinite scroll sentinel -->
      <div ref="sentinelRef" class="ipl__sentinel">
        <CLoader v-if="loading" :size="20" />
      </div>

      <div v-if="loadMoreErrored && !loading" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ t('inv.installmentPlans.list.loadMoreError') }}</p>
          <div class="ds-alert__actions">
            <CButton variant="outline" size="sm" inline @click="retryLoadMore">
              {{ t('common.retry') }}
            </CButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ipl {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ipl__sentinel {
  display: flex;
  justify-content: center;
  min-block-size: var(--size-md);
}
</style>
