<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- NotificationsInboxView (Phase 6, the bell)
// =============================================================================
//
// The screen the header's bell opens. ONE file, reused verbatim across
// all four authenticated shells (investor / agent / company / staff)
// via router/index.ts -- the same "shared component lives physically
// under views/investor/, other shells' routes import it directly"
// convention already used for PortfolioView, CompanyListView,
// InvestorEventsView, etc. There is no `views/shared/` directory in
// this codebase and this screen does not start one; see the router
// comments at each `*-notifications` route for the four call sites.
//
// FRAME: the title, the line under it, the back control and the "mark all
// read" action are the frame's header (K25, `useScreenHeader`); the list is the
// system's Row list (K23).
//
// CURSOR PAGINATION, NOT PAGE NUMBERS. comms' inbox contract is
// cursor/next_cursor (keyset on sent_at DESC, id DESC -- see
// the comms service's inbox API), not page/per_page. This
// mirrors BalanceView's / AgentBalanceView's epoch-guarded infinite
// scroll (useInfiniteScroll + a stale-fetch epoch + a load-more error
// brake) with the pagination cursor swapped in for a page number --
// forcing a page-number UI onto a cursor API would mean this screen
// inventing an offset the backend cannot answer.
//
// WHERE A TAP LEADS. Tapping a row marks it read and opens the screen of its
// own event. None of the comms-side event producers populates `action_data`
// today (see notifications/schemas.py's own note), so the screen is chosen
// from the notification's type (utils/notificationTarget.ts); an `action_data`
// that names a post or an event wins when comms sends one. A row whose type has
// no screen of its own is only marked read by its tap (its title is the row's
// button form while it is unread, a plain title once read).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, Bell, CheckCheck } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader, CListSkeleton } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useNotificationsStore } from '@/stores/notifications'
import { useAuthStore } from '@/stores/auth'
import { notificationTarget } from '@/utils/notificationTarget'
import { formatDateTime } from '@/utils/format'
import type { NotificationItemOut } from '@/api/generated'

const { t, locale } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const store = useNotificationsStore()
// A genuine Ref, not the unwrapped value store.loadMoreError would
// give -- useInfiniteScroll's `paused` param is watch()ed internally
// (composables/usePagination.ts), which needs a real ref/getter
// source, not a primitive pulled off the store proxy.
const { loadMoreError } = storeToRefs(store)

const sentinelRef = ref<HTMLElement | null>(null)

const hasMore = computed(() => store.nextCursor !== null)
const isEmpty = computed(() => !store.itemsLoading && !store.itemsError && store.items.length === 0)

function isUnread(item: NotificationItemOut): boolean {
  return item.read_at === null
}

// The screen of the row's own event, or null for a type with no screen of its own.
function targetOf(item: NotificationItemOut) {
  return notificationTarget({
    type: item.type,
    actionData: item.action_data,
    kycStatus: authStore.kycStatus,
    shell: route.meta.shell as string | undefined,
  })
}

// A tap marks the row read; a link then opens the screen of its own event.
function markRead(item: NotificationItemOut): void {
  if (isUnread(item)) {
    void store.markRead(item.id)
  }
}

function handleMarkAll(): void {
  if (store.markingAll) return
  void store.markAllRead()
}

// Back: one step back (the screen the bell was opened from restores its scroll
// for free); a deep-linked entry goes to '/' and lets root.beforeEnter resolve
// the role home.
useScreenHeader({
  title: () => t('inv.notifications.title'),
  lead: () => t('inv.notifications.subtitle'),
  back: () => (window.history.state?.back ? true : '/'),
  actions: () =>
    store.unreadCount > 0
      ? [
          {
            id: 'mark-all-read',
            label: t('inv.notifications.markAllRead'),
            icon: CheckCheck,
            onClick: handleMarkAll,
          },
        ]
      : [],
})

useInfiniteScroll(sentinelRef, hasMore, () => store.loadMore(), loadMoreError)

onMounted(() => {
  void store.fetchFirstPage()
})
</script>

<template>
  <div class="nib">
    <!-- Initial load: the placeholder rows of the list that will arrive (K19) -->
    <CListSkeleton v-if="store.itemsLoading && store.items.length === 0" :rows="4" />

    <!-- First-page error -->
    <CEmptyState
      v-else-if="store.itemsError && store.items.length === 0"
      tone="danger"
      :title="t('inv.notifications.errorTitle')"
      :description="t('inv.notifications.errorDesc')"
    >
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="store.fetchFirstPage">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="isEmpty" :title="t('inv.notifications.empty')">
      <template #icon>
        <Bell />
      </template>
    </CEmptyState>

    <!-- List -->
    <ul v-else class="ds-rows">
      <li
        v-for="item in store.items"
        :key="item.id"
        class="ds-row"
        :aria-busy="store.isMarking(item.id)"
      >
        <span class="ds-row__body">
          <RouterLink
            v-if="targetOf(item)"
            class="ds-row__link"
            :to="targetOf(item)!"
            @click="markRead(item)"
          >
            <span class="ds-row__title">{{ item.title }}</span>
          </RouterLink>
          <button
            v-else-if="isUnread(item)"
            type="button"
            class="ds-row__link"
            @click="markRead(item)"
          >
            <span class="ds-row__title">{{ item.title }}</span>
          </button>
          <span v-else class="ds-row__title">{{ item.title }}</span>
          <span class="ds-row__meta">{{ item.body }}</span>
          <span class="ds-row__meta">{{ formatDateTime(item.sent_at, locale) }}</span>
        </span>
        <span v-if="isUnread(item)" class="ds-row__trail">
          <span class="ds-dot" role="img" :aria-label="t('inv.notifications.unread')" />
        </span>
      </li>
    </ul>

    <!-- Infinite scroll sentinel -->
    <div v-if="store.items.length > 0" ref="sentinelRef" class="nib__sentinel">
      <CLoader v-if="store.itemsLoading" :size="20" />
    </div>

    <div
      v-if="store.items.length > 0 && store.loadMoreError && !store.itemsLoading"
      class="ds-alert ds-alert--danger"
      role="alert"
    >
      <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ t('inv.notifications.loadMoreError') }}</p>
        <div class="ds-alert__actions">
          <CButton variant="outline" size="sm" inline @click="store.retryLoadMore">
            {{ t('common.retry') }}
          </CButton>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nib {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.nib__sentinel {
  display: flex;
  justify-content: center;
  min-block-size: var(--size-md);
}
</style>
