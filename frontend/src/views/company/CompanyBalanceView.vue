<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyBalanceView (Phase F5.2 B3 + B4)
// =============================================================================
//
// The project's balance screen, opened from the balance in the top bar and from
// the Home tab. Shows:
//   1. The balance card (confirmed + on hold) from the companyDashboard store,
//      the way to all operations, and the withdrawal rules in words.
//   2. The active withdrawal request, when there is one, before anything else
//      can be asked: a request in review is visible above the button.
//   3. "Request withdrawal" -- a sheet asking for the network, the wallet and
//      the amount; the network and wallet are saved as the payout details when
//      they changed. The request goes to the Company's administrator.
//   4. Withdrawal history (paginated, infinite scroll, status badges).
//
// The withdrawal is used only inside AIVIS and changes no rights of the holders
// of parts.
//
// Withdrawal bounds (MIN/MAX) mirror the backend Sprint 6.3 config
// constants. Hardcoded for now -- when backend surfaces them via
// some /config endpoint, these constants come out.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowUpFromLine, CreditCard, ListChecks, Wallet } from '@/components/ui/icons'

import { useRouter } from 'vue-router'

import { CBottomSheet, CButton, CEmptyState, CLoader, CInput, CSelect } from '@/components/ui'
import { createWithdrawal, listMyWithdrawals } from '@/api/withdrawals'
import { getPayoutDetails, updatePayoutDetails } from '@/api/users'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useInfiniteScroll } from '@/composables/usePagination'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDateTime, formatPrice, parseAmountToCents } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { WithdrawalResponse } from '@/api/types'

const MIN_WITHDRAWAL_CENTS = 1000
const MAX_WITHDRAWAL_CENTS = 10_000_000
const PER_PAGE = 20

const { t, locale } = useI18n()
const router = useRouter()
const dashboardStore = useCompanyDashboardStore()
const { showToast } = useToast()

// ---------------------------------------------------------------------------
// Withdrawals list
// ---------------------------------------------------------------------------

const withdrawals = ref<WithdrawalResponse[]>([])
const withdrawalsTotal = ref(0)
const withdrawalsPage = ref(1)
const withdrawalsLoading = ref(false)
const withdrawalsErrored = ref(false)

// Round 4: epoch counter restored. Without it, an in-flight loadMore
// (page N) racing a fresh fetchWithdrawalsFirstPage (page 1, triggered
// by a new withdrawal) can append the stale page-N items on top of the
// freshly-loaded list, producing duplicates / out-of-order rows.
const withdrawalsEpoch = ref(0)

const sentinelRef = ref<HTMLElement | null>(null)

const hasMoreWithdrawals = computed(() => withdrawals.value.length < withdrawalsTotal.value)

async function fetchWithdrawalsFirstPage(): Promise<void> {
  // Bump epoch first so any in-flight loadMore knows its result is stale.
  const epoch = ++withdrawalsEpoch.value
  withdrawalsLoading.value = true
  withdrawalsErrored.value = false
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
  if (withdrawalsLoading.value || !hasMoreWithdrawals.value) return
  // Capture the current epoch -- we must NOT bump it (loadMore is a
  // continuation of the active session, not a new one). If a fresh
  // fetchWithdrawalsFirstPage runs while this request is in flight,
  // epochs diverge and we drop the stale response on the floor.
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
    // Non-destructive: keep already-loaded pages visible.
  } finally {
    if (epoch === withdrawalsEpoch.value) withdrawalsLoading.value = false
  }
}

useInfiniteScroll(sentinelRef, hasMoreWithdrawals, loadMoreWithdrawals)

// ---------------------------------------------------------------------------
// Payout details
// ---------------------------------------------------------------------------

const payoutDetails = ref<Record<string, unknown> | null>(null)
const payoutLoading = ref(false)
const payoutLoaded = ref(false)
const payoutErrored = ref(false)

// Round 4: epoch counter restored. Two parallel calls (e.g. mount-time
// fetch + a manual refresh after save) racing each other could let the
// older response overwrite the newer one. Epoch ensures only the latest
// invocation can mutate state.
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

const PAYOUT_NETWORKS = [
  { value: 'USDT-TRC20', label: 'USDT (TRC20)' },
  { value: 'USDT-ERC20', label: 'USDT (ERC20)' },
  { value: 'USDT-BSC20', label: 'USDT (BSC20)' },
]

const WALLET_RE = /^\S{10,128}$/

const savedNetwork = computed<string>(() => {
  const v = payoutDetails.value?.network
  return typeof v === 'string' ? v : ''
})
const savedWallet = computed<string>(() => {
  const v = payoutDetails.value?.wallet
  return typeof v === 'string' ? v : ''
})
const hasPayoutDetails = computed(() => savedNetwork.value !== '' && savedWallet.value !== '')

// ---------------------------------------------------------------------------
// Balance derived
// ---------------------------------------------------------------------------

const passiveConfirmed = computed(() => dashboardStore.summary?.passive_balance.confirmed ?? 0)
const passiveFrozen = computed(() => dashboardStore.summary?.passive_balance.frozen ?? 0)
const hasFrozen = computed(() => passiveFrozen.value > 0)

// ---------------------------------------------------------------------------
// Render policy -- spinner until balance + withdrawals first page +
// payout details all settle. Errors win over loading.
// ---------------------------------------------------------------------------

const initialLoading = computed(() => {
  if (hasError.value) return false
  if (dashboardStore.summary === null) return true
  if (withdrawalsLoading.value && withdrawals.value.length === 0) return true
  if (payoutLoading.value && !payoutLoaded.value) return true
  return false
})

const hasError = computed(
  () =>
    // Gate every error source on "no cached data to fall back on": a
    // transient reload failure (e.g. the refetch after a successful
    // withdrawal) must not blank the whole money screen and make the
    // balance vanish (review §2/2.2, mirrors AgentBalanceView).
    (dashboardStore.error !== null && dashboardStore.summary === null) ||
    (withdrawalsErrored.value && withdrawals.value.length === 0) ||
    (payoutErrored.value && !payoutLoaded.value),
)

// ---------------------------------------------------------------------------
// Withdrawal status helpers
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
  return tOrRaw(t, `comp.balance.withdrawals.status.${status}`, status)
}

// A request that is still in review or in payment: shown above the button.
const ACTIVE_STATUSES = ['pending', 'confirmed', 'processing']
const activeRequest = computed<WithdrawalResponse | null>(
  () => withdrawals.value.find((w) => ACTIVE_STATUSES.includes(w.status)) ?? null,
)

function goOperations(): void {
  void safeNavigate(
    router.push({ name: 'company-transactions' }),
    '[CompanyBalanceView] to operations',
  )
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

const parsedAmountCents = computed<number | null>(() =>
  parseAmountToCents(withdrawAmountInput.value),
)

const withdrawValidationKey = computed<string | null>(() => {
  const cents = parsedAmountCents.value
  if (cents === null) return null
  if (cents < MIN_WITHDRAWAL_CENTS) return 'comp.balance.withdrawals.form.errorBelowMin'
  if (cents > MAX_WITHDRAWAL_CENTS) return 'comp.balance.withdrawals.form.errorAboveMax'
  if (cents > passiveConfirmed.value) return 'comp.balance.withdrawals.form.errorInsuff'
  return null
})

const walletValid = computed(() => WALLET_RE.test(withdrawWallet.value.trim()))

const walletErrorKey = computed<string | null>(() => {
  const w = withdrawWallet.value.trim()
  if (w === '' || walletValid.value) return null
  return 'comp.balance.withdrawals.form.errorWallet'
})

const canSubmitWithdraw = computed(() => {
  if (withdrawSubmitting.value) return false
  if (withdrawNetwork.value === '' || !walletValid.value) return false
  if (parsedAmountCents.value === null) return false
  return withdrawValidationKey.value === null
})

const withdrawCtaState = computed(() => {
  if (passiveConfirmed.value < MIN_WITHDRAWAL_CENTS) {
    return { disabled: true, hintKey: 'comp.balance.withdrawals.form.errorInsuffCard' }
  }
  return { disabled: false, hintKey: null as string | null }
})

function openWithdrawSheet(): void {
  if (withdrawCtaState.value.disabled) return
  withdrawAmountInput.value = ''
  withdrawError.value = ''
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
    showToast(t('comp.balance.withdrawals.form.successToast'), 'success')
    closeWithdrawSheet()
    await Promise.all([dashboardStore.refresh(), fetchWithdrawalsFirstPage()])
  } catch (err) {
    withdrawError.value =
      err instanceof Error && err.message ? err.message : t('comp.balance.withdrawals.form.error')
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
  const dashboardPromise =
    dashboardStore.summary === null ? dashboardStore.refresh() : Promise.resolve()
  await Promise.all([dashboardPromise, fetchWithdrawalsFirstPage(), fetchPayoutDetails()])
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="cbal">
    <!-- Header -->
    <div class="cbal__header">
      <h1 class="cbal__title">
        {{ t('comp.balance.title') }}
      </h1>
      <p class="cbal__subtitle">
        {{ t('comp.balance.subtitle') }}
      </p>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="cbal__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="cbal__center">
      <CEmptyState :title="t('comp.balance.errorTitle')" />
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('comp.balance.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Balance card -->
      <section class="cbal__card cbal__balance">
        <div class="cbal__balance-head">
          <Wallet :size="16" />
          <span>{{ t('comp.balance.card.title') }}</span>
        </div>
        <div class="cbal__balance-value">
          {{ formatPrice(passiveConfirmed) }}
        </div>
        <div v-if="hasFrozen" class="cbal__balance-frozen">
          {{ t('comp.balance.card.frozen') }}: {{ formatPrice(passiveFrozen) }}
        </div>

        <div class="cbal__cta-row">
          <CButton
            variant="primary"
            :disabled="withdrawCtaState.disabled"
            @click="openWithdrawSheet"
          >
            <ArrowUpFromLine :size="16" />
            {{ t('comp.balance.withdrawals.newButton') }}
          </CButton>
          <CButton variant="outline" @click="goOperations">
            <ListChecks :size="16" />
            {{ t('comp.balance.operations') }}
          </CButton>
          <span v-if="withdrawCtaState.hintKey" class="cbal__cta-hint">
            {{ t(withdrawCtaState.hintKey) }}
          </span>
        </div>
        <p class="cbal__rule">
          {{
            t('comp.balance.rule', {
              min: formatPrice(MIN_WITHDRAWAL_CENTS),
              max: formatPrice(MAX_WITHDRAWAL_CENTS),
            })
          }}
        </p>
        <p class="cbal__rule">
          {{ t('comp.balance.internalUse') }}
        </p>
      </section>

      <!-- The active request, visible before another one is asked -->
      <section v-if="activeRequest" class="cbal__card cbal__active">
        <div class="cbal__active-head">
          {{ t('comp.balance.active.title') }}
        </div>
        <div class="cbal__item-line">
          <span class="cbal__item-amount">{{ formatPrice(activeRequest.amount_cents) }}</span>
          <span class="cbal__badge" :class="`cbal__badge--${statusVariant(activeRequest.status)}`">
            {{ statusLabel(activeRequest.status) }}
          </span>
        </div>
        <p class="cbal__rule">
          {{ t('comp.balance.active.note') }}
        </p>
      </section>

      <!-- Withdrawal history -->
      <section class="cbal__section">
        <h2 class="cbal__section-title">
          {{ t('comp.balance.withdrawals.title') }}
        </h2>

        <p v-if="withdrawals.length === 0 && !withdrawalsLoading" class="cbal__empty">
          {{ t('comp.balance.withdrawals.empty') }}
        </p>

        <ul v-else class="cbal__list">
          <li v-for="w in withdrawals" :key="w.id" class="cbal__item">
            <div class="cbal__item-icon">
              <CreditCard :size="16" />
            </div>
            <div class="cbal__item-body">
              <div class="cbal__item-line">
                <span class="cbal__item-amount">
                  {{ formatPrice(w.amount_cents) }}
                </span>
                <span class="cbal__badge" :class="`cbal__badge--${statusVariant(w.status)}`">
                  {{ statusLabel(w.status) }}
                </span>
              </div>
              <div class="cbal__item-line cbal__item-line--sub">
                <span class="cbal__item-date">{{ formatDateTime(w.created_at, locale) }}</span>
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

        <div v-if="withdrawals.length > 0" ref="sentinelRef" class="cbal__sentinel">
          <CLoader v-if="withdrawalsLoading" :size="20" />
        </div>
      </section>

      <!-- Payout details: saved by the withdrawal request -->
      <section class="cbal__section">
        <h2 class="cbal__section-title">
          {{ t('comp.balance.payout.title') }}
        </h2>

        <p v-if="!hasPayoutDetails" class="cbal__empty">
          {{ t('comp.balance.payout.empty') }}
        </p>
        <dl v-else class="cbal__payout">
          <div>
            <dt>{{ t('comp.balance.withdrawals.form.networkLabel') }}</dt>
            <dd>{{ savedNetwork }}</dd>
          </div>
          <div>
            <dt>{{ t('comp.balance.withdrawals.form.walletLabel') }}</dt>
            <dd>{{ savedWallet }}</dd>
          </div>
        </dl>
      </section>
    </template>

    <!-- Withdraw sheet -->
    <CBottomSheet
      :open="withdrawSheetOpen"
      :title="t('comp.balance.withdrawals.form.title')"
      @close="closeWithdrawSheet"
    >
      <form class="cbal__form" @submit.prevent="submitWithdraw">
        <CSelect
          v-model="withdrawNetwork"
          :label="t('comp.balance.withdrawals.form.networkLabel')"
          :options="PAYOUT_NETWORKS"
          :placeholder="t('comp.balance.withdrawals.form.networkPlaceholder')"
          :disabled="withdrawSubmitting"
        />

        <label class="cbal__field">
          <span class="cbal__field-label">
            {{ t('comp.balance.withdrawals.form.walletLabel') }}
          </span>
          <CInput
            v-model="withdrawWallet"
            class="cbal__control"
            size="compact"
            autocomplete="off"
            spellcheck="false"
            :placeholder="t('comp.balance.withdrawals.form.walletPlaceholder')"
            :disabled="withdrawSubmitting"
          />
        </label>
        <p v-if="walletErrorKey" class="cbal__form-error cbal__form-error--soft">
          {{ t(walletErrorKey) }}
        </p>

        <label class="cbal__field">
          <span class="cbal__field-label">
            {{ t('comp.balance.withdrawals.form.amountLabel') }}
          </span>
          <CInput
            v-model="withdrawAmountInput"
            class="cbal__control"
            size="compact"
            type="number"
            inputmode="decimal"
            step="0.01"
            min="0"
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

        <p v-if="withdrawValidationKey" class="cbal__form-error cbal__form-error--soft">
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
          <CButton
            variant="outline"
            type="button"
            :disabled="withdrawSubmitting"
            @click="closeWithdrawSheet"
          >
            {{ t('comp.balance.withdrawals.form.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            type="submit"
            :disabled="!canSubmitWithdraw"
            :loading="withdrawSubmitting"
          >
            {{ t('comp.balance.withdrawals.form.submit') }}
          </CButton>
        </div>
      </form>
    </CBottomSheet>
  </div>
</template>

<style scoped>
.cbal {
  display: flex;
  flex-direction: column;
  padding: var(--space-4);
  gap: var(--space-4);
  padding-block-end: var(--space-5);
}

.cbal__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.cbal__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.cbal__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.cbal__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-block-size: calc(100vh - 240px);
  min-block-size: calc(100dvh - 240px);
  padding: var(--space-5);
  text-align: center;
}

.cbal__card {
  padding: var(--space-4) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: thin solid var(--border-default);
}

.cbal__balance {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cbal__balance-head {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cbal__balance-value {
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
}
.cbal__balance-frozen {
  font-size: var(--fs-xs);
  color: var(--warning);
}

.cbal__cta-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-block-start: var(--space-3);
  flex-wrap: wrap;
}
.cbal__cta-hint {
  font-size: var(--fs-xs);
  font-style: italic;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.cbal__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cbal__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0 0;
}

.cbal__empty {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: thin dashed var(--border-default);
  text-align: center;
}

.cbal__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.cbal__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  border: thin solid var(--border-default);
}
.cbal__item-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: var(--size-md);
  block-size: var(--size-md);
  border-radius: var(--radius-sm);
  background: var(--bg-page);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.cbal__item-body {
  flex: 1;
  min-inline-size: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.cbal__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.cbal__item-line--sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
.cbal__item-amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.cbal__item-date {
  white-space: nowrap;
}
.cbal__item-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--danger);
  font-style: italic;
  text-align: end;
  max-inline-size: 60%;
}

.cbal__badge {
  display: inline-block;
  font-size: var(--fs-3xs);
  font-weight: 700;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-pill);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.cbal__badge--success {
  background: var(--bg-page);
  color: var(--success);
  border: thin solid var(--success);
}
.cbal__badge--warning {
  background: var(--bg-page);
  color: var(--warning);
  border: thin solid var(--warning);
}
.cbal__badge--danger {
  background: var(--bg-page);
  color: var(--danger);
  border: thin solid var(--danger);
}
.cbal__badge--neutral {
  background: var(--bg-page);
  color: var(--text-secondary);
  border: thin solid var(--border-default);
}

.cbal__sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-block-size: var(--size-md);
}

.cbal__json {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-subtle);
  border: thin solid var(--border-default);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre;
  line-height: 1.5;
}

.cbal__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.cbal__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
/* The field's own rhythm is the flex gap above; the kit group's bottom margin
   would add a second, larger one inside it. The payout box keeps the height it
   was given -- :deep() because that height belongs to the control, not the group. */
.cbal__control {
  margin-block-end: 0;
}
.cbal__control--payout :deep(.ds-input) {
  min-block-size: 160px;
}
.cbal__field-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cbal__field-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

.cbal__form-error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: thin solid var(--danger);
  color: var(--danger);
}
.cbal__form-error--soft {
  background: transparent;
  border: thin solid var(--warning);
  color: var(--warning);
}

.cbal__form-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-block-start: var(--space-1);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.cbal__subtitle {
  max-inline-size: var(--maxw-prose);
}

.cbal__rule {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}
.cbal__active {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: thin solid var(--warning);
}
.cbal__active-head {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-secondary);
}
.cbal__payout {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
.cbal__payout div {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}
.cbal__payout dt {
  color: var(--text-secondary);
}
.cbal__payout dd {
  margin: 0;
  color: var(--text-primary);
  word-break: break-all;
  text-align: end;
}
</style>
