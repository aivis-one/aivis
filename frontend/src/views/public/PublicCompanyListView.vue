<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicCompanyListView (iter 2.6 batch 3, R1 §1.6.1)
// =============================================================================
//
// Anonymous storefront catalogue. Public counterpart to
// /investor/companies + /agent/companies. Same store, same card, same
// infinite-scroll mechanics; the differences are tiny and live in
// this file:
//
//   - Click target is `public-company-overview` (anonymous detail
//     page) instead of the role-aware investor-/agent- variant.
//   - i18n strings come from the `public.companyList.*` block so
//     marketing copy ("Discover companies on AIVIS.ONE ...") can
//     differ from the investor-side strings ("Companies you can
//     buy from", etc.) without coupling.
//   - The header CTA inside PublicShell ("Sign in") covers the
//     "what do I do as a visitor" UX; this view is free of any
//     in-page auth nudges.
//
// STORE REUSE.
//   `useCompanyListStore` already hits `/api/v1/public/companies`
//   (see api/companies.ts + stores/companyList.ts). For an anonymous
//   visitor `api/client.ts::request()` simply omits the Bearer header
//   (no token in memory); the backend public endpoint accepts the
//   request unchanged. No anonymous-specific store is needed -- the
//   investor-side store IS the public storefront store.
//
// CACHE BEHAVIOUR ACROSS VIEW SWAPS.
//   The store keeps its items across this view's unmount + remount
//   (same pattern as the investor side). A visitor who taps into a
//   company overview and back keeps the same scroll-position list
//   without a flash of skeleton. fetchFirstPage on mount refreshes
//   page 1, so newly added companies appear; the epoch guard handles
//   the race where the user navigates away mid-fetch.
//
// FP-16 BRAKE.
//   loadMoreErrored is fed into useInfiniteScroll as the `paused`
//   parameter. When set, the sentinel intersect handler is suppressed
//   and a row-level retry banner appears under the list. Retry tap
//   calls clearLoadMoreError + loadMore -- the explicit call covers
//   the case where the sentinel is already on-screen. See
//   AIVIS-Frontend.md FP-16.
//
// NO HEADER OF ITS OWN.
//   The frame carries the only header for the page; the view hands it the
//   title and the line under it through useScreenHeader.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { AlertTriangle } from '@/components/ui/icons'
import { CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CompanyCard from '@/components/shared/CompanyCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useInfiniteScroll } from '@/composables/usePagination'

const { t } = useI18n()

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('public.companyList.title'),
  lead: () => t('public.companyList.subtitle'),
})

const store = useCompanyListStore()
const { hasMore, loadMoreErrored } = storeToRefs(store)

const sentinelRef = ref<HTMLElement | null>(null)

const initialLoading = computed<boolean>(
  () => store.loading && store.items.length === 0 && !store.errored,
)

const hasItems = computed<boolean>(() => store.items.length > 0)

const isEmpty = computed<boolean>(() => !initialLoading.value && !store.errored && !hasItems.value)

useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

onMounted(() => {
  void store.fetchFirstPage()
})

async function retryFirstPage(): Promise<void> {
  await store.fetchFirstPage()
}

async function retryLoadMore(): Promise<void> {
  // Clear the brake, then trigger an immediate fetch -- the composable's
  // pause-watcher will also fire if the sentinel is on-screen, but the
  // store's loading guard collapses the duplicate.
  store.clearLoadMoreError()
  await store.loadMore()
}
</script>

<template>
  <div class="cl">
    <!-- Initial loading: a placeholder grid of cards (K19). Only fires when there
         are no items yet and no error -- a refresh on a non-empty list doesn't
         blank the existing cards. -->
    <div v-if="initialLoading" class="cl__grid" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div v-for="n in 3" :key="n" class="ds-card ds-card--media" aria-hidden="true">
        <span class="ds-skeleton ds-skeleton--block" />
        <div class="ds-card__content">
          <span class="ds-skeleton-stack">
            <span class="ds-skeleton ds-skeleton--title" />
            <span class="ds-skeleton ds-skeleton--text" />
          </span>
        </div>
      </div>
    </div>

    <!-- First-page error: the empty state with Retry. -->
    <CEmptyState
      v-else-if="store.errored"
      tone="danger"
      :title="t('public.companyList.errorTitle')"
    >
      <template #actions>
        <CButton variant="primary" inline @click="retryFirstPage">
          {{ t('public.companyList.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty (successful but zero companies). -->
    <CEmptyState
      v-else-if="isEmpty"
      :title="t('public.companyList.empty.title')"
      :description="t('public.companyList.empty.subtitle')"
    />

    <!-- List + sentinel + load-more error banner. -->
    <template v-else>
      <div class="cl__grid">
        <CompanyCard
          v-for="company in store.items"
          :key="company.id"
          :company="company"
          :to="{ name: 'public-company-overview', params: { id: company.id } }"
        />
      </div>

      <div ref="sentinelRef" class="cl__sentinel" />

      <div v-if="store.loadMoreErrored" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ t('public.companyList.errorTitle') }}</p>
          <div class="ds-alert__actions">
            <CButton variant="outline" size="sm" inline @click="retryLoadMore">
              {{ t('public.companyList.errorRetry') }}
            </CButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* The frame's main pads the screen; this column lays its parts out with the same gap. */
.cl {
  display: grid;
  gap: var(--space-5);
}

.cl__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

@media (min-width: 640px) {
  .cl__grid {
    grid-template-columns: repeat(auto-fill, minmax(var(--tile-max), 1fr));
  }
}

/* The scroll observer's mark: it needs a height to be seen entering the view. */
.cl__sentinel {
  inline-size: 100%;
  block-size: var(--space-1);
}
</style>
