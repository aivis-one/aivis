<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PurchaseBlock (the buying path, step 1)
// =============================================================================
//
// The Purchase block (K55) under a project's cover: the whole choice in one card.
//   - the portfolio switch (K31): the project's products, one per portfolio, the
//     bonus a payment at once brings written in the label;
//   - the payment switch (K31): at once, or each instalment plan the chosen
//     portfolio has;
//   - the parts, the price of a part and, on an instalment, its money and the
//     parts by month (PurchaseSummary), then "Buy" -- or, when the buyer cannot
//     buy yet, the refusal as a warning Alert (K09) with its Button.
//
// "Buy" leads to the confirmation (step 2): PurchaseView for a payment at once,
// InstallmentView for a plan. A visitor who is not signed in is sent to register.
//
// WHERE THE DATA COMES FROM (no new endpoints).
//   - the products: GET /public/products?company_id=, then each one's detail
//     (its instalment plans);
//   - the bonus: the storefront hides a product's purchase configuration, so a
//     signed-in buyer reads it from the purchase preview (the server's own
//     figure) and a visitor reads the leading "+N %" of the description's first
//     line, where the project writes it;
//   - the buyer's identity check and balance: the auth and dashboard stores.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CAlert, CButton, CLoader } from '@/components/ui'
import PurchaseStepLine from '@/components/shared/PurchaseStepLine.vue'
import PurchaseSummary from '@/components/shared/PurchaseSummary.vue'
import { getProduct, getPurchasePreview, listProducts, type PurchasePreview } from '@/api/products'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useAuthWall } from '@/composables/useAuthWall'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'
import { safeNavigate } from '@/composables/safeNavigate'
import { parsePlanConfig, type PlanConfig } from '@/utils/installmentPlans'
import { bonusPercentFromText, formatUsd, formatUsdCents } from '@/utils/parts'
import { formatNumber } from '@/utils/format'
import type { PublicProductDetailResponse } from '@/api/types'

const props = defineProps<{
  companyId: string
  companyName: string
  /** The parts in one lot: a product counts lots, the buyer sees parts. */
  sharesPerOption: number
}>()

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()
const { requireAuth } = useAuthWall()

const ONCE = '__once'

const products = ref<PublicProductDetailResponse[]>([])
const previews = ref<Record<string, PurchasePreview | null>>({})
const loading = ref(true)
const errored = ref(false)
const balanceReady = ref(false)

const selectedId = ref<string>('')
const payKey = ref<string>(ONCE)

// Who may buy: a visitor (sent to register) and the two buying roles. Staff and
// project accounts have no purchase route, so the block is not drawn for them.
const isBuyer = computed(() => authStore.role === 'investor' || authStore.role === 'agent')
const canBuy = computed(() => !authStore.isAuthenticated || isBuyer.value)

const selected = computed<PublicProductDetailResponse | null>(
  () => products.value.find((p) => p.id === selectedId.value) ?? null,
)

interface PlanOption {
  id: string
  name: string
  config: PlanConfig
}

const planOptions = computed<PlanOption[]>(() =>
  (selected.value?.installments ?? []).flatMap((pl) => {
    const config = parsePlanConfig(pl.plan_config)
    return config ? [{ id: pl.id, name: pl.name, config }] : []
  }),
)

const plan = computed<PlanOption | null>(
  () => planOptions.value.find((p) => p.name === payKey.value) ?? null,
)

function bonusPercentOf(p: PublicProductDetailResponse): number {
  const preview = previews.value[p.id]
  return preview ? preview.bonus_percent : bonusPercentFromText(p.description)
}

function bonusLotsOf(p: PublicProductDetailResponse): number {
  const preview = previews.value[p.id]
  if (preview) return preview.bonus_units
  return Math.floor((p.package_size * bonusPercentOf(p)) / 100)
}

function portfolioLabel(p: PublicProductDetailResponse): string {
  const price = formatUsd(p.price_per_pack_cents, locale.value)
  const pct = bonusPercentOf(p)
  return pct > 0 ? t('buy.portfolioOption', { price, n: formatNumber(pct, locale.value) }) : price
}

// ---------------------------------------------------------------------------
// The buyer's standing: identity check and balance
// ---------------------------------------------------------------------------

const payNowCents = computed<number>(() => {
  if (plan.value) return plan.value.config.tranches[0]?.amount_cents ?? 0
  return selected.value?.price_per_pack_cents ?? 0
})

const needsKyc = computed(() => isBuyer.value && authStore.kycStatus !== 'approved')
const balanceCents = computed(() => dashboardStore.activeBalance.confirmed)
const shortfallCents = computed(() => Math.max(0, payNowCents.value - balanceCents.value))
const needsMoney = computed(
  () => isBuyer.value && !needsKyc.value && balanceReady.value && shortfallCents.value > 0,
)

const soldOut = computed(() => (selected.value?.available_packages ?? 0) <= 0)

// The deposit minimum is $10: the top-up opens with the shortfall, never less.
const MIN_TOP_UP_CENTS = 1000
const topUpAmount = computed(() =>
  (Math.max(shortfallCents.value, MIN_TOP_UP_CENTS) / 100).toFixed(2),
)

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

let epoch = 0

async function load(): Promise<void> {
  const mine = ++epoch
  loading.value = true
  errored.value = false
  try {
    const list = await listProducts({ company_id: props.companyId, per_page: 100 })
    const details = await Promise.all(list.items.map((p) => getProduct(p.id)))
    const found: Record<string, PurchasePreview | null> = {}
    if (isBuyer.value) {
      await Promise.all(
        details.map(async (p) => {
          try {
            found[p.id] = await getPurchasePreview(p.id)
          } catch {
            found[p.id] = null
          }
        }),
      )
    }
    if (mine !== epoch) return
    // The cheapest portfolio first.
    products.value = [...details].sort((a, b) => a.price_per_pack_cents - b.price_per_pack_cents)
    previews.value = found
    if (!products.value.some((p) => p.id === selectedId.value)) {
      selectedId.value = products.value[0]?.id ?? ''
      payKey.value = ONCE
    } else if (!planOptions.value.some((p) => p.name === payKey.value)) {
      payKey.value = ONCE
    }
  } catch {
    if (mine !== epoch) return
    errored.value = true
  } finally {
    if (mine === epoch) loading.value = false
  }
}

function onPortfolioChange(): void {
  // The same plan carries over when the new portfolio has it, else back to "at once".
  if (!planOptions.value.some((p) => p.name === payKey.value)) payKey.value = ONCE
}

useReloadOnLocale(() => load())

onMounted(() => {
  void load()
  if (isBuyer.value) {
    void dashboardStore.refresh().finally(() => {
      balanceReady.value = true
    })
  }
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function buy(): void {
  const p = selected.value
  if (!p || soldOut.value) return
  if (!authStore.isAuthenticated) {
    requireAuth('purchase')
    return
  }
  const agent = authStore.role === 'agent'
  const chosen = plan.value
  void safeNavigate(
    chosen
      ? router.push({
          name: agent ? 'agent-installment' : 'investor-installment',
          params: { id: p.id },
          query: { plan: chosen.id },
        })
      : router.push({ name: agent ? 'agent-purchase' : 'investor-purchase', params: { id: p.id } }),
    '[PurchaseBlock] to the confirmation',
  )
}

function toVerification(): void {
  void safeNavigate(router.push('/verification'), '[PurchaseBlock] to verification')
}

function toTopUp(): void {
  void safeNavigate(
    router.push({
      name: 'investor-deposit',
      query: { amount: topUpAmount.value, min: '10' },
    }),
    '[PurchaseBlock] to top-up',
  )
}
</script>

<template>
  <article v-if="canBuy && (loading || errored || selected)" class="ds-card">
    <div class="ds-card__body ds-purchase">
      <CLoader v-if="loading" centered />

      <CAlert v-else-if="errored" tone="danger" :title="t('buy.loadError')">
        <template #actions>
          <CButton variant="outline" size="sm" inline @click="load">
            {{ t('buy.retry') }}
          </CButton>
        </template>
      </CAlert>

      <template v-else-if="selected">
        <PurchaseStepLine :step="1" />
        <h2 class="ds-card__title">{{ t('buy.title', { project: companyName }) }}</h2>

        <fieldset v-if="products.length > 1" class="ds-segmented">
          <legend class="ds-sr-only">{{ t('buy.portfolio') }}</legend>
          <label v-for="p in products" :key="p.id" class="ds-segmented__option">
            <input
              v-model="selectedId"
              class="ds-segmented__input"
              type="radio"
              name="buy-portfolio"
              :value="p.id"
              @change="onPortfolioChange"
            />
            {{ portfolioLabel(p) }}
          </label>
        </fieldset>

        <PurchaseSummary
          :title="selected.name"
          :lots="selected.package_size"
          :lot-price-cents="selected.price_per_unit_cents"
          :shares-per-option="sharesPerOption"
          :total-cents="selected.price_per_pack_cents"
          :bonus-percent="bonusPercentOf(selected)"
          :bonus-lots="bonusLotsOf(selected)"
          :plan="plan ? plan.config : null"
          :plan-name="plan ? plan.name : undefined"
        >
          <fieldset v-if="planOptions.length > 0" class="ds-segmented">
            <legend class="ds-sr-only">{{ t('buy.payment') }}</legend>
            <label class="ds-segmented__option">
              <input
                v-model="payKey"
                class="ds-segmented__input"
                type="radio"
                name="buy-payment"
                :value="ONCE"
              />
              {{ t('buy.payAtOnce') }}
            </label>
            <label v-for="o in planOptions" :key="o.id" class="ds-segmented__option">
              <input
                v-model="payKey"
                class="ds-segmented__input"
                type="radio"
                name="buy-payment"
                :value="o.name"
              />
              {{ o.name }}
            </label>
          </fieldset>
        </PurchaseSummary>

        <template v-if="needsKyc">
          <CAlert tone="warning" :title="t('buy.kycTitle')">
            {{ t('buy.kycText') }}
          </CAlert>
          <CButton variant="primary" @click="toVerification">{{ t('buy.kycGo') }}</CButton>
        </template>
        <template v-else-if="needsMoney">
          <CAlert
            tone="warning"
            :title="t('buy.shortTitle', { amount: formatUsdCents(shortfallCents, locale) })"
          >
            {{
              t(plan ? 'buy.shortFirst' : 'buy.shortPortfolio', {
                balance: formatUsdCents(balanceCents, locale),
                need: formatUsdCents(payNowCents, locale),
              })
            }}
          </CAlert>
          <CButton variant="primary" @click="toTopUp">{{ t('buy.topUp') }}</CButton>
        </template>
        <CButton v-else variant="primary" :disabled="soldOut" @click="buy">
          {{ soldOut ? t('buy.soldOut') : t('buy.buy') }}
        </CButton>
      </template>
    </div>
  </article>
</template>
