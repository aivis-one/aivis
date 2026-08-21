<script setup lang="ts">
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
// STATES (mirrors CompanyListView): initial-loading spinner /
//   first-page error + retry / empty / list + sentinel + load-more
//   error banner. No <CHeader> -- the shell renders it (FP-19); the
//   page title is an inline <h1>.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import EventCard from '@/components/shared/EventCard.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { listPublicEvents } from '@/api/events'
import type { EventResponse } from '@/api/types'

const { t } = useI18n()

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
    <header class="iev__header">
      <h1 class="iev__title">{{ t('inv.events.title') }}</h1>
    </header>

    <!-- Filter chips: upcoming / past -->
    <div class="iev__filters">
      <button
        type="button"
        class="filter-chip"
        :class="{ active: filter === 'upcoming' }"
        @click="setFilter('upcoming')"
      >{{ t('inv.events.filter.upcoming') }}</button>
      <button
        type="button"
        class="filter-chip"
        :class="{ active: filter === 'past' }"
        @click="setFilter('past')"
      >{{ t('inv.events.filter.past') }}</button>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="iev__center">
      <CLoader :size="32" />
    </div>

    <!-- First-page error + retry -->
    <div v-else-if="errored" class="iev__center">
      <CEmptyState :title="t('inv.events.errorTitle')" />
      <CButton variant="primary" @click="retryFirstPage">
        {{ t('inv.events.errorRetry') }}
      </CButton>
    </div>

    <!-- Empty (minimal fallback per R1 §6.3) -->
    <div v-else-if="isEmpty" class="iev__center">
      <CEmptyState :title="t('inv.events.empty')" />
    </div>

    <!-- List + sentinel + load-more error banner -->
    <template v-else>
      <div class="iev__list">
        <EventCard
          v-for="event in items"
          :key="event.id"
          :event="event"
          variant="full"
        />
      </div>

      <div ref="sentinelRef" class="iev__sentinel" />

      <div v-if="loadMoreErrored" class="iev__retry">
        <span class="iev__retry-text">{{ t('inv.events.errorTitle') }}</span>
        <CButton variant="outline" size="sm" @click="retryLoadMore">
          {{ t('inv.events.errorRetry') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.iev {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}
.iev__header { display: flex; flex-direction: column; gap: var(--space-1); }
.iev__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.iev__filters { display: flex; gap: var(--space-2); }
.iev__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-md);
  padding: var(--space-5) var(--space-2);
}
.iev__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.iev__sentinel { height: 1px; }
.iev__retry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
}
.iev__retry-text { font-size: var(--fs-sm); color: var(--text-secondary); }

/* Filter chip -- same pattern as EventEditor / TemplatesSection. */
.filter-chip {
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}
.filter-chip.active {
  border-color: var(--accent);
  /* A6: --accent (#B1581B) as TEXT on --bg-subtle (#EDF1F5) measures 4.32.
     It passes on --bg-page (4.61) and fails on the card it is actually drawn
     on. --accent-hover is the darker amber that already exists and measures
     5.77 there, so the chip keeps its amber identity and no new value enters
     the ramp. The border stays --accent -- a border carries no text.
     This is the only one of six .filter-chip.active rules that colours text
     with --accent; the other five use --primary with --on-primary. */
  color: var(--accent-hover);
  background: var(--bg-subtle);
}
</style>
