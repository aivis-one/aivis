<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PurchaseView (the buying path, steps 2 and 3, a payment
//                                     at once)
// =============================================================================
//
// The confirmation of a purchase at once and the screen that follows it. Shared
// across /investor/purchase/:id and /agent/purchase/:id via role-aware route
// names (same approach as InstallmentView, its twin for a plan).
//
// Flow:
//   1. On mount, fetch the product, the project (for the parts in a lot) and the
//      dashboard summary in parallel, then the bonus preview.
//   2. STEP 2 -- the buyer reviews the Purchase block (K55): the portfolio, its
//      parts, the price of a part and the total, the balance, the disclosure and
//      ONE tick that accepts the buyer agreement.
//   3. "Pay" records the acceptance, then POST /api/v1/products/{id}/purchase.
//      Backend owns the authoritative balance / KYC / status checks; the
//      disabled button is a UX courtesy, not a security boundary.
//   4. STEP 3 -- the same screen turns into the done screen: the congratulation
//      (a success Alert), the summary, the documents the purchase issued and
//      "To my portfolio".
//   5. Error -> narrow to ApiResponseError and branch on the server's error
//      code (kyc_required, insufficient_balance, sold_out,
//      product_not_available, company_not_active). A 402 from the KYC gate
//      is left to main.ts, which shows the verification prompt; the
//      service's own kyc_required refusal (what an agent meets) opens the
//      same prompt from here.
//
// The frame's header (K25) holds the product name and the back control (the same
// step as "Back to the terms"). The buyer sees PARTS (lots times the parts in a
// lot), the price of a part and the total in dollars and cents -- never the lot.
//
// Balance source: active_balance.confirmed from /dashboard/summary. The backend
// reads the same figure via get_active_balance (frozen excluded).
//
// Back used router.push(ProductDetail) once, which turned the header back button
// into a trap; now it steps back one entry and only pushes when there is no entry
// (the buyer deep-linked into this screen) -- to the project page.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CAlert, CButton, CLoader, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import PurchaseDone, { type DoneDocument } from '@/components/shared/PurchaseDone.vue'
import PurchaseStepLine from '@/components/shared/PurchaseStepLine.vue'
import PurchaseSummary from '@/components/shared/PurchaseSummary.vue'
import PurchaseTerms from '@/components/shared/PurchaseTerms.vue'
import { ApiResponseError } from '@/api/client'
import { getCompany } from '@/api/companies'
import { acceptDocumentByType } from '@/api/documents'
import { getProduct, getPurchasePreview, type PurchasePreview } from '@/api/products'
import { createPurchase } from '@/api/purchases'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatUsdCents } from '@/utils/parts'
import type { PublicProductDetailResponse } from '@/api/types'
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
const bonusPreview = ref<PurchasePreview | null>(null)

// The step the screen shows: the confirmation, then the done screen.
const step = ref<'confirm' | 'done'>('confirm')
const doneDocuments = ref<DoneDocument[]>([])
const doneBonusLots = ref(0)

const productId = computed(() => route.params.id as string)
const agentShell = computed(() => isAgentShell(route))

const totalCents = computed<number>(() => {
  const p = product.value
  return p ? p.package_size * p.price_per_unit_cents : 0
})

// F4.4: backend guarantees available_packages is populated; no `?? 0`.
const available = computed<number>(() => {
  const p = product.value
  return p ? p.available_packages : 0
})

const soldOut = computed(() => available.value <= 0)

// Spendable balance -- reads the store's computed getter, which
// falls back to a zeroed placeholder before the first refresh.
const balanceCents = computed<number>(() => dashboardStore.activeBalance.confirmed)

const insufficientBalance = computed<boolean>(() => {
  return balanceCents.value < totalCents.value
})

// What is missing, and the amount the top-up screen opens with: the shortfall,
// and never less than the deposit minimum of $10.
const MIN_TOP_UP_CENTS = 1000
const shortfallCents = computed<number>(() => Math.max(0, totalCents.value - balanceCents.value))
const topUpAmount = computed<string>(() =>
  (Math.max(shortfallCents.value, MIN_TOP_UP_CENTS) / 100).toFixed(2),
)

// The buyer agreement is accepted by ONE tick before paying.
const accepted = ref(false)

const canConfirm = computed<boolean>(() => {
  return (
    !loading.value &&
    !submitting.value &&
    !errored.value &&
    product.value !== null &&
    !soldOut.value &&
    !insufficientBalance.value &&
    accepted.value
  )
})

const summaryTitle = computed<string>(() =>
  product.value ? `${product.value.company_name} · ${product.value.name}` : '',
)

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    // Parallel probe: product detail + balance store refresh. Only
    // the product fetch's failure flips `errored` -- balance load
    // failures surface through dashboardStore.error and would leave
    // the UI with a zeroed balance, which the insufficient-balance
    // gate already handles gracefully.
    const [p] = await Promise.all([getProduct(productId.value), dashboardStore.refresh()])
    // The parts in a lot come with the project, not with the product.
    const company = await getCompany(p.company_id)
    sharesPerOption.value = company.shares_per_option
    product.value = p
    // The bonus preview is informational: a failure hides the row only.
    try {
      bonusPreview.value = await getPurchasePreview(productId.value)
    } catch {
      bonusPreview.value = null
    }
  } catch {
    product.value = null
    errored.value = true
  } finally {
    loading.value = false
  }
}

async function confirm(): Promise<void> {
  if (!canConfirm.value) return
  // A deep link records no acceptance for an unverified buyer.
  if (authStore.kycStatus !== 'approved') {
    showKycPrompt('purchase')
    return
  }
  submitting.value = true
  try {
    // The acceptance of the buyer agreement is recorded BEFORE the money
    // moves: the signing time is the acceptance time the purchase agreement
    // prints. Nothing is charged if the recording cannot be made.
    const recorded = await acceptDocumentByType(
      'buyer_agreement',
      locale.value === 'ru' ? 'ru' : 'en',
    )
    if (recorded === 'missing') {
      showToast(t('inv.purchase.error.agreementMissing'), 'error')
      return
    }

    const rows = await createPurchase(productId.value, {})
    // The bonus parts the purchase brought, one-time, are shown on the done screen.
    doneBonusLots.value = rows
      .filter((r) => r.legal_basis === 'gift')
      .reduce((sum, r) => sum + r.units, 0)
    doneDocuments.value = [
      ...rows.map((r) => ({ kind: 'agreement' as const, id: r.id, legalBasis: r.legal_basis })),
      { kind: 'ownership' as const },
    ]
    step.value = 'done'
    void dashboardStore.refresh()
    window.scrollTo?.({ top: 0 })
  } catch (err: unknown) {
    await handlePurchaseError(err)
  } finally {
    submitting.value = false
  }
}

// Errors are read from the server's code, never from the text of its message.
async function handlePurchaseError(err: unknown): Promise<void> {
  if (err instanceof ApiResponseError) {
    // 402 -- the KYC gate. main.ts has already shown the verification
    // prompt; a toast here would only say "error" on top of it.
    if (err.status === 402) return

    switch (err.code) {
      case 'kyc_required':
        // What an agent meets: the gate lets agents through by role.
        showKycPrompt('purchase')
        return
      case 'insufficient_balance':
        // Refresh the balance probe so the next render shows the fresh
        // figure; the screen then offers the top-up for what is missing.
        showToast(t('inv.purchase.error.insufficientBalance'), 'error')
        await dashboardStore.refresh()
        return
      case 'sold_out':
        showToast(t('inv.purchase.error.soldOut'), 'error')
        await load()
        return
      case 'product_not_available':
      case 'company_not_active':
        showToast(t('inv.purchase.error.productInactive'), 'error')
        return
      default:
        if (err.status === 404) {
          showToast(t('inv.purchase.error.productInactive'), 'error')
          return
        }
    }
  }

  // Network / timeout / unknown -- fall through to generic.
  showToast(t('inv.purchase.error.generic'), 'error')
}

function toTopUp(): void {
  void safeNavigate(
    router.push({
      name: 'investor-deposit',
      query: { amount: topUpAmount.value, min: '10' },
    }),
    '[PurchaseView] to top-up',
  )
}

function projectPage() {
  return {
    name: agentShell.value ? 'agent-company-overview' : 'investor-company-overview',
    params: { id: product.value?.company_id ?? '' },
  }
}

function cancel(): void {
  // Prefer router.back() so the project page restores its scroll/state for free and
  // we don't pollute history with a duplicate entry. Only push when vue-router has
  // no prior entry -- i.e. PurchaseView was opened via a deep-linked URL.
  if (router.options.history.state.back) {
    router.back()
    return
  }
  void safeNavigate(router.push(projectPage()), '[PurchaseView] back to the project page')
}

function toPortfolio(): void {
  void safeNavigate(
    router.push({ name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio' }),
    '[PurchaseView] to the portfolio',
  )
}

function backToMarket(): void {
  void safeNavigate(
    router.push({
      name: agentShell.value ? 'agent-companies' : 'investor-companies',
    }),
    '[PurchaseView] to companies list',
  )
}

// The frame's header: the product name, and the back control (the step "Back to the
// terms" takes). On the done screen there is nothing to go back to but the project.
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    step.value === 'done'
      ? projectPage()
      : router.options.history.state.back
        ? true
        : projectPage(),
})

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => {
  if (step.value === 'confirm') return load()
})

onMounted(load)
</script>

<template>
  <div class="pv">
    <CLoader v-if="loading" centered extent="page" />

    <CEmptyState
      v-else-if="errored || !product"
      tone="danger"
      :title="t('inv.purchase.loadError.title')"
      :description="t('inv.purchase.loadError.desc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="backToMarket">
          {{ t('inv.product.backToMarket') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Step 3: the done screen -->
    <PurchaseDone
      v-else-if="step === 'done'"
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
        :bonus-percent="bonusPreview?.bonus_percent ?? 0"
        :bonus-lots="doneBonusLots"
        :plan="null"
      />
    </PurchaseDone>

    <!-- Step 2: the confirmation -->
    <template v-else>
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
            :bonus-percent="bonusPreview?.bonus_percent ?? 0"
            :bonus-lots="bonusPreview?.bonus_units ?? 0"
            :plan="null"
          />
          <p class="ds-note">
            {{
              t('buy.balanceNote', {
                balance: formatUsdCents(balanceCents, locale),
                pay: formatUsdCents(totalCents, locale),
              })
            }}
          </p>
          <CAlert
            v-if="insufficientBalance"
            tone="warning"
            :title="t('buy.shortTitle', { amount: formatUsdCents(shortfallCents, locale) })"
          >
            {{
              t('buy.shortPortfolio', {
                balance: formatUsdCents(balanceCents, locale),
                need: formatUsdCents(totalCents, locale),
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
              {{
                soldOut
                  ? t('inv.product.soldOut')
                  : t('buy.payAmount', { amount: formatUsdCents(totalCents, locale) })
              }}
            </CButton>
            <CButton variant="outline" :disabled="submitting" @click="cancel">
              {{ t('buy.backToTerms') }}
            </CButton>
          </div>
        </div>
      </article>
    </template>
  </div>
</template>

<style scoped>
.pv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
</style>
