<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InstallmentView (the buying path, steps 2 and 3, an
//                                        instalment)
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
//     The selected plan is pre-resolved, the Purchase block (K55) shows the
//     portfolio, its parts and the instalment's money, the schedule is a Row
//     list (K23), and "Pay" kicks off POST /api/v1/products/{id}/installment.
//     This is the happy path -- the project page's Buy leads here.
//
//   * SELECT mode (no query, or query.plan doesn't match)
//     Defensive fallback for deep-linked / bookmarked URLs and for
//     the rare case where a stale template id was passed in. Shows
//     the full list of plans as rows; picking one triggers
//     router.replace to update the URL and flips the view to
//     CONFIRM mode in the same screen -- no remount.
//
// After the plan is created the screen turns into the done screen (step 3): the
// congratulation, the summary, the documents the first payment issued and "To my
// portfolio".
//
// "Back to the terms" always returns to the project page in the current shell.
//
// The frame's header (K25) holds the product name and the back control (the same
// step as "Back to the terms"). The buyer sees PARTS (lots times the parts in a
// lot), the price of a part and the money of the instalment -- never the lot.
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
// Plan-config parsing and tranche-units math live in utils/installmentPlans
// (TD-F11 tracks replacing the scheduler mirror with a backend-issued preview).
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CAlert, CButton, CLoader, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
import { getProduct } from '@/api/products'
import { createInstallmentPlan, getPlanDetail } from '@/api/installments'
import { acceptDocumentByType } from '@/api/documents'
import PurchaseDone, { type DoneDocument } from '@/components/shared/PurchaseDone.vue'
import PurchaseStepLine from '@/components/shared/PurchaseStepLine.vue'
import PurchaseSummary from '@/components/shared/PurchaseSummary.vue'
import PurchaseTerms from '@/components/shared/PurchaseTerms.vue'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber } from '@/utils/format'
import { parsePlanConfig, type PlanConfig } from '@/utils/installmentPlans'
import { formatUsd, formatUsdCents } from '@/utils/parts'
import type { InstallmentResponse, PublicProductDetailResponse } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const authStore = useAuthStore()
const { showToast } = useToast()
const dashboardStore = useDashboardStore()

const product = ref<PublicProductDetailResponse | null>(null)
const sharesPerOption = ref(1)
const loading = ref(true)
const errored = ref(false)
const submitting = ref(false)

// The step the screen shows: the confirmation, then the done screen.
const step = ref<'confirm' | 'done'>('confirm')
const doneDocuments = ref<DoneDocument[]>([])
const nextPayment = ref<{ amount: string; date: string } | null>(null)

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
  // PublicProductDetailResponse.installments is required server-side --
  // always an array, never absent.
  return product.value !== null && product.value.installments.length === 0
})

const mode = computed<'select' | 'confirm'>(() => {
  return selectedPlan.value ? 'confirm' : 'select'
})

const planConfig = computed<PlanConfig | null>(() => {
  if (!selectedPlan.value) return null
  return parsePlanConfig(selectedPlan.value.plan_config)
})

const totalCents = computed<number>(() => {
  const p = product.value
  return p ? p.package_size * p.price_per_unit_cents : 0
})

const firstTrancheCents = computed<number>(() => {
  const tranches = planConfig.value?.tranches ?? []
  return tranches[0]?.amount_cents ?? 0
})

const summaryTitle = computed<string>(() =>
  product.value ? `${product.value.company_name} · ${product.value.name}` : '',
)

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

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

function resolvePlanById(id: string): InstallmentResponse | null {
  const list = product.value?.installments ?? []
  return list.find((p) => p.id === id) ?? null
}

function installmentRouteName(): string {
  return agentShell.value ? 'agent-installment' : 'investor-installment'
}

function projectPage() {
  return {
    name: agentShell.value ? 'agent-company-overview' : 'investor-company-overview',
    params: { id: product.value?.company_id ?? '' },
  }
}

function formatDueDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(locale.value, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return iso
  }
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
    // The parts in a lot come with the project, not with the product.
    const company = await getCompany(p.company_id)
    sharesPerOption.value = company.shares_per_option
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
  if (!canConfirm.value || !selectedPlan.value || !planConfig.value) return
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
    const plan = await createInstallmentPlan(productId.value, {
      product_installment_id: selectedPlan.value.id,
    })
    // The first payment's agreement and the date of the next payment come from the
    // plan's own record; the done screen still stands if that read fails.
    const docs: DoneDocument[] = []
    nextPayment.value = null
    try {
      const detail = await getPlanDetail(plan.id)
      const first = detail.tranches?.find((x) => x.number === 1) ?? detail.tranches?.[0]
      if (first?.purchase_id) {
        docs.push({
          kind: 'agreement',
          id: first.purchase_id,
          legalBasis: 'installment_tranche',
        })
      }
      const second = detail.tranches?.find((x) => x.number === 2)
      const cfgSecond = planConfig.value.tranches[1]
      if (second && cfgSecond) {
        nextPayment.value = {
          amount: formatUsd(cfgSecond.amount_cents, locale.value),
          date: formatDueDate(second.due_date),
        }
      }
    } catch {
      // The documents are reachable from the portfolio.
    }
    docs.push({ kind: 'ownership' })
    doneDocuments.value = docs
    step.value = 'done'
    void dashboardStore.refresh()
    window.scrollTo?.({ top: 0 })
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
      // template between the project page's load and Pay.
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
  // Prefer router.back() so the project page restores its scroll/state for free and
  // we don't pollute history with a duplicate entry. Only push when vue-router has
  // no prior entry -- i.e. InstallmentView was opened via a deep-linked URL.
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push(projectPage()), '[InstallmentView] back to the project page')
}

function toPortfolio(): void {
  void safeNavigate(
    router.push({ name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio' }),
    '[InstallmentView] to the portfolio',
  )
}

function backToMarket(): void {
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

// The frame's header: the product name, and the back control (the step "Back to the
// terms" takes). On the done screen there is nothing to go back to but the project.
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    step.value === 'done' ? projectPage() : window.history.state?.back ? true : projectPage(),
})

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => {
  if (step.value === 'confirm') return load()
})

onMounted(load)
</script>

<template>
  <div class="iv">
    <!-- Loading -->
    <CLoader v-if="loading" centered extent="page" />

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
          {{ t('buy.backToTerms') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Step 3: the done screen -->
    <PurchaseDone
      v-else-if="step === 'done' && selectedPlan && planConfig"
      :project-name="product.company_name"
      :company-id="product.company_id"
      :documents="doneDocuments"
      @portfolio="toPortfolio"
      @storefront="backToMarket"
    >
      <PurchaseSummary
        :title="summaryTitle"
        :lots="product.package_size"
        :lot-price-cents="product.price_per_unit_cents"
        :shares-per-option="sharesPerOption"
        :total-cents="totalCents"
        :bonus-percent="0"
        :bonus-lots="0"
        :plan="planConfig"
        :plan-name="selectedPlan.name"
      />
      <p v-if="nextPayment" class="ds-note">
        {{ t('buy.nextPayment', { amount: nextPayment.amount, date: nextPayment.date }) }}
      </p>
    </PurchaseDone>

    <template v-else>
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
            </li>
          </ul>
        </section>

        <div class="iv__actions">
          <CButton variant="outline" @click="cancel">
            {{ t('buy.backToTerms') }}
          </CButton>
        </div>
      </template>

      <!-- CONFIRM mode (step 2): the Purchase block with the schedule, balance, CTAs -->
      <template v-else-if="selectedPlan && planConfig">
        <article class="ds-card">
          <div class="ds-card__body ds-purchase">
            <PurchaseStepLine :step="2" />
            <h2 class="ds-card__title">{{ t('buy.confirmTitle') }}</h2>
            <PurchaseSummary
              :title="summaryTitle"
              :lots="product.package_size"
              :lot-price-cents="product.price_per_unit_cents"
              :shares-per-option="sharesPerOption"
              :total-cents="totalCents"
              :bonus-percent="0"
              :bonus-lots="0"
              :plan="planConfig"
              :plan-name="selectedPlan.name"
            />

            <!-- Payment schedule: one row per payment (K23) -->
            <ul class="ds-rows">
              <li v-for="(tr, i) in planConfig.tranches" :key="i" class="ds-row">
                <span class="ds-row__body">
                  <span class="ds-row__title">{{ t('buy.month', { n: i + 1 }) }}</span>
                  <span class="ds-row__meta">
                    {{ t('buy.monthShare', { n: formatNumber(tr.units_percent, locale) }) }}
                  </span>
                </span>
                <span class="ds-row__trail">
                  <span class="ds-row__value">{{ formatUsd(tr.amount_cents, locale) }}</span>
                </span>
              </li>
            </ul>

            <p class="ds-note">
              {{
                t('buy.balanceNote', {
                  balance: formatUsdCents(balanceCents, locale),
                  pay: formatUsdCents(firstTrancheCents, locale),
                })
              }}
            </p>
            <CAlert
              v-if="insufficientBalance"
              tone="warning"
              :title="t('buy.shortTitle', { amount: formatUsdCents(shortfallCents, locale) })"
            >
              {{
                t('buy.shortFirst', {
                  balance: formatUsdCents(balanceCents, locale),
                  need: formatUsdCents(firstTrancheCents, locale),
                })
              }}
              <template #actions>
                <CButton variant="outline" size="sm" inline @click="toTopUp">
                  {{ t('buy.topUp') }}
                </CButton>
              </template>
            </CAlert>

            <!-- The disclosure, short, and the one tick of the buyer agreement -->
            <PurchaseTerms v-model="accepted" />

            <!-- Actions -->
            <div class="ds-purchase__actions">
              <CButton
                variant="primary"
                :disabled="!canConfirm"
                :loading="submitting"
                @click="confirm"
              >
                {{ t('buy.payAmount', { amount: formatUsdCents(firstTrancheCents, locale) }) }}
              </CButton>
              <CButton variant="outline" :disabled="submitting" @click="cancel">
                {{ t('buy.backToTerms') }}
              </CButton>
            </div>
          </div>
        </article>
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
