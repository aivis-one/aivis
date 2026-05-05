<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanyBalanceView (Phase F5.2 B3)
// =============================================================================
//
// Balance tab inside CompanyShell. Read-only in B3:
//   1. Passive balance card  -- confirmed + frozen, sourced from
//      companyDashboard store (no separate balance fetch).
//   2. Withdrawals history   -- paginated /withdrawals/me, status
//      badges, infinite scroll.
//   3. Payout details        -- preview of GET /users/me/payout-details,
//      JSON view or empty placeholder.
//
// CompanyShell paints CHeader + CTabBar; this view is plain content
// with the inline page-header pattern.
//
// SCOPE -- B3.
//   No write actions. The "Request withdrawal" and "Edit details"
//   buttons render as disabled placeholders with a "Coming next"
//   caption -- B4 swaps them for working forms (POST /withdrawals
//   for the first, PUT /users/me/payout-details for the second).
//   The api wrappers (createWithdrawal, updatePayoutDetails) already
//   ship in B3 to keep B4 a pure UI patch.
//
// DATA SOURCES.
//   1. Passive balance: useCompanyDashboardStore. The store may be
//      already populated when the user navigated through the
//      dashboard tab first -- in that case we render immediately.
//      Hard-refresh straight onto /company/balance leaves the store
//      empty; we call refresh() once. Frontend.md is explicit on
//      not adding a SEPARATE balance endpoint -- "не делать второй
//      вызов /company/dashboard ради того же объекта" -- so we go
//      through the store either way.
//   2. Withdrawals: local ref<WithdrawalResponse[]> with infinite
//      scroll. Single-screen consumer; a Pinia store would be
//      ceremony without upside (mirrors investor BalanceView's
//      payment-history pattern).
//   3. Payout details: local ref<Record<string, unknown> | null>.
//      Single-shot fetch, no pagination, no other consumer.
//
// EPOCH GUARDS.
//   Withdrawals list uses a fetchEpoch counter shared between the
//   first-page fetch and loadMore(), so a Retry click landing while
//   a previous call is still in flight cannot regress the UI. Same
//   FP-17 pattern used in stores/products and the analytics view.
//
//   Payout details fetch is single-shot with its own epoch -- the
//   "edit" path lives in B4 and will need to invalidate this on
//   successful PUT. The epoch counter is already in place.
//
// STATUS MAPPING.
//   Withdrawal lifecycle (Sprint 6.3 state machine):
//     pending    -> warning  (awaiting staff review)
//     confirmed  -> warning  (staff approved, not yet pushed)
//     processing -> warning  (pushed to provider, awaiting webhook)
//     completed  -> success  (terminal: payout confirmed)
//     rejected   -> danger   (terminal: staff rejected with reason)
//     failed     -> danger   (terminal: provider rejected the payout)
//   Unknown future statuses -> neutral. Mirrors the investor-side
//   BalanceView statusVariant() but with the withdrawal enum.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowUpFromLine,
  ChevronRight,
  CreditCard,
  Pencil,
  Wallet,
} from 'lucide-vue-next'

import {
  CBottomSheet,
  CEmptyState,
  CLoader,
} from '@/components/ui'
import { createWithdrawal, listMyWithdrawals } from '@/api/withdrawals'
import { getPayoutDetails, updatePayoutDetails } from '@/api/users'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { WithdrawalResponse } from '@/api/types'

// Withdrawal bounds mirror backend settings (Sprint 6.3 P6-34).
// Hardcoded here because the backend does not surface them via API
// today; if/when an /api/v1/config or similar endpoint lands, replace
// these constants with a fetch + cache. The numbers MUST stay in sync
// with backend config: min_withdrawal_cents=1000, max=10000000.
const MIN_WITHDRAWAL_CENTS = 1000
const MAX_WITHDRAWAL_CENTS = 10_000_000

const PER_PAGE = 20

const { t } = useI18n()
const dashboardStore = useCompanyDashboardStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Withdrawals list -- local state + infinite scroll
// ---------------------------------------------------------------------------

const withdrawals = ref<WithdrawalResponse[]>([])
const withdrawalsTotal = ref<number>(0)
const withdrawalsPage = ref<number>(1)
const withdrawalsLoading = ref<boolean>(false)
const withdrawalsErrored = ref<boolean>(false)

let withdrawalsEpoch = 0

const sentinelRef = ref<HTMLElement | null>(null)

const hasMoreWithdrawals = computed<boolean>(
  () => withdrawals.value.length < withdrawalsTotal.value,
)

async function fetchWithdrawalsFirstPage(): Promise<void> {
  const epoch = ++withdrawalsEpoch
  withdrawalsLoading.value = true
  withdrawalsErrored.value = false
  try {
    const resp = await listMyWithdrawals({ page: 1, per_page: PER_PAGE })
    if (epoch !== withdrawalsEpoch) return
    withdrawals.value = resp.items
    withdrawalsTotal.value = resp.total
    withdrawalsPage.value = 1
  } catch {
    if (epoch !== withdrawalsEpoch) return
    withdrawalsErrored.value = true
  } finally {
    if (epoch === withdrawalsEpoch) withdrawalsLoading.value = false
  }
}

async function loadMoreWithdrawals(): Promise<void> {
  if (withdrawalsLoading.value || !hasMoreWithdrawals.value) return
  const epoch = ++withdrawalsEpoch
  withdrawalsLoading.value = true
  try {
    const nextPage = withdrawalsPage.value + 1
    const resp = await listMyWithdrawals({
      page: nextPage,
      per_page: PER_PAGE,
    })
    if (epoch !== withdrawalsEpoch) return
    withdrawals.value = [...withdrawals.value, ...resp.items]
    withdrawalsTotal.value = resp.total
    withdrawalsPage.value = nextPage
  } catch {
    // Non-destructive: silent swallow. Already-loaded pages stay
    // visible; the user can scroll up and hit Retry on the
    // first-page error surface if they want to recover from a
    // network blip.
  } finally {
    if (epoch === withdrawalsEpoch) withdrawalsLoading.value = false
  }
}

useInfiniteScroll(sentinelRef, hasMoreWithdrawals, loadMoreWithdrawals)

// ---------------------------------------------------------------------------
// Payout details -- local state
// ---------------------------------------------------------------------------

const payoutDetails = ref<Record<string, unknown> | null>(null)
const payoutLoading = ref<boolean>(false)
const payoutErrored = ref<boolean>(false)

let payoutEpoch = 0

async function fetchPayoutDetails(): Promise<void> {
  const epoch = ++payoutEpoch
  payoutLoading.value = true
  payoutErrored.value = false
  try {
    const resp = await getPayoutDetails()
    if (epoch !== payoutEpoch) return
    payoutDetails.value = resp.payout_details ?? null
  } catch {
    if (epoch !== payoutEpoch) return
    payoutErrored.value = true
  } finally {
    if (epoch === payoutEpoch) payoutLoading.value = false
  }
}

const hasPayoutDetails = computed<boolean>(() => {
  const d = payoutDetails.value
  if (!d) return false
  return Object.keys(d).length > 0
})

const payoutDetailsJson = computed<string>(() => {
  if (!payoutDetails.value) return ''
  return JSON.stringify(payoutDetails.value, null, 2)
})

// ---------------------------------------------------------------------------
// Balance derived state
// ---------------------------------------------------------------------------

const passiveConfirmed = computed<number>(
  () => dashboardStore.summary?.passive_balance.confirmed ?? 0,
)
const passiveFrozen = computed<number>(
  () => dashboardStore.summary?.passive_balance.frozen ?? 0,
)
const hasFrozen = computed<boolean>(() => passiveFrozen.value > 0)

// ---------------------------------------------------------------------------
// Render policy
// ---------------------------------------------------------------------------

const initialLoading = computed<boolean>(() => {
  if (dashboardStore.error || withdrawalsErrored.value || payoutErrored.value) {
    return false
  }
  // Hold the spinner until both the balance is available AND the
  // first page of withdrawals AND the payout-details have resolved.
  // Three-store all-or-nothing -- avoids the flash where balance
  // renders before withdrawals or vice versa.
  if (dashboardStore.summary === null) return true
  if (withdrawalsLoading.value && withdrawals.value.length === 0) return true
  if (payoutLoading.value && payoutDetails.value === null && !hasPayoutDetails.value) {
    // payout starts as null -- distinguish "still loading" from
    // "loaded and empty" via the loading flag.
    return true
  }
  return false
})

const hasError = computed<boolean>(
  () =>
    dashboardStore.error !== null
    || withdrawalsErrored.value
    || payoutErrored.value,
)

// ---------------------------------------------------------------------------
// Withdrawal status helpers
// ---------------------------------------------------------------------------

type StatusVariant = 'success' | 'warning' | 'danger' | 'neutral'

function statusVariant(status: string): StatusVariant {
  if (status === 'completed') return 'success'
  if (
    status === 'pending'
    || status === 'confirmed'
    || status === 'processing'
  ) {
    return 'warning'
  }
  if (status === 'rejected' || status === 'failed') return 'danger'
  return 'neutral'
}

function statusLabel(status: string): string {
  return tOrRaw(t, `comp.balance.withdrawals.status.${status}`, status)
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

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

async function loadAll(): Promise<void> {
  // Ensure the dashboard cache is populated -- if the user landed
  // here via the dashboard tab the store already has summary, and
  // refresh() is skipped. On a hard refresh straight onto
  // /company/balance the store is empty and we fetch once.
  const dashboardPromise =
    dashboardStore.summary === null
      ? dashboardStore.refresh()
      : Promise.resolve()

  await Promise.all([
    dashboardPromise,
    fetchWithdrawalsFirstPage(),
    fetchPayoutDetails(),
  ])
}

onMounted(() => {
  void loadAll()
})

// ===========================================================================
// B4 -- write actions
// ===========================================================================

// ---------------------------------------------------------------------------
// Withdraw form (POST /withdrawals)
// ---------------------------------------------------------------------------

const withdrawSheetOpen = ref<boolean>(false)
const withdrawAmountInput = ref<string>('')
const withdrawSubmitting = ref<boolean>(false)
const withdrawError = ref<string>('')

/**
 * Parse the user's amount input into integer cents. Accepts decimal
 * dollars ("25.50") and integer dollars ("100"); returns null on
 * unparseable / negative / NaN. Rounded to nearest cent so a
 * "10.555" input becomes 1056 cents -- safer than truncation in the
 * presence of floating-point quirks. Negative is rejected here, not
 * passed through, so the validation message stays accurate.
 */
const parsedAmountCents = computed<number | null>(() => {
  const raw = withdrawAmountInput.value.trim()
  if (!raw) return null
  const dollars = Number(raw)
  if (!Number.isFinite(dollars) || dollars <= 0) return null
  return Math.round(dollars * 100)
})

const withdrawValidationKey = computed<string | null>(() => {
  const cents = parsedAmountCents.value
  if (cents === null) return null
  if (cents < MIN_WITHDRAWAL_CENTS) {
    return 'comp.balance.withdrawals.form.errorBelowMin'
  }
  if (cents > MAX_WITHDRAWAL_CENTS) {
    return 'comp.balance.withdrawals.form.errorAboveMax'
  }
  if (cents > passiveConfirmed.value) {
    return 'comp.balance.withdrawals.form.errorInsuff'
  }
  return null
})

/**
 * The Submit button is enabled only when:
 *   - the amount parses to a positive integer-cent value
 *   - that value satisfies all bounds and balance checks
 *   - we are not mid-submit
 *   - payout details are configured (backend gates on this; we
 *     prevent the round-trip when we already know it would 400)
 */
const canSubmitWithdraw = computed<boolean>(() => {
  if (withdrawSubmitting.value) return false
  if (!hasPayoutDetails.value) return false
  if (parsedAmountCents.value === null) return false
  return withdrawValidationKey.value === null
})

/**
 * Determines whether the "Request withdrawal" button on the balance
 * card is disabled (and what hint to show next to it). Three reasons,
 * checked in order:
 *   1. payout details not configured -> "Configure payout details first"
 *   2. balance below minimum withdrawal -> "Insufficient balance"
 *   3. otherwise enabled, no hint
 *
 * Reason ordering matters: a user with empty payout AND empty balance
 * sees the payout hint first because configuring payout is the first
 * blocker they need to clear regardless of what their balance grows to.
 */
const withdrawCtaState = computed<{
  disabled: boolean
  hintKey: string | null
}>(() => {
  if (!hasPayoutDetails.value) {
    return {
      disabled: true,
      hintKey: 'comp.balance.withdrawals.form.errorPayout',
    }
  }
  if (passiveConfirmed.value < MIN_WITHDRAWAL_CENTS) {
    return {
      disabled: true,
      hintKey: 'comp.balance.withdrawals.form.errorInsuffCard',
    }
  }
  return { disabled: false, hintKey: null }
})

function openWithdrawSheet(): void {
  if (withdrawCtaState.value.disabled) return
  withdrawAmountInput.value = ''
  withdrawError.value = ''
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
    showToast(
      t('comp.balance.withdrawals.form.successToast'),
      'success',
    )
    closeWithdrawSheet()
    // Backend debits the passive ledger immediately (P6-26), so the
    // dashboard balance is stale until refreshed. Refetch withdrawals
    // too so the new pending row shows at the top.
    await Promise.all([
      dashboardStore.refresh(),
      fetchWithdrawalsFirstPage(),
    ])
  } catch (err) {
    // Backend may surface 400 (bounds, payout, insufficient) or 409
    // (active withdrawal exists). All of them carry a message we can
    // display verbatim; falling back to a generic key only when the
    // error has no readable message.
    withdrawError.value =
      err instanceof Error && err.message
        ? err.message
        : t('comp.balance.withdrawals.form.error')
  } finally {
    withdrawSubmitting.value = false
  }
}

// Reset on sheet close transition so re-opening starts clean.
watch(withdrawSheetOpen, (open) => {
  if (!open) {
    withdrawAmountInput.value = ''
    withdrawError.value = ''
  }
})

// ---------------------------------------------------------------------------
// Payout details form (PUT /users/me/payout-details)
// ---------------------------------------------------------------------------

const payoutSheetOpen = ref<boolean>(false)
const payoutEditInput = ref<string>('')
const payoutSubmitting = ref<boolean>(false)
const payoutError = ref<string>('')

/**
 * Validate that the textarea contains a parseable JSON OBJECT --
 * not a primitive, not an array. Returns:
 *   - null  if input is empty (treated as "not yet typed")
 *   - 'json' if JSON.parse fails
 *   - 'object' if parsed but not a plain object
 *   - true if valid (passes all checks)
 *
 * The free-form JSONB contract (P6-32) means we can't validate
 * content -- only shape. The backend accepts any keys.
 */
const payoutValidation = computed<true | 'json' | 'object' | null>(() => {
  const raw = payoutEditInput.value.trim()
  if (!raw) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return 'json'
  }
  if (
    parsed === null
    || typeof parsed !== 'object'
    || Array.isArray(parsed)
  ) {
    return 'object'
  }
  return true
})

const payoutValidationKey = computed<string | null>(() => {
  const v = payoutValidation.value
  if (v === 'json') return 'comp.balance.payout.form.errorJson'
  if (v === 'object') return 'comp.balance.payout.form.errorObject'
  return null
})

const canSubmitPayout = computed<boolean>(() => {
  if (payoutSubmitting.value) return false
  return payoutValidation.value === true
})

function openPayoutSheet(): void {
  // Pre-fill with the current value (pretty-printed). New companies
  // start with an empty editor; an explicit "{}" placeholder would
  // pass our object check on submit, sending an empty object and
  // erasing whatever was there -- prefer the empty string + a
  // suggestion in the placeholder attribute.
  payoutEditInput.value = hasPayoutDetails.value
    ? JSON.stringify(payoutDetails.value, null, 2)
    : ''
  payoutError.value = ''
  payoutSheetOpen.value = true
}

function closePayoutSheet(): void {
  payoutSheetOpen.value = false
}

async function submitPayout(): Promise<void> {
  if (!canSubmitPayout.value) return
  // Re-parse here -- the validation computed has already proven this
  // is a valid object, so the cast is safe.
  const parsed = JSON.parse(payoutEditInput.value) as Record<
    string,
    unknown
  >
  payoutSubmitting.value = true
  payoutError.value = ''
  try {
    await updatePayoutDetails(parsed)
    showToast(t('comp.balance.payout.form.successToast'), 'success')
    closePayoutSheet()
    await fetchPayoutDetails()
  } catch (err) {
    payoutError.value =
      err instanceof Error && err.message
        ? err.message
        : t('comp.balance.payout.form.error')
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
</script>

<template>
  <div class="cbal">
    <!-- Page header -->
    <div class="cbal__header">
      <h1 class="cbal__title">{{ t('comp.balance.title') }}</h1>
      <p class="cbal__subtitle">{{ t('comp.balance.subtitle') }}</p>
    </div>

    <!-- Initial load -->
    <div v-if="initialLoading" class="cbal__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="cbal__center">
      <CEmptyState :title="t('comp.balance.errorTitle')" />
      <button
        type="button"
        class="cbal__btn cbal__btn--outline cbal__btn--sm"
        @click="loadAll"
      >
        {{ t('comp.balance.errorRetry') }}
      </button>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Passive balance card -->
      <section class="cbal__card cbal__balance">
        <div class="cbal__balance-head">
          <Wallet :size="14" />
          <span>{{ t('comp.balance.card.title') }}</span>
        </div>
        <div class="cbal__balance-value">
          {{ formatPrice(passiveConfirmed) }}
        </div>
        <div v-if="hasFrozen" class="cbal__balance-frozen">
          {{ t('comp.balance.card.frozen') }}:
          {{ formatPrice(passiveFrozen) }}
        </div>

        <!-- B4: Request withdrawal CTA. Disabled when payout is not
             configured (most common blocker) or balance is below the
             minimum withdrawal floor. -->
        <div class="cbal__cta-row">
          <button
            type="button"
            class="cbal__btn cbal__btn--primary"
            :disabled="withdrawCtaState.disabled"
            @click="openWithdrawSheet"
          >
            <ArrowUpFromLine :size="16" />
            {{ t('comp.balance.withdrawals.newButton') }}
          </button>
          <span
            v-if="withdrawCtaState.hintKey"
            class="cbal__cta-hint"
          >
            {{ t(withdrawCtaState.hintKey) }}
          </span>
        </div>
      </section>

      <!-- Withdrawals history -->
      <section class="cbal__section">
        <h2 class="cbal__section-title">
          {{ t('comp.balance.withdrawals.title') }}
        </h2>

        <p
          v-if="withdrawals.length === 0 && !withdrawalsLoading"
          class="cbal__empty"
        >
          {{ t('comp.balance.withdrawals.empty') }}
        </p>

        <ul v-else class="cbal__list">
          <li
            v-for="w in withdrawals"
            :key="w.id"
            class="cbal__item"
          >
            <div class="cbal__item-icon">
              <CreditCard :size="18" />
            </div>
            <div class="cbal__item-body">
              <div class="cbal__item-line">
                <span class="cbal__item-amount">
                  {{ formatPrice(w.amount_cents) }}
                </span>
                <span
                  class="cbal__badge"
                  :class="`cbal__badge--${statusVariant(w.status)}`"
                >
                  {{ statusLabel(w.status) }}
                </span>
              </div>
              <div class="cbal__item-line cbal__item-line--sub">
                <span class="cbal__item-date">
                  {{ formatDate(w.created_at) }}
                </span>
                <span
                  v-if="w.rejection_reason"
                  class="cbal__item-reason"
                  :title="w.rejection_reason"
                >
                  {{ w.rejection_reason }}
                </span>
              </div>
            </div>
          </li>
        </ul>

        <div
          v-if="withdrawals.length > 0"
          ref="sentinelRef"
          class="cbal__sentinel"
        >
          <CLoader v-if="withdrawalsLoading" :size="20" />
        </div>
      </section>

      <!-- Payout details -->
      <section class="cbal__section">
        <h2 class="cbal__section-title">
          {{ t('comp.balance.payout.title') }}
        </h2>

        <p v-if="!hasPayoutDetails" class="cbal__empty">
          {{ t('comp.balance.payout.empty') }}
        </p>

        <pre v-else class="cbal__json">{{ payoutDetailsJson }}</pre>

        <!-- B4: Edit payout details CTA. Always enabled; the form
             handles both the empty-initial and the edit-existing
             cases via openPayoutSheet's pre-fill logic. -->
        <div class="cbal__cta-row">
          <button
            type="button"
            class="cbal__btn cbal__btn--outline cbal__btn--sm"
            @click="openPayoutSheet"
          >
            <Pencil :size="14" />
            {{ t('comp.balance.payout.editButton') }}
            <ChevronRight :size="14" />
          </button>
        </div>
      </section>
    </template>

    <!-- ===================================================================== -->
    <!-- B4: Withdraw form (POST /withdrawals)                                  -->
    <!-- ===================================================================== -->
    <CBottomSheet
      :open="withdrawSheetOpen"
      :title="t('comp.balance.withdrawals.form.title')"
      @close="closeWithdrawSheet"
    >
      <form class="cbal__form" @submit.prevent="submitWithdraw">
        <label class="cbal__field">
          <span class="cbal__field-label">
            {{ t('comp.balance.withdrawals.form.amountLabel') }}
          </span>
          <input
            v-model="withdrawAmountInput"
            type="number"
            inputmode="decimal"
            step="0.01"
            min="0"
            class="cbal__input"
            :placeholder="t('comp.balance.withdrawals.form.amountPlaceholder')"
            :disabled="withdrawSubmitting"
            autofocus
          />
          <span class="cbal__field-hint">
            {{
              t('comp.balance.withdrawals.form.amountHint', {
                min: formatPrice(MIN_WITHDRAWAL_CENTS),
                max: formatPrice(MAX_WITHDRAWAL_CENTS),
                available: formatPrice(passiveConfirmed),
              })
            }}
          </span>
        </label>

        <p
          v-if="withdrawValidationKey"
          class="cbal__form-error cbal__form-error--soft"
        >
          {{
            t(withdrawValidationKey, {
              min: formatPrice(MIN_WITHDRAWAL_CENTS),
              max: formatPrice(MAX_WITHDRAWAL_CENTS),
              available: formatPrice(passiveConfirmed),
            })
          }}
        </p>

        <p v-if="withdrawError" class="cbal__form-error">
          {{ withdrawError }}
        </p>

        <div class="cbal__form-actions">
          <button
            type="button"
            class="cbal__btn cbal__btn--outline"
            :disabled="withdrawSubmitting"
            @click="closeWithdrawSheet"
          >
            {{ t('comp.balance.withdrawals.form.cancel') }}
          </button>
          <button
            type="submit"
            class="cbal__btn cbal__btn--primary"
            :disabled="!canSubmitWithdraw"
          >
            <span v-if="withdrawSubmitting" class="cbal__btn-spinner" />
            <span v-else>
              {{ t('comp.balance.withdrawals.form.submit') }}
            </span>
          </button>
        </div>
      </form>
    </CBottomSheet>

    <!-- ===================================================================== -->
    <!-- B4: Payout details form (PUT /users/me/payout-details)                 -->
    <!-- ===================================================================== -->
    <CBottomSheet
      :open="payoutSheetOpen"
      :title="t('comp.balance.payout.form.title')"
      @close="closePayoutSheet"
    >
      <form class="cbal__form" @submit.prevent="submitPayout">
        <label class="cbal__field">
          <span class="cbal__field-label">
            {{ t('comp.balance.payout.form.label') }}
          </span>
          <textarea
            v-model="payoutEditInput"
            class="cbal__textarea"
            :placeholder="t('comp.balance.payout.form.placeholder')"
            :disabled="payoutSubmitting"
            rows="10"
            spellcheck="false"
          />
          <span class="cbal__field-hint">
            {{ t('comp.balance.payout.form.hint') }}
          </span>
        </label>

        <p
          v-if="payoutValidationKey"
          class="cbal__form-error cbal__form-error--soft"
        >
          {{ t(payoutValidationKey) }}
        </p>

        <p v-if="payoutError" class="cbal__form-error">
          {{ payoutError }}
        </p>

        <div class="cbal__form-actions">
          <button
            type="button"
            class="cbal__btn cbal__btn--outline"
            :disabled="payoutSubmitting"
            @click="closePayoutSheet"
          >
            {{ t('comp.balance.payout.form.cancel') }}
          </button>
          <button
            type="submit"
            class="cbal__btn cbal__btn--primary"
            :disabled="!canSubmitPayout"
          >
            <span v-if="payoutSubmitting" class="cbal__btn-spinner" />
            <span v-else>
              {{ t('comp.balance.payout.form.submit') }}
            </span>
          </button>
        </div>
      </form>
    </CBottomSheet>
  </div>
</template>

<style scoped>
.cbal {
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 16px;
  padding-bottom: 24px;
}

/* Page header */
.cbal__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cbal__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}
.cbal__subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Whole-screen states */
.cbal__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: calc(100vh - 240px);
  min-height: calc(100dvh - 240px);
  padding: 24px;
  text-align: center;
}

/* Card base */
.cbal__card {
  padding: 16px 18px;
  border-radius: var(--radius);
  background: var(--bg-elevated, var(--bg));
  border: 1px solid var(--border);
}

/* Balance card */
.cbal__balance {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cbal__balance-head {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cbal__balance-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
}
.cbal__balance-frozen {
  font-size: 12px;
  color: var(--warning, var(--text-secondary));
}

/* Disabled CTA row + "Coming next" hint */
.cbal__cta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.cbal__cta-hint {
  font-size: 11px;
  font-style: italic;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Section */
.cbal__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cbal__section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin: 4px 0 0;
}

/* Empty placeholder */
.cbal__empty {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-elevated, var(--bg));
  border: 1px dashed var(--border);
  text-align: center;
}

/* Withdrawal list */
.cbal__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cbal__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-elevated, var(--bg));
  border: 1px solid var(--border);
}
.cbal__item-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.cbal__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cbal__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.cbal__item-line--sub {
  font-size: 11px;
  color: var(--text-tertiary);
}
.cbal__item-amount {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.cbal__item-date {
  white-space: nowrap;
}
.cbal__item-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--danger, var(--text-secondary));
  font-style: italic;
  text-align: right;
  max-width: 60%;
}

/* Status badge */
.cbal__badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: var(--radius-full, 999px);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.cbal__badge--success {
  background: var(--bg);
  color: var(--success, var(--primary));
  border: 1px solid var(--success, var(--primary));
}
.cbal__badge--warning {
  background: var(--bg);
  color: var(--warning, var(--text-secondary));
  border: 1px solid var(--warning, var(--border));
}
.cbal__badge--danger {
  background: var(--bg);
  color: var(--danger, #DC2626);
  border: 1px solid var(--danger, #DC2626);
}
.cbal__badge--neutral {
  background: var(--bg);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

/* Sentinel */
.cbal__sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 0 0;
  min-height: 32px;
}

/* Payout details JSON view -- consistent with Settings distribution_config */
.cbal__json {
  margin: 0;
  padding: 12px 14px;
  background: var(--bg-subtle, var(--bg));
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre;
  line-height: 1.5;
}

/* B4 -- form sheets */
.cbal__form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cbal__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cbal__field-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.cbal__field-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.cbal__input {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 16px;
  font-family: inherit;
  transition: border-color 0.15s;
}
.cbal__input:focus {
  outline: none;
  border-color: var(--primary);
}
.cbal__input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.cbal__textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1.5;
  resize: vertical;
  min-height: 160px;
  transition: border-color 0.15s;
}
.cbal__textarea:focus {
  outline: none;
  border-color: var(--primary);
}
.cbal__textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/*
 * Two error severities. --soft is a quiet client-side validation
 * notice (amber tint via border, no fill) that updates as the user
 * types. The non-soft variant is for backend errors after submit --
 * filled red so a 409 / 400 lands with weight.
 */
.cbal__form-error {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  background: var(--danger-dim, rgba(220, 38, 38, 0.08));
  border: 1px solid var(--danger, #DC2626);
  color: var(--danger, #DC2626);
}
.cbal__form-error--soft {
  background: transparent;
  border: 1px solid var(--warning, var(--border));
  color: var(--warning, var(--text-secondary));
}

.cbal__form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}

/*
 * Native button styles -- mirrors the CButton visuals (primary
 * filled accent, outline neutral, small variant) without going
 * through the component, because @click on <CButton> isn't being
 * picked up in this view (suspected attrs-fallthrough quirk).
 * Logout-style native <button> works reliably in the rest of the
 * project, so we follow that pattern here too.
 */
.cbal__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-weight: 600;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  white-space: nowrap;
}
.cbal__btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.cbal__btn--primary {
  background: var(--accent, var(--primary));
  color: #fff;
}
.cbal__btn--primary:hover:not(:disabled) {
  filter: brightness(0.92);
}
.cbal__btn--primary:disabled {
  background: var(--border);
  color: var(--text-tertiary);
  opacity: 1;
}

.cbal__btn--outline {
  background: transparent;
  color: var(--text-secondary);
  border: 2px solid var(--border);
}
.cbal__btn--outline:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}

.cbal__btn--sm {
  padding: 8px 14px;
  font-size: 13px;
}

.cbal__btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: cbal-spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes cbal-spin {
  to { transform: rotate(360deg); }
}
</style>
