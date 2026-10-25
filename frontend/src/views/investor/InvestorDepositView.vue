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
//   The person picks one of three USDT networks (TRC20, ERC20, BSC20) before
//   the invoice is opened, and the warning under the address names the
//   network the invoice is on. NETWORKS is a statement about what THIS SCREEN
//   OFFERS -- it is not a registry of what the service serves. Which
//   networks are served is the service's fact; it refuses the rest with 400
//   network_not_supported. An invoice already open on any of the three is
//   found on arrival and shown, so a person is never asked to open a second
//   one beside it.
//
// Arrival with an amount:
//   The identity-verification screen sends a person who is short of the fee
//   here with `?amount=10&min=10`: the amount field opens filled and a line
//   names the minimum. The minimum is a message and is not checked in code.
//
// After verification the screen adds a line: to pay by bank, write to support.
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
//   - Copy fail -> the block's status line; the address is still visible
//     and selectable.
//
// The invoice is the system's Invoice and QR block (K43): its fields, the QR as an
// image with the pad the system draws (white in both themes, because camera
// scanners expect dark modules on white regardless of the host UI theme), the
// address as text, the Copy button and its status line. The network choice is the
// Segmented control (K31). The title and the back control are the frame's header (K25).
//
// QR generation:
//   `qrcode` renders an SVG string with its defaults (black modules on white), which
//   the screen shows as an image; the image's size is the system's.
// =============================================================================

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import { AlertTriangle, ArrowLeft, Check, Copy, Info } from '@/components/ui/icons'
import { CButton, CEmptyState, CInput, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { ApiNetworkError, ApiResponseError, ApiTimeoutError } from '@/api/client'
import { createInvoice, getCurrentInvoice, getInvoice, submitInvoiceTxid } from '@/api/payments'
import type { InvoiceResponse } from '@/api/types'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

// See the header: what this screen offers, not what is available. `id` is the
// network name the payments service takes; `key` names the screen's own
// translations (its name and its warning) for that network.
const NETWORKS = [
  { id: 'USDT-TRC20', key: 'trc20' },
  { id: 'USDT-ERC20', key: 'erc20' },
  { id: 'USDT-BSC20', key: 'bsc20' },
] as const

type NetworkId = (typeof NETWORKS)[number]['id']

function networkKey(id: string): string {
  return NETWORKS.find((n) => n.id === id)?.key ?? 'trc20'
}

// Statuses the service never leaves on its own. attempts_exhausted is
// deliberately absent: such an invoice takes no more hashes but is
// still waiting for its TTL to turn it into expired, so offering a new
// invoice would strand it.
const TERMINAL = ['confirmed', 'expired', 'stalled']

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const authStore = useAuthStore()

// Prefer router.back() -- restores BalanceView scroll/state. Fallback to the
// balance only when vue-router has no prior entry (user deep-linked straight to
// /investor/balance/deposit).
useScreenHeader({
  title: () => t('inv.deposit.title'),
  back: () => (window.history.state?.back ? true : { name: 'investor-balance' }),
})

const loading = ref(true)
// `unavailable` is not `errored`. It is the deployment saying it cannot
// serve deposits right now, which is a different sentence to the user.
const unavailable = ref(false)
// Why: the person's own connection (`offline`) or the service (`service`).
// The two read differently and the first is the person's to fix.
const unavailableReason = ref<'offline' | 'service'>('service')
const invoice = ref<InvoiceResponse | null>(null)
const qrSrc = ref<string | null>(null)

// The network the person picked for a new invoice. An open invoice sets it to
// its own network when the screen finds one.
const network = ref<NetworkId>(NETWORKS[0].id)

// A person who comes here short of the KYC fee arrives with the amount.
function queryNumber(key: string): string {
  const raw = route.query[key]
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && /^\d+(\.\d{1,2})?$/.test(value) ? value : ''
}
const minimumAmount = queryNumber('min')

const amountInput = ref(queryNumber('amount'))
const amountError = ref('')
const creating = ref(false)

// Verified accounts are told how to pay by bank.
const showBankLine = computed(() => authStore.kycStatus === 'approved')

// The name of the network the screen is showing, from the translations.
const shownNetworkKey = computed(() => networkKey(invoice.value?.network ?? network.value))

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
  invoice.value?.expires_at ? formatDateTime(invoice.value.expires_at, locale.value) : null,
)

// The library's defaults are black modules on white -- the contrast camera
// scanners need; a theme-matching dark QR fails on most wallet cameras. The pad
// round it is the system's (white in both themes).
async function generateQr(value: string): Promise<string | null> {
  try {
    const svg = await QRCode.toString(value, {
      type: 'svg',
      margin: 0,
      errorCorrectionLevel: 'M',
    })
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
  } catch {
    return null
  }
}

/**
 * Every failure that means "this deployment cannot serve deposits".
 *
 * 503 and 504 are the client's own verdicts for an unreachable or
 * unconfigured service; 502 is a service answer we could not use. 400
 * lands here too: the service does not serve the network that was asked
 * for. (When the person has picked that network by hand, `create` says so
 * next to the choice instead, and lets them pick another.)
 */
function isUnavailable(err: unknown): boolean {
  return (
    err instanceof ApiResponseError &&
    (err.status === 400 || err.status === 502 || err.status === 503 || err.status === 504)
  )
}

/** The person's own connection failed, as opposed to the service. */
function isOffline(err: unknown): boolean {
  return err instanceof ApiNetworkError || err instanceof ApiTimeoutError
}

async function showInvoice(next: InvoiceResponse | null): Promise<void> {
  invoice.value = next
  qrSrc.value = next?.address ? await generateQr(next.address) : null
}

async function load(): Promise<void> {
  loading.value = true
  unavailable.value = false
  txidError.value = ''
  txidNotice.value = ''
  try {
    // One look at each network: an invoice already open on any of them is the
    // one to show. The screen is unavailable only when EVERY look failed; a
    // network the service does not serve leaves the other two usable.
    const looks = await Promise.allSettled(NETWORKS.map((n) => getCurrentInvoice(n.id)))
    const open = looks.find(
      (r): r is PromiseFulfilledResult<InvoiceResponse> =>
        r.status === 'fulfilled' && r.value !== null,
    )
    if (open) {
      const found = NETWORKS.find((n) => n.id === open.value.network)
      if (found) network.value = found.id
      await showInvoice(open.value)
      return
    }
    // No branch on 404 here: `current` answers null for "no invoice",
    // so a 404 would mean the route is gone -- an unavailability, not
    // an empty state.
    const failures = looks.filter((r): r is PromiseRejectedResult => r.status === 'rejected')
    if (failures.length === looks.length) {
      unavailable.value = true
      unavailableReason.value = failures.some((f) => isOffline(f.reason)) ? 'offline' : 'service'
    }
    await showInvoice(null)
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
    await showInvoice(await createInvoice({ network: network.value, amount_cents: cents }))
    amountInput.value = ''
  } catch (err: unknown) {
    if (err instanceof ApiResponseError && err.code === 'network_not_supported') {
      // The service does not serve the network just picked: say so next to the
      // choice, so another can be picked.
      amountError.value = t('inv.deposit.networkNotSupported')
    } else if (isOffline(err)) {
      amountError.value = t('inv.deposit.offline')
    } else if (isUnavailable(err)) {
      unavailable.value = true
      unavailableReason.value = 'service'
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
  qrSrc.value = null
  txidInput.value = ''
  txidError.value = ''
  txidNotice.value = ''
}

// The Copy button and its status line (K43): the label turns to "Copied" with a
// check for three seconds; a failure is written into the status.
const COPIED_MS = 3000
const copied = ref(false)
const copyStatus = ref('')
let copiedTimer: ReturnType<typeof setTimeout> | null = null

async function copyAddress(): Promise<void> {
  const value = invoice.value?.address
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copyStatus.value = t('inv.deposit.copied')
    copied.value = true
    if (copiedTimer !== null) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => {
      copied.value = false
      copyStatus.value = ''
      copiedTimer = null
    }, COPIED_MS)
  } catch {
    copyStatus.value = t('inv.deposit.copyError')
  }
}

onBeforeUnmount(() => {
  if (copiedTimer !== null) clearTimeout(copiedTimer)
})

function toSupport(): void {
  void safeNavigate(router.push({ name: 'investor-support' }), '[InvestorDepositView] to support')
}

// The not-available state's own button: same rule as the header's back control.
function goBack(): void {
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
    <CLoader v-if="loading" centered extent="page" />

    <!-- Temporarily unavailable: unreachable, unconfigured, or a network
         this deployment's service does not serve. Deliberately not
         worded as an error -- see the script header. -->
    <CEmptyState
      v-else-if="unavailable"
      :title="t('inv.deposit.unavailable.title')"
      :description="
        unavailableReason === 'offline'
          ? t('inv.deposit.unavailable.offline')
          : t('inv.deposit.unavailable.desc')
      "
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="goBack">
          <ArrowLeft size="sm" />
          {{ t('inv.deposit.backToBalance') }}
        </CButton>
        <CButton variant="primary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else>
      <!-- No invoice open: ask for an amount. The service will not
           open one without it (invoice_amount_cents >= 1). -->
      <section v-if="!invoice" class="ds-card">
        <p class="ds-card__body">
          {{ t('inv.deposit.amountIntro') }}
        </p>

        <!-- The network the money will be sent on: one of three (K31). -->
        <fieldset class="ds-segmented">
          <legend class="ds-sr-only">{{ t('inv.deposit.network') }}</legend>
          <label v-for="n in NETWORKS" :key="n.id" class="ds-segmented__option">
            <input
              v-model="network"
              class="ds-segmented__input"
              type="radio"
              name="deposit-network"
              :value="n.id"
            />
            {{ t(`inv.deposit.networks.${n.key}.name`) }}
          </label>
        </fieldset>
        <p class="ds-card__body">
          {{ t(`inv.deposit.networks.${networkKey(network)}.warning`) }}
        </p>

        <p v-if="minimumAmount" class="ds-card__body">
          {{ t('inv.deposit.minimum', { amount: minimumAmount }) }}
        </p>
        <CInput
          v-model="amountInput"
          type="text"
          inputmode="decimal"
          :label="t('inv.deposit.amountLabel')"
          :error="amountError"
          :placeholder="t('inv.deposit.amountPlaceholder')"
        />
        <CButton variant="primary" :loading="creating" :disabled="creating" @click="create">
          {{ t('inv.deposit.createCta') }}
        </CButton>
      </section>

      <!-- The open invoice: the Invoice and QR block (K43) -->
      <section
        v-else
        class="ds-invoice"
        aria-labelledby="dv-invoice"
        :data-state="!isTerminal && !qrSrc ? 'unavailable' : undefined"
      >
        <h2 id="dv-invoice" class="ds-sr-only">{{ t('inv.deposit.title') }}</h2>

        <!-- Network + amount + deadline -->
        <dl class="ds-invoice__fields">
          <div class="ds-invoice__field">
            <dt>{{ t('inv.deposit.network') }}</dt>
            <dd>{{ t(`inv.deposit.networks.${shownNetworkKey}.name`) }}</dd>
          </div>
          <div class="ds-invoice__field">
            <dt>{{ t('inv.deposit.amountLabel') }}</dt>
            <dd>{{ amountDisplay }} {{ t('inv.deposit.coin') }}</dd>
          </div>
          <div v-if="expiresDisplay" class="ds-invoice__field">
            <dt>{{ t('inv.deposit.expiresAt') }}</dt>
            <dd>{{ expiresDisplay }}</dd>
          </div>
        </dl>

        <!-- Security warning, right under the network, amount and deadline: still the
             only realistic mitigation at the UI layer for a cross-network transfer. -->
        <div class="ds-alert ds-alert--warning" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">
              {{ t(`inv.deposit.networks.${shownNetworkKey}.warning`) }}
            </p>
          </div>
        </div>

        <!-- Terminal statuses. Each is its own message: "confirmed"
             and "stalled" have nothing in common for the user. -->
        <template v-if="isTerminal">
          <div
            class="ds-alert"
            :class="status === 'confirmed' ? 'ds-alert--success' : 'ds-alert--warning'"
            :role="status === 'confirmed' ? 'status' : 'alert'"
          >
            <span class="ds-alert__icon" aria-hidden="true">
              <Check v-if="status === 'confirmed'" size="sm" />
              <AlertTriangle v-else size="sm" />
            </span>
            <div class="ds-alert__content">
              <p class="ds-alert__title">
                {{ t(`inv.deposit.status.${status}`) }}
              </p>
              <p v-if="status === 'confirmed'" class="ds-alert__text">
                <!-- credited, not invoiced: the service credits what
                     actually arrived, which may be less -- and may be
                     zero for a dust transfer. Zero is a legitimate
                     outcome, so it is shown rather than suppressed. -->
                {{ t('inv.deposit.creditedAmount', { amount: creditedDisplay ?? '0.00' }) }}
                <span v-if="invoice.underpaid"> {{ t('inv.deposit.underpaid') }}</span>
              </p>
            </div>
          </div>
          <CButton variant="primary" @click="startOver">
            {{ t('inv.deposit.newDeposit') }}
          </CButton>
        </template>

        <template v-else>
          <!-- QR + address -->
          <div class="ds-invoice__qr">
            <img v-if="qrSrc" :src="qrSrc" :alt="t('inv.deposit.qrAlt')" />
            <p class="ds-invoice__qr-note">{{ t('inv.deposit.qrUnavailable') }}</p>
          </div>

          <p id="dv-address" class="ds-invoice__address" dir="ltr">
            {{ invoice.address }}
          </p>

          <CButton
            variant="primary"
            inline
            class="ds-invoice__copy"
            :data-state="copied ? 'copied' : undefined"
            @click="copyAddress"
          >
            <Check v-if="copied" size="sm" />
            <Copy v-else size="sm" />
            {{ copied ? t('inv.deposit.copied') : t('inv.deposit.copy') }}
          </CButton>
          <p class="ds-invoice__status" role="status">{{ copyStatus }}</p>
        </template>
      </section>

      <!-- TXID submission. Only `created` accepts one. -->
      <section v-if="invoice && !isTerminal" class="ds-card">
        <p class="ds-card__body">
          {{ t('inv.deposit.txidIntro') }}
        </p>

        <template v-if="acceptsTxid">
          <CInput
            v-model="txidInput"
            :label="t('inv.deposit.txidLabel')"
            :error="txidError"
            :placeholder="t('inv.deposit.txidPlaceholder')"
          />
          <p v-if="invoice.attempts_remaining != null" class="ds-note ds-note--xs">
            {{ t('inv.deposit.attemptsRemaining', { n: invoice.attempts_remaining }) }}
          </p>
          <CButton
            variant="primary"
            :loading="submitting"
            :disabled="submitting"
            @click="submitTxid"
          >
            {{ t('inv.deposit.txidCta') }}
          </CButton>
        </template>

        <!-- awaiting_confirmations / attempts_exhausted -->
        <div v-else class="ds-alert ds-alert--info" role="status">
          <span class="ds-alert__icon" aria-hidden="true"><Info size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ t(`inv.deposit.status.${status}`) }}</p>
          </div>
        </div>

        <div v-if="txidNotice" class="ds-alert ds-alert--info" role="status">
          <span class="ds-alert__icon" aria-hidden="true"><Info size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ txidNotice }}</p>
          </div>
        </div>
        <div v-if="!acceptsTxid && txidError" class="ds-alert ds-alert--danger" role="alert">
          <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
          <div class="ds-alert__content">
            <p class="ds-alert__text">{{ txidError }}</p>
          </div>
        </div>
      </section>

      <!-- After verification, a deposit by bank goes through support. -->
      <section v-if="showBankLine" class="ds-card">
        <p class="ds-card__body">
          {{ t('inv.deposit.bankLine') }}
        </p>
        <div class="ds-card__foot">
          <CButton variant="outline" size="sm" inline @click="toSupport">
            {{ t('inv.deposit.bankCta') }}
          </CButton>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dv {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
</style>
