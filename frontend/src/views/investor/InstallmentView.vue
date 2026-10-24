<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InstallmentView (Phase F4.2 + F4.2.2 polish + F4.3 fix)
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
// The frame's header (K25) holds the product name and the back control (the same
// step as Cancel); the product is the system's Hero (K47), its text on the
// scrim; the plan choices are Row list rows (K23, each a real link that puts the
// plan in the URL), the payment schedule the Schedule list (K32), the first
// payment and the balance a Key-value list (K49).
//
// Error handling mirrors PurchaseView: narrow to ApiResponseError,
// discriminate by the server's error code, map to toast + side-effect.
//
// A plan is accepted ONCE, when it is created: the confirmation shows the
// disclosure short and one tick of the buyer agreement, and the button
// ("Pay") records the acceptance before the first payment. Short of money,
// the screen says how much is missing and offers the top-up for it.
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
import { AlertTriangle, Building, Calendar } from '@/components/ui/icons'
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { ApiResponseError } from '@/api/client'
import { getProduct } from '@/api/products'
import { createInstallmentPlan } from '@/api/installments'
import { acceptDocumentByType } from '@/api/documents'
import PurchaseTerms from '@/components/shared/PurchaseTerms.vue'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
import {
  getPlanBonus,
  getTrancheUnits,
  parsePlanConfig,
  type PlanConfig,
} from '@/utils/installmentPlans'
import type { InstallmentResponse, PublicProductDetailResponse } from '@/api/types'

// Backend currency field is not emitted on Public*/BalanceResponse
// yet (TD-F03 scope includes both). Same escape hatch as the other
// F4.2 views -- remove once the multi-currency contract ships.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()
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
const balanceCents = computed<number>(() => dashboardStore.activeBalance.confirmed)

const insufficientBalance = computed<boolean>(() => {
  return balanceCents.value < firstTrancheCents.value
})

// What is missing for the first payment, and the amount the top-up screen
// opens with: the shortfall, and never less than the deposit minimum of $10.
const MIN_TOP_UP_CENTS = 1000
const shortfallCents = computed<number>(() =>
  Math.max(0, firstTrancheCents.value - balanceCents.value),
)
const topUpAmount = computed<string>(() =>
  (Math.max(shortfallCents.value, MIN_TOP_UP_CENTS) / 100).toFixed(2),
)

// The plan is accepted ONCE, at its creation, by one tick of the buyer
// agreement; the months that follow are not accepted again.
const accepted = ref(false)

const canConfirm = computed<boolean>(() => {
  return (
    !loading.value &&
    !submitting.value &&
    !errored.value &&
    product.value !== null &&
    selectedPlan.value !== null &&
    planConfig.value !== null &&
    planConfig.value.tranches.length >= 2 &&
    !insufficientBalance.value &&
    accepted.value
  )
})

// The cover is the product's own picture, else the company's logo.
const coverSrc = computed<string | null>(
  () => product.value?.cover_url ?? product.value?.company_logo_url ?? null,
)

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
    const [p] = await Promise.all([getProduct(productId.value), dashboardStore.refresh()])
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

async function confirm(): Promise<void> {
  if (!canConfirm.value || !selectedPlan.value) return
  // A deep link records no acceptance for an unverified buyer.
  if (authStore.kycStatus !== 'approved') {
    showKycPrompt('installment')
    return
  }
  submitting.value = true
  try {
    // The acceptance is recorded before the first payment is taken; nothing is
    // charged if the recording cannot be made.
    const recorded = await acceptDocumentByType(
      'buyer_agreement',
      locale.value === 'ru' ? 'ru' : 'en',
    )
    if (recorded === 'missing') {
      showToast(t('inv.installment.error.agreementMissing'), 'error')
      return
    }
    await createInstallmentPlan(productId.value, {
      product_installment_id: selectedPlan.value.id,
    })
    showToast(t('inv.installment.success'), 'success')
    // Awaited push so `submitting` stays true until navigation
    // resolves, avoiding a brief UI flash of the Confirm button
    // between API success and unmount. safeNavigate is no-throw
    // by contract -- critical here so a benign NavigationFailure
    // does NOT bubble into the outer catch and trip handlePlanError(),
    // which would otherwise surface a generic-error toast on top of
    // the success toast.
    await safeNavigate(
      router.push({
        name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio',
      }),
      '[InstallmentView] post-submit to portfolio',
    )
  } catch (err: unknown) {
    await handlePlanError(err)
  } finally {
    submitting.value = false
  }
}

// Errors are read from the server's code, never from the text of its message.
async function handlePlanError(err: unknown): Promise<void> {
  if (err instanceof ApiResponseError) {
    // 402 -- the KYC gate. main.ts has already shown the verification
    // prompt; a toast here would only say "error" on top of it.
    if (err.status === 402) return

    switch (err.code) {
      case 'kyc_required':
        // What an agent meets: the gate lets agents through by role.
        showKycPrompt('installment')
        return
      case 'insufficient_balance':
        showToast(t('inv.installment.error.insufficientBalance'), 'error')
        await dashboardStore.refresh()
        return
      case 'insufficient_pool_capacity':
        showToast(t('inv.installment.error.poolCapacity'), 'error')
        return
      // Template drift -- rare, but possible if an admin soft-deletes the
      // template between ProductDetail load and Confirm click.
      case 'installment_template_mismatch':
        showToast(t('inv.installment.error.templateMismatch'), 'error')
        return
      case 'product_not_available':
      case 'company_not_active':
        showToast(t('inv.installment.error.productInactive'), 'error')
        return
      default:
        if (err.status === 404) {
          showToast(t('inv.installment.error.productInactive'), 'error')
          return
        }
    }
  }

  showToast(t('inv.installment.error.generic'), 'error')
}

function toTopUp(): void {
  void safeNavigate(
    router.push({
      name: 'investor-deposit',
      query: { amount: topUpAmount.value, min: '10' },
    }),
    '[InstallmentView] to top-up',
  )
}

function cancel(): void {
  // Prefer router.back() so the ProductDetail screen restores its
  // scroll/state for free and we don't pollute history with a
  // duplicate ProductDetail entry (which would turn the back button
  // on that screen into a back-to-Installment trap). Only push when
  // vue-router has no prior entry -- i.e. InstallmentView was opened
  // via a deep-linked URL.
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({
      name: agentShell.value ? 'agent-product-detail' : 'investor-product-detail',
      params: { id: productId.value },
    }),
    '[InstallmentView] cancel fallback to product detail',
  )
}

function backToMarket(): void {
  // iter 2.6.x hotfix: market routes removed in iter 2.5 batch 9,
  // catalogue moved to *-companies (CompanyListView). Function
  // name kept as `backToMarket` -- internal label, see also
  // `inv.product.backToMarket` i18n key which carries the updated
  // user-facing label "Back to companies".
  void safeNavigate(
    router.push({
      name: agentShell.value ? 'agent-companies' : 'investor-companies',
    }),
    '[InstallmentView] to companies list',
  )
}

// A plan choice is a link that REPLACES the URL (`?plan=`), so the history does
// not pile up an entry for each tap inside the selector. If the user navigates
// inside the shell (e.g. tapping a different plan) without a full remount,
// re-resolve selectedPlan from the updated query string. Keeps SELECT/CONFIRM modes in sync with
// deep-link state without requiring onMounted to run again.
watch(queryPlanId, (qid) => {
  if (!product.value) return
  if (qid) {
    selectedPlan.value = resolvePlanById(qid)
  } else {
    selectedPlan.value = null
  }
})

// The frame's header: the product name, and the back control (the step Cancel takes).
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    window.history.state?.back
      ? true
      : {
          name: agentShell.value ? 'agent-product-detail' : 'investor-product-detail',
          params: { id: productId.value },
        },
})

onMounted(load)
</script>

<template>
  <div class="iv">
    <!-- Loading -->
    <CLoader v-if="loading" />

    <!-- Product load error -->
    <CEmptyState
      v-else-if="errored || !product"
      tone="danger"
      :title="t('inv.installment.loadError.title')"
      :description="t('inv.installment.loadError.desc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="backToMarket">
          {{ t('inv.product.backToMarket') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- No installment plans configured on this product -->
    <CEmptyState
      v-else-if="noPlans"
      :title="t('inv.installment.empty.title')"
      :description="t('inv.installment.empty.desc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="cancel">
          {{ t('inv.installment.backToProduct') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else>
      <!-- Product hero (K47): the company and the product name over the photo, or
           the fallback tile with the icon when there is no photo. -->
      <section class="ds-hero" data-size="sm" aria-labelledby="iv-hero-title">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="iv-hero-title" class="ds-hero__title">
            {{ product.name }}
          </h2>
          <p class="ds-hero__meta">
            {{ product.company_name }}
          </p>
        </div>
      </section>

      <!-- SELECT mode: fallback for deep-links without ?plan= -->
      <template v-if="mode === 'select'">
        <section class="ds-card" aria-labelledby="iv-select">
          <header class="ds-card__head">
            <h2 id="iv-select" class="ds-card__title">
              {{ t('inv.installment.selectTitle') }}
            </h2>
          </header>
          <p class="ds-card__body">
            {{ t('inv.installment.selectHint') }}
          </p>
          <ul class="ds-rows">
            <li v-for="plan in product.installments" :key="plan.id" class="ds-row">
              <span class="ds-row__body">
                <RouterLink
                  class="ds-row__link"
                  replace
                  :to="{
                    name: installmentRouteName(),
                    params: { id: productId },
                    query: { plan: plan.id },
                  }"
                >
                  <span class="ds-row__title">{{ plan.name }}</span>
                </RouterLink>
              </span>
              <span v-if="getPlanBonus(plan) > 0" class="ds-row__trail">
                <span class="ds-badge ds-badge--success">
                  {{ t('inv.product.installmentsBonus', { n: getPlanBonus(plan) }) }}
                </span>
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
        <section class="ds-card" aria-labelledby="iv-plan">
          <header class="ds-card__head">
            <h2 id="iv-plan" class="ds-card__title">
              {{ t('inv.installment.planTitle') }}
            </h2>
          </header>
          <ul class="ds-rows">
            <li class="ds-row">
              <span class="ds-row__body">
                <span class="ds-row__title">{{ selectedPlan.name }}</span>
              </span>
              <span v-if="planConfig.bonus_units > 0" class="ds-row__trail">
                <span class="ds-badge ds-badge--success">
                  {{ t('inv.product.installmentsBonus', { n: planConfig.bonus_units }) }}
                </span>
              </span>
            </li>
          </ul>
        </section>

        <!-- Payment schedule (K32) -->
        <section class="ds-card" aria-labelledby="iv-tranches">
          <header class="ds-card__head">
            <h2 id="iv-tranches" class="ds-card__title">
              {{ t('inv.installment.tranches') }}
            </h2>
          </header>
          <ol class="ds-schedule" aria-labelledby="iv-tranches">
            <li v-for="(tr, i) in planConfig.tranches" :key="i" class="ds-schedule__item">
              <div class="ds-schedule__head">
                <span class="ds-schedule__num">
                  {{ t('inv.installment.tranche', { n: i + 1 }) }}
                </span>
              </div>
              <dl class="ds-schedule__stats">
                <div class="ds-schedule__stat">
                  <dt>{{ t('inv.installmentPlans.detail.schedule.amount') }}</dt>
                  <dd>{{ formatPrice(tr.amount_cents, product.currency) }}</dd>
                </div>
                <div class="ds-schedule__stat">
                  <dt>{{ t('inv.installmentPlans.detail.schedule.units') }}</dt>
                  <dd>{{ formatNumber(unitsForTranche(i), locale) }} {{ t('inv.unit') }}</dd>
                </div>
              </dl>
            </li>
          </ol>
          <p class="ds-card__body">
            {{ t('inv.installment.scheduleNote') }}
          </p>
        </section>

        <!-- First payment + spendable balance -->
        <section class="ds-card">
          <dl class="ds-kv">
            <div class="ds-kv__row">
              <dt>{{ t('inv.installment.firstPayment') }}</dt>
              <dd>{{ formatPrice(firstTrancheCents, product.currency) }}</dd>
            </div>
            <div class="ds-kv__row">
              <dt>{{ t('inv.installment.yourBalance') }}</dt>
              <dd :data-tone="insufficientBalance ? 'danger' : undefined">
                {{ formatPrice(balanceCents, product.currency) }}
              </dd>
            </div>
          </dl>
          <div v-if="insufficientBalance" class="ds-alert ds-alert--danger" role="alert">
            <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
            <div class="ds-alert__content">
              <p class="ds-alert__text">
                {{
                  t('inv.installment.shortfall', {
                    amount: formatPrice(shortfallCents, product.currency),
                  })
                }}
              </p>
              <div class="ds-alert__actions">
                <CButton variant="outline" size="sm" inline @click="toTopUp">
                  {{ t('inv.installment.topUp') }}
                </CButton>
              </div>
            </div>
          </div>
        </section>

        <!-- The disclosure, short, and the one tick of the buyer agreement -->
        <PurchaseTerms v-model="accepted" />

        <!-- Actions -->
        <div class="iv__actions">
          <CButton variant="primary" :disabled="!canConfirm" @click="confirm">
            <Calendar size="sm" />
            {{ t('inv.installment.pay') }}
          </CButton>
          <CButton variant="outline" :disabled="submitting" @click="cancel">
            {{ t('inv.installment.cancel') }}
          </CButton>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.iv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Actions */
.iv__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
</style>
