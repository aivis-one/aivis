<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PublicCompanyListView (iter 2.6 batch 3, R1 §1.6.1)
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
//     marketing copy ("Discover companies on CBS HOME ...") can
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
//   CBSHOME-Frontend.md FP-16.
//
// NO HEADER COMPONENT.
//   The shell carries the only <CHeader> for the page. The view's
//   title / subtitle live below as ordinary <h1> / <p>, scrolling
//   away with the content (same pattern as the investor-side
//   CompanyListView -- its .cl__title / .cl__subtitle are inline, not
//   stuck to the top).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import CompanyCard from '@/components/shared/CompanyCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useInfiniteScroll } from '@/composables/usePagination'
import type { PublicCompanyListResponse } from '@/api/types'

type CompanyListItem = PublicCompanyListResponse['items'][number]

const { t } = useI18n()
const router = useRouter()

const store = useCompanyListStore()
const { hasMore, loadMoreErrored } = storeToRefs(store)

const sentinelRef = ref<HTMLElement | null>(null)

const initialLoading = computed<boolean>(
  () => store.loading && store.items.length === 0 && !store.errored,
)

const hasItems = computed<boolean>(() => store.items.length > 0)

const isEmpty = computed<boolean>(
  () =>
    !initialLoading.value
    && !store.errored
    && !hasItems.value,
)

useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

onMounted(() => {
  void store.fetchFirstPage()
})

function openCompany(company: CompanyListItem): void {
  router
    .push({
      name: 'public-company-overview',
      params: { id: company.id },
    })
    .catch((err: unknown) => {
      // Benign vue-router rejection types stay silent (see
      // useAuthWall R20 STYLE-20-01 for the rationale). Real
      // navigation issues log with a contextual prefix.
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error('[PublicCompanyListView] navigation to company failed:', err)
    })
}

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
    <header class="cl__header">
      <h1 class="cl__title">{{ t('public.companyList.title') }}</h1>
      <p class="cl__subtitle">{{ t('public.companyList.subtitle') }}</p>
    </header>

    <!-- Initial loading: full-page spinner. Only fires when there are
         no items yet and no error -- a refresh on a non-empty list
         doesn't blank the existing cards. -->
    <div v-if="initialLoading" class="cl__center">
      <CLoader :size="32" />
    </div>

    <!-- First-page error: full-page empty state + Retry. -->
    <div v-else-if="store.errored" class="cl__center">
      <CEmptyState :title="t('public.companyList.errorTitle')" />
      <CButton variant="primary" @click="retryFirstPage">
        {{ t('public.companyList.errorRetry') }}
      </CButton>
    </div>

    <!-- Empty (successful but zero companies). -->
    <div v-else-if="isEmpty" class="cl__center">
      <CEmptyState
        :title="t('public.companyList.empty.title')"
        :description="t('public.companyList.empty.subtitle')"
      />
    </div>

    <!-- List + sentinel + load-more error banner. -->
    <template v-else>
      <div class="cl__grid">
        <CompanyCard
          v-for="company in store.items"
          :key="company.id"
          :company="company"
          @click="openCompany"
        />
      </div>

      <div ref="sentinelRef" class="cl__sentinel" />

      <div v-if="store.loadMoreErrored" class="cl__retry">
        <span class="cl__retry-text">
          {{ t('public.companyList.errorTitle') }}
        </span>
        <CButton variant="outline" size="sm" @click="retryLoadMore">
          {{ t('public.companyList.errorRetry') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cl {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
}

.cl__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.cl__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
}

.cl__subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.cl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  min-height: 240px;
}

.cl__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-md);
}

@media (min-width: 640px) {
  .cl__grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

.cl__sentinel {
  width: 100%;
  height: 1px;
}

.cl__retry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: var(--space-md);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.cl__retry-text {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
