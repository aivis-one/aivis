<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicProductDetailView (iter 2.6 batch 6, R1 §1.6.1)
// =============================================================================
//
// Anonymous storefront product detail. Public counterpart to the
// investor-side /investor/products/:id. Differences with the auth
// view:
//
//   1. NO `<CHeader>` inside the view. The shell carries the only
//      header for the public flow (single-header policy, Batch 3).
//      An inline back-link "Back to company" sits above the hero so
//      the deep-linked visitor has an explicit path into the company
//      overview context.
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
import { Building, ShoppingCart } from 'lucide-vue-next'

import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { getProduct } from '@/api/products'
import { useAuthStore } from '@/stores/auth'
import { useAuthWall } from '@/composables/useAuthWall'
import { usePublicErrorToast } from '@/composables/usePublicErrorToast'
import {
  formatNumber,
  formatPrice,
  resolveCoverImage,
} from '@/utils/format'
import { getPlanBonus } from '@/utils/installmentPlans'
import type { PublicProductDetailResponse } from '@/api/types'

// Backend currency field is not emitted yet (TD-F03). Keep the
// escape hatch here so the page is correct once it lands -- same
// pattern as auth-flow ProductDetailView.
type ProductWithOptionalCurrency = PublicProductDetailResponse & {
  currency?: string
}

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { requireAuth } = useAuthWall()
const { notifyRateLimit } = usePublicErrorToast()

const product = ref<ProductWithOptionalCurrency | null>(null)
const loading = ref<boolean>(true)
const errored = ref<boolean>(false)
const notFound = ref<boolean>(false)

// Epoch guard. The :id route param can change in-place (rare for a
// detail view, but possible if the visitor navigates between two
// public-product links in a chat), so the fetch path needs the same
// FP-17 race protection used elsewhere.
let fetchEpoch = 0

const productId = computed<string>(() => route.params.id as string)

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

const coverImage = computed<string | null>(() => {
  const p = product.value
  return p ? resolveCoverImage(p) : null
})

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
  return authStore.isAuthenticated
    ? t('inv.product.buy')
    : t('public.productDetail.purchaseCTA')
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

function goToCompany(): void {
  const p = product.value
  if (!p) return
  void safeNavigate(
    router.push({
      name: 'public-company-overview',
      params: { id: p.company_id },
    }),
    '[PublicProductDetailView] to company',
  )
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
    console.warn(
      '[PublicProductDetailView] Buy CTA tapped for unsupported role:',
      role,
    )
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
    <div v-if="loading" class="ppd__center">
      <CLoader :size="32" />
    </div>

    <!-- 404 -->
    <div v-else-if="notFound" class="ppd__center">
      <CEmptyState
        :title="t('public.productDetail.notFound.title')"
        :description="t('public.productDetail.notFound.subtitle')"
      />
    </div>

    <!-- Generic error -->
    <div v-else-if="errored" class="ppd__center">
      <CEmptyState :title="t('public.productDetail.errorTitle')" />
      <CButton variant="primary" @click="onRetry">
        {{ t('public.productDetail.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else-if="product">
      <!-- Inline back-link to company overview. Unlike the public
           CompanyOverview (where browser back covers the list -> overview
           navigation), this view is typically reached via deep-link;
           an explicit path to the company context is worth the row.
           iter 2.7 batch B3: button shape extracted to CBackLink so the
           public and auth flows share the same component. -->
      <div class="ppd__back-row">
        <CBackLink
          :label="t('public.productDetail.backLink')"
          @click="goToCompany"
        />
      </div>

      <!-- Hero with cover image (matches auth-flow ProductDetailView
           proportions and gradient overlay). -->
      <div
        class="ppd__hero"
        :class="{ 'ppd__hero--fallback': !coverImage }"
        :style="{ backgroundImage: coverImage ?? 'none' }"
      >
        <Building v-if="!coverImage" :size="64" class="ppd__hero-icon" />
        <div class="ppd__hero-content">
          <div class="ppd__hero-company">{{ product.company_name }}</div>
          <h1 class="ppd__hero-title">{{ product.name }}</h1>
        </div>
      </div>

      <div class="ppd__body">
        <!-- Stats: pack price (primary) + packs available -->
        <div class="ppd__stats">
          <div class="ppd__stat">
            <div class="ppd__stat-label">
              {{ t('inv.product.pricePerPack') }}
            </div>
            <div class="ppd__stat-value ppd__stat-value--price">
              {{ formatPrice(product.price_per_pack_cents, product.currency) }}
            </div>
            <div class="ppd__stat-unit">
              {{ formatPrice(product.price_per_unit_cents, product.currency) }}
              / {{ t('inv.unit') }}
            </div>
          </div>
          <div class="ppd__stat">
            <div class="ppd__stat-label">
              {{ t('inv.product.packsAvailability') }}
            </div>
            <div class="ppd__stat-value">
              {{ formatNumber(available, locale) }}
            </div>
            <div class="ppd__stat-unit">{{ t('inv.available') }}</div>
          </div>
        </div>

        <!-- Description -->
        <section v-if="product.description" class="ppd__section">
          <h2 class="ppd__section-title">
            {{ t('inv.product.description') }}
          </h2>
          <p class="ppd__description">{{ product.description }}</p>
        </section>

        <!-- Installment plans: read-only list for public visitor.
             Tappable cards in the auth-flow view deep-link into the
             auth-only InstallmentView; here we list plans as marketing
             proof and let the primary Buy CTA drive the funnel. -->
        <section class="ppd__section">
          <h2 class="ppd__section-title">
            {{ t('inv.product.installments') }}
          </h2>
          <div
            v-if="product.installments.length === 0"
            class="ppd__empty"
          >
            {{ t('inv.product.installmentsEmpty') }}
          </div>
          <ul v-else class="ppd__plans">
            <li
              v-for="plan in product.installments"
              :key="plan.id"
              class="ppd__plan"
            >
              <span class="ppd__plan-name">{{ plan.name }}</span>
              <span
                v-if="getPlanBonus(plan) > 0"
                class="ppd__plan-bonus"
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

        <!-- Primary CTA. Visible for anonymous (Register to buy),
             investor (Buy now), agent (Buy now). Hidden for staff /
             company / other authenticated roles to avoid the silent
             guard-rejection failure mode (R26 lesson). When sold out,
             the button stays visible but disabled with a "Sold out"
             label so the visitor knows the product exists. -->
        <div v-if="canNavigateToPurchase" class="ppd__actions">
          <CButton
            variant="primary"
            :disabled="isSoldOut"
            @click="onBuyClick"
          >
            <ShoppingCart :size="16" />
            {{ buyLabel }}
          </CButton>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ppd {
  display: flex;
  flex-direction: column;
}

.ppd__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: 320px;
  padding: var(--space-4);
}

/* iter 2.7 batch B3 -- positioning wrapper for the inline back-link
   above the hero. Button shape lives in CBackLink (R32 STYLE-32-02);
   this row only owns the margin. */
.ppd__back-row {
  display: flex;
  margin: var(--space-4) var(--space-4) 0;
}

/* Hero with cover image -- proportions mirror auth-flow
   ProductDetailView for visual consistency across flows. */
.ppd__hero {
  position: relative;
  height: 220px;
  background-color: var(--bg-subtle);
  background-size: cover;
  background-position: center;
  display: flex;
  align-items: flex-end;
  justify-content: flex-start;
  color: #fff;
}

.ppd__hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(transparent 30%, rgba(0, 0, 0, 0.75));
  pointer-events: none;
}

.ppd__hero--fallback {
  background-color: var(--bg-subtle);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.ppd__hero--fallback::after {
  display: none;
}

.ppd__hero-icon {
  position: relative;
  z-index: 1;
  color: var(--text-tertiary);
  stroke-width: 2;
}

.ppd__hero-content {
  position: relative;
  z-index: 2;
  padding: 20px;
  width: 100%;
}

.ppd__hero--fallback .ppd__hero-content {
  text-align: center;
  color: var(--text-primary);
  padding: 0 20px 20px;
}

.ppd__hero-company {
  font-size: var(--fs-xs);
  font-weight: 600;
  opacity: 0.85;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ppd__hero-title {
  font-size: var(--fs-xl);
  font-weight: 700;
  margin: 0;
  line-height: 1.3;
}

.ppd__body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.ppd__stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ppd__stat {
  padding: 14px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
  text-align: center;
}

.ppd__stat-label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.ppd__stat-value {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.ppd__stat-value--price {
  color: var(--primary);
}

.ppd__stat-unit {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}

.ppd__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ppd__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ppd__description {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

.ppd__empty {
  padding: 14px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
  font-size: var(--fs-xs-lg);
  color: var(--text-tertiary);
  text-align: center;
}

.ppd__plans {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Plan row is NON-interactive in the public flow. Auth-flow renders
   tappable cards that deep-link into InstallmentView -- a route the
   public visitor cannot enter. We strip the cursor / hover / focus
   affordances to make the read-only intent obvious. */
.ppd__plan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.ppd__plan-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.ppd__plan-bonus {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--success);
  white-space: nowrap;
}

.ppd__actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 8px;
}

@media (min-width: 520px) {
  .ppd__actions {
    flex-direction: row;
  }
  .ppd__actions > * {
    flex: 1;
  }
}
</style>
