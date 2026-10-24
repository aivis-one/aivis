<script setup lang="ts">
import { AlertTriangle, Check } from '@/components/ui/icons'
// =============================================================================
// AIVIS.ONE Frontend -- InvestorEventsView (iter 2.7b C, R1 §6.3)
// =============================================================================
//
// Full events screen. Mounted under BOTH shells via parallel route
// records (investor-events / agent-events) -- same view, agent layout,
// exactly like CompanyListView. The screen itself never navigates to a
// child route (an event has no detail page in the MVP; the only
// outbound link is the external url handled inside EventCard via a
// plain <a>), so there is NO isAgentShell route-name resolution here --
// nothing to resolve.
//
// STATE: LOCAL, NOT A STORE.
//   Per the 2.7b decision, this list keeps its pagination in local
//   refs rather than a Pinia store. Events are not a frequently
//   re-entered surface, so cross-navigation cache is not worth a
//   store clone of useCompanyListStore. useInfiniteScroll takes plain
//   refs, so the FP-16 retry-storm brake (loadMoreErrored as the
//   `paused` arg) works the same as the store-backed lists.
//
// EPOCH GUARD.
//   Switching the upcoming/past filter resets to page 1 and refetches.
//   A local epoch counter (bumped on every first-page load) tags each
//   in-flight request; a response from a superseded epoch is dropped,
//   so a slow page-1 fetch from the previous filter cannot overwrite
//   the new filter's list. Same idea as the store's epoch guard, kept
//   in a closure here.
//
// STATES (mirrors CompanyListView): initial-loading skeleton /
//   first-page error + retry / empty / list + sentinel + load-more
//   error banner. The title is the frame's header (K25).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import EventCard from '@/components/shared/EventCard.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { listPublicEvents } from '@/api/events'
import type { EventResponse } from '@/api/types'

const { t } = useI18n()

useScreenHeader({ title: () => t('inv.events.title') })

const PER_PAGE = 20

type Filter = 'upcoming' | 'past'

const filter = ref<Filter>('upcoming')

const items = ref<EventResponse[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const errored = ref(false)
const loadMoreErrored = ref(false)

const sentinelRef = ref<HTMLElement | null>(null)

// Epoch guard: every first-page load bumps this; a response whose
// epoch no longer matches is discarded (stale filter / unmount race).
let epoch = 0

const hasMore = computed<boolean>(() => items.value.length < total.value)

const initialLoading = computed<boolean>(
  () => loading.value && items.value.length === 0 && !errored.value,
)

const isEmpty = computed<boolean>(
  () => !initialLoading.value && !errored.value && items.value.length === 0,
)

async function loadFirstPage(): Promise<void> {
  const myEpoch = ++epoch
  loading.value = true
  errored.value = false
  loadMoreErrored.value = false
  page.value = 1
  try {
    const resp = await listPublicEvents({
      upcoming: filter.value === 'upcoming',
      page: 1,
      per_page: PER_PAGE,
    })
    if (myEpoch !== epoch) return // superseded by a newer load
    items.value = resp.items
    total.value = resp.total
  } catch {
    if (myEpoch !== epoch) return
    errored.value = true
  } finally {
    if (myEpoch === epoch) loading.value = false
  }
}

async function loadMore(): Promise<void> {
  // Guarded against re-entry by the loading flag; the sentinel can fire
  // repeatedly while a page is in flight.
  if (loading.value || !hasMore.value) return
  const myEpoch = epoch
  const next = page.value + 1
  loading.value = true
  try {
    const resp = await listPublicEvents({
      upcoming: filter.value === 'upcoming',
      page: next,
      per_page: PER_PAGE,
    })
    if (myEpoch !== epoch) return // filter changed mid-fetch
    items.value = [...items.value, ...resp.items]
    total.value = resp.total
    page.value = next
  } catch {
    if (myEpoch !== epoch) return
    // FP-16 brake: stop the observer from stampeding until Retry.
    loadMoreErrored.value = true
  } finally {
    if (myEpoch === epoch) loading.value = false
  }
}

// FP-16: pass loadMoreErrored as the pause arg so a failed page
// suppresses further auto-fetches until the user taps Retry.
useInfiniteScroll(sentinelRef, hasMore, loadMore, loadMoreErrored)

function setFilter(next: Filter): void {
  if (filter.value === next) return
  filter.value = next
  void loadFirstPage()
}

function retryFirstPage(): void {
  void loadFirstPage()
}

function retryLoadMore(): void {
  loadMoreErrored.value = false
  void loadMore()
}

onMounted(() => {
  void loadFirstPage()
})
</script>

<template>
  <div class="iev">
    <!-- Filter chips: upcoming / past (K13) -->
    <div class="ds-chip-row" role="group" :aria-label="t('inv.events.title')">
      <button
        type="button"
        class="ds-chip"
        :aria-pressed="filter === 'upcoming'"
        @click="setFilter('upcoming')"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ t('inv.events.filter.upcoming') }}</span>
      </button>
      <button
        type="button"
        class="ds-chip"
        :aria-pressed="filter === 'past'"
        @click="setFilter('past')"
      >
        <Check class="ds-chip__check" size="sm" />
        <span>{{ t('inv.events.filter.past') }}</span>
      </button>
    </div>

    <!-- Initial loading: the placeholder cards of the list that will arrive (K19) -->
    <section v-if="initialLoading" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="iev__list" aria-hidden="true">
        <div v-for="n in 3" :key="n" class="ds-skeleton ds-skeleton--block" />
      </div>
    </section>

    <!-- First-page error + retry -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.events.errorTitle')">
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="retryFirstPage">
          {{ t('inv.events.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty (minimal fallback per R1 §6.3) -->
    <CEmptyState v-else-if="isEmpty" :title="t('inv.events.empty')" />

    <!-- List + sentinel + load-more error banner -->
    <template v-else>
      <div class="iev__list">
        <EventCard v-for="event in items" :key="event.id" :event="event" variant="full" />
      </div>

      <div ref="sentinelRef" class="iev__sentinel" />

      <div v-if="loadMoreErrored" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ t('inv.events.errorTitle') }}</p>
          <div class="ds-alert__actions">
            <CButton variant="outline" size="sm" inline @click="retryLoadMore">
              {{ t('inv.events.errorRetry') }}
            </CButton>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.iev {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.iev__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
/* The sentinel the infinite scroll watches: the thinnest box the system names. */
.iev__sentinel {
  block-size: var(--border-input-width);
}
</style>
