<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PurchaseView (Phase F4.2 + F4.2.1 polish + F4.3 fix
//                                     + F4.4 B7 UX)
// =============================================================================
//
// Instant-purchase confirmation screen. Shared across
// /investor/purchase/:id and /agent/purchase/:id via role-aware
// route names (same approach as ProductDetailView / InstallmentView).
//
// Flow:
//   1. On mount, fetch product detail + dashboard summary in parallel.
//   2. User reviews the order (units * price_per_unit = total) and
//      current spendable balance.
//   3. Confirm -> POST /api/v1/products/{id}/purchase. Backend owns
//      the authoritative balance / KYC / status checks. The UI
//      affordance (disabled button when balance < total) is a UX
//      courtesy, not a security boundary.
//   4. Success -> toast + push to the portfolio in the current shell.
//   5. Error -> narrow to ApiResponseError and branch on the server's error
//      code (kyc_required, insufficient_balance, sold_out,
//      product_not_available, company_not_active). A 402 from the KYC gate
//      is left to main.ts, which shows the verification prompt; the
//      service's own kyc_required refusal (what an agent meets) opens the
//      same prompt from here.
//
// BEFORE PAYING. The screen shows the pre-purchase disclosure short, with its
// full text by link, and ONE tick that accepts the buyer agreement. The
// button ("Pay") stays shut until the tick is set; pressing it records the
// acceptance (a signing of the buyer agreement) and then buys. A purchase
// opens in the position of its own project. Short of money, the screen says
// how much is missing and offers the top-up for exactly that amount.
//
// Balance source:
//   active_balance.confirmed from /dashboard/summary. The backend
//   reads the same figure via get_active_balance (frozen excluded).
//
// F4.2.1 polish:
//   Error identification is by `instanceof ApiResponseError` + the
//   server's error code (the regexes on message text are gone).
//
// F4.3 fix:
//   Cancel used router.push(ProductDetail), which pushed a fresh
//   history entry on top of the existing [Market, ProductDetail,
//   Purchase] stack and turned the header back button on the
//   returned ProductDetail into a back-to-Purchase trap. Now the
//   cancel path asks vue-router to step back one entry (restoring
//   scroll/state for free) and only falls through to push() when
//   there is no back entry -- i.e. the user deep-linked into this
//   screen.
//
// F4.4 B7 UX:
//   Order summary row 2 anchors on the pack: label "Price per pack",
//   value = formatPrice(price_per_pack_cents). Row 1 ("Package size")
//   and row 3 ("Total") are unchanged -- Total stays as a separate
//   line because it equals the pack price for a 1-pack purchase, and
//   keeping it visually distinct preserves the "final amount" anchor
//   pattern users expect on a checkout screen.
//
//   `totalCents` formula is unchanged (package_size * price_per_unit_cents).
//   It is mathematically equal to product.price_per_pack_cents but
//   computed locally so the screen never desyncs from the package
//   numbers it just rendered above.
//
//   Sprint 4.4 also dropped the `= 0` default on `available_packages`
//   on the backend schema. The `?? 0` fallback here is gone -- a
//   missing populate would be a server bug, not a soft default.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, ShoppingCart } from 'lucide-vue-next'
import { CBackLink, CButton, CLoader, CEmptyState } from '@/components/ui'
import PurchaseTerms from '@/components/shared/PurchaseTerms.vue'
import { ApiResponseError } from '@/api/client'
import { acceptDocumentByType } from '@/api/documents'
import { getProduct } from '@/api/products'
import { createPurchase } from '@/api/purchases'
import { useDashboardStore } from '@/stores/dashboard'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice, resolveCoverImage } from '@/utils/format'
import type { PublicProductDetailResponse } from '@/api/types'

// Backend currency is not emitted on Public* yet (TD-F03). Same
// escape hatch as ProductDetailView -- remove once the field lands.
// Note: BalanceResponse also lacks a currency field (TD-F03 scope
// extended) -- spendable balance is assumed USD cents until the
// multi-currency contract ships.
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
// Aligning with the F4.4 B2 store migration: no more local
// balanceCents ref, no more inline getDashboardSummary probe.
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

const coverImage = computed<string | null>(() => {
  return product.value ? resolveCoverImage(product.value) : null
})

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
    product.value = p
  } catch {
    product.value = null
    errored.value = true
  } finally {
    loading.value = false
  }
}

async function confirm(): Promise<void> {
  if (!canConfirm.value) return
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
    // The bonus parts the purchase brought, one-time, are named at once.
    const bonusUnits = rows
      .filter((r) => r.legal_basis === 'gift')
      .reduce((sum, r) => sum + r.units, 0)
    showToast(
      bonusUnits > 0
        ? t('inv.purchase.successBonus', { units: formatNumber(bonusUnits, locale.value) })
        : t('inv.purchase.success'),
      'success',
    )
    // Awaited push so `submitting` stays true until navigation
    // resolves, avoiding a brief UI flash of the Confirm button
    // between API success and unmount. safeNavigate is no-throw
    // by contract -- critical here so a benign NavigationFailure
    // does NOT bubble into the outer catch and trip handlePurchaseError(),
    // which would otherwise surface a generic-error toast on top of
    // the success toast. The purchase opens in the position of ITS project.
    await safeNavigate(
      router.push({
        name: agentShell.value ? 'agent-company-position' : 'investor-company-position',
        params: { id: product.value?.company_id ?? '' },
      }),
      '[PurchaseView] post-submit to the project position',
    )
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

function cancel(): void {
  // Prefer router.back() so the ProductDetail screen restores its
  // scroll/state for free and we don't pollute history with a
  // duplicate ProductDetail entry (which would turn the back button
  // on that screen into a back-to-Purchase trap). Only push when
  // vue-router has no prior entry -- i.e. PurchaseView was opened
  // via a deep-linked URL.
  if (router.options.history.state.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({
      name: agentShell.value ? 'agent-product-detail' : 'investor-product-detail',
      params: { id: productId.value },
    }),
    '[PurchaseView] cancel fallback to product detail',
  )
}

function backToMarket(): void {
  // iter 2.6.x hotfix: market routes removed in iter 2.5 batch 9,
  // catalogue moved to *-companies (CompanyListView). Function
  // name kept -- see also `inv.product.backToMarket` i18n key which
  // carries the updated "Back to companies" user-facing label.
  void safeNavigate(
    router.push({
      name: agentShell.value ? 'agent-companies' : 'investor-companies',
    }),
    '[PurchaseView] to companies list',
  )
}

onMounted(load)
</script>

<template>
  <div class="pv">
    <!-- iter 2.7 batch B2: <CHeader> removed (single-shell-header
         paradigm). The product name lives in the hero <h1> below.
         The screen has its own back control; cancel() is history-aware. -->
    <div v-if="!loading && product" class="pv__back-row">
      <CBackLink :label="t('inv.purchase.backLink')" @click="cancel" />
    </div>

    <div v-if="loading" class="pv__center">
      <CLoader />
    </div>

    <template v-else-if="errored || !product">
      <div class="pv__center">
        <CEmptyState
          :title="t('inv.purchase.loadError.title')"
          :description="t('inv.purchase.loadError.desc')"
        />
        <CButton variant="outline" @click="backToMarket">
          {{ t('inv.product.backToMarket') }}
        </CButton>
      </div>
    </template>

    <template v-else>
      <!-- Product hero -->
      <div
        class="pv__hero"
        :class="{ 'pv__hero--fallback': !coverImage }"
        :style="{ backgroundImage: coverImage ?? 'none' }"
      >
        <Building v-if="!coverImage" :size="48" class="pv__hero-icon" />
        <div class="pv__hero-content">
          <div class="pv__hero-company">
            {{ product.company_name }}
          </div>
          <h1 class="pv__hero-title">
            {{ product.name }}
          </h1>
        </div>
      </div>

      <div class="pv__body">
        <!-- Order summary -->
        <section class="pv__card">
          <h2 class="pv__card-title">
            {{ t('inv.purchase.orderSummary') }}
          </h2>

          <div class="pv__row">
            <span class="pv__row-label">
              {{ t('inv.purchase.packageSize') }}
            </span>
            <span class="pv__row-value">
              {{ formatNumber(product.package_size, locale) }}
              {{ t('inv.unit') }}
            </span>
          </div>

          <div class="pv__row">
            <span class="pv__row-label">
              {{ t('inv.purchase.pricePerPack') }}
            </span>
            <span class="pv__row-value">
              {{ formatPrice(product.price_per_pack_cents, product.currency) }}
            </span>
          </div>

          <div class="pv__row pv__row--total">
            <span class="pv__row-label">{{ t('inv.purchase.total') }}</span>
            <span class="pv__row-value pv__row-value--total">
              {{ formatPrice(totalCents, product.currency) }}
            </span>
          </div>
        </section>

        <!-- Balance -->
        <section class="pv__card">
          <h2 class="pv__card-title">
            {{ t('inv.purchase.yourBalance') }}
          </h2>
          <div class="pv__balance" :class="{ 'pv__balance--warn': insufficientBalance }">
            {{ formatPrice(balanceCents, product.currency) }}
          </div>
          <template v-if="insufficientBalance">
            <p class="pv__balance-hint">
              {{
                t('inv.purchase.shortfall', {
                  amount: formatPrice(shortfallCents, product.currency),
                })
              }}
            </p>
            <CButton variant="outline" size="sm" @click="toTopUp">
              {{ t('inv.purchase.topUp') }}
            </CButton>
          </template>
        </section>

        <!-- The disclosure, short, and the one tick of the buyer agreement -->
        <PurchaseTerms v-model="accepted" />

        <!-- Actions -->
        <div class="pv__actions">
          <CButton variant="primary" :disabled="!canConfirm" @click="confirm">
            <ShoppingCart :size="16" />
            {{ soldOut ? t('inv.product.soldOut') : t('inv.purchase.pay') }}
          </CButton>
          <CButton variant="outline" :disabled="submitting" @click="cancel">
            {{ t('inv.purchase.cancel') }}
          </CButton>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pv {
  display: flex;
  flex-direction: column;
}

.pv__back-row {
  padding: var(--space-3) var(--space-4) 0;
}

.pv__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: calc(100vh - 120px);
  min-height: calc(100dvh - 120px);
  padding: var(--space-5);
}

/* Hero with cover */
.pv__hero {
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
.pv__hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(transparent 30%, rgba(0, 0, 0, 0.75));
  pointer-events: none;
}
.pv__hero--fallback {
  background-color: var(--bg-subtle);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}
.pv__hero--fallback::after {
  display: none;
}
.pv__hero-icon {
  position: relative;
  z-index: 1;
  color: var(--text-tertiary);
  stroke-width: 2;
}
.pv__hero-content {
  position: relative;
  z-index: 2;
  padding: var(--space-4) var(--space-4-lg);
  width: 100%;
}
.pv__hero--fallback .pv__hero-content {
  text-align: center;
  color: var(--text-primary);
  padding: 0 var(--space-4-lg) var(--space-4);
}
.pv__hero-company {
  font-size: var(--fs-xs);
  font-weight: 600;
  opacity: 0.85;
  margin-bottom: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.pv__hero-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  margin: 0;
  line-height: 1.3;
  word-break: break-word;
}

.pv__body {
  padding: var(--space-4-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Generic card */
.pv__card {
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}
.pv__card-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  margin: 0 0 var(--space-3);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Rows inside summary */
.pv__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) 0;
}
.pv__row--total {
  margin-top: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-default);
}
.pv__row-label {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.pv__row-value {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.pv__row-value--total {
  font-size: var(--fs-lg);
  color: var(--primary);
}

/* Balance */
.pv__balance {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.pv__balance--warn {
  color: var(--danger);
}
.pv__balance-hint {
  margin: var(--space-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--danger);
}

/* Actions */
.pv__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-2);
}
</style>
