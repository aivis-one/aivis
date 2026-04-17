<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PurchaseView (Phase F4.2)
// =============================================================================
//
// Instant-purchase confirmation screen. Shared across
// /investor/purchase/:id and /agent/purchase/:id via role-aware
// route names (same approach as MarketView / ProductDetailView).
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
//   5. Error -> map ApiResponseError to a specific toast / side-effect.
//      KYC rejection nudges to /onboarding/kyc.
//
// Balance source:
//   active_balance.confirmed from /dashboard/summary. The backend
//   reads the same figure via get_active_balance (frozen excluded).
//
// Error identification is done by (status, message-regex) duck-typing
// rather than by importing a specific error class. This keeps the
// view decoupled from the concrete shape of api/client errors and
// survives any reshuffle of error-type exports.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building, ShoppingCart } from 'lucide-vue-next'
import { CButton, CLoader, CEmptyState } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import { getProduct } from '@/api/products'
import { createPurchase } from '@/api/purchases'
import { getDashboardSummary } from '@/api/dashboard'
import { useToast } from '@/composables/useToast'
import { isAgentShell } from '@/router/helpers'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
import type { PublicProductDetailResponse } from '@/api/types'

// Backend currency is not emitted on Public* yet (TD-F03). Same
// escape hatch as ProductDetailView -- remove once the field lands.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const { showToast } = useToast()

const product = ref<ProductWithOptionalCurrency | null>(null)
const balanceCents = ref(0)
const loading = ref(true)
const errored = ref(false)
const submitting = ref(false)

const productId = computed(() => route.params.id as string)
const agentShell = computed(() => isAgentShell(route))

const totalCents = computed<number>(() => {
  const p = product.value
  return p ? p.units * p.price_per_unit_cents : 0
})

const available = computed<number>(() => {
  const p = product.value
  return p ? Math.max(p.units - p.sold_units, 0) : 0
})

const soldOut = computed(() => available.value <= 0)

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

const headerTitle = computed<string>(() => {
  return product.value?.name ?? t('inv.purchase.title')
})

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const [p, s] = await Promise.all([
      getProduct(productId.value),
      getDashboardSummary(),
    ])
    product.value = p
    balanceCents.value = s.active_balance.confirmed
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
    router.push({
      name: agentShell.value ? 'agent-portfolio' : 'investor-portfolio',
    })
  } catch (err: unknown) {
    handlePurchaseError(err)
  } finally {
    submitting.value = false
  }
}

function handlePurchaseError(err: unknown): void {
  const status = readErrorStatus(err)
  const message = readErrorMessage(err)

  // KYC first -- matches BadRequestError('KYC verification required ...')
  // from purchases/service.py execute_purchase KYC guard.
  if (status === 400 && /kyc/i.test(message)) {
    showToast(t('inv.purchase.error.kycRequired'), 'warning')
    // Path-based push -- safer than named route if the onboarding
    // route name drifts. Router guards send the user onward if KYC
    // has actually already been approved.
    router.push('/onboarding/kyc')
    return
  }

  // Insufficient balance. Refresh our balance probe in case another
  // tab / session already spent some of it.
  if (status === 400 && /insufficient/i.test(message)) {
    showToast(t('inv.purchase.error.insufficientBalance'), 'error')
    void refreshBalance()
    return
  }

  // Product / company status changed under us.
  if ((status === 400 && /not active/i.test(message)) || status === 404) {
    showToast(t('inv.purchase.error.productInactive'), 'error')
    return
  }

  showToast(t('inv.purchase.error.generic'), 'error')
}

async function refreshBalance(): Promise<void> {
  try {
    const s = await getDashboardSummary()
    balanceCents.value = s.active_balance.confirmed
  } catch {
    // Balance display is a hint, not a gate. Swallow.
  }
}

function readErrorStatus(err: unknown): number | null {
  if (typeof err === 'object' && err !== null && 'status' in err) {
    const s = (err as { status: unknown }).status
    if (typeof s === 'number') return s
  }
  return null
}

function readErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

function cancel(): void {
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

onMounted(load)
</script>

<template>
  <div class="pv">
    <CHeader :title="headerTitle" />

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
              {{ formatNumber(product.units, locale) }}
              {{ t('inv.unit') }}
            </span>
          </div>

          <div class="pv__row">
            <span class="pv__row-label">
              {{ t('inv.purchase.pricePerUnit') }}
            </span>
            <span class="pv__row-value">
              {{ formatPrice(product.price_per_unit_cents, product.currency) }}
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
  stroke-width: 1.5;
}
.pv__hero-content {
  position: relative;
  z-index: 2;
  padding: 16px 20px;
  width: 100%;
}
.pv__hero--fallback .pv__hero-content {
  text-align: center;
  color: var(--text);
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
  border-radius: var(--radius-md, 12px);
  background: var(--bg-secondary, var(--surface));
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
  border-top: 1px solid var(--border, rgba(255, 255, 255, 0.08));
}
.pv__row-label {
  font-size: 14px;
  color: var(--text-secondary);
}
.pv__row-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.pv__row-value--total {
  font-size: 20px;
  color: var(--primary);
}

/* Balance */
.pv__balance {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
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
