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
// The frame's header (K25) holds the product name and the back control (the same
// step as Cancel); the product is the Hero (K47), its text on the scrim; the order
// summary and the balance are Key-value lists (K49) in Cards (K07).
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
import { AlertTriangle, Building, ShoppingCart } from '@/components/ui/icons'
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import PurchaseTerms from '@/components/shared/PurchaseTerms.vue'
import { ApiResponseError } from '@/api/client'
import { acceptDocumentByType } from '@/api/documents'
import { getProduct, getPurchasePreview, type PurchasePreview } from '@/api/products'
import { createPurchase } from '@/api/purchases'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { showKycPrompt } from '@/composables/useKycPrompt'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { formatNumber, formatPrice } from '@/utils/format'
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
const authStore = useAuthStore()
const { showToast } = useToast()
const dashboardStore = useDashboardStore()

const product = ref<ProductWithOptionalCurrency | null>(null)
const loading = ref(true)
const errored = ref(false)
const submitting = ref(false)
const bonusPreview = ref<PurchasePreview | null>(null)

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

// The cover is the product's own picture, else the company's logo.
const coverSrc = computed<string | null>(
  () => product.value?.cover_url ?? product.value?.company_logo_url ?? null,
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

// The frame's header: the product name, and the back control (the step Cancel takes).
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    router.options.history.state.back
      ? true
      : {
          name: agentShell.value ? 'agent-product-detail' : 'investor-product-detail',
          params: { id: productId.value },
        },
})

onMounted(load)
</script>

<template>
  <div class="pv">
    <CLoader v-if="loading" />

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

    <template v-else>
      <!-- Product hero (K47): the company and the product name over the photo, or
           the fallback tile with the icon when there is no photo. -->
      <section class="ds-hero" data-size="sm" aria-labelledby="pv-hero-title">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="pv-hero-title" class="ds-hero__title">
            {{ product.name }}
          </h2>
          <p class="ds-hero__meta">
            {{ product.company_name }}
          </p>
        </div>
      </section>

      <!-- Order summary (K49) -->
      <section class="ds-card" aria-labelledby="pv-summary">
        <header class="ds-card__head">
          <h2 id="pv-summary" class="ds-card__title">
            {{ t('inv.purchase.orderSummary') }}
          </h2>
        </header>
        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('inv.purchase.packageSize') }}</dt>
            <dd>{{ formatNumber(product.package_size, locale) }} {{ t('inv.unit') }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('inv.purchase.pricePerPack') }}</dt>
            <dd>{{ formatPrice(product.price_per_pack_cents, product.currency) }}</dd>
          </div>
          <div v-if="bonusPreview && bonusPreview.bonus_units > 0" class="ds-kv__row">
            <dt>{{ t('inv.purchase.bonusParts') }}</dt>
            <dd>
              +{{ formatNumber(bonusPreview.bonus_units, locale) }} ({{
                formatNumber(bonusPreview.bonus_percent, locale)
              }}%)
            </dd>
          </div>
          <div class="ds-kv__row ds-kv__row--total">
            <dt>{{ t('inv.purchase.total') }}</dt>
            <dd>{{ formatPrice(totalCents, product.currency) }}</dd>
          </div>
        </dl>
      </section>

      <!-- Balance -->
      <section class="ds-card">
        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('inv.purchase.yourBalance') }}</dt>
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
                t('inv.purchase.shortfall', {
                  amount: formatPrice(shortfallCents, product.currency),
                })
              }}
            </p>
            <div class="ds-alert__actions">
              <CButton variant="outline" size="sm" inline @click="toTopUp">
                {{ t('inv.purchase.topUp') }}
              </CButton>
            </div>
          </div>
        </div>
      </section>

      <!-- The disclosure, short, and the one tick of the buyer agreement -->
      <PurchaseTerms v-model="accepted" />

      <!-- Actions -->
      <div class="pv__actions">
        <CButton variant="primary" :disabled="!canConfirm" @click="confirm">
          <ShoppingCart size="sm" />
          {{ soldOut ? t('inv.product.soldOut') : t('inv.purchase.pay') }}
        </CButton>
        <CButton variant="outline" :disabled="submitting" @click="cancel">
          {{ t('inv.purchase.cancel') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Actions */
.pv__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
</style>
