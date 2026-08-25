<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ProductsByCompanyView (iter 2.5 batch 8, R1 §1.4)
// =============================================================================
//
// Investor "company's products" view. Replaces MarketView, which used
// to be the catalogue + filter-sheet surface; in iter 2.5 the
// catalogue moves to CompanyListView (companies tab) and the per-
// company products list lives here.
//
// ROUTE.
//   /investor/companies/:id/products
//   /agent/companies/:id/products
//   Both routes target this component under their respective shells.
//   The route entries land in batch 9 -- this view alone is dead code
//   until the router gets the matching names.
//
// COMPANY PINNED VIA URL.
//   `:id` route param is the canonical filter input. No filter chip,
//   no CompanyFilterSheet -- the user got here from a company page,
//   the company is locked. To browse a different company, navigate
//   back to CompanyListView.
//
// HEADER TITLE RESOLUTION (R1 §1.4).
//   The header reads "<company name>". Resolution order:
//     1. companyListStore items lookup (the user just came from
//        CompanyListView -- the store already has the name in cache).
//     2. First product's denormalised company_name (deep-link path
//        where the store is empty but products load fast).
//     3. Generic placeholder t('inv.productsByCompany.title') for the
//        200-300ms window before either resolves. Spec acknowledges
//        this is a degraded state, treated as acceptable boundary.
//   No extra getCompany(id) fetch -- the round-trip would dominate
//   the visible time-to-first-paint and we already have two
//   plausible name sources.
//
// COMPANY_ID GUARD.
//   route.params.id is a string in Vue Router's typed API, but Vue's
//   permissive runtime can hand us '' for a malformed deep-link. A
//   normalised empty value triggers a protective redirect to the
//   companies list -- safer than letting useProductsStore drop the
//   filter to null and silently show every company's products.
//
// STORE SHARING NOTE.
//   useProductsStore is the same singleton MarketView used to drive.
//   Empty / blank stores after route enter are normal (resetAll on
//   logout / role switch). Cross-route navigation between two
//   companies on this view reuses the store via setCompanyFilter,
//   which is idempotent on identical id and resets+refetches on a
//   different id (the FP-17 epoch guard inside the store kills any
//   stale in-flight response).
//
// NO ONUNMOUNTED RESET.
//   Same trade-off MarketView made: keep the store populated so a
//   round-trip back to this view (e.g. user opens a product, hits
//   back) doesn't pay for the page-1 fetch again. resetAllDataStores
//   on logout / role switch covers the real cleanup case.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import ProductCard from '@/components/shared/ProductCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useProductsStore } from '@/stores/products'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import type { PublicProductResponse } from '@/api/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const productsStore = useProductsStore()
const companyListStore = useCompanyListStore()

// storeToRefs keeps hasMore reactive when destructured for the
// infinite-scroll composable.
const { hasMore } = storeToRefs(productsStore)

const sentinelRef = ref<HTMLElement | null>(null)

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const companiesListRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-companies' : 'investor-companies',
)

const productDetailRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-product-detail' : 'investor-product-detail',
)

const companyOverviewRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-company-overview' : 'investor-company-overview',
)

// ---------------------------------------------------------------------------
// Header title resolution (R1 §1.4)
// ---------------------------------------------------------------------------

const headerTitle = computed<string>(() => {
  const id = companyId.value
  if (!id) return t('inv.productsByCompany.title')
  // 1) companyListStore lookup -- the cache that survives the
  // navigation from CompanyListView.
  const cached = companyListStore.items.find((c) => c.id === id)
  if (cached?.name) return cached.name
  // 2) First product's denormalised company_name. ProductCard payloads
  // carry company_name on PublicProductResponse -- it's the same name
  // the storefront shows on the card subline.
  const firstProductName = productsStore.items[0]?.company_name
  if (firstProductName) return firstProductName
  // 3) Generic placeholder while we wait for either source.
  return t('inv.productsByCompany.title')
})

// ---------------------------------------------------------------------------
// Lifecycle: protective guard + filter pinning
// ---------------------------------------------------------------------------

useInfiniteScroll(sentinelRef, hasMore, productsStore.loadMore)

onMounted(() => {
  // Protective: malformed deep-link bypass. setCompanyFilter would
  // normalise an empty string to null and silently load the global
  // catalogue, which is wrong for this view.
  if (!companyId.value) {
    void safeNavigate(
      router.replace({ name: companiesListRouteName.value }),
      '[ProductsByCompanyView] protective replace to companies list',
    )
    return
  }
  void productsStore.setCompanyFilter(companyId.value)
})

// In-place :id swap. Vue Router reuses the component when navigating
// from /investor/companies/A/products to /investor/companies/B/products;
// without this watch the user would see A's products under B's title.
watch(
  () => route.params.id,
  (next) => {
    if (typeof next !== 'string' || !next) return
    void productsStore.setCompanyFilter(next)
  },
)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function openProduct(product: PublicProductResponse): void {
  void safeNavigate(
    router.push({
      name: productDetailRouteName.value,
      params: { id: product.id },
    }),
    '[ProductsByCompanyView] to product detail',
  )
}

function onRetry(): void {
  void productsStore.fetchFirstPage()
}

// iter 2.7 batch B2: inline back-link handler. Prefers router.back()
// so the originating screen (CompanyOverviewView most commonly)
// restores scroll/state for free; falls back to the company overview
// for the current companyId when there's no prior history (deep-link).
function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  const id = companyId.value
  if (!id) {
    // Defensive: an empty companyId means the deep-link is malformed.
    // onMounted's guard already redirected, but if we somehow hit this
    // path, send the user to the catalogue rather than a broken overview.
    void safeNavigate(
      router.push({ name: companiesListRouteName.value }),
      '[ProductsByCompanyView] back fallback to companies list (no id)',
    )
    return
  }
  void safeNavigate(
    router.push({ name: companyOverviewRouteName.value, params: { id } }),
    '[ProductsByCompanyView] back fallback to company overview',
  )
}
</script>

<template>
  <div class="pbc">
    <!-- iter 2.7 batch B2: inline page-header replaces view-CHeader.
         The company name (resolved by headerTitle) lives in the h1;
         the back-link goes to company overview, mirroring the previous
         CHeader back's history-back default with a deep-link fallback.
         B3: button shape extracted to CBackLink. -->
    <div class="pbc__page-header">
      <CBackLink :label="t('inv.productsByCompany.backLink')" @click="goBack" />
      <h1 class="pbc__page-title">
        {{ headerTitle }}
      </h1>
    </div>

    <!-- Grid (visible whenever we have items) -->
    <div v-if="productsStore.items.length > 0" class="pbc__grid">
      <ProductCard
        v-for="item in productsStore.items"
        :key="item.id"
        :product="item"
        @click="openProduct"
      />
    </div>

    <!-- Initial load spinner -->
    <div v-else-if="productsStore.loading" class="pbc__center">
      <CLoader :size="28" />
    </div>

    <!-- Error state -->
    <div v-else-if="productsStore.error" class="pbc__center">
      <CEmptyState
        :title="t('inv.productsByCompany.errorTitle')"
        :description="productsStore.error"
      />
      <CButton variant="outline" size="sm" @click="onRetry">
        {{ t('inv.productsByCompany.errorRetry') }}
      </CButton>
    </div>

    <!-- Empty (filter set, company has no active products) -->
    <div v-else class="pbc__center">
      <CEmptyState
        :title="t('inv.productsByCompany.empty.title')"
        :description="t('inv.productsByCompany.empty.subtitle')"
      />
    </div>

    <!-- Infinite-scroll sentinel (only when we already have items). -->
    <div v-if="productsStore.items.length > 0" ref="sentinelRef" class="pbc__sentinel">
      <CLoader v-if="productsStore.loading" :size="20" />
    </div>
  </div>
</template>

<style scoped>
.pbc {
  display: flex;
  flex-direction: column;
}

/* iter 2.7 batch B2 -- inline page-header (back-link + title) replaces
   the previous view-CHeader. No hero on this view, so the title lives
   inside a header block at the top. */
.pbc__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4) var(--space-2);
}
.pbc__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.pbc__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
  padding: var(--space-4);
}

/* Two-column grid for wider viewports -- matches MarketView's old
   breakpoint so the layout transition between CompanyListView,
   CompanyOverviewView and here stays predictable. */
@media (min-width: 640px) {
  .pbc__grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 960px) {
  .pbc__grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.pbc__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-lg);
  padding: var(--space-4);
}

.pbc__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}
</style>
