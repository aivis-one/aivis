<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- MarketView (Phase F4.1 + F4.1.3 polish)
// =============================================================================
//
// Investor storefront. Shared with /agent/market -- both routes render
// this component under their respective shells.
//
// Features:
//   - Product grid powered by useProductsStore (infinite scroll).
//   - Company filter via CompanyFilterSheet bottom-sheet.
//   - Loading / error / empty (unfiltered) / empty (filtered) states.
//   - Click-through to ProductDetailView (role-aware route name).
//
// F4.1.3 polish:
//   - filterLabel now derives the company name primarily from the
//     denormalised `company_name` on the first product item. This
//     makes deeplinks / restored-state filters display the real
//     name immediately rather than falling back to a generic label.
//     The companies-store cache stays as a secondary fallback for
//     the edge case where the filter yields zero products.
//   - hasMore is pulled via storeToRefs instead of an ad-hoc computed
//     wrapper (Pinia-idiomatic).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { ChevronDown, X } from 'lucide-vue-next'
import { CLoader, CEmptyState, CButton } from '@/components/ui'
import ProductCard from '@/components/shared/ProductCard.vue'
import CompanyFilterSheet from '@/components/shared/CompanyFilterSheet.vue'
import { useProductsStore } from '@/stores/products'
import { useCompaniesStore } from '@/stores/companies'
import { useInfiniteScroll } from '@/composables/usePagination'
import type { PublicProductResponse } from '@/api/types'

const { t } = useI18n()
const router = useRouter()

const productsStore = useProductsStore()
const companiesStore = useCompaniesStore()

// Reactive refs the composable needs. storeToRefs keeps them reactive
// when destructured out of the Pinia store.
const { hasMore } = storeToRefs(productsStore)

// Sentinel element the IntersectionObserver watches.
const sentinelRef = ref<HTMLElement | null>(null)

// Bottom-sheet open state.
const filterOpen = ref(false)

// Chip label resolution order (F4.1.3):
//   1. No filter -> "All companies".
//   2. Filter set + at least one product loaded -> use the denormalised
//      company_name from the first item. This is the fast path for
//      deeplinks / restored state where the filter sheet hasn't been
//      opened yet (so companiesStore.items is empty).
//   3. Filter set + zero products (filtered company has no active
//      products right now) -> try the filter sheet's cached list.
//   4. Still nothing -> generic "Company" fallback for the split
//      second before the first fetch resolves.
const filterLabel = computed<string>(() => {
  if (productsStore.companyIdFilter === null) {
    return t('inv.market.filter.all')
  }
  const firstItem = productsStore.items[0]
  if (firstItem) return firstItem.company_name
  const cached = companiesStore.items.find(
    (c) => c.id === productsStore.companyIdFilter,
  )
  return cached?.name ?? t('inv.market.filter.company')
})

// Wire up infinite scroll.
useInfiniteScroll(sentinelRef, hasMore, productsStore.loadMore)

onMounted(() => {
  // Always refresh page 1 on mount -- avoids stale data from a
  // prior session flashing while the fetch is in flight.
  void productsStore.fetchFirstPage()
})

function openProduct(product: PublicProductResponse): void {
  // Role-aware route name: /investor/products/:id vs /agent/products/:id.
  const currentPath = router.currentRoute.value.path
  const name = currentPath.startsWith('/agent')
    ? 'agent-product-detail'
    : 'investor-product-detail'
  void router.push({ name, params: { id: product.id } })
}

function openFilter(): void {
  filterOpen.value = true
}

function closeFilter(): void {
  filterOpen.value = false
}

function selectCompany(companyId: string | null): void {
  void productsStore.setCompanyFilter(companyId)
}

function clearFilter(): void {
  void productsStore.setCompanyFilter(null)
}
</script>

<template>
  <div class="market">
    <!-- Header -->
    <div class="market__header">
      <h1 class="market__title">{{ t('inv.market.title') }}</h1>
      <p class="market__subtitle">{{ t('inv.market.subtitle') }}</p>
    </div>

    <!-- Filter row -->
    <div class="market__filters">
      <button class="market__chip" @click="openFilter">
        <span class="market__chip-label">{{ filterLabel }}</span>
        <ChevronDown :size="14" />
      </button>
      <button
        v-if="productsStore.companyIdFilter !== null"
        class="market__chip market__chip--clear"
        :aria-label="t('inv.market.filter.clear')"
        @click="clearFilter"
      >
        <X :size="14" />
      </button>
    </div>

    <!-- Grid -->
    <div v-if="productsStore.items.length > 0" class="market__grid">
      <ProductCard
        v-for="item in productsStore.items"
        :key="item.id"
        :product="item"
        @click="openProduct"
      />
    </div>

    <!-- Initial load spinner (no items yet, fetching) -->
    <div
      v-else-if="productsStore.loading"
      class="market__center"
    >
      <CLoader :size="28" />
    </div>

    <!-- Error state -->
    <div
      v-else-if="productsStore.error"
      class="market__center"
    >
      <CEmptyState
        :title="t('common.error')"
        :description="productsStore.error"
      />
      <CButton
        variant="outline"
        size="sm"
        @click="productsStore.fetchFirstPage"
      >
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty (no filter, nothing on the platform yet) -->
    <div
      v-else-if="productsStore.companyIdFilter === null"
      class="market__center"
    >
      <CEmptyState
        :title="t('inv.market.empty.title')"
        :description="t('inv.market.empty.desc')"
      />
    </div>

    <!-- Empty (filtered to a company with no active products) -->
    <div v-else class="market__center">
      <CEmptyState
        :title="t('inv.market.empty.filteredTitle')"
        :description="t('inv.market.empty.filteredDesc')"
      />
      <CButton variant="outline" size="sm" @click="clearFilter">
        {{ t('inv.market.filter.clear') }}
      </CButton>
    </div>

    <!-- Infinite scroll sentinel (only when we already have items) -->
    <div
      v-if="productsStore.items.length > 0"
      ref="sentinelRef"
      class="market__sentinel"
    >
      <CLoader v-if="productsStore.loading" :size="20" />
    </div>

    <!-- Filter bottom sheet -->
    <CompanyFilterSheet
      :open="filterOpen"
      :selected-id="productsStore.companyIdFilter"
      @close="closeFilter"
      @select="selectCompany"
    />
  </div>
</template>

<style scoped>
.market { padding: 16px; }

.market__header { margin-bottom: 16px; }
.market__title {
  font-size: 20px; font-weight: 700;
  color: var(--text); margin: 0 0 4px;
}
.market__subtitle {
  font-size: 14px; color: var(--text-secondary);
  margin: 0;
}

.market__filters {
  display: flex; gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

.market__chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  max-width: 220px;
  font-family: inherit;
  transition: border-color 0.15s;
}
.market__chip:hover { border-color: var(--primary); }

.market__chip-label {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.market__chip--clear {
  padding: 8px 10px;
  color: var(--text-secondary);
  max-width: none;
}

.market__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
@media (min-width: 520px) {
  .market__grid { grid-template-columns: repeat(2, 1fr); }
}
@media (min-width: 900px) {
  .market__grid { grid-template-columns: repeat(3, 1fr); }
}

.market__center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 16px;
  min-height: 240px;
  padding: 24px;
}

.market__sentinel {
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
  min-height: 40px;
}
</style>
