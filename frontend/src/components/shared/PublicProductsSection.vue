<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PublicProductsSection (iter 2.6 batch 5, R1 §1.6.1)
// =============================================================================
//
// Anonymous-storefront products teaser. Embedded in
// PublicCompanyOverviewView between the Roadmap and Documents
// sections (R1 §1.6.1 ordering: Hero -> Stats -> Roadmap -> Products
// -> Documents).
//
// WHY A TEASER, NOT INFINITE SCROLL.
//   The investor-side ProductsByCompanyView gives the full paginated
//   list under its own URL (/investor/companies/:id/products). The
//   public CompanyOverview is a marketing-funnel surface: show the
//   first page of products inline as proof of inventory, then defer
//   the deep list to the authenticated experience (or to anonymous
//   visitors who click through to a single product detail). Burning
//   the full list inline would dilute the page's narrative without
//   adding marketing value.
//
// STORE REUSE.
//   useProductsStore is shared with MarketView (removed) and
//   ProductsByCompanyView (auth-flow). It already calls
//   /api/v1/public/products via api/products.ts::listProducts -- the
//   wrapper sends `Authorization` only when a token is set, so the
//   same endpoint works for anonymous and authenticated visitors.
//   setCompanyFilter(id) is idempotent on the same id; on a different
//   id it resets+refetches with the FP-17 epoch guard inside the store.
//
// "SEE ALL" CTA -- branched on auth state.
//   Anonymous visitor: tapping "Register to see all products" routes
//   through useAuthWall().requireAuth('explore_products'), which
//   pushes to /register?next=<current path>&intent=explore_products.
//   `intent` is a forward-compatible passthrough (iter 2.6 does not
//   consume it).
//
//   Authenticated visitor (sharing-link sceneario -- agent sends a
//   public URL to a registered investor): tapping "See all products"
//   routes directly to the authenticated company-products view under
//   the visitor's role-appropriate shell. agent -> agent-company-products,
//   everyone else -> investor-company-products (investor/staff/company
//   roles all land on the investor-side view; staff and company are
//   rare edge cases that work because the view itself doesn't enforce
//   role beyond the shell's `roles` meta).
//
//   Inline role check (no helper) because this is the only public-flow
//   site that needs role-aware authenticated routing, and a 3-line
//   inline conditional is clearer than a one-off helper hidden in
//   utils.
//
// CTA VISIBILITY.
//   Only when `total > items.length` -- i.e. when there are more
//   products than what the teaser shows. A company with 1-19 products
//   surfaces all of them inline and the CTA is hidden; a company with
//   20+ shows the first 20 and offers a path to the rest.
//
// SELF-HIDE CONTRACT (R1 §1.6.1).
//   - loading           -> render (spinner inside)
//   - errored           -> render (error + retry inside)
//   - success + empty   -> DON'T render at all
//   - success + items   -> render (grid + maybe-CTA)
//   The parent does NOT wrap this in v-if; the component decides.
//   Matches AttachmentsSection / PublicAttachmentsSection contract.
// =============================================================================

import { computed, onMounted, watch } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import ProductCard from '@/components/shared/ProductCard.vue'
import { useAuthStore } from '@/stores/auth'
import { useProductsStore } from '@/stores/products'
import { useAuthWall } from '@/composables/useAuthWall'
import type { PublicProductResponse } from '@/api/types'

const props = defineProps<{
  companyId: string
}>()

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const productsStore = useProductsStore()
const { requireAuth } = useAuthWall()

// storeToRefs keeps `total` reactive for the shouldRender / hasMore
// computations below. We don't destructure `items` -- the template
// reads productsStore.items directly so length changes trigger
// reactivity without a wrapper.
const { total } = storeToRefs(productsStore)

// ---------------------------------------------------------------------------
// Lifecycle: pin the company filter
// ---------------------------------------------------------------------------

onMounted(() => {
  // setCompanyFilter is idempotent on an unchanged id. First-mount
  // path triggers fetchFirstPage; navigation-back-then-here path
  // short-circuits and the cached first page renders without flash.
  void productsStore.setCompanyFilter(props.companyId)
})

// In-place :company-id swap. PublicCompanyOverviewView is reused by
// Vue Router across /public/companies/A -> /public/companies/B
// navigations; the watch keeps the products grid honest under the
// new hero.
watch(
  () => props.companyId,
  (next) => {
    if (next) {
      void productsStore.setCompanyFilter(next)
    }
  },
)

// ---------------------------------------------------------------------------
// Render decision (self-hide contract)
// ---------------------------------------------------------------------------

const hasError = computed<boolean>(() => productsStore.error !== null)

const initialLoading = computed<boolean>(
  () => productsStore.loading && productsStore.items.length === 0,
)

const shouldRender = computed<boolean>(() => {
  // Render while loading so visitors get a spinner instead of layout
  // pop-in once data arrives.
  if (initialLoading.value) return true
  // Render the error state so visitors can retry.
  if (hasError.value) return true
  // Successful empty -> hide entirely (R1 §1.6.1 "hide when empty").
  return productsStore.items.length > 0
})

// ---------------------------------------------------------------------------
// CTA visibility + label (branched on auth state, see file header)
// ---------------------------------------------------------------------------

const hasMoreThanShown = computed<boolean>(
  () => total.value > productsStore.items.length,
)

const ctaLabel = computed<string>(() =>
  authStore.isAuthenticated
    ? t('public.companyOverview.products.seeAllAuth')
    : t('public.companyOverview.products.seeAll'),
)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function openProduct(product: PublicProductResponse): void {
  // Anonymous storefront stays on /public/* throughout. The detail
  // route lands as a stub in Batch 2 and gets its real implementation
  // in Batch 6; navigation succeeds either way.
  router
    .push({
      name: 'public-product-detail',
      params: { id: product.id },
    })
    .catch((err: unknown) => {
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error(
        '[PublicProductsSection] navigation to product failed:',
        err,
      )
    })
}

function onSeeAllClick(): void {
  if (authStore.isAuthenticated) {
    // Share-link scenario: a registered investor follows a public URL
    // sent by an agent. Skip the register screen entirely and route
    // straight to the authenticated products list under the visitor's
    // shell.
    const targetRoute =
      authStore.role === 'agent'
        ? 'agent-company-products'
        : 'investor-company-products'
    router
      .push({
        name: targetRoute,
        params: { id: props.companyId },
      })
      .catch((err: unknown) => {
        if (
          isNavigationFailure(err, NavigationFailureType.duplicated)
          || isNavigationFailure(err, NavigationFailureType.cancelled)
          || isNavigationFailure(err, NavigationFailureType.aborted)
        ) {
          return
        }
        console.error(
          '[PublicProductsSection] navigation to auth products failed:',
          err,
        )
      })
    return
  }
  // Anonymous: requireAuth pushes to /register?next=...&intent=...
  // and returns false (we don't act on the return -- the navigation
  // is the action).
  requireAuth('explore_products')
}

function onRetry(): void {
  void productsStore.fetchFirstPage()
}
</script>

<template>
  <section v-if="shouldRender" class="pps">
    <header class="pps__head">
      <h2 class="pps__title">
        {{ t('public.companyOverview.sectionProducts') }}
      </h2>
    </header>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="pps__center">
      <CLoader :size="24" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="pps__center">
      <CEmptyState
        :title="t('public.companyOverview.products.errorTitle')"
        :description="productsStore.error ?? undefined"
      />
      <CButton variant="outline" size="sm" @click="onRetry">
        {{ t('public.companyOverview.products.errorRetry') }}
      </CButton>
    </div>

    <!-- Grid -->
    <template v-else>
      <div class="pps__grid">
        <ProductCard
          v-for="product in productsStore.items"
          :key="product.id"
          :product="product"
          @click="openProduct"
        />
      </div>

      <div v-if="hasMoreThanShown" class="pps__cta">
        <CButton variant="primary" @click="onSeeAllClick">
          {{ ctaLabel }}
        </CButton>
      </div>
    </template>
  </section>
</template>

<style scoped>
.pps {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.pps__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pps__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.pps__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  min-height: 120px;
}

.pps__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
}

/* Two-column grid at narrow tablet breakpoint, three at wider --
   mirrors ProductsByCompanyView's breakpoints so the layout
   transition between public overview and authenticated full-list
   stays predictable. */
@media (min-width: 640px) {
  .pps__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 960px) {
  .pps__grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.pps__cta {
  display: flex;
  justify-content: center;
  padding-top: var(--space-sm);
}
</style>
