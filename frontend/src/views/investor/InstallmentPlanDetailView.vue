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
// overdue/defaulted/reversed tranches get the schedule list's problem tint
// (not just the badge, K32) for the same "unmistakable at a glance" reason
// as the list view's defaulted-plan row.
//
// The title and the back control are the frame's header (K25); the summary is
// a Card with a key-value list (K07, K49), the tranches the system's schedule
// list (K32).
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
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { AlertTriangle } from '@/components/ui/icons'
import { ApiResponseError } from '@/api/client'
import { getPlanDetail } from '@/api/installments'
import { isAgentShell } from '@/router/helpers'
import { formatDate, formatDateTime, formatNumber, formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { InstallmentPlanDetailResponse, InstallmentTrancheResponse } from '@/api/types'

const route = useRoute()
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

function planStatusVariant(
  status: string,
): 'success' | 'warning' | 'danger' | 'primary' | 'neutral' {
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

// Same history-aware pattern as NotificationsInboxView / InstallmentView:
// one step back so the list screen restores its scroll for free; a
// deep-linked entry falls back to the list route.
useScreenHeader({
  title: () => t('inv.installmentPlans.detail.title'),
  back: () => (window.history.state?.back ? true : { name: listRouteName.value }),
})

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
    <!-- Loading -->
    <CLoader v-if="loading" />

    <!-- Not found (missing or not owned -- backend does not distinguish) -->
    <CEmptyState
      v-else-if="notFound"
      :title="t('inv.installmentPlans.detail.notFoundTitle')"
      :description="t('inv.installmentPlans.detail.notFoundDesc')"
    />

    <!-- Generic error (network / 5xx) -->
    <CEmptyState
      v-else-if="errored || !plan"
      tone="danger"
      :title="t('inv.installmentPlans.detail.errorTitle')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Populated -->
    <template v-else>
      <!-- Summary card -->
      <section class="ds-card">
        <header class="ds-card__head">
          <CBadge :variant="planStatusVariant(plan.status)" :text="planStatusLabel(plan.status)" />
        </header>

        <!-- Defaulted plans get an explicit banner, not just a badge --
             the whole point of this task is that this must be
             unmistakable at a glance. -->
        <div v-if="plan.status === 'defaulted'" class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ t('inv.installmentPlans.detail.defaultedBanner') }}</p>
          </div>
        </div>

        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.totalPrice') }}</dt>
            <dd>{{ formatPrice(plan.total_price_cents) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.totalUnits') }}</dt>
            <dd>{{ formatNumber(plan.total_units, locale) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.pricePerUnit') }}</dt>
            <dd>{{ formatPrice(plan.price_per_unit_cents) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.created') }}</dt>
            <dd>{{ formatDateTime(plan.created_at, locale) }}</dd>
          </div>
          <div v-if="plan.completed_at" class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.completed') }}</dt>
            <dd>{{ formatDateTime(plan.completed_at, locale) }}</dd>
          </div>
          <div v-if="plan.defaulted_at" class="ds-kv__row">
            <dt>{{ t('inv.installmentPlans.detail.summary.defaulted') }}</dt>
            <dd class="ipd__danger">{{ formatDateTime(plan.defaulted_at, locale) }}</dd>
          </div>
        </dl>
      </section>

      <!-- Tranche schedule (K32) -->
      <section class="ipd__schedule" aria-labelledby="ipd-schedule">
        <h2 id="ipd-schedule" class="ipd__section-title">
          {{ t('inv.installmentPlans.detail.schedule.title') }}
        </h2>
        <ol class="ds-schedule" aria-labelledby="ipd-schedule">
          <li
            v-for="tr in tranches"
            :key="tr.id"
            class="ds-schedule__item"
            :data-status="trancheIsProblem(tr.status) ? 'problem' : undefined"
          >
            <div class="ds-schedule__head">
              <span class="ds-schedule__num">
                {{ t('inv.installmentPlans.detail.schedule.tranche', { n: tr.number }) }}
              </span>
              <CBadge
                :variant="trancheStatusVariant(tr.status)"
                :text="trancheStatusLabel(tr.status)"
              />
            </div>
            <dl class="ds-schedule__stats">
              <div class="ds-schedule__stat">
                <dt>{{ t('inv.installmentPlans.detail.schedule.due') }}</dt>
                <dd>{{ formatDate(tr.due_date, locale) }}</dd>
              </div>
              <div class="ds-schedule__stat">
                <dt>{{ t('inv.installmentPlans.detail.schedule.amount') }}</dt>
                <dd>{{ formatPrice(tr.amount_cents) }}</dd>
              </div>
              <div class="ds-schedule__stat">
                <dt>{{ t('inv.installmentPlans.detail.schedule.units') }}</dt>
                <dd>{{ formatNumber(tr.units_unlocked, locale) }}</dd>
              </div>
            </dl>
            <p v-if="tr.paid_at" class="ds-schedule__foot">
              {{
                t('inv.installmentPlans.detail.schedule.paidOn', {
                  date: formatDateTime(tr.paid_at, locale),
                })
              }}
            </p>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<style scoped>
.ipd {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ipd__danger {
  color: var(--danger);
}

/* A section heading inside the screen */
.ipd__schedule {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ipd__section-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}
</style>
