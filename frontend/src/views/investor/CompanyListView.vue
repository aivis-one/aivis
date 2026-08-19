<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyListView (iter 2.5 batch 5, R1 §1.2)
// =============================================================================
//
// Investor "Companies" tab. Top-level entry into the company-overview
// flow; replaces the legacy MarketView root for the Market tab. Shared
// with /agent/companies -- both routes render this component under
// their respective shells.
//
// FEATURES.
//   - Vertical card list (CompanyCard) powered by useCompanyListStore.
//   - Infinite scroll via useInfiniteScroll with the FP-16 retry-storm
//     brake (loadMoreErrored / clearLoadMoreError -> Retry banner).
//   - Loading / error / empty / loadMoreError states, each typed.
//   - Click-through to CompanyOverviewView (role-aware route name).
//
// ROUTING NOTE.
//   Target route names (investor-company-overview / agent-company-
//   overview) land in batch 9. Between batches 5 and 9 the names are
//   unresolved -- router.push will emit a runtime warning and no-op.
//   This is acceptable for the intermediate state; once batch 9 lands,
//   navigation starts working without further edits here.
//
// NO SEARCH AFFORDANCE.
//   The spec calls for a plain list, no search box. If a future
//   iteration adds search, plumb a searchQuery ref + setQuery() action
//   on the store and a CInput in the header; do not touch CompanyCard.
//
// FETCH LIFECYCLE.
//   onMounted always calls fetchFirstPage -- on re-entry from the
//   detail view this refreshes page 1 (a company may have been added
//   while the user was elsewhere). The store's epoch guard handles
//   the race where the user navigates away mid-fetch. clearCurrent is
//   not appropriate on unmount: the list belongs to the tab, not to a
//   single visit, and PortfolioView's TD-style "share between visits"
//   pattern keeps cached data visible on tab re-entry.
//
// FP-16 BRAKE.
//   loadMoreErrored is fed into useInfiniteScroll as the `paused`
//   parameter. When set, the sentinel intersect handler is suppressed
//   and a row-level retry banner appears under the list. The banner's
//   Retry tap calls clearLoadMoreError + loadMore -- the explicit
//   call covers the case where the sentinel is already on-screen.
//   See AIVIS-Frontend.md FP-16.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import CompanyCard from '@/components/shared/CompanyCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import type { PublicCompanyListResponse } from '@/api/types'

type CompanyListItem = PublicCompanyListResponse['items'][number]

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const store = useCompanyListStore()

// storeToRefs keeps refs reactive when destructured for the composable.
const { hasMore, loadMoreErrored } = storeToRefs(store)

const sentinelRef = ref<HTMLElement | null>(null)

// Role-aware target route name -- resolved from the shell tag on the
// current route meta. Batches 5-8 produce a warning when this route
// name is unresolved; batch 9 lands the actual route record.
const overviewRouteName = computed<string>(() =>
  isAgentShell(route) ? 'agent-company-overview' : 'investor-company-overview',
)

// First-load skeleton: nothing in the list, no error, store is
// busy. After the first successful fetch this flips false even if
// items[] turned out empty -- the empty state owns that case.
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

// Wire up infinite scroll with the FP-16 brake.
useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

onMounted(() => {
  // Always refresh page 1 -- a re-entry might see a freshly added
  // company on the platform. The store's epoch guard prevents
  // duplicate writes if the user navigates away mid-fetch.
  void store.fetchFirstPage()
})

function openCompany(company: CompanyListItem): void {
  void safeNavigate(
    router.push({
      name: overviewRouteName.value,
      params: { id: company.id },
    }),
    '[CompanyListView] to company overview',
  )
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
      <h1 class="cl__title">{{ t('inv.companyList.title') }}</h1>
      <p class="cl__subtitle">{{ t('inv.companyList.subtitle') }}</p>
    </header>

    <!-- Initial loading: full-page spinner. Only fires when there are
         no items yet and no error -- a refresh on a non-empty list
         doesn't blank the existing cards. -->
    <div v-if="initialLoading" class="cl__center">
      <CLoader :size="32" />
    </div>

    <!-- First-page error: full-page empty state + Retry. -->
    <div v-else-if="store.errored" class="cl__center">
      <CEmptyState :title="t('inv.companyList.errorTitle')" />
      <CButton variant="primary" @click="retryFirstPage">
        {{ t('inv.companyList.errorRetry') }}
      </CButton>
    </div>

    <!-- Empty (successful but zero companies). -->
    <div v-else-if="isEmpty" class="cl__center">
      <CEmptyState
        :title="t('inv.companyList.empty.title')"
        :description="t('inv.companyList.empty.subtitle')"
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

      <!-- Sentinel sits AFTER the list. The brake (loadMoreErrored)
           lives in the composable's paused param -- when set, the
           IntersectionObserver swallows intersects until Retry. -->
      <div ref="sentinelRef" class="cl__sentinel" />

      <!-- LoadMore error banner: row-level, doesn't displace the
           already-loaded cards. Retry calls clearLoadMoreError + loadMore. -->
      <div v-if="store.loadMoreErrored" class="cl__retry">
        <span class="cl__retry-text">
          {{ t('inv.companyList.errorTitle') }}
        </span>
        <CButton variant="outline" size="sm" @click="retryLoadMore">
          {{ t('inv.companyList.errorRetry') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cl {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}

.cl__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.cl__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.cl__subtitle {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.cl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
}

.cl__grid {
  /* Vertical card list on mobile (one per row), grid on wider screens
     so tablet / desktop don't look painfully sparse. */
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

@media (min-width: 640px) {
  .cl__grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

.cl__sentinel {
  /* Non-zero height so IntersectionObserver has something to detect.
     A 1px sliver is enough -- the rootMargin: '200px 0px' in the
     composable does the heavy lifting. */
  width: 100%;
  height: 1px;
}

.cl__retry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.cl__retry-text {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.cl__subtitle { max-width: var(--maxw-prose); }
</style>
