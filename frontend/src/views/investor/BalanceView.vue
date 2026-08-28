<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- BalanceView (Phase F4.3 B2 + F4.4 B2 store rename)
// =============================================================================
//
// Investor balance screen. Shows the active ledger balance and a
// paginated payment-history feed. The "Deposit" CTA pushes to the
// dedicated /investor/balance/deposit screen (InvestorDepositView).
//
// State split:
//   - balance figures live in the Pinia `dashboard` store, sourced
//     from GET /api/v1/dashboard/summary. The store exposes the
//     full DashboardSummaryResponse and is shared with the F4.4
//     InvestorDashboardView / PurchaseView / InstallmentView, so
//     balance never desyncs across views in one session. This view
//     only reads `activeBalance` (a computed getter over
//     `summary?.active_balance`) -- the portfolio aggregate fields
//     are ignored here.
//   - payment history lives in a local ref on this view. There is
//     no reuse across screens, no filters, and the list is only
//     consumed by this component -- a dedicated Pinia store would
//     be ceremony without upside.
//
// Pagination:
//   Infinite scroll via useInfiniteScroll on a sentinel div. Uses
//   the same stale-epoch guard pattern as stores/products.ts: a
//   counter bumped on every network-touching path so resolves from
//   older fetches can't overwrite newer state.
//
// Formatting:
//   - formatPrice with `undefined` currency -- BalanceResponse and
//     PaymentResponse both lack the field on the backend (TD-F08a).
//     formatPrice falls back to USD, which is correct for today's
//     single-currency platform.
//
// Error strategy:
//   Balance card errors surface inline with a retry button.
//   Payment history errors surface inline under the balance card.
//   No toasts -- this is a passive read-only screen, a toast would
//   vanish before the user notices it on mount.
//
// WITHDRAWALS (added -- closes the "investor passive earnings have no
// way out" gap; backend POST/GET /api/v1/withdrawals was already
// role-agnostic, see backend/app/modules/withdrawals/router.py).
//   Debits ALWAYS hit the passive ledger (dashboardStore.passiveBalance),
//   never `activeBalance` -- a withdrawal request has nothing to do
//   with the deposit/purchase flow above and must not perturb it.
//   Mirrors AgentBalanceView's withdrawal card + CBottomSheet form +
//   epoch-guarded paginated history, with one deliberate deviation:
//   AgentBalanceView gates the CTA on payout details and, when absent,
//   redirects to AgentSettingsView (which hosts a payout-details
//   editor). InvestorSettingsView has NO payout-details editor -- a
//   redirect there would dead-end the investor. So the "no payout
//   details" state instead opens an inline JSON payout-details editor
//   sheet, the same self-contained pattern CompanyBalanceView uses
//   (GET/PUT /users/me/payout-details via api/users.ts).
//
//   Withdrawal MIN/MAX bounds are hardcoded client-side (1000 /
//   10_000_000 cents) -- same documented TD-F14 debt as
//   AgentBalanceView / CompanyBalanceView, not invented here.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDownToLine, ArrowUpFromLine, CreditCard, Pencil, Wallet } from 'lucide-vue-next'
import {
  CBadge,
  CBottomSheet,
  CButton,
  CEmptyState,
  CInput,
  CLoader,
  CTextarea,
} from '@/components/ui'
import { useDashboardStore } from '@/stores/dashboard'
import { listPaymentHistory } from '@/api/payments'
import { createWithdrawal, listMyWithdrawals } from '@/api/withdrawals'
import { getPayoutDetails, updatePayoutDetails } from '@/api/users'
import { useInfiniteScroll } from '@/composables/usePagination'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'
import { formatDateTime, formatPrice, parseAmountToCents } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { PaymentResponse, WithdrawalResponse } from '@/api/types'

const PER_PAGE = 20

// TD-F14 (same debt as AgentBalanceView / CompanyBalanceView): hardcoded
// until a /config endpoint surfaces the backend's withdrawal bounds.
const MIN_WITHDRAWAL_CENTS = 1000
const MAX_WITHDRAWAL_CENTS = 10_000_000

const router = useRouter()
const { t, locale } = useI18n()
const dashboardStore = useDashboardStore()
const { showToast } = useToast()

// -- Payment history local state --
const items = ref<PaymentResponse[]>([])
const total = ref(0)
const page = ref(1)
const loadingHistory = ref(false)
const historyError = ref(false)

const sentinelRef = ref<HTMLElement | null>(null)

// Stale-epoch guard -- see stores/products.ts notes. Shared between
// fetchFirstPage and loadMore so a fresh first-page call invalidates
// any in-flight loadMore from a previous visit to this screen.
let fetchEpoch = 0

const hasMore = computed(() => items.value.length < total.value)

const hasFrozen = computed<boolean>(() => {
  return dashboardStore.activeBalance.frozen > 0
})

// Map backend payment status onto a CBadge variant. Mirrors the
// staff-side mapping in StaffPaymentsView -- keep the two in sync
// if a new status shows up.
function statusVariant(s: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (s === 'confirmed') return 'success'
  if (s === 'frozen' || s === 'created') return 'warning'
  if (s === 'reversed' || s === 'failed') return 'danger'
  return 'neutral'
}

function statusLabel(s: string): string {
  // TD-F08c-style fall-through: if the backend adds a status we
  // haven't i18n'd yet, show the raw token rather than blanking.
  return tOrRaw(t, `inv.balance.status.${s}`, s)
}

function typeLabel(type: string): string {
  return tOrRaw(t, `inv.balance.type.${type}`, type)
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

async function fetchFirstPage(): Promise<void> {
  const epoch = ++fetchEpoch
  loadingHistory.value = true
  historyError.value = false
  try {
    const resp = await listPaymentHistory({ page: 1, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = resp.items
    total.value = resp.total
    page.value = 1
  } catch {
    if (epoch !== fetchEpoch) return
    historyError.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loadingHistory.value = false
    }
  }
}

async function loadMore(): Promise<void> {
  if (loadingHistory.value || !hasMore.value) return
  const epoch = ++fetchEpoch
  loadingHistory.value = true
  try {
    const nextPage = page.value + 1
    const resp = await listPaymentHistory({
      page: nextPage,
      per_page: PER_PAGE,
    })
    if (epoch !== fetchEpoch) return
    items.value = [...items.value, ...resp.items]
    total.value = resp.total
    page.value = nextPage
  } catch {
    // Non-destructive: silent swallow keeps the already-loaded pages
    // visible; the user can scroll back up and tap Retry on the
    // empty-state if first-page itself had failed.
  } finally {
    if (epoch === fetchEpoch) {
      loadingHistory.value = false
    }
  }
}

function goDeposit(): void {
  void safeNavigate(router.push({ name: 'investor-deposit' }), '[BalanceView] to deposit')
}

async function reload(): Promise<void> {
  await Promise.all([dashboardStore.refresh(), fetchFirstPage()])
}

// Wire up the infinite scroll sentinel.
useInfiniteScroll(sentinelRef, hasMore, loadMore)

// ---------------------------------------------------------------------------
// Withdrawals -- passive balance (never activeBalance; see header note)
// ---------------------------------------------------------------------------

const passiveConfirmed = computed(() => dashboardStore.passiveBalance.confirmed)
const passiveFrozen = computed(() => dashboardStore.passiveBalance.frozen)
const hasPassiveFrozen = computed(() => passiveFrozen.value > 0)

const withdrawals = ref<WithdrawalResponse[]>([])
const withdrawalsTotal = ref(0)
const withdrawalsPage = ref(1)
const withdrawalsLoading = ref(false)
const withdrawalsErrored = ref(false)
const withdrawalsEpoch = ref(0)
const withdrawalsLoadMoreErrored = ref(false)
const withdrawalsSentinelRef = ref<HTMLElement | null>(null)

const hasMoreWithdrawals = computed(() => withdrawals.value.length < withdrawalsTotal.value)

async function fetchWithdrawalsFirstPage(): Promise<void> {
  const epoch = ++withdrawalsEpoch.value
  withdrawalsLoading.value = true
  withdrawalsErrored.value = false
  withdrawalsLoadMoreErrored.value = false
  try {
    const resp = await listMyWithdrawals({ page: 1, per_page: PER_PAGE })
    if (epoch !== withdrawalsEpoch.value) return
    withdrawals.value = resp.items
    withdrawalsTotal.value = resp.total
    withdrawalsPage.value = 1
  } catch {
    if (epoch === withdrawalsEpoch.value) withdrawalsErrored.value = true
  } finally {
    if (epoch === withdrawalsEpoch.value) withdrawalsLoading.value = false
  }
}

async function loadMoreWithdrawals(): Promise<void> {
  if (withdrawalsLoading.value || !hasMoreWithdrawals.value || withdrawalsLoadMoreErrored.value) {
    return
  }
  const epoch = withdrawalsEpoch.value
  withdrawalsLoading.value = true
  try {
    const next = withdrawalsPage.value + 1
    const resp = await listMyWithdrawals({ page: next, per_page: PER_PAGE })
    if (epoch !== withdrawalsEpoch.value) return
    withdrawals.value = [...withdrawals.value, ...resp.items]
    withdrawalsTotal.value = resp.total
    withdrawalsPage.value = next
  } catch {
    // FP-16 brake (mirrors AgentBalanceView): flag the failure so the
    // IntersectionObserver stops re-firing; the retry banner lets the
    // user resume. Non-destructive -- already-loaded pages stay visible.
    if (epoch === withdrawalsEpoch.value) {
      withdrawalsLoadMoreErrored.value = true
    }
  } finally {
    if (epoch === withdrawalsEpoch.value) withdrawalsLoading.value = false
  }
}

function retryLoadMoreWithdrawals(): void {
  withdrawalsLoadMoreErrored.value = false
  void loadMoreWithdrawals()
}

useInfiniteScroll(
  withdrawalsSentinelRef,
  hasMoreWithdrawals,
  loadMoreWithdrawals,
  withdrawalsLoadMoreErrored,
)

function withdrawalStatusVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'completed') return 'success'
  if (status === 'pending' || status === 'confirmed' || status === 'processing') {
    return 'warning'
  }
  if (status === 'rejected' || status === 'failed') return 'danger'
  return 'neutral'
}

function withdrawalStatusLabel(status: string): string {
  return tOrRaw(t, `inv.balance.withdrawals.status.${status}`, status)
}

// ---------------------------------------------------------------------------
// Payout details -- boolean gate for the withdraw CTA. AgentBalanceView
// redirects to a Settings-hosted editor; InvestorSettingsView has none,
// so this view hosts a self-contained JSON editor sheet instead (same
// mechanism CompanyBalanceView uses against the same endpoint).
// ---------------------------------------------------------------------------

const payoutDetails = ref<Record<string, unknown> | null>(null)
const payoutLoading = ref(false)
const payoutLoaded = ref(false)
const payoutErrored = ref(false)
const payoutEpoch = ref(0)

async function fetchPayoutDetails(): Promise<void> {
  const epoch = ++payoutEpoch.value
  payoutLoading.value = true
  payoutErrored.value = false
  try {
    const resp = await getPayoutDetails()
    if (epoch !== payoutEpoch.value) return
    payoutDetails.value = resp.payout_details ?? null
    payoutLoaded.value = true
  } catch {
    if (epoch === payoutEpoch.value) payoutErrored.value = true
  } finally {
    if (epoch === payoutEpoch.value) payoutLoading.value = false
  }
}

const hasPayoutDetails = computed(() => {
  const d = payoutDetails.value
  return !!d && Object.keys(d).length > 0
})

// Withdraw CTA is live only once payout details are set AND the
// confirmed passive balance clears the minimum.
const canWithdraw = computed(
  () => hasPayoutDetails.value && passiveConfirmed.value >= MIN_WITHDRAWAL_CENTS,
)

// ---------------------------------------------------------------------------
// Withdraw form
// ---------------------------------------------------------------------------

const withdrawSheetOpen = ref(false)
const withdrawAmountInput = ref('')
const withdrawSubmitting = ref(false)
const withdrawError = ref('')

const parsedAmountCents = computed<number | null>(() =>
  parseAmountToCents(withdrawAmountInput.value),
)

const withdrawValidationKey = computed<string | null>(() => {
  const cents = parsedAmountCents.value
  if (cents === null) return null
  if (cents < MIN_WITHDRAWAL_CENTS) return 'inv.balance.withdrawals.form.errorBelowMin'
  if (cents > MAX_WITHDRAWAL_CENTS) return 'inv.balance.withdrawals.form.errorAboveMax'
  if (cents > passiveConfirmed.value) return 'inv.balance.withdrawals.form.errorInsuff'
  return null
})

const canSubmitWithdraw = computed(() => {
  if (withdrawSubmitting.value) return false
  if (!hasPayoutDetails.value) return false
  if (parsedAmountCents.value === null) return false
  return withdrawValidationKey.value === null
})

function openWithdrawSheet(): void {
  if (!canWithdraw.value) return
  withdrawSheetOpen.value = true
}

function closeWithdrawSheet(): void {
  withdrawSheetOpen.value = false
}

async function submitWithdraw(): Promise<void> {
  if (!canSubmitWithdraw.value) return
  const cents = parsedAmountCents.value
  if (cents === null) return
  withdrawSubmitting.value = true
  withdrawError.value = ''
  try {
    await createWithdrawal(cents)
    showToast(t('inv.balance.withdrawals.form.successToast'), 'success')
    closeWithdrawSheet()
    await Promise.all([dashboardStore.refresh(), fetchWithdrawalsFirstPage()])
  } catch (err) {
    withdrawError.value =
      err instanceof Error && err.message ? err.message : t('inv.balance.withdrawals.form.error')
    // Backup: if payout details were cleared mid-session (backend 400),
    // re-read the gate so the CTA flips back to "set up payout details".
    void fetchPayoutDetails()
  } finally {
    withdrawSubmitting.value = false
  }
}

watch(withdrawSheetOpen, (open) => {
  if (!open) {
    withdrawAmountInput.value = ''
    withdrawError.value = ''
  }
})

// ---------------------------------------------------------------------------
// Payout details form (inline JSON editor -- see header note)
// ---------------------------------------------------------------------------

const payoutSheetOpen = ref(false)
const payoutEditInput = ref('')
const payoutSubmitting = ref(false)
const payoutError = ref('')

const payoutValidation = computed<true | 'json' | 'object' | 'empty' | null>(() => {
  const raw = payoutEditInput.value.trim()
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return 'json'
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return 'object'
  }
  if (Object.keys(parsed as Record<string, unknown>).length === 0) {
    return 'empty'
  }
  return true
})

const payoutValidationKey = computed<string | null>(() => {
  const v = payoutValidation.value
  if (v === 'json') return 'inv.balance.payout.form.errorJson'
  if (v === 'object') return 'inv.balance.payout.form.errorObject'
  if (v === 'empty') return 'inv.balance.payout.form.errorEmpty'
  return null
})

const canSubmitPayout = computed(() => {
  if (payoutSubmitting.value) return false
  return payoutValidation.value === true
})

function openPayoutSheet(): void {
  payoutEditInput.value = hasPayoutDetails.value ? JSON.stringify(payoutDetails.value, null, 2) : ''
  payoutError.value = ''
  payoutSheetOpen.value = true
}

function closePayoutSheet(): void {
  payoutSheetOpen.value = false
}

async function submitPayout(): Promise<void> {
  if (!canSubmitPayout.value) return
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(payoutEditInput.value) as Record<string, unknown>
  } catch {
    payoutError.value = t('inv.balance.payout.form.errorJson')
    return
  }
  payoutSubmitting.value = true
  payoutError.value = ''
  try {
    await updatePayoutDetails(parsed)
    showToast(t('inv.balance.payout.form.successToast'), 'success')
    // PUT replaces payout_details wholesale -> write locally instead of
    // refetching (a failing refetch here must not blank the "saved"
    // state right after the success toast).
    payoutDetails.value = parsed
    payoutLoaded.value = true
    payoutErrored.value = false
    closePayoutSheet()
  } catch (err) {
    payoutError.value =
      err instanceof Error && err.message ? err.message : t('inv.balance.payout.form.error')
  } finally {
    payoutSubmitting.value = false
  }
}

watch(payoutSheetOpen, (open) => {
  if (!open) {
    payoutEditInput.value = ''
    payoutError.value = ''
  }
})

// If the balance store was populated by another view (purchase
// confirm probe, etc.) there's no need to reset it; refresh will
// overwrite. We don't reset on unmount because the store is shared
// with F4.4 screens and clearing on nav would cause a flash there.
onMounted(() => {
  void dashboardStore.refresh()
  void fetchFirstPage()
  void fetchWithdrawalsFirstPage()
  void fetchPayoutDetails()
})

// If the user deposits and returns here via router.back(), the
// BalanceView instance is already mounted and onMounted will NOT
// rerun. Watching the route name wouldn't help since we stay on
// the same name. A fresh refresh is driven by DepositView pushing
// a toast + the user glancing back -- acceptable for F4.3; if
// stickiness bites, F4.4 can add a store-level subscription.
watch(
  () => dashboardStore.error,
  (err) => {
    // Surface as inline banner, no toast (see header comment).
    void err
  },
)
</script>

<template>
  <div class="bv">
    <div class="bv__header">
      <h1 class="bv__title">
        {{ t('inv.balance.title') }}
      </h1>
    </div>

    <!-- Active balance card -->
    <section class="bv__card bv__balance">
      <h2 class="bv__card-title">
        {{ t('inv.balance.active') }}
      </h2>

      <div
        v-if="
          dashboardStore.loading &&
          dashboardStore.activeBalance.confirmed === 0 &&
          dashboardStore.activeBalance.frozen === 0
        "
        class="bv__balance-loading"
      >
        <CLoader :size="20" />
      </div>

      <template v-else>
        <div class="bv__balance-main">
          {{ formatPrice(dashboardStore.activeBalance.confirmed) }}
        </div>

        <div v-if="hasFrozen" class="bv__balance-frozen">
          <span class="bv__balance-frozen-label">
            {{ t('inv.balance.frozen') }}
          </span>
          <span class="bv__balance-frozen-value">
            {{ formatPrice(dashboardStore.activeBalance.frozen) }}
          </span>
        </div>

        <div v-if="dashboardStore.error" class="bv__balance-error">
          <span>{{ t('inv.balance.refreshFailed') }}</span>
          <CButton variant="outline" size="sm" @click="reload">
            {{ t('common.retry') }}
          </CButton>
        </div>

        <CButton variant="primary" class="bv__deposit" @click="goDeposit">
          <ArrowDownToLine :size="16" />
          {{ t('inv.balance.deposit') }}
        </CButton>
      </template>
    </section>

    <!-- Withdrawal (passive) balance card -->
    <section class="bv__card bv__wd-balance">
      <div class="bv__wd-balance-head">
        <Wallet :size="16" />
        <span>{{ t('inv.balance.withdrawals.cardTitle') }}</span>
      </div>

      <div
        v-if="dashboardStore.loading && passiveConfirmed === 0 && passiveFrozen === 0"
        class="bv__balance-loading"
      >
        <CLoader :size="20" />
      </div>

      <template v-else>
        <div class="bv__wd-balance-value">
          {{ formatPrice(passiveConfirmed) }}
        </div>
        <div v-if="hasPassiveFrozen" class="bv__wd-balance-frozen">
          {{ t('inv.balance.frozen') }}: {{ formatPrice(passiveFrozen) }}
        </div>

        <div class="bv__wd-cta-row">
          <template v-if="!hasPayoutDetails">
            <CButton
              variant="outline"
              :disabled="payoutLoading && !payoutLoaded"
              @click="openPayoutSheet"
            >
              <Pencil :size="16" />
              {{ t('inv.balance.withdrawals.setupPayout') }}
            </CButton>
            <span class="bv__wd-cta-hint">
              {{ t('inv.balance.withdrawals.needPayout') }}
            </span>
          </template>
          <template v-else>
            <CButton variant="primary" :disabled="!canWithdraw" @click="openWithdrawSheet">
              <ArrowUpFromLine :size="16" />
              {{ t('inv.balance.withdrawals.newButton') }}
            </CButton>
            <CButton variant="outline" size="sm" @click="openPayoutSheet">
              <Pencil :size="16" />
              {{ t('inv.balance.payout.editButton') }}
            </CButton>
            <span v-if="!canWithdraw" class="bv__wd-cta-hint">
              {{ t('inv.balance.withdrawals.lowBalance') }}
            </span>
          </template>
        </div>
      </template>
    </section>

    <!-- Payment history -->
    <section class="bv__history">
      <h2 class="bv__card-title bv__history-title">
        {{ t('inv.balance.history') }}
      </h2>

      <!-- Initial load spinner (no items yet, fetching) -->
      <div v-if="loadingHistory && items.length === 0 && !historyError" class="bv__history-center">
        <CLoader :size="24" />
      </div>

      <!-- Error (first-page failure) -->
      <div v-else-if="historyError && items.length === 0" class="bv__history-center">
        <CEmptyState
          :title="t('inv.balance.historyError.title')"
          :description="t('inv.balance.historyError.desc')"
        />
        <CButton variant="outline" size="sm" @click="fetchFirstPage">
          {{ t('common.retry') }}
        </CButton>
      </div>

      <!-- Empty state -->
      <div v-else-if="!loadingHistory && items.length === 0" class="bv__history-center">
        <CEmptyState :title="t('inv.balance.historyEmpty')">
          <template #icon>
            <CreditCard :size="32" />
          </template>
        </CEmptyState>
      </div>

      <!-- List -->
      <ul v-else class="bv__list">
        <li v-for="item in items" :key="item.id" class="bv__item">
          <div class="bv__item-icon">
            <CreditCard :size="16" />
          </div>
          <div class="bv__item-body">
            <div class="bv__item-line">
              <span class="bv__item-type">
                {{ typeLabel(item.payment_type) }}
              </span>
              <span class="bv__item-amount">
                {{ formatPrice(item.amount_cents, item.currency) }}
              </span>
            </div>
            <div class="bv__item-line bv__item-line--sub">
              <span class="bv__item-date">
                {{ formatDate(item.created_at) }}
              </span>
              <CBadge :variant="statusVariant(item.status)" :text="statusLabel(item.status)" />
            </div>
          </div>
        </li>
      </ul>

      <!-- Infinite scroll sentinel (only when we already have items) -->
      <div v-if="items.length > 0" ref="sentinelRef" class="bv__sentinel">
        <CLoader v-if="loadingHistory" :size="20" />
      </div>
    </section>

    <!-- Withdrawal history -->
    <section class="bv__history">
      <h2 class="bv__card-title bv__history-title">
        {{ t('inv.balance.withdrawals.title') }}
      </h2>

      <!-- Initial load spinner (no items yet, fetching) -->
      <div
        v-if="withdrawalsLoading && withdrawals.length === 0 && !withdrawalsErrored"
        class="bv__history-center"
      >
        <CLoader :size="24" />
      </div>

      <!-- Error (first-page failure) -->
      <div v-else-if="withdrawalsErrored && withdrawals.length === 0" class="bv__history-center">
        <CEmptyState :title="t('inv.balance.historyError.title')" />
        <CButton variant="outline" size="sm" @click="fetchWithdrawalsFirstPage">
          {{ t('common.retry') }}
        </CButton>
      </div>

      <!-- Empty state -->
      <div v-else-if="!withdrawalsLoading && withdrawals.length === 0" class="bv__history-center">
        <CEmptyState :title="t('inv.balance.withdrawals.empty')">
          <template #icon>
            <ArrowUpFromLine :size="32" />
          </template>
        </CEmptyState>
      </div>

      <!-- List -->
      <ul v-else class="bv__list">
        <li v-for="w in withdrawals" :key="w.id" class="bv__item">
          <div class="bv__item-icon">
            <ArrowUpFromLine :size="16" />
          </div>
          <div class="bv__item-body">
            <div class="bv__item-line">
              <span class="bv__wd-item-amount">
                {{ formatPrice(w.amount_cents) }}
              </span>
              <CBadge
                :variant="withdrawalStatusVariant(w.status)"
                :text="withdrawalStatusLabel(w.status)"
              />
            </div>
            <div class="bv__item-line bv__item-line--sub">
              <span class="bv__item-date">
                {{ formatDateTime(w.created_at, locale) }}
              </span>
              <span
                v-if="w.rejection_reason"
                class="bv__wd-item-reason"
                :title="w.rejection_reason"
              >
                {{ w.rejection_reason }}
              </span>
            </div>
          </div>
        </li>
      </ul>

      <!-- Infinite scroll sentinel (only when we already have items) -->
      <div v-if="withdrawals.length > 0" ref="withdrawalsSentinelRef" class="bv__sentinel">
        <CLoader v-if="withdrawalsLoading" :size="20" />
      </div>

      <div
        v-if="withdrawals.length > 0 && withdrawalsLoadMoreErrored && !withdrawalsLoading"
        class="bv__loadmore-error"
      >
        <span>{{ t('inv.balance.withdrawals.loadMoreError') }}</span>
        <CButton variant="outline" size="sm" @click="retryLoadMoreWithdrawals">
          {{ t('common.retry') }}
        </CButton>
      </div>
    </section>

    <!-- Withdraw sheet -->
    <CBottomSheet
      :open="withdrawSheetOpen"
      :title="t('inv.balance.withdrawals.form.title')"
      @close="closeWithdrawSheet"
    >
      <form class="bv__form" @submit.prevent="submitWithdraw">
        <label class="bv__field">
          <span class="bv__field-label">
            {{ t('inv.balance.withdrawals.form.amountLabel') }}
          </span>
          <CInput
            v-model="withdrawAmountInput"
            class="bv__control"
            size="compact"
            type="number"
            inputmode="decimal"
            step="0.01"
            min="0"
            :placeholder="t('inv.balance.withdrawals.form.amountPlaceholder')"
            :disabled="withdrawSubmitting"
          />
          <span class="bv__field-hint">
            {{
              t('inv.balance.withdrawals.form.amountHint', {
                min: formatPrice(MIN_WITHDRAWAL_CENTS),
                max: formatPrice(MAX_WITHDRAWAL_CENTS),
                available: formatPrice(passiveConfirmed),
              })
            }}
          </span>
        </label>

        <p v-if="withdrawValidationKey" class="bv__form-error bv__form-error--soft">
          {{
            t(withdrawValidationKey, {
              min: formatPrice(MIN_WITHDRAWAL_CENTS),
              max: formatPrice(MAX_WITHDRAWAL_CENTS),
              available: formatPrice(passiveConfirmed),
            })
          }}
        </p>

        <p v-if="withdrawError" class="bv__form-error">
          {{ withdrawError }}
        </p>

        <div class="bv__form-actions">
          <CButton
            variant="outline"
            type="button"
            :disabled="withdrawSubmitting"
            @click="closeWithdrawSheet"
          >
            {{ t('inv.balance.withdrawals.form.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            type="submit"
            :disabled="!canSubmitWithdraw"
            :loading="withdrawSubmitting"
          >
            {{ t('inv.balance.withdrawals.form.submit') }}
          </CButton>
        </div>
      </form>
    </CBottomSheet>

    <!-- Payout details sheet -->
    <CBottomSheet
      :open="payoutSheetOpen"
      :title="t('inv.balance.payout.form.title')"
      @close="closePayoutSheet"
    >
      <form class="bv__form" @submit.prevent="submitPayout">
        <label class="bv__field">
          <span class="bv__field-label">
            {{ t('inv.balance.payout.form.label') }}
          </span>
          <CTextarea
            v-model="payoutEditInput"
            class="bv__control bv__control--payout"
            size="compact"
            mono
            :placeholder="t('inv.balance.payout.form.placeholder')"
            :disabled="payoutSubmitting"
            :rows="10"
            spellcheck="false"
          />
          <span class="bv__field-hint">
            {{ t('inv.balance.payout.form.hint') }}
          </span>
        </label>

        <p v-if="payoutValidationKey" class="bv__form-error bv__form-error--soft">
          {{ t(payoutValidationKey) }}
        </p>

        <p v-if="payoutError" class="bv__form-error">
          {{ payoutError }}
        </p>

        <div class="bv__form-actions">
          <CButton
            variant="outline"
            type="button"
            :disabled="payoutSubmitting"
            @click="closePayoutSheet"
          >
            {{ t('inv.balance.payout.form.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            type="submit"
            :disabled="!canSubmitPayout"
            :loading="payoutSubmitting"
          >
            {{ t('inv.balance.payout.form.submit') }}
          </CButton>
        </div>
      </form>
    </CBottomSheet>
  </div>
</template>

<style scoped>
.bv {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

/* Page header (inline, not CHeader -- shell already renders CHeader) */
.bv__header {
  padding: var(--space-4) var(--space-4) 0;
}
.bv__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

/* Card base */
.bv__card {
  padding: var(--space-4-lg);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin: var(--space-4) var(--space-4) 0;
}

.bv__card-title {
  font-size: var(--fs-xs);
  font-weight: 700;
  margin: 0 0 var(--space-3);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Active balance */
.bv__balance {
  display: flex;
  flex-direction: column;
}

.bv__balance-loading {
  display: flex;
  justify-content: center;
  padding: var(--space-2) 0;
}

.bv__balance-main {
  font-size: var(--fs-4xl);
  font-weight: 700;
  color: var(--accent);
  line-height: 1.1;
  margin-bottom: var(--space-2);
  word-break: break-word;
}

.bv__balance-frozen {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-2);
  margin-top: var(--space-1);
  border-top: 1px solid var(--border-default);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.bv__balance-frozen-label {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.bv__balance-frozen-value {
  font-weight: 600;
  color: var(--text-secondary);
}

.bv__balance-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--danger-subtle);
  color: var(--danger);
  font-size: var(--fs-xs);
}

.bv__deposit {
  margin-top: var(--space-4);
}

/* History */
.bv__history {
  padding: var(--space-4-lg) var(--space-4) 0;
}

.bv__history-title {
  padding: 0 var(--space-1);
}

.bv__history-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
}

.bv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.bv__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
}

.bv__item-icon {
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

.bv__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.bv__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.bv__item-line--sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.bv__item-type {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}
.bv__item-amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--success);
  white-space: nowrap;
}
.bv__item-date {
  color: var(--text-tertiary);
}

.bv__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

/* Withdrawal (passive) balance card -- same card shell as .bv__balance,
   distinct value/CTA classes so a debit figure never inherits the
   deposit-flow's green/success styling. */
.bv__wd-balance {
  display: flex;
  flex-direction: column;
}
.bv__wd-balance-head {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: var(--space-3);
}
.bv__wd-balance-value {
  font-size: var(--fs-4xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
  word-break: break-word;
}
.bv__wd-balance-frozen {
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--warning);
}

.bv__wd-cta-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
  flex-wrap: wrap;
}
.bv__wd-cta-hint {
  font-size: var(--fs-xs);
  font-style: italic;
  color: var(--text-tertiary);
}

/* Withdrawal history list items reuse .bv__item / .bv__item-icon /
   .bv__item-body / .bv__item-line / .bv__item-date / .bv__sentinel
   as-is (same card shell as payment history); only the amount and
   rejection-reason need dedicated classes. */
.bv__wd-item-amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.bv__wd-item-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--danger);
  font-style: italic;
  text-align: right;
  max-width: 60%;
}

.bv__loadmore-error {
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

/* Withdraw / payout-details bottom-sheet forms */
.bv__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.bv__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.bv__control {
  margin-bottom: 0;
}
.bv__control--payout :deep(.c-textarea) {
  min-height: 160px;
}
.bv__field-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.bv__field-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

.bv__form-error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}
.bv__form-error--soft {
  background: transparent;
  border: 1px solid var(--warning);
  color: var(--warning);
}

.bv__form-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-1);
}
</style>
