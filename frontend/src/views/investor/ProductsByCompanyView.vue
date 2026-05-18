<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- ProductsByCompanyView (iter 2.5 batch 8, R1 §1.4)
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
import {
  isNavigationFailure,
  NavigationFailureType,
  useRoute,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import ProductCard from '@/components/shared/ProductCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useProductsStore } from '@/stores/products'
import { useInfiniteScroll } from '@/composables/usePagination'
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
    router
      .replace({ name: companiesListRouteName.value })
      .catch((err: unknown) => {
        // Benign vue-router rejection types stay silent so real
        // issues (unknown route, thrown guard) remain visible.
        if (
          isNavigationFailure(err, NavigationFailureType.duplicated)
          || isNavigationFailure(err, NavigationFailureType.cancelled)
          || isNavigationFailure(err, NavigationFailureType.aborted)
        ) {
          return
        }
        console.error(
          '[ProductsByCompanyView] protective replace to companies list failed:',
          err,
        )
      })
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
  router
    .push({
      name: productDetailRouteName.value,
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
        '[ProductsByCompanyView] navigation to product detail failed:',
        err,
      )
    })
}

function onRetry(): void {
  void productsStore.fetchFirstPage()
}
</script>

<template>
  <div class="pbc">
    <CHeader :title="headerTitle" show-back />

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
    <div
      v-else-if="productsStore.loading"
      class="pbc__center"
    >
      <CLoader :size="28" />
    </div>

    <!-- Error state -->
    <div
      v-else-if="productsStore.error"
      class="pbc__center"
    >
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
    <div
      v-if="productsStore.items.length > 0"
      ref="sentinelRef"
      class="pbc__sentinel"
    >
      <CLoader v-if="productsStore.loading" :size="20" />
    </div>
  </div>
</template>

<style scoped>
.pbc {
  display: flex;
  flex-direction: column;
}

.pbc__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
  padding: var(--space-md);
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
  gap: var(--space-md);
  min-height: 320px;
  padding: var(--space-md);
}

.pbc__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-md) 0 0;
  min-height: 32px;
}
</style>
