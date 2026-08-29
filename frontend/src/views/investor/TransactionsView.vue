<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- TransactionsView (Phase F4.3 B3)
// =============================================================================
//
// Investor transaction history screen. Replaces the F2.2 stub.
//
// SHELL.
//   This is a top-level tab view ("Transactions" tab reachable from
//   the investor tab bar). Shell already renders CHeader, so no
//   CHeader here -- just an inline page-header block with title +
//   subtitle, matching MarketView / BalanceView.
//
// CATEGORY TABS.
//   Five chips map directly to backend prefix filters:
//     All          -> null
//     Deposits     -> 'deposit:'
//     Purchases    -> 'purchase:'
//     Installments -> 'installment:'
//     Withdrawals  -> 'withdrawal:'
//   Backend dispatches on trailing ':' and does a startswith match.
//   Horizontal chip row with overflow scroll -- five labels fit on
//   desktop, scroll on narrow mobile. No date/amount filter sheet
//   in F4.3 (explicit scope decision).
//
// LIST.
//   Infinite scroll via useInfiniteScroll on a sentinel div. Data
//   lives in the Pinia store so tab switches restart pagination
//   cleanly via the fetch-epoch guard in the store.
//
// DETAIL SHEET.
//   Tapping a row sets selectedId. The sheet owns its own fetch
//   (it needs details JSONB resolved via GET /transactions/{id});
//   store only hands over the id.
//
// TYPE LABELS.
//   Translated via inv.transactions.type.{full_type}. If a future
//   backend type has no i18n entry, the raw token renders through
//   -- same fallback pattern as BalanceView status/type labels.
//
// AMOUNT COLORING.
//   Positive -> success (credit). Negative -> danger (debit). Plus
//   sign prefixed explicitly for positive so the direction is
//   visible at a glance; minus sign comes from the number itself.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  ArrowDownLeft,
  ArrowUpRight,
  CreditCard,
  Download,
  RefreshCw,
  Repeat,
  ShoppingBag,
} from 'lucide-vue-next'

import { ApiResponseError } from '@/api/client'
import { downloadTransactionsExport } from '@/api/transactions'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import TransactionDetailSheet from '@/components/shared/TransactionDetailSheet.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { useTransactionsStore } from '@/stores/transactions'
import { formatSignedPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { TransactionResponse } from '@/api/types'

const { t } = useI18n()
const store = useTransactionsStore()
const { showToast } = useToast()
// storeToRefs keeps hasMore reactive when destructured -- matches
// MarketView / productsStore pattern. Passing store.hasMore directly
// would unwrap to a plain boolean; wrapping in computed(() => ...)
// works but adds a redundant layer.
// loadMoreErrored is threaded into useInfiniteScroll as the `paused`
// signal so a transient failure on page N does not stampede the
// sentinel into refiring on every scroll oscillation (F4.4 B1-post).
const { hasMore, loadMoreErrored } = storeToRefs(store)

interface Tab {
  key: string
  labelKey: string
  // null = All. Otherwise a trailing-colon prefix passed through to
  // the backend type filter.
  filter: string | null
}

const TABS: readonly Tab[] = [
  { key: 'all', labelKey: 'inv.transactions.tabs.all', filter: null },
  { key: 'deposits', labelKey: 'inv.transactions.tabs.deposits', filter: 'deposit:' },
  { key: 'purchases', labelKey: 'inv.transactions.tabs.purchases', filter: 'purchase:' },
  { key: 'installments', labelKey: 'inv.transactions.tabs.installments', filter: 'installment:' },
  { key: 'withdrawals', labelKey: 'inv.transactions.tabs.withdrawals', filter: 'withdrawal:' },
] as const

const sentinelRef = ref<HTMLElement | null>(null)
const selectedId = ref<string | null>(null)

const hasItems = computed<boolean>(() => store.items.length > 0)

function isTabActive(tab: Tab): boolean {
  return store.typeFilter === tab.filter
}

// Pick an icon per transaction group -- decoded by the first
// segment of the event type. Kept inside the view (not the store)
// because this is presentation-only.
function iconFor(type: string) {
  if (type.startsWith('deposit:')) return ArrowDownLeft
  if (type.startsWith('withdrawal:')) return ArrowUpRight
  if (type.startsWith('purchase:')) return ShoppingBag
  if (type.startsWith('installment:')) return Repeat
  if (type.startsWith('reversal:')) return RefreshCw
  return CreditCard
}

function typeLabel(type: string): string {
  return tOrRaw(t, `inv.transactions.type.${type}`, type)
}

function amountClass(cents: number): string {
  if (cents > 0) return 'tv__amount--credit'
  if (cents < 0) return 'tv__amount--debit'
  return ''
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function openDetail(txn: TransactionResponse): void {
  selectedId.value = txn.id
}

function closeDetail(): void {
  selectedId.value = null
}

function selectTab(tab: Tab): void {
  void store.setTypeFilter(tab.filter)
}

// TASK-39 item 2: statement export. Passes whatever filter the screen
// currently has applied -- today that is only store.typeFilter (the
// active category tab); date/amount ranges are not wired into this
// view yet (see file header CATEGORY TABS note) so they are not
// threaded through here either. Every failure path shows a toast --
// no silent no-op button.
const exporting = ref(false)

async function handleExport(): Promise<void> {
  if (exporting.value) return
  exporting.value = true
  try {
    await downloadTransactionsExport({ type: store.typeFilter ?? undefined })
    showToast(t('inv.transactions.export.success'), 'success')
  } catch (e) {
    if (e instanceof ApiResponseError && e.status === 429) {
      // Rate-limited (backend/app/modules/transactions/router.py --
      // shared default cap, keyed per user). retryAfter is populated
      // from the backend's Retry-After header when parseable.
      const seconds = e.retryAfter
      if (typeof seconds === 'number' && seconds > 0) {
        showToast(t('inv.transactions.export.errorRateLimit', { seconds }), 'warning')
      } else {
        showToast(t('inv.transactions.export.errorRateLimitGeneric'), 'warning')
      }
    } else if (e instanceof ApiResponseError && e.detail) {
      // Covers the row-cap boundary (400 -- backend's message already
      // names the matched count and the cap, see
      // export_transactions_csv()'s docstring) and any other backend-
      // surfaced detail. Same pattern as CompanyAttachmentsView's
      // save/replace error handling.
      showToast(e.detail, 'error')
    } else {
      // ApiNetworkError / ApiTimeoutError / anything else unexpected.
      showToast(t('inv.transactions.export.errorGeneric'), 'error')
    }
  } finally {
    exporting.value = false
  }
}

// Wire up infinite scroll to the store's loadMore. loadMoreErrored
// is the `paused` brake -- see store header for the retry-storm
// rationale. On user Retry below we clear the brake AND call
// loadMore() directly so the attempt feels instant; the composable's
// watcher on paused->false handles the edge case where the sentinel
// is still visible but the caller (e.g. keyboard-only user) did not
// scroll to trigger a fresh intersect.
useInfiniteScroll(sentinelRef, hasMore, store.loadMore, loadMoreErrored)

function retryLoadMore(): void {
  store.clearLoadMoreError()
  void store.loadMore()
}

onMounted(() => {
  // Always refresh on mount -- even a fresh store returns cached
  // state from a previous session. The epoch guard makes this safe
  // if the user navigates away before the fetch resolves.
  void store.fetchFirstPage()
})
</script>

<template>
  <div class="tv">
    <!-- Page header -->
    <div class="tv__header">
      <div class="tv__header-row">
        <div class="tv__header-text">
          <h1 class="tv__title">
            {{ t('inv.transactions.title') }}
          </h1>
          <p class="tv__subtitle">
            {{ t('inv.transactions.subtitle') }}
          </p>
        </div>
        <CButton
          variant="outline"
          size="sm"
          inline
          :loading="exporting"
          @click="handleExport"
        >
          <Download :size="14" />
          {{ t('inv.transactions.export.button') }}
        </CButton>
      </div>
    </div>

    <!-- Category tabs -->
    <div class="tv__tabs" role="tablist">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        class="tv__tab"
        :class="{ 'tv__tab--active': isTabActive(tab) }"
        role="tab"
        :aria-selected="isTabActive(tab)"
        @click="selectTab(tab)"
      >
        {{ t(tab.labelKey) }}
      </button>
    </div>

    <!-- Initial load spinner (no items yet, fetching) -->
    <div v-if="store.loading && !hasItems && !store.errored" class="tv__center">
      <CLoader :size="28" />
    </div>

    <!-- First-page error -->
    <div v-else-if="store.errored && !hasItems" class="tv__center">
      <CEmptyState
        :title="t('inv.transactions.errorTitle')"
        :description="t('inv.transactions.errorDesc')"
      />
      <CButton variant="outline" size="sm" @click="store.fetchFirstPage()">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty state -->
    <div v-else-if="!store.loading && !hasItems" class="tv__center">
      <CEmptyState :title="t('inv.transactions.empty')">
        <template #icon>
          <CreditCard :size="32" />
        </template>
      </CEmptyState>
    </div>

    <!-- List -->
    <ul v-else class="tv__list">
      <li v-for="item in store.items" :key="item.id">
        <button type="button" class="tv__item" @click="openDetail(item)">
          <div class="tv__item-icon">
            <component :is="iconFor(item.type)" :size="16" />
          </div>
          <div class="tv__item-body">
            <div class="tv__item-line">
              <span class="tv__item-type">{{ typeLabel(item.type) }}</span>
              <span class="tv__amount" :class="amountClass(item.amount_cents)">
                {{ formatSignedPrice(item.amount_cents, item.currency) }}
              </span>
            </div>
            <div class="tv__item-line tv__item-line--sub">
              <span class="tv__item-date">{{ formatDate(item.created_at) }}</span>
            </div>
          </div>
        </button>
      </li>
    </ul>

    <!-- Infinite scroll sentinel (only when we already have items) -->
    <div v-if="hasItems" ref="sentinelRef" class="tv__sentinel">
      <CLoader v-if="store.loading" :size="20" />
    </div>

    <!--
      loadMore error banner. Rendered only when page > 1 failed so
      the first-page error state (above) stays the canonical empty-
      list treatment. Tapping Retry clears the pause flag in the
      store and re-fires loadMore explicitly.
    -->
    <div v-if="hasItems && store.loadMoreErrored && !store.loading" class="tv__loadmore-error">
      <span class="tv__loadmore-error-text">
        {{ t('inv.transactions.errorTitle') }}
      </span>
      <CButton variant="outline" size="sm" @click="retryLoadMore">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Detail sheet -->
    <TransactionDetailSheet
      :open="selectedId !== null"
      :transaction-id="selectedId"
      @close="closeDetail"
    />
  </div>
</template>

<style scoped>
.tv {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

/* Page header */
.tv__header {
  padding: var(--space-4) var(--space-4) var(--space-2);
}
.tv__header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}
.tv__header-text {
  min-width: 0;
}
.tv__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.tv__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

/* Tabs row */
.tv__tabs {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4) var(--space-3);
  overflow-x: auto;
  scrollbar-width: none;
}
.tv__tabs::-webkit-scrollbar {
  display: none;
}

.tv__tab {
  position: relative;
  flex-shrink: 0;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;
}

/* A5: the PAINTED box stays this size on purpose -- growing it would move the
   text beside it. The HIT AREA is expanded past it with a centred overlay, the
   pattern CInput.vue established and this codebase already uses ten times.
   max() so an already-large box never shrinks. Added 2026-08-25 after the first
   HIT TEST (elementFromPoint) rather than a bounding-box census: a pseudo-element
   is not in getBoundingClientRect(), so no box-based count here could ever see
   an overlay, and every A5 figure this project published measured the wrong
   quantity. */
.tv__tab::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}
.tv__tab:hover {
  border-color: var(--primary);
  color: var(--text-primary);
}
.tv__tab--active {
  background: var(--primary-subtle);
  border-color: var(--primary);
  color: var(--primary);
}

/* Center block for loading / empty / error */
.tv__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
}

/* List */
.tv__list {
  list-style: none;
  margin: 0;
  padding: 0 var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tv__item {
  appearance: none;
  background: none;
  border: none;
  margin: 0;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: start;
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.tv__item:hover,
.tv__item:focus-visible {
  border-color: var(--primary);
}

/* A7: `outline: none` was removed here. The only indicator this row had was a
   border colour it SHARES with :hover, so keyboard focus looked exactly like
   the mouse passing over it. The global ring now applies. */

.tv__item-icon {
  flex-shrink: 0;
  width: var(--size-lg);
  height: var(--size-lg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.tv__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.tv__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.tv__item-line--sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.tv__item-type {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tv__item-date {
  color: var(--text-tertiary);
}

.tv__amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  white-space: nowrap;
}
.tv__amount--credit {
  color: var(--success);
}
.tv__amount--debit {
  color: var(--danger);
}

.tv__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

/* loadMore error banner -- shown under the sentinel when page > 1
   failed. Retry button resets the store pause flag and re-fires
   loadMore. Matches BalanceView balance-error banner styling for
   consistency across investor lists. */
.tv__loadmore-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: var(--space-3) var(--space-4) 0;
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--danger-subtle);
  color: var(--danger);
  font-size: var(--fs-xs);
}
.tv__loadmore-error-text {
  flex: 1;
  min-width: 0;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.tv__subtitle {
  max-width: var(--maxw-prose);
}
</style>
