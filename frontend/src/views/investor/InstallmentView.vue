<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- InstallmentView (Phase F4.2 + F4.2.2 polish + F4.3 fix)
// =============================================================================
//
// Installment plan confirmation screen. Shared across
// /investor/installment/:id and /agent/installment/:id via
// role-aware route names.
//
// Two runtime modes, controlled by whether the current route carries
// a valid `?plan=<template_id>` query parameter:
//
//   * CONFIRM mode (query.plan matches one of product.installments)
//     The selected plan is pre-resolved, full breakdown is shown,
//     Confirm kicks off POST /api/v1/products/{id}/installment.
//     This is the happy path -- ProductDetailView deep-links here
//     when the user taps a plan card.
//
//   * SELECT mode (no query, or query.plan doesn't match)
//     Defensive fallback for deep-linked / bookmarked URLs and for
//     the rare case where a stale template id was passed in. Shows
//     the full list of plans as tappable cards; picking one triggers
//     router.replace to update the URL and flips the view to
//     CONFIRM mode in the same screen -- no remount.
//
// Cancel always returns to ProductDetail in the current shell. The
// user can pick a different plan from there (three cards in total,
// no infinite list per product).
//
// Error handling mirrors PurchaseView (F4.2.1): narrow to
// ApiResponseError, discriminate 400 sub-cases by regex on message,
// map to toast + side-effect. TD-F10 will replace the regex with a
// backend-emitted `error_code` discriminator.
//
// Balance source: active_balance.confirmed from /dashboard/summary.
// The backend validates first-tranche affordability inside create_plan,
// the UI check is a courtesy.
//
// F4.2.2 polish:
//   Plan-config parsing, bonus extraction, and tranche-units math
//   moved to utils/installmentPlans -- shared with ProductDetailView
//   and (upcoming) F4.4 Portfolio. The backend-scheduler mirror math
//   lives in a single place now; TD-F11 tracks replacing it with a
//   backend-issued preview endpoint.
//
// F4.3 fix:
//   Cancel used router.push(ProductDetail), which pushed a fresh
//   history entry on top of the existing stack and turned the header
//   back button on the returned ProductDetail into a back-to-
//   Installment trap. Now the cancel path asks vue-router to step
//   back one entry (restoring scroll/state for free) and only falls
//   through to push() when there is no back entry -- i.e. the user
//   deep-linked into this screen.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, Calendar } from 'lucide-vue-next'
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import { ApiResponseError } from '@/api/client'
import { getProduct } from '@/api/products'
import { createInstallmentPlan } from '@/api/installments'
import { useDashboardStore } from '@/stores/dashboard'
import { useToast } from '@/composables/useToast'
import { isAgentShell } from '@/router/helpers'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
import {
  getPlanBonus,
  getTrancheUnits,
  parsePlanConfig,
  type PlanConfig,
} from '@/utils/installmentPlans'
import type {
  InstallmentResponse,
  PublicProductDetailResponse,
} from '@/api/types'

// Backend currency field is not emitted on Public*/BalanceResponse
// yet (TD-F03 scope includes both). Same escape hatch as the other
// F4.2 views -- remove once the multi-currency contract ships.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const { showToast } = useToast()
const dashboardStore = useDashboardStore()

const product = ref<ProductWithOptionalCurrency | null>(null)
const loading = ref(true)
const errored = ref(false)
const submitting = ref(false)

// Currently-selected template. Null in SELECT mode.
const selectedPlan = ref<InstallmentResponse | null>(null)

const productId = computed(() => route.params.id as string)
const agentShell = computed(() => isAgentShell(route))

const queryPlanId = computed<string | null>(() => {
  const q = route.query.plan
  if (typeof q === 'string' && q.length > 0) return q
  return null
})

const noPlans = computed<boolean>(() => {
  // Sprint 4.4: PublicProductDetailResponse.installments is now
  // required server-side -- always an array, never absent. Drop the
  // `?? []` compensation that B7 carried over from the previous schema.
  return product.value !== null && product.value.installments.length === 0
})

const mode = computed<'select' | 'confirm'>(() => {
  return selectedPlan.value ? 'confirm' : 'select'
})

const planConfig = computed<PlanConfig | null>(() => {
  if (!selectedPlan.value) return null
  return parsePlanConfig(selectedPlan.value.plan_config)
})

const firstTrancheCents = computed<number>(() => {
  const tranches = planConfig.value?.tranches ?? []
  return tranches[0]?.amount_cents ?? 0
})

// Spendable balance from the shared dashboard store. Falls back to
// zero before the first refresh resolves (zeroed placeholder) -- the
// insufficientBalance gate below treats that as "not enough", which
// is the safe pessimistic default until the real value arrives.
const balanceCents = computed<number>(
  () => dashboardStore.activeBalance.confirmed,
)

const insufficientBalance = computed<boolean>(() => {
  return balanceCents.value < firstTrancheCents.value
})

const canConfirm = computed<boolean>(() => {
  return (
    !loading.value &&
    !submitting.value &&
    !errored.value &&
    product.value !== null &&
    selectedPlan.value !== null &&
    planConfig.value !== null &&
    planConfig.value.tranches.length >= 2 &&
    !insufficientBalance.value
  )
})

const coverImage = computed<string | null>(() => {
  return product.value ? resolveCoverImage(product.value) : null
})

const headerTitle = computed<string>(() => {
  return product.value?.name ?? t('inv.installment.title')
})

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

function resolvePlanById(id: string): InstallmentResponse | null {
  const list = product.value?.installments ?? []
  return list.find((p) => p.id === id) ?? null
}

/**
 * Tranche row units -- thin wrapper that feeds the shared util
 * the product total. Kept local so the template stays terse.
 */
function unitsForTranche(index: number): number {
  if (!product.value || !planConfig.value) return 0
  return getTrancheUnits(planConfig.value, product.value.package_size, index)
}

function installmentRouteName(): string {
  return agentShell.value ? 'agent-installment' : 'investor-installment'
}

// ---------------------------------------------------------------------------
// Lifecycle + actions
// ---------------------------------------------------------------------------

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    // Parallel probe: product detail + balance store refresh. Only
    // the product fetch's failure flips `errored` -- balance load
    // failures surface through dashboardStore.error; a zeroed balance
    // is handled by the insufficientBalance gate below.
    const [p] = await Promise.all([
      getProduct(productId.value),
      dashboardStore.refresh(),
    ])
    product.value = p

    // Resolve the query-provided template against the just-loaded
    // plan list. If it matches -> CONFIRM mode; otherwise leave
    // selectedPlan null -> SELECT mode (fallback).
    const qid = queryPlanId.value
    if (qid) {
      selectedPlan.value = resolvePlanById(qid)
    } else {
      selectedPlan.value = null
    }
  } catch {
    product.value = null
    selectedPlan.value = null
    errored.value = true
  } finally {
    loading.value = false
  }
}

function pickPlan(plan: InstallmentResponse): void {
  selectedPlan.value = plan
  // Keep the URL in sync for deep-linking / back button. Replace so
  // we don't pile up history entries for each tap inside the selector.
  void router.replace({
    name: installmentRouteName(),
    params: { id: productId.value },
    query: { plan: plan.id },
  })
}

async function confirm(): Promise<void> {
  if (!canConfirm.value || !selectedPlan.value) return
  submitting.value = true
  try {
    await createInstallmentPlan(productId.value, {
      product_installment_id: selectedPlan.value.id,
    })
    showToast(t('inv.installment.success'), 'success')
    router.push({
      name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio',
    })
  } catch (err: unknown) {
    await handlePlanError(err)
  } finally {
    submitting.value = false
  }
}

async function handlePlanError(err: unknown): Promise<void> {
  if (err instanceof ApiResponseError) {
    const { status, message } = err

    if (status === 400 && /kyc/i.test(message)) {
      showToast(t('inv.installment.error.kycRequired'), 'warning')
      router.push('/onboarding/kyc')
      return
    }

    if (status === 400 && /insufficient/i.test(message)) {
      showToast(t('inv.installment.error.insufficientBalance'), 'error')
      await dashboardStore.refresh()
      return
    }

    // Template drift -- rare, but possible if an admin soft-deletes
    // the template between ProductDetail load and Confirm click.
    if (status === 400 && /(template|does not belong)/i.test(message)) {
      showToast(t('inv.installment.error.templateMismatch'), 'error')
      return
    }

    if ((status === 400 && /not active/i.test(message)) || status === 404) {
      showToast(t('inv.installment.error.productInactive'), 'error')
      return
    }
  }

  showToast(t('inv.installment.error.generic'), 'error')
}

function cancel(): void {
  // Prefer router.back() so the ProductDetail screen restores its
  // scroll/state for free and we don't pollute history with a
  // duplicate ProductDetail entry (which would turn the back button
  // on that screen into a back-to-Installment trap). Only push when
  // vue-router has no prior entry -- i.e. InstallmentView was opened
  // via a deep-linked URL.
  if (router.options.history.state.back) {
    router.back()
    return
  }
  router.push({
    name: agentShell.value
      ? 'agent-product-detail'
      : 'investor-product-detail',
    params: { id: productId.value },
  })
}

function backToMarket(): void {
  router.push({
    name: agentShell.value ? 'agent-market' : 'investor-market',
  })
}

// If the user navigates inside the shell (e.g. tapping a different
// plan card) without a full remount, re-resolve selectedPlan from
// the updated query string. Keeps SELECT/CONFIRM modes in sync with
// deep-link state without requiring onMounted to run again.
watch(queryPlanId, (qid) => {
  if (!product.value) return
  if (qid) {
    selectedPlan.value = resolvePlanById(qid)
  } else {
    selectedPlan.value = null
  }
})

onMounted(load)
</script>

<template>
  <div class="iv">
    <CHeader
      :show-back="true"
      :show-logo="false"
      :title="headerTitle"
    />

    <!-- Loading -->
    <div v-if="loading" class="iv__center">
      <CLoader :size="28" />
    </div>

    <!-- Product load error -->
    <template v-else-if="errored || !product">
      <div class="iv__center">
        <CEmptyState
          :title="t('inv.installment.loadError.title')"
          :description="t('inv.installment.loadError.desc')"
        />
        <CButton variant="outline" size="sm" @click="backToMarket">
          {{ t('inv.product.backToMarket') }}
        </CButton>
      </div>
    </template>

    <!-- No installment plans configured on this product -->
    <template v-else-if="noPlans">
      <div class="iv__center">
        <CEmptyState
          :title="t('inv.installment.empty.title')"
          :description="t('inv.installment.empty.desc')"
        />
        <CButton variant="outline" size="sm" @click="cancel">
          {{ t('inv.installment.backToProduct') }}
        </CButton>
      </div>
    </template>

    <template v-else>
      <!-- Product hero -->
      <div
        class="iv__hero"
        :class="{ 'iv__hero--fallback': !coverImage }"
        :style="{ backgroundImage: coverImage ?? 'none' }"
      >
        <Building v-if="!coverImage" :size="48" class="iv__hero-icon" />
        <div class="iv__hero-content">
          <div class="iv__hero-company">{{ product.company_name }}</div>
          <h1 class="iv__hero-title">{{ product.name }}</h1>
        </div>
      </div>

      <div class="iv__body">
        <!-- SELECT mode: fallback for deep-links without ?plan= -->
        <template v-if="mode === 'select'">
          <section class="iv__card">
            <h2 class="iv__card-title">
              {{ t('inv.installment.selectTitle') }}
            </h2>
            <p class="iv__hint">
              {{ t('inv.installment.selectHint') }}
            </p>
            <ul class="iv__plans">
              <li
                v-for="plan in product.installments"
                :key="plan.id"
                class="iv__plan"
                role="button"
                tabindex="0"
                @click="pickPlan(plan)"
                @keydown.enter.prevent="pickPlan(plan)"
                @keydown.space.prevent="pickPlan(plan)"
              >
                <span class="iv__plan-name">{{ plan.name }}</span>
                <span
                  v-if="getPlanBonus(plan) > 0"
                  class="iv__plan-bonus"
                >
                  {{
                    t('inv.product.installmentsBonus', {
                      n: getPlanBonus(plan),
                    })
                  }}
                </span>
              </li>
            </ul>
          </section>

          <div class="iv__actions">
            <CButton variant="outline" @click="cancel">
              {{ t('inv.installment.cancel') }}
            </CButton>
          </div>
        </template>

        <!-- CONFIRM mode: selected plan, schedule, balance, CTAs -->
        <template v-else-if="selectedPlan && planConfig">
          <!-- Chosen plan summary -->
          <section class="iv__card">
            <h2 class="iv__card-title">
              {{ t('inv.installment.planTitle') }}
            </h2>
            <div class="iv__plan iv__plan--selected">
              <span class="iv__plan-name">{{ selectedPlan.name }}</span>
              <span
                v-if="planConfig.bonus_units > 0"
                class="iv__plan-bonus"
              >
                {{
                  t('inv.product.installmentsBonus', {
                    n: planConfig.bonus_units,
                  })
                }}
              </span>
            </div>
          </section>

          <!-- Payment schedule -->
          <section class="iv__card">
            <h2 class="iv__card-title">
              {{ t('inv.installment.tranches') }}
            </h2>
            <ul class="iv__tranches">
              <li
                v-for="(tr, i) in planConfig.tranches"
                :key="i"
                class="iv__tranche"
              >
                <span class="iv__tranche-num">
                  {{ t('inv.installment.tranche', { n: i + 1 }) }}
                </span>
                <span class="iv__tranche-amount">
                  {{ formatPrice(tr.amount_cents, product.currency) }}
                </span>
                <span class="iv__tranche-units">
                  {{ formatNumber(unitsForTranche(i), locale) }}
                  {{ t('inv.unit') }}
                </span>
              </li>
            </ul>
            <p class="iv__note">
              {{ t('inv.installment.scheduleNote') }}
            </p>
          </section>

          <!-- First payment + spendable balance -->
          <section class="iv__card">
            <div class="iv__row">
              <span class="iv__row-label">
                {{ t('inv.installment.firstPayment') }}
              </span>
              <span class="iv__row-value iv__row-value--accent">
                {{ formatPrice(firstTrancheCents, product.currency) }}
              </span>
            </div>
            <div class="iv__row">
              <span class="iv__row-label">
                {{ t('inv.installment.yourBalance') }}
              </span>
              <span
                class="iv__row-value"
                :class="{ 'iv__row-value--warn': insufficientBalance }"
              >
                {{ formatPrice(balanceCents, product.currency) }}
              </span>
            </div>
            <p
              v-if="insufficientBalance"
              class="iv__balance-hint"
            >
              {{ t('inv.installment.insufficientHint') }}
            </p>
          </section>

          <!-- Actions -->
          <div class="iv__actions">
            <CButton
              variant="primary"
              :disabled="!canConfirm"
              @click="confirm"
            >
              <Calendar :size="16" />
              {{ t('inv.installment.confirm') }}
            </CButton>
            <CButton
              variant="outline"
              :disabled="submitting"
              @click="cancel"
            >
              {{ t('inv.installment.cancel') }}
            </CButton>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.iv {
  display: flex;
  flex-direction: column;
}

.iv__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: calc(100vh - 120px);
  min-height: calc(100dvh - 120px);
  padding: 24px;
}

/* Hero with cover */
.iv__hero {
  position: relative;
  height: 160px;
  background-color: var(--bg-subtle);
  background-size: cover;
  background-position: center;
  display: flex;
  align-items: flex-end;
  justify-content: flex-start;
  color: #fff;
}
.iv__hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(transparent 30%, rgba(0, 0, 0, 0.75));
  pointer-events: none;
}
.iv__hero--fallback {
  background-color: var(--bg-subtle);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.iv__hero--fallback::after {
  display: none;
}
.iv__hero-icon {
  position: relative;
  z-index: 1;
  color: var(--text-tertiary);
  stroke-width: 1.5;
}
.iv__hero-content {
  position: relative;
  z-index: 2;
  padding: 16px 20px;
  width: 100%;
}
.iv__hero--fallback .iv__hero-content {
  text-align: center;
  color: var(--text);
  padding: 0 20px 16px;
}
.iv__hero-company {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.iv__hero-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0;
  line-height: 1.3;
  word-break: break-word;
}

/* Body */
.iv__body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Card container */
.iv__card {
  padding: 16px;
  border-radius: var(--radius-md, 12px);
  background: var(--bg-secondary, var(--surface));
}
.iv__card-title {
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.iv__hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin: -4px 0 12px;
  line-height: 1.4;
}
.iv__note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* Plans list (SELECT mode) */
.iv__plans {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.iv__plan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  user-select: none;
  transition: border-color 0.15s ease, background-color 0.15s ease,
    transform 0.05s ease;
}
.iv__plan:hover {
  border-color: var(--primary);
}
.iv__plan:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px
    color-mix(in srgb, var(--primary) 30%, transparent);
}
.iv__plan:active {
  transform: scale(0.99);
}

/* Selected-plan card in CONFIRM mode: same layout, no tap affordance. */
.iv__plan--selected {
  cursor: default;
  user-select: auto;
  border-color: var(--primary);
}
.iv__plan--selected:hover {
  border-color: var(--primary);
}
.iv__plan--selected:active {
  transform: none;
}

.iv__plan-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.iv__plan-bonus {
  font-size: 12px;
  font-weight: 600;
  color: var(--success);
  white-space: nowrap;
}

/* Tranche rows */
.iv__tranches {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.iv__tranche {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.iv__tranche:last-child {
  border-bottom: none;
}
.iv__tranche-num {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
.iv__tranche-amount {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  text-align: right;
}
.iv__tranche-units {
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: right;
  white-space: nowrap;
}

/* Row (label + value) for balance / first-payment */
.iv__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
}
.iv__row-label {
  font-size: 14px;
  color: var(--text-secondary);
}
.iv__row-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.iv__row-value--accent {
  font-size: 18px;
  color: var(--primary);
}
.iv__row-value--warn {
  color: var(--danger);
}
.iv__balance-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--danger);
}

/* Actions */
.iv__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}
</style>
