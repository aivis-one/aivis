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

import { computed, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ArrowUpFromLine,
  ChevronDown,
  CreditCard,
  ListChecks,
} from '@/components/ui/icons'

import { useRouter } from 'vue-router'

import { CAlert, CBadge, CBottomSheet, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
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

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('comp.balance.title'),
  lead: () => t('comp.balance.subtitle'),
})

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
  <!-- Initial loading -->
  <CLoader v-if="initialLoading" centered extent="page" />

  <!-- Error -->
  <CEmptyState v-else-if="hasError" tone="danger" :title="t('comp.balance.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="loadAll">
        {{ t('comp.balance.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else>
    <!-- Balance card -->
    <section class="ds-card" aria-labelledby="cbal-card">
      <header class="ds-card__head">
        <h2 id="cbal-card" class="ds-card__title">{{ t('comp.balance.card.title') }}</h2>
      </header>
      <p class="ds-card__figure">{{ formatPrice(passiveConfirmed) }}</p>
      <div v-if="hasFrozen">
        <CBadge
          variant="warning"
          :text="`${t('comp.balance.card.frozen')}: ${formatPrice(passiveFrozen)}`"
        />
      </div>
      <p v-if="withdrawCtaState.hintKey" class="ds-card__body">
        {{ t(withdrawCtaState.hintKey) }}
      </p>
      <p class="ds-card__body">
        {{
          t('comp.balance.rule', {
            min: formatPrice(MIN_WITHDRAWAL_CENTS),
            max: formatPrice(MAX_WITHDRAWAL_CENTS),
          })
        }}
      </p>
      <p class="ds-card__body">
        {{ t('comp.balance.internalUse') }}
      </p>
      <footer class="ds-card__foot">
        <CButton
          variant="primary"
          inline
          :disabled="withdrawCtaState.disabled"
          @click="openWithdrawSheet"
        >
          <ArrowUpFromLine size="sm" />
          {{ t('comp.balance.withdrawals.newButton') }}
        </CButton>
        <CButton variant="outline" inline @click="goOperations">
          <ListChecks size="sm" />
          {{ t('comp.balance.operations') }}
        </CButton>
      </footer>
    </section>

    <!-- The active request, visible before another one is asked -->
    <section v-if="activeRequest" class="ds-card ds-card--flat" aria-labelledby="cbal-active">
      <header class="ds-card__head">
        <h2 id="cbal-active" class="ds-card__title">{{ t('comp.balance.active.title') }}</h2>
        <CBadge
          :variant="statusVariant(activeRequest.status)"
          :text="statusLabel(activeRequest.status)"
        />
      </header>
      <p class="ds-card__figure">{{ formatPrice(activeRequest.amount_cents) }}</p>
      <p class="ds-card__body">
        {{ t('comp.balance.active.note') }}
      </p>
    </section>

    <!-- Withdrawal history -->
    <section class="cbal__section" aria-labelledby="cbal-history">
      <h2 id="cbal-history" class="ds-section-title">
        {{ t('comp.balance.withdrawals.title') }}
      </h2>

      <CEmptyState
        v-if="withdrawals.length === 0 && !withdrawalsLoading"
        framed
        :description="t('comp.balance.withdrawals.empty')"
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

      <div v-if="withdrawals.length > 0" ref="sentinelRef" class="cbal__sentinel">
        <CLoader v-if="withdrawalsLoading" :size="24" />
      </div>
    </section>

    <!-- Payout details: saved by the withdrawal request -->
    <section class="cbal__section" aria-labelledby="cbal-payout">
      <h2 id="cbal-payout" class="ds-section-title">
        {{ t('comp.balance.payout.title') }}
      </h2>

      <CEmptyState v-if="!hasPayoutDetails" framed :description="t('comp.balance.payout.empty')" />
      <dl v-else class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('comp.balance.withdrawals.form.networkLabel') }}</dt>
          <dd>{{ savedNetwork }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('comp.balance.withdrawals.form.walletLabel') }}</dt>
          <dd>{{ savedWallet }}</dd>
        </div>
      </dl>
    </section>
  </template>

  <!-- Withdraw sheet: the structured payout form (K35) -->
  <CBottomSheet
    :open="withdrawSheetOpen"
    :title="t('comp.balance.withdrawals.form.title')"
    @close="closeWithdrawSheet"
  >
    <form
      class="ds-payout"
      novalidate
      :aria-label="t('comp.balance.withdrawals.form.title')"
      :aria-busy="withdrawSubmitting || undefined"
      @submit.prevent="submitWithdraw"
    >
      <CAlert v-if="withdrawError" tone="danger">{{ withdrawError }}</CAlert>

      <fieldset class="ds-payout__group" :disabled="withdrawSubmitting">
        <legend class="ds-payout__legend">
          {{ t('comp.balance.withdrawals.form.groupPayee') }}
        </legend>
        <div class="ds-payout__grid">
          <div class="ds-field">
            <label class="ds-field__label" :for="networkId">
              {{ t('comp.balance.withdrawals.form.networkLabel') }}
            </label>
            <div class="ds-select">
              <select :id="networkId" v-model="withdrawNetwork" class="ds-input">
                <option value="" disabled>
                  {{ t('comp.balance.withdrawals.form.networkPlaceholder') }}
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
              {{ t('comp.balance.withdrawals.form.walletLabel') }}
            </label>
            <input
              :id="walletId"
              v-model="withdrawWallet"
              class="ds-input ds-input--num"
              type="text"
              autocomplete="off"
              spellcheck="false"
              :placeholder="t('comp.balance.withdrawals.form.walletPlaceholder')"
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
          {{ t('comp.balance.withdrawals.form.groupAmount') }}
        </legend>
        <div class="ds-payout__grid">
          <div class="ds-field ds-payout__wide">
            <label class="ds-field__label" :for="amountId">
              {{ t('comp.balance.withdrawals.form.amountLabel') }}
            </label>
            <input
              :id="amountId"
              v-model="withdrawAmountInput"
              class="ds-input ds-input--num"
              type="number"
              inputmode="decimal"
              step="0.01"
              min="0"
              autofocus
              :placeholder="t('comp.balance.withdrawals.form.amountPlaceholder')"
              :aria-invalid="withdrawValidationKey ? 'true' : undefined"
              :aria-describedby="
                withdrawValidationKey ? `${amountId}-hint ${amountId}-error` : `${amountId}-hint`
              "
            />
            <p :id="`${amountId}-hint`" class="ds-field__hint">
              {{
                t('comp.balance.withdrawals.form.amountHint', {
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
          {{ t('comp.balance.withdrawals.form.submit') }}
        </CButton>
        <CButton
          variant="link"
          type="button"
          :disabled="withdrawSubmitting"
          @click="closeWithdrawSheet"
        >
          {{ t('comp.balance.withdrawals.form.cancel') }}
        </CButton>
      </div>
    </form>
  </CBottomSheet>
</template>

<style scoped>
/* A section: its heading over its content, on the frame's rhythm. */
.cbal__section {
  display: grid;
  gap: var(--space-3);
}

/* The load-more sentinel the scroll observer watches. */
.cbal__sentinel {
  display: grid;
  place-items: center;
  min-block-size: var(--size-md);
}
</style>
