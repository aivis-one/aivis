<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentBalanceView (Task 3 Block D, Phase F6.2)
// =============================================================================
//
// Replaces the F6.2 stub. The agent's passive (earnings) balance tab:
//   1. Passive balance card (confirmed + frozen) from the shared
//      stores/dashboard.ts -- commissions land on the passive ledger,
//      so passive_balance IS the agent's earnings. One endpoint, one
//      store (same source AgentDashboardView uses).
//   2. Withdrawal CTA + bottom-sheet form (amount, client validation,
//      POST /withdrawals). FP-04 double-submit guard via
//      withdrawSubmitting. avatar mode is blocked server-side (403) --
//      the backend message is shown in the form, not crashed on.
//   3. Withdrawal history (paginated, infinite scroll, status badges).
//
// PAYOUT DETAILS LIVE IN SETTINGS (decision B).
//   This view does NOT edit payout details -- it only reads them as a
//   boolean gate. With none set, the CTA becomes "Set up payout
//   details" -> AgentSettingsView (safeNavigate), so the user is led
//   there instead of hitting a raw 400 "configure payout details
//   first". Backup: if details are cleared mid-session, a failed
//   submit re-fetches the gate so the CTA flips back.
//
// FP notes:
//   FP-19 -- shell owns the header; inline abal__header h1. No back-link:
//            /agent/balance is a top-level tab (AGENT_TABS).
//   FP-18 -- the Settings link navigates via safeNavigate.
//   FP-15 -- withdrawal status rendered via tOrRaw.
//
// Withdrawal bounds mirror the Sprint 6.3 backend config; hardcoded
// until a /config endpoint surfaces them (TD-F14, same as
// CompanyBalanceView).
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowUpFromLine, CreditCard, Wallet } from 'lucide-vue-next'

import { CBottomSheet, CButton, CEmptyState, CLoader } from '@/components/ui'
import { createWithdrawal, listMyWithdrawals } from '@/api/withdrawals'
import { getPayoutDetails } from '@/api/users'
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

const hasMoreWithdrawals = computed(
  () => withdrawals.value.length < withdrawalsTotal.value,
)

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
  if (
    withdrawalsLoading.value
    || !hasMoreWithdrawals.value
    || withdrawalsLoadMoreErrored.value
  ) {
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
useInfiniteScroll(
  sentinelRef,
  hasMoreWithdrawals,
  loadMoreWithdrawals,
  withdrawalsLoadMoreErrored,
)

// ---------------------------------------------------------------------------
// Payout details -- boolean gate only (editor lives in AgentSettingsView)
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

// ---------------------------------------------------------------------------
// Balance derived (shared dashboard store)
// ---------------------------------------------------------------------------

const passiveConfirmed = computed(() => dashboardStore.passiveBalance.confirmed)
const passiveFrozen = computed(() => dashboardStore.passiveBalance.frozen)
const hasFrozen = computed(() => passiveFrozen.value > 0)

// ---------------------------------------------------------------------------
// Render policy -- spinner until balance + withdrawals + payout settle
// ---------------------------------------------------------------------------

const hasError = computed(
  () =>
    // Couple to the shared dashboard error ONLY when there is no
    // cached summary to fall back on -- otherwise a transient refresh
    // failure with a still-valid cached balance would hide the whole
    // screen and retry could not clear it (review §2).
    (dashboardStore.error !== null && dashboardStore.summary === null)
    // Same "no cached data to fall back on" gate for the local fetches:
    // a transient reload failure after a first page already loaded (e.g.
    // the refetch right after a successful withdrawal) must not replace
    // the whole screen with an error and make the balance vanish (2.2).
    || (withdrawalsErrored.value && withdrawals.value.length === 0)
    || (payoutErrored.value && !payoutLoaded.value),
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

const parsedAmountCents = computed<number | null>(
  () => parseAmountToCents(withdrawAmountInput.value),
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

const canSubmitWithdraw = computed(() => {
  if (withdrawSubmitting.value) return false
  if (!hasPayoutDetails.value) return false
  if (parsedAmountCents.value === null) return false
  return withdrawValidationKey.value === null
})

// Withdraw button is live only with payout details set AND a balance
// at or above the minimum. Without payout details the CTA is replaced
// by the "set up payout details" link (Balance -> Settings stitch).
const canWithdraw = computed(
  () => hasPayoutDetails.value && passiveConfirmed.value >= MIN_WITHDRAWAL_CENTS,
)

function goSettingsForPayout(): void {
  void safeNavigate(
    router.push({ name: 'agent-settings' }),
    '[AgentBalanceView] to settings for payout details',
  )
}

function openWithdrawSheet(): void {
  if (!canWithdraw.value) return
  // Fields are cleared by the close watcher below; just open.
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
    showToast(t('agent.balance.withdrawals.form.successToast'), 'success')
    closeWithdrawSheet()
    await Promise.all([dashboardStore.refresh(), fetchWithdrawalsFirstPage()])
  } catch (err) {
    withdrawError.value =
      err instanceof Error && err.message
        ? err.message
        : t('agent.balance.withdrawals.form.error')
    // Backup for the Balance -> Settings stitch: if payout details were
    // cleared mid-session (the backend 400), re-read the gate so the
    // CTA flips back to "set up payout details" once the sheet closes.
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
// Lifecycle
// ---------------------------------------------------------------------------

async function loadAll(): Promise<void> {
  // Refresh the dashboard unconditionally (parity with the investor
  // BalanceView). A conditional "only if summary is null" refresh left
  // retry unable to clear a stale shared error (review §2).
  await Promise.all([
    dashboardStore.refresh(),
    fetchWithdrawalsFirstPage(),
    fetchPayoutDetails(),
  ])
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="abal">
    <!-- Header (FP-19: shell owns the header; tab -> no back-link) -->
    <div class="abal__header">
      <h1 class="abal__title">{{ t('agent.balance.title') }}</h1>
      <p class="abal__subtitle">{{ t('agent.balance.subtitle') }}</p>
    </div>

    <!-- Initial loading -->
    <div v-if="initialLoading" class="abal__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="abal__center">
      <CEmptyState :title="t('agent.balance.errorTitle')" />
      <CButton variant="outline" size="sm" @click="loadAll">
        {{ t('agent.balance.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Balance card -->
      <section class="abal__card abal__balance">
        <div class="abal__balance-head">
          <Wallet :size="16" />
          <span>{{ t('agent.balance.card.title') }}</span>
        </div>
        <div class="abal__balance-value">{{ formatPrice(passiveConfirmed) }}</div>
        <div v-if="hasFrozen" class="abal__balance-frozen">
          {{ t('agent.balance.card.frozen') }}: {{ formatPrice(passiveFrozen) }}
        </div>

        <div class="abal__cta-row">
          <!-- No payout details: lead the user to Settings (decision B) -->
          <template v-if="!hasPayoutDetails">
            <CButton variant="primary" @click="goSettingsForPayout">
              <CreditCard :size="16" />
              {{ t('agent.balance.withdrawals.setupPayout') }}
            </CButton>
            <span class="abal__cta-hint">
              {{ t('agent.balance.withdrawals.needPayout') }}
            </span>
          </template>
          <!-- Payout details present: normal withdraw CTA -->
          <template v-else>
            <CButton
              variant="primary"
              :disabled="!canWithdraw"
              @click="openWithdrawSheet"
            >
              <ArrowUpFromLine :size="16" />
              {{ t('agent.balance.withdrawals.newButton') }}
            </CButton>
            <span v-if="!canWithdraw" class="abal__cta-hint">
              {{ t('agent.balance.withdrawals.lowBalance') }}
            </span>
          </template>
        </div>
      </section>

      <!-- Withdrawal history -->
      <section class="abal__section">
        <h2 class="abal__section-title">
          {{ t('agent.balance.withdrawals.title') }}
        </h2>

        <p
          v-if="withdrawals.length === 0 && !withdrawalsLoading"
          class="abal__empty"
        >
          {{ t('agent.balance.withdrawals.empty') }}
        </p>

        <ul v-else class="abal__list">
          <li v-for="w in withdrawals" :key="w.id" class="abal__item">
            <div class="abal__item-icon">
              <CreditCard :size="16" />
            </div>
            <div class="abal__item-body">
              <div class="abal__item-line">
                <span class="abal__item-amount">
                  {{ formatPrice(w.amount_cents) }}
                </span>
                <span
                  class="abal__badge"
                  :class="`abal__badge--${statusVariant(w.status)}`"
                >
                  {{ statusLabel(w.status) }}
                </span>
              </div>
              <div class="abal__item-line abal__item-line--sub">
                <span class="abal__item-date">{{ formatDateTime(w.created_at, locale) }}</span>
                <span
                  v-if="w.rejection_reason"
                  class="abal__item-reason"
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
          class="abal__sentinel"
        >
          <CLoader v-if="withdrawalsLoading" :size="20" />
        </div>

        <div
          v-if="withdrawals.length > 0 && withdrawalsLoadMoreErrored && !withdrawalsLoading"
          class="abal__loadmore-error"
        >
          <span>{{ t('agent.balance.withdrawals.loadMoreError') }}</span>
          <CButton variant="outline" size="sm" @click="retryLoadMoreWithdrawals">
            {{ t('common.retry') }}
          </CButton>
        </div>
      </section>
    </template>

    <!-- Withdraw sheet -->
    <CBottomSheet
      :open="withdrawSheetOpen"
      :title="t('agent.balance.withdrawals.form.title')"
      @close="closeWithdrawSheet"
    >
      <form class="abal__form" @submit.prevent="submitWithdraw">
        <label class="abal__field">
          <span class="abal__field-label">
            {{ t('agent.balance.withdrawals.form.amountLabel') }}
          </span>
          <input
            v-model="withdrawAmountInput"
            type="number"
            inputmode="decimal"
            step="0.01"
            min="0"
            class="abal__input"
            :placeholder="t('agent.balance.withdrawals.form.amountPlaceholder')"
            :disabled="withdrawSubmitting"
          />
          <span class="abal__field-hint">
            {{
              t('agent.balance.withdrawals.form.amountHint', {
                min: formatPrice(MIN_WITHDRAWAL_CENTS),
                max: formatPrice(MAX_WITHDRAWAL_CENTS),
                available: formatPrice(passiveConfirmed),
              })
            }}
          </span>
        </label>

        <p
          v-if="withdrawValidationKey"
          class="abal__form-error abal__form-error--soft"
        >
          {{
            t(withdrawValidationKey, {
              min: formatPrice(MIN_WITHDRAWAL_CENTS),
              max: formatPrice(MAX_WITHDRAWAL_CENTS),
              available: formatPrice(passiveConfirmed),
            })
          }}
        </p>

        <p v-if="withdrawError" class="abal__form-error">{{ withdrawError }}</p>

        <div class="abal__form-actions">
          <CButton
            variant="outline"
            type="button"
            :disabled="withdrawSubmitting"
            @click="closeWithdrawSheet"
          >
            {{ t('agent.balance.withdrawals.form.cancel') }}
          </CButton>
          <CButton
            variant="primary"
            type="submit"
            :disabled="!canSubmitWithdraw"
            :loading="withdrawSubmitting"
          >
            {{ t('agent.balance.withdrawals.form.submit') }}
          </CButton>
        </div>
      </form>
    </CBottomSheet>
  </div>
</template>

<style scoped>
.abal {
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 16px;
  padding-bottom: 24px;
}

.abal__header { display: flex; flex-direction: column; gap: 4px; }
.abal__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.abal__subtitle {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
  margin: 0;
}

.abal__center {
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

.abal__card {
  padding: 16px 18px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}

.abal__balance { display: flex; flex-direction: column; gap: 6px; }
.abal__balance-head {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.abal__balance-value {
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
}
.abal__balance-frozen {
  font-size: var(--fs-xs);
  color: var(--warning);
}

.abal__cta-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.abal__cta-hint {
  font-size: var(--fs-xs);
  font-style: italic;
  color: var(--text-tertiary);
}

.abal__section { display: flex; flex-direction: column; gap: 8px; }
.abal__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 4px 0 0;
}

.abal__empty {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
  margin: 0;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px dashed var(--border-default);
  text-align: center;
}

.abal__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.abal__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
}
.abal__item-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--bg-page);
  color: var(--text-secondary);
  flex-shrink: 0;
}
.abal__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.abal__item-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.abal__item-line--sub { font-size: var(--fs-xs); color: var(--text-tertiary); }
.abal__item-amount {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.abal__item-date { white-space: nowrap; }
.abal__item-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--danger);
  font-style: italic;
  text-align: right;
  max-width: 60%;
}

.abal__badge {
  display: inline-block;
  font-size: var(--fs-3xs);
  font-weight: 700;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.abal__badge--success {
  background: var(--bg-page);
  color: var(--success);
  border: 1px solid var(--success);
}
.abal__badge--warning {
  background: var(--bg-page);
  color: var(--warning);
  border: 1px solid var(--warning);
}
.abal__badge--danger {
  background: var(--bg-page);
  color: var(--danger);
  border: 1px solid var(--danger);
}
.abal__badge--neutral {
  background: var(--bg-page);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.abal__sentinel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 0 0;
  min-height: 32px;
}

.abal__loadmore-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px;
  margin-top: 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}

.abal__form { display: flex; flex-direction: column; gap: 14px; }
.abal__field { display: flex; flex-direction: column; gap: 6px; }
.abal__field-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.abal__field-hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  line-height: 1.4;
}

.abal__input {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-primary);
  font-size: var(--fs-body);
  font-family: inherit;
  transition: border-color 0.15s;
}
.abal__input:focus { outline: none; border-color: var(--primary); }
.abal__input:disabled { opacity: 0.6; cursor: not-allowed; }

.abal__form-error {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}
.abal__form-error--soft {
  background: transparent;
  border: 1px solid var(--warning);
  color: var(--warning);
}

.abal__form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 4px;
}
</style>
