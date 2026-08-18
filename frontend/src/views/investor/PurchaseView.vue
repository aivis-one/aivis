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
//   5. Error -> narrow to ApiResponseError and branch on status + a
//      message hint. KYC rejection nudges to /onboarding/kyc.
//
// Balance source:
//   active_balance.confirmed from /dashboard/summary. The backend
//   reads the same figure via get_active_balance (frozen excluded).
//
// F4.2.1 polish:
//   Error identification switched from (duck-typed status, regex)
//   to `instanceof ApiResponseError` + status/message. Regex on the
//   backend message string is still the discriminator between the
//   three 400 sub-cases -- not ideal, but robust enough until the
//   backend starts emitting error codes in `detail` (tracked as
//   TD-F10). Until then, at least the type and status are rigid.
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
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { getProduct } from '@/api/products'
import { createPurchase } from '@/api/purchases'
import { useDashboardStore } from '@/stores/dashboard'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
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
const balanceCents = computed<number>(
  () => dashboardStore.activeBalance.confirmed,
)

const insufficientBalance = computed<boolean>(() => {
  return balanceCents.value < totalCents.value
})

const canConfirm = computed<boolean>(() => {
  return (
    !loading.value &&
    !submitting.value &&
    !errored.value &&
    product.value !== null &&
    !soldOut.value &&
    !insufficientBalance.value
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
    const [p] = await Promise.all([
      getProduct(productId.value),
      dashboardStore.refresh(),
    ])
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
    await createPurchase(productId.value, {})
    showToast(t('inv.purchase.success'), 'success')
    // Awaited push so `submitting` stays true until navigation
    // resolves, avoiding a brief UI flash of the Confirm button
    // between API success and unmount. safeNavigate is no-throw
    // by contract -- critical here so a benign NavigationFailure
    // does NOT bubble into the outer catch and trip handlePurchaseError(),
    // which would otherwise surface a generic-error toast on top of
    // the success toast.
    await safeNavigate(
      router.push({
        name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio',
      }),
      '[PurchaseView] post-submit to portfolio',
    )
  } catch (err: unknown) {
    await handlePurchaseError(err)
  } finally {
    submitting.value = false
  }
}

async function handlePurchaseError(err: unknown): Promise<void> {
  if (err instanceof ApiResponseError) {
    const { status, message } = err

    // KYC first -- matches BadRequestError('KYC verification required ...')
    // from purchases/service.py KYC guard. TD-F10 will replace the
    // regex with a backend-emitted error code.
    if (status === 400 && /kyc/i.test(message)) {
      showToast(t('inv.purchase.error.kycRequired'), 'warning')
      void safeNavigate(
        router.push('/onboarding/kyc'),
        '[PurchaseView] to KYC onboarding',
      )
      return
    }

    // Insufficient balance. Refresh the balance probe before returning
    // so the next render shows the fresh figure, not the stale one.
    // Store.refresh never throws -- balance display is a hint, not a
    // gate, so a failed refresh here is acceptable (the previous
    // stale value stays on screen).
    if (status === 400 && /insufficient/i.test(message)) {
      showToast(t('inv.purchase.error.insufficientBalance'), 'error')
      await dashboardStore.refresh()
      return
    }

    // Product / company status changed under us.
    if ((status === 400 && /not active/i.test(message)) || status === 404) {
      showToast(t('inv.purchase.error.productInactive'), 'error')
      return
    }
  }

  // Network / timeout / unknown -- fall through to generic.
  showToast(t('inv.purchase.error.generic'), 'error')
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
      name: agentShell.value
        ? 'agent-product-detail'
        : 'investor-product-detail',
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
         paradigm). The product name lives in the hero <h1> below;
         no inline title block is needed. By design no back-link --
         this view's existing pattern (pre-B2) intentionally omitted
         one, and purchases are typically reached from product detail
         where the user can hit browser back. -->

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
          <div class="pv__hero-company">{{ product.company_name }}</div>
          <h1 class="pv__hero-title">{{ product.name }}</h1>
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
          <div
            class="pv__balance"
            :class="{ 'pv__balance--warn': insufficientBalance }"
          >
            {{ formatPrice(balanceCents, product.currency) }}
          </div>
          <p v-if="insufficientBalance" class="pv__balance-hint">
            {{ t('inv.purchase.insufficientHint') }}
          </p>
        </section>

        <!-- Actions -->
        <div class="pv__actions">
          <CButton
            variant="primary"
            :disabled="!canConfirm"
            @click="confirm"
          >
            <ShoppingCart :size="16" />
            {{
              soldOut
                ? t('inv.product.soldOut')
                : t('inv.purchase.confirm')
            }}
          </CButton>
          <CButton
            variant="outline"
            :disabled="submitting"
            @click="cancel"
          >
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

.pv__center {
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
  gap: 8px;
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
  padding: 16px 20px;
  width: 100%;
}
.pv__hero--fallback .pv__hero-content {
  text-align: center;
  color: var(--text-primary);
  padding: 0 20px 16px;
}
.pv__hero-company {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.pv__hero-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0;
  line-height: 1.3;
  word-break: break-word;
}

.pv__body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Generic card */
.pv__card {
  padding: 16px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}
.pv__card-title {
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Rows inside summary */
.pv__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
}
.pv__row--total {
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
}
.pv__row-label {
  font-size: 14px;
  color: var(--text-secondary);
}
.pv__row-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.pv__row-value--total {
  font-size: 20px;
  color: var(--primary);
}

/* Balance */
.pv__balance {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}
.pv__balance--warn {
  color: var(--danger);
}
.pv__balance-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--danger);
}

/* Actions */
.pv__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}
</style>
