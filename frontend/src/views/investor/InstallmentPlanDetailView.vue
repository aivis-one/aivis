<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InstallmentPlanDetailView (TASK-39 item 1)
// =============================================================================
//
// One installment plan with its full tranche schedule
// (GET /api/v1/installments/{plan_id}). Reached by tapping a row in
// InstallmentPlansView.vue; mounted under both
// /investor/installments/:id and /agent/installments/:id via
// role-distinct route names, same shared-component convention as
// InstallmentPlansView / PortfolioView.
//
// This is the screen where a buyer can actually see an OVERDUE
// tranche -- InstallmentPlanListResponse items carry no tranche data
// (see InstallmentPlansView's header note), so this detail endpoint
// is the only place OVERDUE is visible before the plan as a whole
// flips to `defaulted`.
//
// STATUS SOURCE OF TRUTH: backend/app/modules/installments/constants.py
//   InstallmentPlanStatus:    active | completed | defaulted | cancelled
//   InstallmentTrancheStatus: scheduled | paid | overdue | defaulted |
//                             cancelled | reversed
// overdue/defaulted/reversed tranches get a tinted-row treatment
// (not just the badge) for the same "unmistakable at a glance" reason
// as the list view's defaulted-plan card.
//
// OWNERSHIP: the backend 404s a plan that exists but belongs to
// someone else (get_plan_detail, service.py) -- indistinguishable
// from "plan does not exist" by design, so both render the same
// not-found state here rather than leaking existence.
//
// LOADING / ERROR TAXONOMY (matches PortfolioView /
// NotificationsInboxView): first-load spinner; a distinct not-found
// state for 404 (no retry -- retrying an ownership 404 cannot
// succeed); a generic error state with retry for anything else
// (network failure, 5xx). No empty state -- a plan detail either
// loads or it doesn't; there is no "zero tranches" case
// (create_plan always expands at least one tranche).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CBackLink, CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { getPlanDetail } from '@/api/installments'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatDate, formatDateTime, formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { InstallmentPlanDetailResponse, InstallmentTrancheResponse } from '@/api/types'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()

const plan = ref<InstallmentPlanDetailResponse | null>(null)
const loading = ref(true)
const notFound = ref(false)
const errored = ref(false)

const planId = computed(() => route.params.id as string)
const tranches = computed<InstallmentTrancheResponse[]>(() => plan.value?.tranches ?? [])

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
  return tOrRaw(t, `inv.installmentPlans.status.plan.${status}`, status)
}

function trancheStatusVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'paid') return 'success'
  if (status === 'overdue') return 'warning'
  if (status === 'defaulted' || status === 'reversed') return 'danger'
  return 'neutral' // scheduled, cancelled
}

function trancheStatusLabel(status: string): string {
  return tOrRaw(t, `inv.installmentPlans.status.tranche.${status}`, status)
}

// overdue/defaulted/reversed all mean "this payment is a problem" --
// the row-level accent treatment is shared across the three so a
// tranche that has gone all the way to defaulted/reversed doesn't
// look calmer than one that is merely overdue.
function trancheIsProblem(status: string): boolean {
  return status === 'overdue' || status === 'defaulted' || status === 'reversed'
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

const listRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-installment-plans' : 'investor-installment-plans',
)

function goBack(): void {
  // Same history-aware pattern as NotificationsInboxView / InstallmentView:
  // prefer router.back() so the list screen restores its scroll for
  // free; a deep-linked entry falls back to pushing the list route.
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: listRouteName.value }),
    '[InstallmentPlanDetailView] back fallback to list',
  )
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function load(): Promise<void> {
  loading.value = true
  notFound.value = false
  errored.value = false
  try {
    plan.value = await getPlanDetail(planId.value)
  } catch (err: unknown) {
    plan.value = null
    if (err instanceof ApiResponseError && err.status === 404) {
      notFound.value = true
    } else {
      errored.value = true
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="ipd">
    <div class="ipd__back-row">
      <CBackLink :label="t('inv.installmentPlans.detail.backLink')" @click="goBack" />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="ipd__center">
      <CLoader :size="28" />
    </div>

    <!-- Not found (missing or not owned -- backend does not distinguish) -->
    <div v-else-if="notFound" class="ipd__center">
      <CEmptyState
        :title="t('inv.installmentPlans.detail.notFoundTitle')"
        :description="t('inv.installmentPlans.detail.notFoundDesc')"
      />
    </div>

    <!-- Generic error (network / 5xx) -->
    <div v-else-if="errored || !plan" class="ipd__center">
      <CEmptyState :title="t('inv.installmentPlans.detail.errorTitle')" />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Populated -->
    <template v-else>
      <div class="ipd__body">
        <!-- Summary card -->
        <section class="ipd__card">
          <div class="ipd__summary-head">
            <h1 class="ipd__title">
              {{ t('inv.installmentPlans.detail.title') }}
            </h1>
            <CBadge :variant="planStatusVariant(plan.status)" :text="planStatusLabel(plan.status)" />
          </div>

          <!-- Defaulted plans get an explicit banner, not just a badge --
               the whole point of this task is that this must be
               unmistakable at a glance. -->
          <div v-if="plan.status === 'defaulted'" class="ipd__alert ipd__alert--danger">
            {{ t('inv.installmentPlans.detail.defaultedBanner') }}
          </div>

          <div class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.totalPrice') }}</span>
            <span class="ipd__row-value">{{ formatPrice(plan.total_price_cents) }}</span>
          </div>
          <div class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.totalUnits') }}</span>
            <span class="ipd__row-value">{{ formatNumber(plan.total_units, locale) }}</span>
          </div>
          <div class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.pricePerUnit') }}</span>
            <span class="ipd__row-value">{{ formatPrice(plan.price_per_unit_cents) }}</span>
          </div>
          <div class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.created') }}</span>
            <span class="ipd__row-value">{{ formatDateTime(plan.created_at, locale) }}</span>
          </div>
          <div v-if="plan.completed_at" class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.completed') }}</span>
            <span class="ipd__row-value">{{ formatDateTime(plan.completed_at, locale) }}</span>
          </div>
          <div v-if="plan.defaulted_at" class="ipd__row">
            <span class="ipd__row-label">{{ t('inv.installmentPlans.detail.summary.defaulted') }}</span>
            <span class="ipd__row-value ipd__row-value--danger">
              {{ formatDateTime(plan.defaulted_at, locale) }}
            </span>
          </div>
        </section>

        <!-- Tranche schedule -->
        <section class="ipd__card">
          <h2 class="ipd__card-title">
            {{ t('inv.installmentPlans.detail.schedule.title') }}
          </h2>
          <ul class="ipd__tranches">
            <li
              v-for="tr in tranches"
              :key="tr.id"
              class="ipd__tranche"
              :class="{ 'ipd__tranche--problem': trancheIsProblem(tr.status) }"
            >
              <div class="ipd__tranche-head">
                <span class="ipd__tranche-num">
                  {{ t('inv.installmentPlans.detail.schedule.tranche', { n: tr.number }) }}
                </span>
                <CBadge :variant="trancheStatusVariant(tr.status)" :text="trancheStatusLabel(tr.status)" />
              </div>
              <div class="ipd__tranche-stats">
                <div class="ipd__tranche-stat">
                  <div class="ipd__tranche-stat-label">
                    {{ t('inv.installmentPlans.detail.schedule.due') }}
                  </div>
                  <div class="ipd__tranche-stat-value">
                    {{ formatDate(tr.due_date, locale) }}
                  </div>
                </div>
                <div class="ipd__tranche-stat">
                  <div class="ipd__tranche-stat-label">
                    {{ t('inv.installmentPlans.detail.schedule.amount') }}
                  </div>
                  <div class="ipd__tranche-stat-value">
                    {{ formatPrice(tr.amount_cents) }}
                  </div>
                </div>
                <div class="ipd__tranche-stat">
                  <div class="ipd__tranche-stat-label">
                    {{ t('inv.installmentPlans.detail.schedule.units') }}
                  </div>
                  <div class="ipd__tranche-stat-value">
                    {{ formatNumber(tr.units_unlocked, locale) }}
                  </div>
                </div>
              </div>
              <div v-if="tr.paid_at" class="ipd__tranche-foot">
                {{ t('inv.installmentPlans.detail.schedule.paidOn', { date: formatDateTime(tr.paid_at, locale) }) }}
              </div>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ipd {
  display: flex;
  flex-direction: column;
}

.ipd__back-row {
  display: flex;
  margin: var(--space-4) var(--space-4) 0;
}

.ipd__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.ipd__body {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ipd__card {
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}
.ipd__card-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  margin: 0 0 var(--space-3);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.ipd__summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.ipd__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.ipd__alert {
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  font-weight: 600;
  margin-bottom: var(--space-3);
}
.ipd__alert--danger {
  background: var(--danger-subtle);
  color: var(--danger);
}

.ipd__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-default);
}
.ipd__row:last-child {
  border-bottom: none;
}
.ipd__row-label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.ipd__row-value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.ipd__row-value--danger {
  color: var(--danger);
}

/* Tranche rows */
.ipd__tranches {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.ipd__tranche {
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* Overdue/defaulted/reversed tranches must read as a problem before the
   badge text is even parsed -- same tinted-surface treatment as the
   defaulted-plan card in InstallmentPlansView. */
.ipd__tranche--problem {
  background: var(--danger-subtle);
  border-color: var(--danger);
}

.ipd__tranche-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.ipd__tranche-num {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.ipd__tranche-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}
.ipd__tranche-stat-label {
  font-size: var(--fs-3xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--space-1);
}
.ipd__tranche-stat-value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.ipd__tranche-foot {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
</style>
