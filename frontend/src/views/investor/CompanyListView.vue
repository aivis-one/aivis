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

import { CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CompanyCard from '@/components/shared/CompanyCard.vue'
import { useCompanyListStore } from '@/stores/companyList'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { isAgentShell } from '@/router/helpers'
import { useAgentLink } from '@/composables/useAgentLink'
import { useAgentStore } from '@/stores/agent'
import { AlertTriangle, Link2 } from '@/components/ui/icons'
import type { PublicCompanyListResponse } from '@/api/types'

type CompanyListItem = PublicCompanyListResponse['items'][number]

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

useScreenHeader({
  title: () => t('inv.companyList.title'),
  lead: () => t('inv.companyList.subtitle'),
})

const store = useCompanyListStore()

// An integrator takes the link to a project here, at the project itself: their
// one code plus the project's address.
const agentShell = computed<boolean>(() => isAgentShell(route))
const agentStore = useAgentStore()
const { link: agentLink, copy: copyLink } = useAgentLink()

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

const isEmpty = computed<boolean>(() => !initialLoading.value && !store.errored && !hasItems.value)

// Wire up infinite scroll with the FP-16 brake.
useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

onMounted(() => {
  // Always refresh page 1 -- a re-entry might see a freshly added
  // company on the platform. The store's epoch guard prevents
  // duplicate writes if the user navigates away mid-fetch.
  void store.fetchFirstPage()
  if (agentShell.value && agentStore.myLink === null) void agentStore.fetchLinksFirstPage()
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
    <!-- Initial loading: the placeholder cards of the list that will arrive (K19).
         Only fires when there are no items yet and no error -- a refresh on a
         non-empty list doesn't blank the existing cards. -->
    <section v-if="initialLoading" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="cl__grid" aria-hidden="true">
        <div v-for="n in 3" :key="n" class="ds-skeleton ds-skeleton--block" />
      </div>
    </section>

    <!-- First-page error: full-page empty state + Retry. -->
    <CEmptyState v-else-if="store.errored" tone="danger" :title="t('inv.companyList.errorTitle')">
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="retryFirstPage">
          {{ t('inv.companyList.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty (successful but zero companies). -->
    <CEmptyState
      v-else-if="isEmpty"
      :title="t('inv.companyList.empty.title')"
      :description="t('inv.companyList.empty.subtitle')"
    />

    <!-- List + sentinel + load-more error banner. -->
    <template v-else>
      <div class="cl__grid">
        <div v-for="company in store.items" :key="company.id" class="cl__item">
          <CompanyCard :company="company" @click="openCompany" />
          <button
            v-if="agentShell && agentLink"
            type="button"
            class="ds-button ds-button--ghost"
            data-size="sm"
            @click="copyLink(company.id)"
          >
            <Link2 size="sm" />
            <span>{{ t('agent.link.copyProject') }}</span>
          </button>
        </div>
      </div>

      <!-- Sentinel sits AFTER the list. The brake (loadMoreErrored)
           lives in the composable's paused param -- when set, the
           IntersectionObserver swallows intersects until Retry. -->
      <div ref="sentinelRef" class="cl__sentinel" />

      <!-- LoadMore error banner: row-level, doesn't displace the
           already-loaded cards. Retry calls clearLoadMoreError + loadMore. -->
      <div v-if="store.loadMoreErrored" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ t('inv.companyList.errorTitle') }}</p>
          <div class="ds-alert__actions">
            <CButton variant="outline" size="sm" inline @click="retryLoadMore">
              {{ t('inv.companyList.errorRetry') }}
            </CButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cl {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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
    grid-template-columns: repeat(auto-fill, minmax(var(--tile-max), 1fr));
  }
}

.cl__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cl__item > .ds-button {
  align-self: flex-start;
}

.cl__sentinel {
  /* Non-zero height so IntersectionObserver has something to detect.
     The thinnest box the system names is enough -- the root margin
     in the composable does the heavy lifting. */
  inline-size: 100%;
  block-size: var(--border-input-width);
}
</style>
