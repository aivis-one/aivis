<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicProductDetailView (iter 2.6 batch 6, R1 §1.6.1)
// =============================================================================
//
// Anonymous storefront product detail. Public counterpart to the
// investor-side /investor/products/:id. Differences with the auth
// view:
//
//   1. NO header inside the view. The frame carries the only
//      header for the public flow (single-header policy, Batch 3).
//      The header's back control leads to the company overview so the
//      deep-linked visitor has an explicit path into that context.
//
//   2. Installment plans are READ-ONLY for the public visitor. The
//      auth-flow renders each plan as a tappable card that deep-links
//      into InstallmentView with `?plan=<id>`. For an anonymous
//      visitor that target is auth-gated, and for staff / company the
//      route's meta.roles would reject -- both cases would dead-tap
//      (R26 lesson on silent guard rejection). Instead we list plans
//      flat: visitors see "this product has X, Y, Z installment plans
//      with these bonuses" as marketing proof, and act on the primary
//      Buy CTA below.
//
//   3. Primary CTA branches on auth state, mirroring the §1.6.5
//      contract from PublicProductsSection (Batch 5 + R26 fix):
//        - anonymous -> "Register to buy" via useAuthWall().requireAuth
//          ('purchase'); pushes /register?next=...&intent=purchase.
//        - investor / agent -> "Buy now" via router.push into
//          investor-purchase / agent-purchase respectively.
//        - staff / company / other authenticated -> CTA is HIDDEN via
//          canNavigateToPurchase. R26 lesson: a button that would
//          silent-fail on globalGuard meta.roles rejection is worse
//          than a button that is not there.
//
//   4. Sold-out handling. The auth-flow renders the Buy CTA disabled
//      with label "Sold out" when available_packages <= 0. Same
//      contract here: the CTA stays visible (so the visitor knows the
//      product exists but is unavailable) but is disabled and labelled.
//
//   5. i18n reuse. Most strings come from the inv.product.* catalogue
//      already in en.json -- "Price per pack", "Description",
//      "Installment plans", "Buy now", "Sold out", "+N bonus units"
//      etc. are domain-neutral. Same pattern as Batch 4 reusing
//      inv.path.* for documents L1 labels. Only public-specific
//      strings (error / back-link / register-CTA) live under
//      public.productDetail.*.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { useI18n } from 'vue-i18n'
import { Building, ShoppingCart } from '@/components/ui/icons'

import { CBadge, CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { ApiResponseError } from '@/api/client'
import { getProduct } from '@/api/products'
import { useAuthStore } from '@/stores/auth'
import { useAuthWall } from '@/composables/useAuthWall'
import { usePublicErrorToast } from '@/composables/usePublicErrorToast'
import { formatNumber, formatPrice } from '@/utils/format'
import { formatPartPrice, formatPartsCount } from '@/utils/parts'
import { useSharesPerOption } from '@/composables/useSharesPerOption'
import { getPlanBonus, planMonthsLabel } from '@/utils/installmentPlans'
import type { PublicProductDetailResponse } from '@/api/types'
import { useProductCover } from '@/composables/useThemedLogo'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

// Backend currency field is not emitted yet (TD-F03). Keep the
// escape hatch here so the page is correct once it lands -- same
// pattern as auth-flow ProductDetailView.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const { t, locale } = useI18n()
const planLabel = (plan: { name: string; plan_config: Record<string, unknown> }): string =>
  planMonthsLabel(plan, t, locale.value)
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { requireAuth } = useAuthWall()
const { notifyRateLimit } = usePublicErrorToast()

const product = ref<ProductWithOptionalCurrency | null>(null)

// The price of one part: the lot's price over the project's parts per lot; a dash
// while the project's parts per lot is not known (never the lot's price).
const { ensure: ensureParts, partsPerLot } = useSharesPerOption()
watch(
  () => product.value?.company_id,
  (id) => {
    if (id) void ensureParts([id])
  },
  { immediate: true },
)
const partPriceDisplay = computed<string>(() => {
  const p = product.value
  const perLot = p ? partsPerLot(p.company_id) : null
  return p && perLot !== null ? formatPartPrice(p.price_per_unit_cents, perLot, locale.value) : '—'
})
const loading = ref<boolean>(true)
const errored = ref<boolean>(false)
const notFound = ref<boolean>(false)

// Epoch guard. The :id route param can change in-place (rare for a
// detail view, but possible if the visitor navigates between two
// public-product links in a chat), so the fetch path needs the same
// FP-17 race protection used elsewhere.
let fetchEpoch = 0

const productId = computed<string>(() => route.params.id as string)

// The frame's header carries the title and the way back: the product's name and
// a link to its company (a deep-linked visitor has an explicit path into the
// company overview). Called synchronously in setup.
useScreenHeader({
  title: () => product.value?.name,
  back: () =>
    product.value
      ? { name: 'public-company-overview', params: { id: product.value.company_id } }
      : undefined,
})

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

async function loadProduct(id: string): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  notFound.value = false
  product.value = null

  try {
    const resp = await getProduct(id)
    if (epoch !== fetchEpoch) return
    product.value = resp
  } catch (err) {
    if (epoch !== fetchEpoch) return
    if (err instanceof ApiResponseError && err.status === 404) {
      // Product hidden, archived, or never existed. Same UX for all
      // three to avoid confirming the existence of private rows
      // (matches backend "404 not 403" policy, R1 §1.6.4).
      notFound.value = true
      return
    }
    // 429 / 5xx / network: render generic error + retry, plus a
    // toast on 429 with the Retry-After hint.
    notifyRateLimit(err)
    errored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadProduct(productId.value))

onMounted(() => {
  void loadProduct(productId.value)
})

watch(
  () => route.params.id,
  (next) => {
    if (typeof next !== 'string' || !next) return
    void loadProduct(next)
  },
)

// ---------------------------------------------------------------------------
// Derived display state
// ---------------------------------------------------------------------------

// The cover is the product's own picture, else the company's logo for the
// theme (K47 hero).
const coverSrc = useProductCover(() => product.value)

// available_packages is required on the backend schema (no `?? 0`
// default, see auth-flow ProductDetailView's F4.4 note). The 0
// fallback here only exists for the pre-load window when product is
// still null.
const available = computed<number>(() => {
  const p = product.value
  return p ? p.available_packages : 0
})

const isSoldOut = computed<boolean>(() => available.value <= 0)

const buyLabel = computed<string>(() => {
  if (isSoldOut.value) return t('inv.product.soldOut')
  return authStore.isAuthenticated ? t('inv.product.buy') : t('public.productDetail.purchaseCTA')
})

// ---------------------------------------------------------------------------
// CTA visibility (R26 lesson -- hide for roles without a target route)
// ---------------------------------------------------------------------------

/**
 * Whether the visitor's auth state has somewhere to go on tap.
 * Anonymous visitors do (auth wall -> /register). investor / agent
 * do (investor-purchase / agent-purchase). staff / company / other
 * authenticated roles have no public-purchase route under their
 * shell and would trip globalGuard's meta.roles guard -- the CTA is
 * hidden for them rather than rendering a silent dead button.
 */
const canNavigateToPurchase = computed<boolean>(() => {
  if (!authStore.isAuthenticated) return true
  const role = authStore.role
  return role === 'investor' || role === 'agent'
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function onRetry(): void {
  void loadProduct(productId.value)
}

function onBuyClick(): void {
  const p = product.value
  if (!p) return
  if (isSoldOut.value) return

  if (!authStore.isAuthenticated) {
    // Anonymous: requireAuth pushes to /register?next=...&intent=...
    // and returns false (we don't act on the return -- the navigation
    // is the action).
    requireAuth('purchase')
    return
  }

  // Authenticated: route to the role-appropriate purchase view. The
  // explicit role check mirrors PublicProductsSection (R26 FE-26-01)
  // -- the template guard hides this CTA for staff / company, the
  // handler check is defence-in-depth in case the guard is bypassed
  // by a future refactor.
  const role = authStore.role
  let targetRoute: 'agent-purchase' | 'investor-purchase'
  if (role === 'agent') {
    targetRoute = 'agent-purchase'
  } else if (role === 'investor') {
    targetRoute = 'investor-purchase'
  } else {
    console.warn('[PublicProductDetailView] Buy CTA tapped for unsupported role:', role)
    return
  }
  void safeNavigate(
    router.push({
      name: targetRoute,
      params: { id: p.id },
    }),
    '[PublicProductDetailView] to purchase',
  )
}
</script>

<template>
  <div class="ppd">
    <!-- Loading -->
    <CLoader v-if="loading" centered extent="page" />

    <!-- 404 -->
    <CEmptyState
      v-else-if="notFound"
      :title="t('public.productDetail.notFound.title')"
      :description="t('public.productDetail.notFound.subtitle')"
    />

    <!-- Generic error -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('public.productDetail.errorTitle')">
      <template #actions>
        <CButton variant="primary" inline @click="onRetry">
          {{ t('public.productDetail.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else-if="product">
      <!-- Hero with the cover (K47): the company and the product name over the
           photo, or the fallback tile with the icon when there is no photo. -->
      <section class="ds-hero" aria-labelledby="ppd-hero-title">
        <img v-if="coverSrc" class="ds-hero__image" :src="coverSrc" alt="" />
        <span v-else class="ds-hero__fallback"><Building /></span>
        <div class="ds-hero__content">
          <h2 id="ppd-hero-title" class="ds-hero__title">
            {{ product.name }}
          </h2>
          <p class="ds-hero__meta">
            {{ product.company_name }}
          </p>
        </div>
      </section>

      <!-- Stats: pack price (primary) + packs available (K46) -->
      <div class="ds-stats">
        <CStatCard
          :label="t('inv.product.pricePerPack')"
          :value="formatPrice(product.price_per_pack_cents, product.currency)"
          :sub="`${t('buy.partPrice')}: ${partPriceDisplay}`"
        />
        <CStatCard
          :label="t('inv.product.packsAvailability')"
          :value="formatNumber(available, locale)"
          :sub="t('inv.available')"
        />
      </div>

      <!-- Description -->
      <section v-if="product.description" class="ds-card ds-card--flat">
        <div class="ds-card__head">
          <h2 class="ds-card__title">
            {{ t('inv.product.description') }}
          </h2>
        </div>
        <p class="ds-card__body ppd__description">
          {{ product.description }}
        </p>
      </section>

      <!-- Installment plans: a read-only list for the public visitor (K23 rows
           with no link). Tappable cards in the auth-flow view deep-link into the
           auth-only InstallmentView; here the plans are marketing proof and the
           primary Buy CTA drives the funnel. -->
      <section class="ds-card ds-card--flat">
        <div class="ds-card__head">
          <h2 class="ds-card__title">
            {{ t('inv.product.installments') }}
          </h2>
        </div>
        <p v-if="product.installments.length === 0" class="ds-card__body">
          {{ t('inv.product.installmentsEmpty') }}
        </p>
        <ul v-else class="ds-rows">
          <li v-for="plan in product.installments" :key="plan.id" class="ds-row">
            <span class="ds-row__body">
              <span class="ds-row__title">{{ planLabel(plan) }}</span>
            </span>
            <span v-if="getPlanBonus(plan) > 0" class="ds-row__trail">
              <CBadge
                variant="success"
                :text="
                  t('inv.product.installmentsBonus', {
                    n: formatPartsCount(
                      getPlanBonus(plan),
                      partsPerLot(product.company_id),
                      locale,
                    ),
                  })
                "
              />
            </span>
          </li>
        </ul>
      </section>

      <!-- Primary CTA. Visible for anonymous (Register to buy),
           investor (Buy now), agent (Buy now). Hidden for staff /
           company / other authenticated roles to avoid the silent
           guard-rejection failure mode (R26 lesson). When sold out,
           the button stays visible but disabled with a "Sold out"
           label so the visitor knows the product exists. -->
      <CButton
        v-if="canNavigateToPurchase"
        variant="primary"
        :disabled="isSoldOut"
        @click="onBuyClick"
      >
        <ShoppingCart size="sm" />
        {{ buyLabel }}
      </CButton>
    </template>
  </div>
</template>

<style scoped>
/* The frame's main pads the screen; this column only lays its parts out with the
   same gap the main uses. */
.ppd {
  display: grid;
  gap: var(--space-5);
}

/* The description keeps the visitor's own line breaks and is capped at the reading
   measure (--maxw-prose is a ceiling: on a phone it does nothing). */
.ppd__description {
  white-space: pre-wrap;
  overflow-wrap: break-word;
  max-inline-size: var(--maxw-prose);
}
</style>
