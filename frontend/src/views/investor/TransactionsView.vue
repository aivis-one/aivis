<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- TransactionsView (Phase F4.3 B3)
// =============================================================================
//
// Investor transaction history screen. Replaces the F2.2 stub.
//
// SHELL.
//   This is a top-level tab view ("Transactions" tab reachable from
//   the investor tab bar). The frame's header (K25) holds the title, the
//   line under it and the export action, set here with `useScreenHeader`.
//
// CATEGORY TABS.
//   Four chips map directly to backend prefix filters (an investor has no
//   withdrawals, so no chip for them; they stay in "All"):
//     All          -> null
//     Deposits     -> 'deposit:'
//     Purchases    -> 'purchase:'
//     Installments -> 'installment:'
//   Backend dispatches on trailing ':' and does a startswith match.
//   Horizontal chip row with overflow scroll -- four labels fit on
//   desktop, scroll on narrow mobile. No date/amount filter sheet
//   in F4.3 (explicit scope decision).
//
// LIST.
//   The system's Row list (K23): the lead icon is toned by the direction of the
//   money, the value carries its sign. Infinite scroll via useInfiniteScroll on
//   a sentinel div. Data
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
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { onTablistKeydown } from '@/composables/tablistKeys'
import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowUpRight,
  CreditCard,
  Download,
  RefreshCw,
  Repeat,
  ShoppingBag,
} from '@/components/ui/icons'

import { ApiResponseError } from '@/api/client'
import { downloadTransactionsExport } from '@/api/transactions'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import TransactionDetailSheet from '@/components/shared/TransactionDetailSheet.vue'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { useTransactionsStore } from '@/stores/transactions'
import { formatSignedPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { TransactionResponse } from '@/api/types'

const { t, locale } = useI18n()
// The project account reads its own operations here too: the same list, with
// its own wording (a sale, not a purchase) and its own tabs.
const isCompany = useRoute().meta.shell === 'company'
const store = useTransactionsStore()
const { showToast } = useToast()

useScreenHeader({
  title: () => t(isCompany ? 'comp.operations.title' : 'inv.transactions.title'),
  lead: () => t(isCompany ? 'comp.operations.subtitle' : 'inv.transactions.subtitle'),
  actions: () => [
    {
      id: 'export',
      label: t('inv.transactions.export.button'),
      icon: Download,
      onClick: () => {
        void handleExport()
      },
    },
  ],
})
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

const COMPANY_FILTER_TABS: readonly Tab[] = [
  { key: 'all', labelKey: 'inv.transactions.tabs.all', filter: null },
  { key: 'sales', labelKey: 'comp.operations.tabs.sales', filter: 'purchase:' },
  { key: 'withdrawals', labelKey: 'comp.operations.tabs.withdrawals', filter: 'withdrawal:' },
] as const

const TABS: readonly Tab[] = isCompany
  ? COMPANY_FILTER_TABS
  : ([
      { key: 'all', labelKey: 'inv.transactions.tabs.all', filter: null },
      { key: 'deposits', labelKey: 'inv.transactions.tabs.deposits', filter: 'deposit:' },
      { key: 'purchases', labelKey: 'inv.transactions.tabs.purchases', filter: 'purchase:' },
      {
        key: 'installments',
        labelKey: 'inv.transactions.tabs.installments',
        filter: 'installment:',
      },
    ] as const)

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
  const own = tOrRaw(t, `inv.transactions.type.${type}`, type)
  return isCompany ? tOrRaw(t, `comp.operations.type.${type}`, own) : own
}

function amountClass(cents: number): string {
  if (cents > 0) return 'tv__amount--credit'
  if (cents < 0) return 'tv__amount--debit'
  return ''
}

// The tone of the lead icon says the direction of the money (a second sign: the
// value carries its sign in the text).
function toneFor(cents: number): 'success' | 'danger' | undefined {
  if (cents > 0) return 'success'
  if (cents < 0) return 'danger'
  return undefined
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(locale.value, {
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
    <!-- Category tabs -->
    <div class="ds-tabs" role="tablist" @keydown="onTablistKeydown">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        class="ds-tab"
        role="tab"
        :aria-selected="isTabActive(tab)"
        :tabindex="isTabActive(tab) ? 0 : -1"
        @click="selectTab(tab)"
      >
        {{ t(tab.labelKey) }}
      </button>
    </div>

    <!-- Initial load: the placeholder rows of the list that will arrive (K19) -->
    <section v-if="store.loading && !hasItems && !store.errored" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="ds-rows" aria-hidden="true">
        <div v-for="n in 5" :key="n" class="ds-skeleton-row">
          <span class="ds-skeleton ds-skeleton--avatar" />
          <span class="ds-skeleton-stack">
            <span class="ds-skeleton ds-skeleton--title" />
            <span class="ds-skeleton ds-skeleton--text" />
          </span>
        </div>
      </div>
    </section>

    <!-- First-page error -->
    <CEmptyState
      v-else-if="store.errored && !hasItems"
      tone="danger"
      :title="t('inv.transactions.errorTitle')"
      :description="t('inv.transactions.errorDesc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="store.fetchFirstPage()">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty state -->
    <CEmptyState v-else-if="!store.loading && !hasItems" :title="t('inv.transactions.empty')">
      <template #icon>
        <CreditCard />
      </template>
    </CEmptyState>

    <!-- List: a row opens the detail sheet in place -->
    <ul v-else class="ds-rows">
      <li v-for="item in store.items" :key="item.id" class="ds-row">
        <span class="ds-row__lead" :data-tone="toneFor(item.amount_cents)">
          <component :is="iconFor(item.type)" size="sm" />
        </span>
        <span class="ds-row__body">
          <a
            class="ds-row__link"
            href="#"
            role="button"
            @click.prevent="openDetail(item)"
            @keydown.space.prevent="openDetail(item)"
          >
            <span class="ds-row__title">{{ typeLabel(item.type) }}</span>
          </a>
          <span class="ds-row__meta">{{ formatDate(item.created_at) }}</span>
        </span>
        <span class="ds-row__trail">
          <span class="ds-row__value" :class="amountClass(item.amount_cents)">
            {{ formatSignedPrice(item.amount_cents, item.currency) }}
          </span>
        </span>
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
    <div
      v-if="hasItems && store.loadMoreErrored && !store.loading"
      class="ds-alert ds-alert--danger"
      role="alert"
    >
      <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">{{ t('inv.transactions.errorTitle') }}</p>
        <div class="ds-alert__actions">
          <CButton variant="outline" size="sm" inline @click="retryLoadMore">
            {{ t('common.retry') }}
          </CButton>
        </div>
      </div>
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
  gap: var(--space-3);
}

/* The sign of the money on the value (K23: credit --success, debit --danger). */
.tv__amount--credit {
  color: var(--success);
}
.tv__amount--debit {
  color: var(--danger);
}

.tv__sentinel {
  display: flex;
  justify-content: center;
  min-block-size: var(--size-md);
}
</style>
