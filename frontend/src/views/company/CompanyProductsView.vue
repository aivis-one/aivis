<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyProductsView (Phase F5.2 B0)
// =============================================================================
//
// "Products" tab inside CompanyShell. Shows the active products of
// the authenticated company on the public storefront (i.e. the way
// investors see them).
//
// SHELL.
//   Top-level tab view. CompanyShell paints the global CHeader and
//   CTabBar -- this view renders only the content column with an
//   inline page-header block. Mirrors MarketView / CompanyDashboardView.
//
// DATA SOURCES.
//   1. companyProfile.loadIfMissing()
//        -> we need profile.id to filter the products endpoint.
//        Cache-first: a previous visit to /company/dashboard or any
//        F5.2 view that needed the profile leaves it loaded; the
//        second call is a no-op.
//   2. productsStore.setCompanyFilter(profile.id)
//        -> kicks fetchFirstPage with company_id locked to the
//        company. The shared products store is the same one
//        MarketView uses; resetAllDataStores() on logout/role-switch
//        already clears it so investor-side state cannot bleed.
//
// READ-ONLY (MVP).
//   Product editing happens via staff endpoints (Sprint 4.1). The
//   company-side UI shows products as the storefront does, and a tap
//   on a card surfaces a toast pointing the user at support. A future
//   F5+ scope can add a CompanyProductDetailView with edit affordances
//   once company-side write endpoints exist; the click handler is the
//   only place to grow.
//
// STORE SHARING NOTE.
//   useProductsStore is a singleton across the app. MarketView (under
//   investor / agent shells) uses it without a company filter; this
//   view uses it with one. Two scenarios to watch:
//     (a) company logs in fresh -> store is empty after the global
//         resetAllDataStores() on _clearSession; setCompanyFilter
//         loads page 1 cleanly.
//     (b) company navigates dashboard -> products on the same session
//         -> store stays in sync because setCompanyFilter normalises
//         and re-fetches whenever the filter value changes.
//   The investor shell never reaches a CompanyShell route (router
//   guard meta.roles=['company']), so a stale investor filter cannot
//   land in this view's first paint.
//
// COMPANY_ID GUARANTEED.
//   The route guard already ensures the user has role=company. The
//   /companies/me endpoint then returns a CompanyResponse for the
//   single CompanyProfile owned by that user. profile.id is the
//   company id we filter on -- we cannot reach this view with no
//   company. The `null` fallback in the computed is type-narrowing
//   only; the inner if-guard inside loadAll() makes the contract
//   explicit at runtime.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import ProductCard from '@/components/shared/ProductCard.vue'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useProductsStore } from '@/stores/products'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const profileStore = useCompanyProfileStore()
const productsStore = useProductsStore()
const { showToast } = useToast()

// storeToRefs keeps hasMore reactive when destructured into the
// composable -- same pattern MarketView uses.
const { hasMore } = storeToRefs(productsStore)

const sentinelRef = ref<HTMLElement | null>(null)

const myCompanyId = computed<string | null>(
  () => profileStore.profile?.id ?? null,
)

// Initial load: empty store and no error yet, profile not yet
// resolved -- show the central spinner. Once profile resolves AND
// the products fetch runs, this flips false.
const initialLoading = computed<boolean>(() => {
  if (productsStore.error || profileStore.error) return false
  if (productsStore.items.length > 0) return false
  return profileStore.profile === null || productsStore.loading
})

const hasError = computed<boolean>(
  () => profileStore.error !== null || productsStore.error !== null,
)

const errorMessage = computed<string>(
  () =>
    productsStore.error
    ?? profileStore.error
    ?? t('comp.products.errorTitle'),
)

const isEmpty = computed<boolean>(
  () =>
    !initialLoading.value
    && !hasError.value
    && productsStore.items.length === 0,
)

useInfiniteScroll(sentinelRef, hasMore, productsStore.loadMore)

/**
 * Resolve company id (cache-first) and pin the products filter to
 * it. The first fetch fires from setCompanyFilter as a side-effect
 * of changing the filter value.
 *
 * Idempotent: calling again is a no-op for the profile (cache hit)
 * and a no-op for the filter (same value short-circuits inside
 * setCompanyFilter). Used by onMounted and the Retry button.
 */
async function loadAll(): Promise<void> {
  await profileStore.loadIfMissing()
  const id = myCompanyId.value
  if (!id) return
  // setCompanyFilter is idempotent on equal value; on first mount
  // this is what triggers fetchFirstPage. On retry it does the
  // same because we explicitly null the filter first to force a
  // re-fetch even when the id is unchanged.
  if (productsStore.companyIdFilter !== id) {
    await productsStore.setCompanyFilter(id)
  } else {
    // Same filter, force a fresh fetch (Retry button path).
    await productsStore.fetchFirstPage()
  }
}

onMounted(() => {
  void loadAll()
})

/**
 * Card tap. MVP: product editing is staff-only, so we acknowledge
 * the tap with a toast pointing the user at support instead of
 * opening a non-existent detail view. ProductCard always emits a
 * click event by contract -- the parent decides what to do with it.
 */
function onCardClick(): void {
  showToast(t('comp.products.editViaSupport'), 'info')
}
</script>

<template>
  <div class="cprods">
    <!-- Header -->
    <div class="cprods__header">
      <h1 class="cprods__title">{{ t('comp.products.title') }}</h1>
      <p class="cprods__subtitle">{{ t('comp.products.subtitle') }}</p>
    </div>

    <!-- Initial load -->
    <div v-if="initialLoading" class="cprods__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="cprods__center">
      <CEmptyState
        :title="t('comp.products.errorTitle')"
        :description="errorMessage"
      />
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('comp.products.errorRetry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <div v-else-if="isEmpty" class="cprods__center">
      <CEmptyState
        :title="t('comp.products.empty.title')"
        :description="t('comp.products.empty.desc')"
      />
    </div>

    <!-- Grid + sentinel -->
    <template v-else>
      <div class="cprods__grid">
        <ProductCard
          v-for="item in productsStore.items"
          :key="item.id"
          :product="item"
          @click="onCardClick"
        />
      </div>
      <div ref="sentinelRef" class="cprods__sentinel">
        <CLoader v-if="productsStore.loading" :size="20" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.cprods { padding: var(--space-4); }

.cprods__header { margin-bottom: var(--space-4); }
.cprods__title {
  font-size: var(--fs-lg); font-weight: 700;
  color: var(--text-primary); margin: 0 0 var(--space-1);
}
.cprods__subtitle {
  font-size: var(--fs-sm); color: var(--text-secondary);
  margin: 0;
}

.cprods__center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: var(--space-4);
  min-height: 240px;
  padding: var(--space-5);
  text-align: center;
}

/* Grid mirrors MarketView -- 1 / 2 / 3 columns by viewport width. */
.cprods__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}
@media (min-width: 520px) {
  .cprods__grid { grid-template-columns: repeat(2, 1fr); }
}
@media (min-width: 900px) {
  .cprods__grid { grid-template-columns: repeat(3, 1fr); }
}

.cprods__sentinel {
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-4);
  min-height: 40px;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.cprods__subtitle { max-width: var(--maxw-prose); }
</style>
