<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorDepositView (H7)
// =============================================================================
//
// WHAT REPLACED WHAT. This screen used to request a per-user deposit
// address and draw it as a QR. There is no such thing any more: the
// payments service owns the wallets, one static address per network,
// and the unit of work is an INVOICE -- an amount, an address, a
// deadline, and a transaction hash the user submits by hand so their
// transfer can be told apart from everybody else's on the same address.
//
// So the screen is a small state machine, and every branch below
// corresponds to a status the service can report. The statuses are the
// service's (TOR section 5) and are never invented here.
//
// Network:
//   Hardcoded to one network, as before. NETWORK is a statement about
//   what THIS SCREEN ASKS FOR -- it is not a registry of what the
//   service serves. Which networks are served is the service's fact; it
//   refuses the rest with 400 network_not_supported, and a list here
//   would be a second answer that drifts. Whoever adds a selector
//   should ask the service, not extend this const.
//
// THE COUNTER IS NEVER COMPUTED HERE. `attempts_remaining` comes from
// the server on every read and on every submission, because two of the
// six verdicts -- invalid_format and api_error -- never reach an
// explorer and spend no attempt. Counting submissions locally would
// show a budget the user has not spent.
//
// A 200 FROM THE SUBMIT CALL IS NOT A SUCCESS. It carries a verdict;
// five of the six mean the hash was not accepted. The screen reads
// result_code, not the absence of an exception.
//
// Error strategy:
//   - Unavailable / misconfigured / unknown network -> the SAME
//     "temporarily unavailable" panel. All three are true statements
//     about the deployment and none of them is something the user did,
//     so none of them says "error". A support queue full of reports
//     about a fault that does not exist is the failure mode being
//     avoided here.
//   - Submit failures -> inline under the field; the invoice stays.
//   - Copy fail -> toast; the address is still visible and selectable.
//
// QR generation:
//   `qrcode` renders an inline SVG string. Forced light background
//   (white fill, black modules) because camera scanners expect that
//   contrast regardless of the host UI theme.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import { ArrowLeft, Copy, ShieldAlert } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CInput, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import {
  createInvoice,
  getCurrentInvoice,
  getInvoice,
  submitInvoiceTxid,
} from '@/api/payments'
import type { InvoiceResponse } from '@/api/types'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'

// See the header: what this screen asks for, not what is available.
const NETWORK = 'USDT-TRC20' as const

// Statuses the service never leaves on its own. attempts_exhausted is
// deliberately absent: such an invoice takes no more hashes but is
// still waiting for its TTL to turn it into expired, so offering a new
// invoice would strand it.
const TERMINAL = ['confirmed', 'expired', 'stalled']

const router = useRouter()
const { t } = useI18n()
const { showToast } = useToast()

const loading = ref(true)
// `unavailable` is not `errored`. It is the deployment saying it cannot
// serve deposits right now, which is a different sentence to the user.
const unavailable = ref(false)
const invoice = ref<InvoiceResponse | null>(null)
const qrSvg = ref<string | null>(null)

const amountInput = ref('')
const amountError = ref('')
const creating = ref(false)

const txidInput = ref('')
const txidError = ref('')
const txidNotice = ref('')
const submitting = ref(false)

const status = computed(() => invoice.value?.status ?? null)
const isTerminal = computed(() => !!status.value && TERMINAL.includes(status.value))
// Only `created` takes a hash. Every other status is refused by the
// service with one of five 409s, so the field is hidden rather than
// offered and then rejected.
const acceptsTxid = computed(() => status.value === 'created')

const amountDisplay = computed(() =>
  invoice.value ? (invoice.value.invoice_amount_cents / 100).toFixed(2) : '',
)
const creditedDisplay = computed(() =>
  invoice.value?.credited_amount_cents != null
    ? (invoice.value.credited_amount_cents / 100).toFixed(2)
    : null,
)
const expiresDisplay = computed(() =>
  invoice.value?.expires_at ? new Date(invoice.value.expires_at).toLocaleString() : null,
)

async function generateQr(value: string): Promise<string | null> {
  try {
    return await QRCode.toString(value, {
      type: 'svg',
      margin: 0,
      width: 240,
      // Forced light palette -- camera scanners need high contrast,
      // theme-matching dark QRs fail on most wallet cameras.
      color: { dark: '#000000', light: '#ffffff' },
      errorCorrectionLevel: 'M',
    })
  } catch {
    return null
  }
}

/**
 * Every failure that means "this deployment cannot serve deposits".
 *
 * 503 and 504 are the client's own verdicts for an unreachable or
 * unconfigured service; 502 is a service answer we could not use. 400
 * lands here too, and that is the least obvious one: it means the
 * service does not serve the network this screen asks for, which is a
 * deployment mismatch and not something the user chose -- they never
 * picked a network.
 */
function isUnavailable(err: unknown): boolean {
  return (
    err instanceof ApiResponseError &&
    (err.status === 400 || err.status === 502 || err.status === 503 || err.status === 504)
  )
}

async function showInvoice(next: InvoiceResponse | null): Promise<void> {
  invoice.value = next
  qrSvg.value = next?.address ? await generateQr(next.address) : null
}

async function load(): Promise<void> {
  loading.value = true
  unavailable.value = false
  txidError.value = ''
  txidNotice.value = ''
  try {
    await showInvoice(await getCurrentInvoice(NETWORK))
  } catch (err: unknown) {
    // No branch on 404 here: `current` answers null for "no invoice",
    // so a 404 would mean the route is gone -- an unavailability, not
    // an empty state.
    unavailable.value = isUnavailable(err)
    if (!unavailable.value) unavailable.value = true
    invoice.value = null
  } finally {
    loading.value = false
  }
}

async function refresh(): Promise<void> {
  if (!invoice.value) return
  try {
    await showInvoice(await getInvoice(invoice.value.id))
  } catch (err: unknown) {
    // A refresh that fails leaves the last known invoice on screen
    // rather than blanking it: the address and the deadline are still
    // the right ones to act on, only the status may be stale.
    if (isUnavailable(err)) {
      txidNotice.value = t('inv.deposit.statusStale')
    }
  }
}

function validateAmount(): number | null {
  const raw = amountInput.value.trim().replace(',', '.')
  if (!raw) {
    amountError.value = t('inv.deposit.amountRequired')
    return null
  }
  const parsed = Number(raw)
  // Number('') is 0 and Number('12abc') is NaN -- both are checked, and
  // the zero case is checked separately below because the service
  // floors the amount at one cent and would answer 422 to a zero.
  if (!Number.isFinite(parsed) || parsed <= 0) {
    amountError.value = t('inv.deposit.amountInvalid')
    return null
  }
  const cents = Math.round(parsed * 100)
  if (cents < 1) {
    amountError.value = t('inv.deposit.amountInvalid')
    return null
  }
  // Mirrors MAX_DEPOSIT_CENTS on the backend. Duplicated on purpose:
  // the alternative is relaying a 422 the user cannot interpret.
  if (cents > 1_000_000_000) {
    amountError.value = t('inv.deposit.amountTooLarge')
    return null
  }
  amountError.value = ''
  return cents
}

async function create(): Promise<void> {
  // Guarded against the double click: the service has no dedupe on
  // product_ref, so two creating calls make two invoices and a user who
  // pays one leaves us waiting on the other.
  if (creating.value) return
  const cents = validateAmount()
  if (cents === null) return

  creating.value = true
  try {
    await showInvoice(await createInvoice({ network: NETWORK, amount_cents: cents }))
    amountInput.value = ''
  } catch (err: unknown) {
    if (isUnavailable(err)) {
      unavailable.value = true
    } else {
      amountError.value = t('inv.deposit.createFailed')
    }
  } finally {
    creating.value = false
  }
}

async function submitTxid(): Promise<void> {
  if (submitting.value || !invoice.value) return
  const value = txidInput.value.trim()
  txidError.value = ''
  txidNotice.value = ''

  if (!value) {
    // Stopped here rather than sent. The service would answer 200 with
    // invalid_format and spend nothing, so nothing is lost -- but a
    // round trip to be told the field is empty is worse than saying so.
    txidError.value = t('inv.deposit.txidRequired')
    return
  }

  submitting.value = true
  try {
    const result = await submitInvoiceTxid(invoice.value.id, value)

    if (result.result_code === 'matched') {
      txidInput.value = ''
      txidNotice.value = t('inv.deposit.txidAccepted')
    } else {
      // One message per verdict. A single "rejected" would leave the
      // user unable to tell a typo from a transfer to the wrong chain,
      // and those have opposite next actions.
      const key = `inv.deposit.verdict.${result.result_code}`
      const message = t(key)
      txidError.value = message === key ? t('inv.deposit.verdict.unknown') : message
    }

    // Refreshed rather than patched from the submission response: the
    // response carries the verdict, the invoice carries the state, and
    // the counter shown must be the one the service reports.
    await refresh()
  } catch (err: unknown) {
    if (isUnavailable(err)) {
      // The attempt was NOT spent: the call did not reach a verdict.
      // Said explicitly, because a user who thinks they burned one of
      // three tries behaves differently.
      txidError.value = t('inv.deposit.txidUnavailable')
    } else if (err instanceof ApiResponseError && err.status === 409) {
      // The five refusals: the invoice moved under the user. Re-reading
      // is what makes the screen agree with the refusal it just got.
      txidError.value = t('inv.deposit.txidRefused')
      await refresh()
    } else {
      txidError.value = t('inv.deposit.txidFailed')
    }
  } finally {
    submitting.value = false
  }
}

function startOver(): void {
  invoice.value = null
  qrSvg.value = null
  txidInput.value = ''
  txidError.value = ''
  txidNotice.value = ''
}

async function copyAddress(): Promise<void> {
  const value = invoice.value?.address
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    showToast(t('inv.deposit.copied'), 'success')
  } catch {
    showToast(t('inv.deposit.copyError'), 'error')
  }
}

function goBack(): void {
  // Prefer router.back() -- restores BalanceView scroll/state.
  // Fallback to explicit push only when vue-router has no prior entry
  // (user deep-linked straight to /investor/balance/deposit).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push({ name: 'investor-balance' }), '[InvestorDepositView] to balance')
}

onMounted(load)
</script>

<template>
  <div class="dv">
    <!-- Loading -->
    <div v-if="loading" class="dv__center">
      <CLoader :size="28" />
    </div>

    <!-- Temporarily unavailable: unreachable, unconfigured, or a network
         this deployment's service does not serve. Deliberately not
         worded as an error -- see the script header. -->
    <template v-else-if="unavailable">
      <div class="dv__center">
        <CEmptyState
          :title="t('inv.deposit.unavailable.title')"
          :description="t('inv.deposit.unavailable.desc')"
        />
        <div class="dv__error-actions">
          <CButton variant="outline" size="sm" inline @click="goBack">
            <ArrowLeft :size="16" />
            {{ t('inv.deposit.backToBalance') }}
          </CButton>
          <CButton variant="primary" size="sm" inline @click="load">
            {{ t('common.retry') }}
          </CButton>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="dv__page-header">
        <CBackLink :label="t('inv.deposit.backLink')" @click="goBack" />
        <h1 class="dv__page-title">
          {{ t('inv.deposit.title') }}
        </h1>
      </div>

      <div class="dv__body">
        <!-- No invoice open: ask for an amount. The service will not
             open one without it (invoice_amount_cents >= 1). -->
        <section v-if="!invoice" class="dv__card">
          <p class="dv__hint">
            {{ t('inv.deposit.amountIntro') }}
          </p>
          <CInput
            v-model="amountInput"
            type="text"
            inputmode="decimal"
            :label="t('inv.deposit.amountLabel')"
            :error="amountError"
            :placeholder="t('inv.deposit.amountPlaceholder')"
          />
          <CButton
            variant="primary"
            class="dv__cta"
            :loading="creating"
            :disabled="creating"
            @click="create"
          >
            {{ t('inv.deposit.createCta') }}
          </CButton>
        </section>

        <template v-else>
          <!-- Network + amount + deadline -->
          <section class="dv__card">
            <div class="dv__row">
              <span class="dv__row-label">{{ t('inv.deposit.network') }}</span>
              <span class="dv__row-value">{{ invoice.network }}</span>
            </div>
            <div class="dv__row">
              <span class="dv__row-label">{{ t('inv.deposit.amountLabel') }}</span>
              <span class="dv__row-value">{{ amountDisplay }} USDT</span>
            </div>
            <div v-if="expiresDisplay" class="dv__row">
              <span class="dv__row-label">{{ t('inv.deposit.expiresAt') }}</span>
              <span class="dv__row-value">{{ expiresDisplay }}</span>
            </div>
          </section>

          <!-- Terminal statuses. Each is its own message: "confirmed"
               and "stalled" have nothing in common for the user. -->
          <section v-if="isTerminal" class="dv__card dv__terminal">
            <p class="dv__terminal-title">
              {{ t(`inv.deposit.status.${status}`) }}
            </p>
            <p v-if="status === 'confirmed'" class="dv__hint">
              <!-- credited, not invoiced: the service credits what
                   actually arrived, which may be less -- and may be
                   zero for a dust transfer. Zero is a legitimate
                   outcome, so it is shown rather than suppressed. -->
              {{ t('inv.deposit.creditedAmount', { amount: creditedDisplay ?? '0.00' }) }}
              <span v-if="invoice.underpaid"> {{ t('inv.deposit.underpaid') }}</span>
            </p>
            <CButton variant="primary" class="dv__cta" @click="startOver">
              {{ t('inv.deposit.newDeposit') }}
            </CButton>
          </section>

          <template v-else>
            <!-- QR + address -->
            <section class="dv__card dv__qr-section">
              <div v-if="qrSvg" class="dv__qr" v-html="qrSvg" />
              <div v-else class="dv__qr dv__qr--fallback">
                <span>{{ t('inv.deposit.qrUnavailable') }}</span>
              </div>

              <div class="dv__address">
                {{ invoice.address }}
              </div>

              <CButton variant="primary" class="dv__cta" @click="copyAddress">
                <Copy :size="16" />
                {{ t('inv.deposit.copy') }}
              </CButton>
            </section>

            <!-- TXID submission. Only `created` accepts one. -->
            <section class="dv__card">
              <p class="dv__hint">
                {{ t('inv.deposit.txidIntro') }}
              </p>

              <template v-if="acceptsTxid">
                <CInput
                  v-model="txidInput"
                  :label="t('inv.deposit.txidLabel')"
                  :error="txidError"
                  :placeholder="t('inv.deposit.txidPlaceholder')"
                />
                <p
                  v-if="invoice.attempts_remaining != null"
                  class="dv__attempts"
                >
                  {{ t('inv.deposit.attemptsRemaining', { n: invoice.attempts_remaining }) }}
                </p>
                <CButton
                  variant="primary"
                  class="dv__cta"
                  :loading="submitting"
                  :disabled="submitting"
                  @click="submitTxid"
                >
                  {{ t('inv.deposit.txidCta') }}
                </CButton>
              </template>

              <!-- awaiting_confirmations / attempts_exhausted -->
              <p v-else class="dv__notice">
                {{ t(`inv.deposit.status.${status}`) }}
              </p>

              <p v-if="txidNotice" class="dv__notice">{{ txidNotice }}</p>
              <p v-if="!acceptsTxid && txidError" class="dv__error">{{ txidError }}</p>
            </section>
          </template>
        </template>

        <!-- Security warning. Still the only realistic mitigation at
             the UI layer for a cross-network transfer. -->
        <section class="dv__card dv__warning">
          <ShieldAlert :size="16" class="dv__warning-icon" />
          <p class="dv__warning-text">
            {{ t('inv.deposit.warning') }}
          </p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dv {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.dv__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: calc(100vh - 120px);
  min-height: calc(100dvh - 120px);
  padding: var(--space-5);
}

.dv__error-actions {
  display: flex;
  gap: var(--space-2);
}

.dv__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4) var(--space-2);
}
.dv__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.dv__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}

.dv__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.dv__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.dv__row-label {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.dv__row-value {
  font-size: var(--fs-sm);
  color: var(--text-primary);
}

.dv__hint {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.dv__cta {
  margin-top: var(--space-1);
}

.dv__qr-section {
  align-items: center;
}
.dv__qr {
  width: 240px;
  max-width: 100%;
  padding: var(--space-3);
  background: var(--neutral-0);
  border-radius: var(--radius-sm);
}
.dv__qr--fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}

.dv__address {
  width: 100%;
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  word-break: break-all;
  text-align: center;
}

.dv__attempts {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.dv__notice {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.dv__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.dv__terminal-title {
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
}

.dv__warning {
  flex-direction: row;
  align-items: flex-start;
  gap: var(--space-2);
  background: var(--warning-subtle);
}
.dv__warning-icon {
  flex-shrink: 0;
  color: var(--warning);
}
.dv__warning-text {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
</style>
