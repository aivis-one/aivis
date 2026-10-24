<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentBalanceView (Task 3 Block D, Phase F6.2)
// =============================================================================
//
// The integrator's balance, reached from Partners (and from the balance in the
// top bar):
//   1. The commission card -- confirmed + frozen commission from the shared
//      stores/dashboard.ts (commissions land on the passive ledger, the
//      withdrawal account) -- with the withdrawal button and "All operations".
//   2. The buyer account card -- what the integrator tops up and spends on
//      parts of AIVIS only -- with "Top up". The two are different accounts
//      and are never added together.
//   3. The withdrawal sheet: the NETWORK and the WALLET are asked here, at the
//      withdrawal, with the amount. They are saved as the payout details
//      (PUT /users/me/payout-details, a free-form object on the backend) just
//      before the request (POST /withdrawals); there is no raw JSON editor
//      anywhere. The limits (minimum 10 USD) and the 14-day rule are written
//      in words in the sheet.
//   4. Withdrawal history (paginated, infinite scroll, status badges).
//
// FP notes:
//   FP-19 -- the frame owns the header (useScreenHeader); a back target to
//            Partners: the balance lies inside that tab.
//   FP-18 -- navigation goes through safeNavigate.
//   FP-15 -- withdrawal status rendered via tOrRaw.
//
// Withdrawal bounds mirror the Sprint 6.3 backend config; hardcoded
// until a /config endpoint surfaces them (TD-F14, same as
// CompanyBalanceView).
// =============================================================================

import { computed, onMounted, ref, useId, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronDown,
  CreditCard,
  ListChecks,
} from '@/components/ui/icons'

import { CAlert, CBadge, CBottomSheet, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { createWithdrawal, listMyWithdrawals } from '@/api/withdrawals'
import { getPayoutDetails, updatePayoutDetails } from '@/api/users'
import { useDashboardStore } from '@/stores/dashboard'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDateTime, formatPrice, parseAmountToCents } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { WithdrawalResponse } from '@/api/types'

const MIN_WITHDRAWAL_CENTS = 1000
const MAX_WITHDRAWAL_CENTS = 10_000_000
const PER_PAGE = 20

const router = useRouter()
const { t, locale } = useI18n()
const dashboardStore = useDashboardStore()
const { showToast } = useToast()

// The frame's header carries the title, the line under it and the way back to Partners.
useScreenHeader({
  title: () => t('agent.balance.title'),
  lead: () => t('agent.balance.subtitle'),
  back: { name: 'agent-partners' },
})

// ---------------------------------------------------------------------------
// Withdrawals list (epoch-guarded; mirrors CompanyBalanceView)
// ---------------------------------------------------------------------------

const withdrawals = ref<WithdrawalResponse[]>([])
const withdrawalsTotal = ref(0)
const withdrawalsPage = ref(1)
const withdrawalsLoading = ref(false)
const withdrawalsErrored = ref(false)
const withdrawalsEpoch = ref(0)
const withdrawalsLoadMoreErrored = ref(false)
const sentinelRef = ref<HTMLElement | null>(null)

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
    // FP-16 brake: flag the failure so the IntersectionObserver stops
    // re-firing; the retry banner lets the user resume. Non-destructive
    // -- already-loaded pages stay visible (review §3).
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

// FP-16 brake fed as the `paused` parameter -- a failed load-more
// suppresses the observer until the user taps retry.
useInfiniteScroll(sentinelRef, hasMoreWithdrawals, loadMoreWithdrawals, withdrawalsLoadMoreErrored)

// ---------------------------------------------------------------------------
// Payout details -- read to prefill the withdrawal sheet (network + wallet)
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

// The networks a payout can go to (the platform's USDT networks). The names are
// the networks' own and are not translated.
const PAYOUT_NETWORKS = [
  { value: 'USDT-TRC20', label: 'USDT (TRC20)' },
  { value: 'USDT-ERC20', label: 'USDT (ERC20)' },
  { value: 'USDT-BSC20', label: 'USDT (BSC20)' },
]

// A wallet address is one token without spaces; the chain's own format is the
// payout service's to judge.
const WALLET_RE = /^\S{10,128}$/

const savedNetwork = computed<string>(() => {
  const v = payoutDetails.value?.network
  return typeof v === 'string' ? v : ''
})
const savedWallet = computed<string>(() => {
  const v = payoutDetails.value?.wallet
  return typeof v === 'string' ? v : ''
})

// ---------------------------------------------------------------------------
// Balance derived (shared dashboard store)
// ---------------------------------------------------------------------------

const passiveConfirmed = computed(() => dashboardStore.passiveBalance.confirmed)
const passiveFrozen = computed(() => dashboardStore.passiveBalance.frozen)
const hasFrozen = computed(() => passiveFrozen.value > 0)

const accountConfirmed = computed(() => dashboardStore.activeBalance.confirmed)
const accountFrozen = computed(() => dashboardStore.activeBalance.frozen)

// ---------------------------------------------------------------------------
// Render policy -- spinner until balance + withdrawals + payout settle
// ---------------------------------------------------------------------------

const hasError = computed(
  () =>
    // Couple to the shared dashboard error ONLY when there is no
    // cached summary to fall back on -- otherwise a transient refresh
    // failure with a still-valid cached balance would hide the whole
    // screen and retry could not clear it (review §2).
    (dashboardStore.error !== null && dashboardStore.summary === null) ||
    // Same "no cached data to fall back on" gate for the local fetches:
    // a transient reload failure after a first page already loaded (e.g.
    // the refetch right after a successful withdrawal) must not replace
    // the whole screen with an error and make the balance vanish (2.2).
    (withdrawalsErrored.value && withdrawals.value.length === 0) ||
    (payoutErrored.value && !payoutLoaded.value),
)

const initialLoading = computed(() => {
  if (hasError.value) return false
  if (dashboardStore.summary === null) return true
  if (withdrawalsLoading.value && withdrawals.value.length === 0) return true
  if (payoutLoading.value && !payoutLoaded.value) return true
  return false
})

// ---------------------------------------------------------------------------
// Withdrawal status helpers (FP-15)
// ---------------------------------------------------------------------------

type StatusVariant = 'success' | 'warning' | 'danger' | 'neutral'

function statusVariant(status: string): StatusVariant {
  if (status === 'completed') return 'success'
  if (status === 'pending' || status === 'confirmed' || status === 'processing') {
    return 'warning'
  }
  if (status === 'rejected' || status === 'failed') return 'danger'
  return 'neutral'
}

function statusLabel(status: string): string {
  return tOrRaw(t, `agent.balance.withdrawals.status.${status}`, status)
}

// ---------------------------------------------------------------------------
// Withdraw form
// ---------------------------------------------------------------------------

const withdrawSheetOpen = ref(false)
const withdrawAmountInput = ref('')
const withdrawSubmitting = ref(false)
const withdrawError = ref('')
const withdrawNetwork = ref('')
const withdrawWallet = ref('')

// The ids that tie the withdrawal form's labels, hints and messages to their fields.
const formId = useId()
const networkId = `${formId}-network`
const walletId = `${formId}-wallet`
const amountId = `${formId}-amount`

const parsedAmountCents = computed<number | null>(() =>
  parseAmountToCents(withdrawAmountInput.value),
)

const withdrawValidationKey = computed<string | null>(() => {
  const cents = parsedAmountCents.value
  if (cents === null) return null
  if (cents < MIN_WITHDRAWAL_CENTS) {
    return 'agent.balance.withdrawals.form.errorBelowMin'
  }
  if (cents > MAX_WITHDRAWAL_CENTS) {
    return 'agent.balance.withdrawals.form.errorAboveMax'
  }
  if (cents > passiveConfirmed.value) {
    return 'agent.balance.withdrawals.form.errorInsuff'
  }
  return null
})

const walletValid = computed(() => WALLET_RE.test(withdrawWallet.value.trim()))

const walletErrorKey = computed<string | null>(() => {
  const w = withdrawWallet.value.trim()
  if (w === '' || walletValid.value) return null
  return 'agent.balance.withdrawals.form.errorWallet'
})

const canSubmitWithdraw = computed(() => {
  if (withdrawSubmitting.value) return false
  if (withdrawNetwork.value === '' || !walletValid.value) return false
  if (parsedAmountCents.value === null) return false
  return withdrawValidationKey.value === null
})

// The button is live at or above the minimum. The network and the wallet are
// asked in the sheet, so nothing else gates it.
const canWithdraw = computed(() => passiveConfirmed.value >= MIN_WITHDRAWAL_CENTS)

function goDeposit(): void {
  void safeNavigate(router.push({ name: 'agent-deposit' }), '[AgentBalanceView] to deposit')
}

function goOperations(): void {
  void safeNavigate(router.push({ name: 'agent-transactions' }), '[AgentBalanceView] to operations')
}

function openWithdrawSheet(): void {
  if (!canWithdraw.value) return
  // The sheet opens on the saved network and wallet, when there are any.
  withdrawNetwork.value = savedNetwork.value
  withdrawWallet.value = savedWallet.value
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
    const network = withdrawNetwork.value
    const wallet = withdrawWallet.value.trim()
    if (network !== savedNetwork.value || wallet !== savedWallet.value) {
      await updatePayoutDetails({ network, wallet })
      payoutDetails.value = { network, wallet }
    }
    await createWithdrawal(cents)
    showToast(t('agent.balance.withdrawals.form.successToast'), 'success')
    closeWithdrawSheet()
    await Promise.all([dashboardStore.refresh(), fetchWithdrawalsFirstPage()])
  } catch (err) {
    withdrawError.value =
      err instanceof Error && err.message ? err.message : t('agent.balance.withdrawals.form.error')
    // Re-read the saved details, so the next opening of the sheet shows what
    // the server holds.
    void fetchPayoutDetails()
  } finally {
    withdrawSubmitting.value = false
  }
}

watch(withdrawSheetOpen, (open) => {
  if (!open) {
    withdrawAmountInput.value = ''
    withdrawError.value = ''
    withdrawNetwork.value = ''
    withdrawWallet.value = ''
  }
})

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

async function loadAll(): Promise<void> {
  // Refresh the dashboard unconditionally (parity with the investor
  // BalanceView). A conditional "only if summary is null" refresh left
  // retry unable to clear a stale shared error (review §2).
  await Promise.all([dashboardStore.refresh(), fetchWithdrawalsFirstPage(), fetchPayoutDetails()])
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <!-- Initial loading -->
  <CLoader v-if="initialLoading" centered extent="page" />

  <!-- Error -->
  <CEmptyState v-else-if="hasError" tone="danger" :title="t('agent.balance.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="loadAll">
        {{ t('agent.balance.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else>
    <!-- The commission, the withdrawal account: withdrawn on request; All operations -->
    <section class="ds-card" aria-labelledby="abal-commission">
      <header class="ds-card__head">
        <h2 id="abal-commission" class="ds-card__title">{{ t('agent.balance.card.title') }}</h2>
      </header>
      <p class="ds-card__figure">{{ formatPrice(passiveConfirmed) }}</p>
      <div v-if="hasFrozen">
        <CBadge
          variant="warning"
          :text="`${t('agent.balance.card.frozen')}: ${formatPrice(passiveFrozen)}`"
        />
      </div>
      <p class="ds-card__body">
        {{ t('agent.balance.withdrawals.rule', { min: formatPrice(MIN_WITHDRAWAL_CENTS) }) }}
        <template v-if="!canWithdraw">
          {{ t('agent.balance.withdrawals.lowBalance') }}
        </template>
      </p>
      <footer class="ds-card__foot">
        <CButton variant="primary" inline :disabled="!canWithdraw" @click="openWithdrawSheet">
          <ArrowUpFromLine size="sm" />
          {{ t('agent.balance.withdrawals.newButton') }}
        </CButton>
        <CButton variant="outline" inline @click="goOperations">
          <ListChecks size="sm" />
          {{ t('agent.balance.account.operations') }}
        </CButton>
      </footer>
    </section>

    <!-- The buyer account: topped up, spent on parts of AIVIS only -->
    <section class="ds-card" aria-labelledby="abal-account">
      <header class="ds-card__head">
        <h2 id="abal-account" class="ds-card__title">{{ t('agent.balance.account.title') }}</h2>
      </header>
      <p class="ds-card__figure">{{ formatPrice(accountConfirmed) }}</p>
      <div v-if="accountFrozen > 0">
        <CBadge
          variant="warning"
          :text="`${t('agent.balance.account.frozen')}: ${formatPrice(accountFrozen)}`"
        />
      </div>
      <p class="ds-card__body">{{ t('agent.balance.account.hint') }}</p>
      <footer class="ds-card__foot">
        <CButton variant="primary" inline @click="goDeposit">
          <ArrowDownToLine size="sm" />
          {{ t('agent.balance.account.deposit') }}
        </CButton>
      </footer>
    </section>

    <!-- Withdrawal history -->
    <section class="abal__section" aria-labelledby="abal-history">
      <h2 id="abal-history" class="ds-section-title">
        {{ t('agent.balance.withdrawals.title') }}
      </h2>

      <CEmptyState
        v-if="withdrawals.length === 0 && !withdrawalsLoading"
        framed
        :description="t('agent.balance.withdrawals.empty')"
      />

      <ul v-else class="ds-rows">
        <li v-for="w in withdrawals" :key="w.id" class="ds-row">
          <span class="ds-row__lead"><CreditCard size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ formatPrice(w.amount_cents) }}</span>
            <span class="ds-row__meta">
              {{ formatDateTime(w.created_at, locale) }}
              <template v-if="w.rejection_reason"> · {{ w.rejection_reason }}</template>
            </span>
          </span>
          <span class="ds-row__trail">
            <CBadge :variant="statusVariant(w.status)" :text="statusLabel(w.status)" />
          </span>
        </li>
      </ul>

      <div v-if="withdrawals.length > 0" ref="sentinelRef" class="abal__sentinel">
        <CLoader v-if="withdrawalsLoading" :size="24" />
      </div>

      <CAlert
        v-if="withdrawals.length > 0 && withdrawalsLoadMoreErrored && !withdrawalsLoading"
        tone="danger"
      >
        {{ t('agent.balance.withdrawals.loadMoreError') }}
        <template #actions>
          <CButton variant="outline" size="sm" inline @click="retryLoadMoreWithdrawals">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CAlert>
    </section>
  </template>

  <!-- Withdraw sheet: the structured payout form (K35) -->
  <CBottomSheet
    :open="withdrawSheetOpen"
    :title="t('agent.balance.withdrawals.form.title')"
    @close="closeWithdrawSheet"
  >
    <form
      class="ds-payout"
      novalidate
      :aria-label="t('agent.balance.withdrawals.form.title')"
      :aria-busy="withdrawSubmitting || undefined"
      @submit.prevent="submitWithdraw"
    >
      <CAlert v-if="withdrawError" tone="danger">{{ withdrawError }}</CAlert>

      <fieldset class="ds-payout__group" :disabled="withdrawSubmitting">
        <legend class="ds-payout__legend">
          {{ t('agent.balance.withdrawals.form.groupPayee') }}
        </legend>
        <div class="ds-payout__grid">
          <div class="ds-field">
            <label class="ds-field__label" :for="networkId">
              {{ t('agent.balance.withdrawals.form.networkLabel') }}
            </label>
            <div class="ds-select">
              <select :id="networkId" v-model="withdrawNetwork" class="ds-input">
                <option value="" disabled>
                  {{ t('agent.balance.withdrawals.form.networkPlaceholder') }}
                </option>
                <option v-for="opt in PAYOUT_NETWORKS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <ChevronDown size="sm" />
            </div>
          </div>

          <div class="ds-field">
            <label class="ds-field__label" :for="walletId">
              {{ t('agent.balance.withdrawals.form.walletLabel') }}
            </label>
            <input
              :id="walletId"
              v-model="withdrawWallet"
              class="ds-input ds-input--num"
              type="text"
              autocomplete="off"
              spellcheck="false"
              :placeholder="t('agent.balance.withdrawals.form.walletPlaceholder')"
              :aria-invalid="walletErrorKey ? 'true' : undefined"
              :aria-describedby="walletErrorKey ? `${walletId}-error` : undefined"
            />
            <p v-if="walletErrorKey" :id="`${walletId}-error`" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>{{ t(walletErrorKey) }}</span>
            </p>
          </div>
        </div>
      </fieldset>

      <fieldset class="ds-payout__group" :disabled="withdrawSubmitting">
        <legend class="ds-payout__legend">
          {{ t('agent.balance.withdrawals.form.groupAmount') }}
        </legend>
        <div class="ds-payout__grid">
          <div class="ds-field ds-payout__wide">
            <label class="ds-field__label" :for="amountId">
              {{ t('agent.balance.withdrawals.form.amountLabel') }}
            </label>
            <input
              :id="amountId"
              v-model="withdrawAmountInput"
              class="ds-input ds-input--num"
              type="number"
              inputmode="decimal"
              step="0.01"
              min="0"
              :placeholder="t('agent.balance.withdrawals.form.amountPlaceholder')"
              :aria-invalid="withdrawValidationKey ? 'true' : undefined"
              :aria-describedby="
                withdrawValidationKey ? `${amountId}-hint ${amountId}-error` : `${amountId}-hint`
              "
            />
            <p :id="`${amountId}-hint`" class="ds-field__hint">
              {{
                t('agent.balance.withdrawals.form.amountHint', {
                  min: formatPrice(MIN_WITHDRAWAL_CENTS),
                  max: formatPrice(MAX_WITHDRAWAL_CENTS),
                  available: formatPrice(passiveConfirmed),
                })
              }}
            </p>
            <p v-if="withdrawValidationKey" :id="`${amountId}-error`" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>
                {{
                  t(withdrawValidationKey, {
                    min: formatPrice(MIN_WITHDRAWAL_CENTS),
                    max: formatPrice(MAX_WITHDRAWAL_CENTS),
                    available: formatPrice(passiveConfirmed),
                  })
                }}
              </span>
            </p>
          </div>
        </div>
      </fieldset>

      <div class="ds-payout__actions">
        <CButton
          variant="primary"
          type="submit"
          inline
          :disabled="!canSubmitWithdraw"
          :loading="withdrawSubmitting"
        >
          {{ t('agent.balance.withdrawals.form.submit') }}
        </CButton>
        <CButton
          variant="link"
          type="button"
          :disabled="withdrawSubmitting"
          @click="closeWithdrawSheet"
        >
          {{ t('agent.balance.withdrawals.form.cancel') }}
        </CButton>
      </div>
    </form>
  </CBottomSheet>
</template>

<style scoped>
/* The history: a heading over its rows, on the frame's rhythm. */
.abal__section {
  display: grid;
  gap: var(--space-3);
}

/* The load-more sentinel the scroll observer watches. */
.abal__sentinel {
  display: grid;
  place-items: center;
  min-block-size: var(--size-md);
}
</style>
