<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- NotificationsInboxView (Phase 6, the bell)
// =============================================================================
//
// The screen CHeader's bell opens. ONE file, reused verbatim across
// all four authenticated shells (investor / agent / company / staff)
// via router/index.ts -- the same "shared component lives physically
// under views/investor/, other shells' routes import it directly"
// convention already used for PortfolioView, CompanyListView,
// InvestorEventsView, etc. There is no `views/shared/` directory in
// this codebase and this screen does not start one; see the router
// comments at each `*-notifications` route for the four call sites.
//
// SHELL PATTERN: no CHeader here -- every shell that reaches this
// route already renders one (that IS how this screen was reached).
// CBackLink + inline <h1>, same paradigm as InvestorSupportView (a
// detail screen reached from More AND from the bell, not a bottom
// tab).
//
// CURSOR PAGINATION, NOT PAGE NUMBERS. comms' inbox contract is
// cursor/next_cursor (keyset on sent_at DESC, id DESC -- see
// D:/02_Projects/comms/app/api/inbox.py), not page/per_page. This
// mirrors BalanceView's / AgentBalanceView's epoch-guarded infinite
// scroll (useInfiniteScroll + a stale-fetch epoch + a load-more error
// brake) with the pagination cursor swapped in for a page number --
// forcing a page-number UI onto a cursor API would mean this screen
// inventing an offset the backend cannot answer.
//
// ACTION_DATA IS NOT WIRED TO NAVIGATION (Phase 6 scope). None of the
// 16 comms-side event producers populate it today (see
// notifications/schemas.py's own note), so every item renders as a
// plain title + body row. Tapping a row marks it read; it does not
// navigate anywhere. Wiring `action_data.action` to a route is
// explicitly future work once a producer actually sends one.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell, CheckCheck } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/format'
import type { NotificationItemOut } from '@/api/generated'

const { t, locale } = useI18n()
const router = useRouter()
const store = useNotificationsStore()
// A genuine Ref, not the unwrapped value store.loadMoreError would
// give -- useInfiniteScroll's `paused` param is watch()ed internally
// (composables/usePagination.ts), which needs a real ref/getter
// source, not a primitive pulled off the store proxy.
const { loadMoreError } = storeToRefs(store)

const sentinelRef = ref<HTMLElement | null>(null)

const hasMore = computed(() => store.nextCursor !== null)
const isEmpty = computed(
  () => !store.itemsLoading && !store.itemsError && store.items.length === 0,
)

function isUnread(item: NotificationItemOut): boolean {
  return item.read_at === null
}

function handleRowTap(item: NotificationItemOut): void {
  if (isUnread(item)) {
    void store.markRead(item.id)
  }
}

function handleMarkAll(): void {
  void store.markAllRead()
}

function goBack(): void {
  // Same history-aware pattern as InvestorSupportView / InstallmentView:
  // prefer router.back() so the screen the bell was opened from
  // restores its scroll for free; a deep-linked entry falls back to
  // the current shell's dashboard-ish landing via router history's
  // absence of a `back` state, so this just goes to '/' and lets
  // root.beforeEnter resolve the role home.
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push('/'), '[NotificationsInboxView] back')
}

useInfiniteScroll(sentinelRef, hasMore, () => store.loadMore(), loadMoreError)

onMounted(() => {
  void store.fetchFirstPage()
})
</script>

<template>
  <div class="nib">
    <div class="nib__back-row">
      <CBackLink :label="t('common.back')" @click="goBack" />
    </div>

    <header class="nib__header">
      <div class="nib__header-text">
        <h1 class="nib__title">
          {{ t('inv.notifications.title') }}
        </h1>
        <p class="nib__subtitle">
          {{ t('inv.notifications.subtitle') }}
        </p>
      </div>
      <CButton
        v-if="store.unreadCount > 0"
        variant="outline"
        size="sm"
        inline
        :loading="store.markingAll"
        :disabled="store.markingAll"
        @click="handleMarkAll"
      >
        <CheckCheck :size="16" />
        {{ t('inv.notifications.markAllRead') }}
      </CButton>
    </header>

    <!-- Initial load -->
    <div v-if="store.itemsLoading && store.items.length === 0" class="nib__center">
      <CLoader :size="32" />
    </div>

    <!-- First-page error -->
    <div v-else-if="store.itemsError && store.items.length === 0" class="nib__center">
      <CEmptyState
        :title="t('inv.notifications.errorTitle')"
        :description="t('inv.notifications.errorDesc')"
      />
      <CButton variant="primary" inline @click="store.fetchFirstPage">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <div v-else-if="isEmpty" class="nib__center">
      <CEmptyState :title="t('inv.notifications.empty')">
        <template #icon>
          <Bell :size="32" />
        </template>
      </CEmptyState>
    </div>

    <!-- List -->
    <ul v-else class="nib__list">
      <li
        v-for="item in store.items"
        :key="item.id"
        class="nib__item"
        :class="{
          'nib__item--unread': isUnread(item),
          'nib__item--marking': store.isMarking(item.id),
        }"
        tabindex="0"
        role="button"
        :aria-busy="store.isMarking(item.id)"
        @click="handleRowTap(item)"
        @keydown.enter="handleRowTap(item)"
      >
        <span v-if="isUnread(item)" class="nib__item-dot" aria-hidden="true" />
        <div class="nib__item-body">
          <div class="nib__item-title">
            {{ item.title }}
          </div>
          <p class="nib__item-text">
            {{ item.body }}
          </p>
          <div class="nib__item-date">
            {{ formatDateTime(item.sent_at, locale) }}
          </div>
        </div>
      </li>
    </ul>

    <!-- Infinite scroll sentinel -->
    <div v-if="store.items.length > 0" ref="sentinelRef" class="nib__sentinel">
      <CLoader v-if="store.itemsLoading" :size="20" />
    </div>

    <div
      v-if="store.items.length > 0 && store.loadMoreError && !store.itemsLoading"
      class="nib__loadmore-error"
    >
      <span>{{ t('inv.notifications.loadMoreError') }}</span>
      <CButton variant="outline" size="sm" @click="store.retryLoadMore">
        {{ t('common.retry') }}
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.nib {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: var(--space-5);
}

.nib__back-row {
  display: flex;
}

.nib__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.nib__header-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}
.nib__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.nib__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
  max-width: var(--maxw-prose);
}

.nib__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-md);
  padding: var(--space-6) var(--space-2);
}

.nib__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.nib__item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4) var(--space-3) var(--space-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.nib__item:hover {
  border-color: var(--primary-hover);
}
.nib__item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.nib__item--unread {
  background: var(--primary-subtle);
  border-color: var(--primary-hover);
}
.nib__item--marking {
  /* A tap already sent (store.isMarking) -- visual feedback so a second
     tap on THIS row reads as "already working", and a tap on a
     DIFFERENT row is still free to fire (per-id guard in the store). */
  opacity: 0.6;
  cursor: default;
}

.nib__item-dot {
  position: absolute;
  left: var(--space-2);
  top: var(--space-4);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.nib__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.nib__item-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.nib__item-text {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  overflow-wrap: break-word;
}
.nib__item-date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.nib__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

.nib__loadmore-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  margin-top: var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}
</style>
