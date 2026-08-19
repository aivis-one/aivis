<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorDepositView (Phase F4.3 B2)
// =============================================================================
//
// Dedicated /investor/balance/deposit screen. Requests a TRC20 USDT
// deposit address (backend endpoint is idempotent -- same user +
// same network always returns the same address), renders it as a
// QR for external wallet scanning plus a Copy button for desktop
// paste flows.
//
// Network:
//   Hardcoded to 'TRC20' per F4.3 plan. The backend supports
//   ERC20/BEP20/PoS too; the multi-network selector is explicitly
//   deferred -- see `AIVIS-Frontend.md` F4.3 scope.
//
// QR generation:
//   `qrcode` package renders an inline SVG string. Forced light
//   background (white fill, black modules) because camera scanners
//   expect that contrast regardless of the host UI theme. The SVG
//   is injected via v-html onto an outer white-backed container.
//
// Error strategy:
//   - Address fetch fail -> inline CEmptyState + retry + back link.
//     No toast (the screen is empty until the address lands; a
//     disappearing toast would leave the user confused).
//   - Copy fail (navigator.clipboard unavailable or denied) ->
//     error toast; the address is still visible and selectable.
//
// Security note:
//   The `warning` block below explicitly tells the user to send
//   only USDT via TRC20. Cross-network transfers to the wrong
//   address lose funds permanently on most chains -- a prominent
//   warning is the only realistic mitigation at the UI layer.
//
// TD-F08c:
//   Error handler for POST /payments/crypto-address narrows on
//   `ApiResponseError` + status. Backend does not emit a rich
//   error_code today (TD-F08c backlog). Current backend behaviour
//   is 400 for unsupported network only; UI stays defensive with a
//   generic fallback.
// =============================================================================

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'
import { ArrowLeft, Copy, ShieldAlert } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { createCryptoAddress } from '@/api/payments'
import { safeNavigate } from '@/composables/safeNavigate'
import { useToast } from '@/composables/useToast'

// Locked to TRC20 for F4.3; the backend `CryptoNetwork` union is
// TRC20 | ERC20 | BEP20 | PoS, future selector replaces this const.
const NETWORK = 'TRC20' as const

const router = useRouter()
const { t } = useI18n()
const { showToast } = useToast()

const address = ref<string | null>(null)
const qrSvg = ref<string | null>(null)
const loading = ref(true)
const errored = ref(false)
const copying = ref(false)

async function generateQr(value: string): Promise<string | null> {
  try {
    return await QRCode.toString(value, {
      type: 'svg',
      margin: 0,
      width: 240,
      // Forced light palette -- camera scanners need high contrast,
      // theme-matching dark QRs fail on most wallet cameras.
      color: {
        dark: '#000000',
        light: '#ffffff',
      },
      errorCorrectionLevel: 'M',
    })
  } catch {
    return null
  }
}

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  address.value = null
  qrSvg.value = null
  try {
    const resp = await createCryptoAddress({ network: NETWORK })
    address.value = resp.address
    qrSvg.value = await generateQr(resp.address)
  } catch (err: unknown) {
    // TD-F08c: narrow on ApiResponseError + status, but the backend
    // has no fine-grained discriminator for this endpoint today, so
    // a single generic banner is enough. We still record the error
    // class so the retry path stays consistent with F4.2 patterns.
    if (err instanceof ApiResponseError) {
      // Specific branches reserved for future backend error_codes.
    }
    errored.value = true
  } finally {
    loading.value = false
  }
}

async function copyAddress(): Promise<void> {
  if (!address.value || copying.value) return
  copying.value = true
  try {
    await navigator.clipboard.writeText(address.value)
    showToast(t('inv.deposit.copied'), 'success')
  } catch {
    showToast(t('inv.deposit.copyError'), 'error')
  } finally {
    copying.value = false
  }
}

function goBack(): void {
  // Prefer router.back() -- restores BalanceView scroll/state and
  // matches the cancel-path fix we made in PurchaseView/InstallmentView.
  // Fallback to explicit push only when vue-router has no prior
  // entry (user deep-linked straight to /investor/balance/deposit).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'investor-balance' }),
    '[InvestorDepositView] to balance',
  )
}

onMounted(load)
</script>

<template>
  <div class="dv">
    <!-- Loading -->
    <div v-if="loading" class="dv__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <template v-else-if="errored || !address">
      <div class="dv__center">
        <CEmptyState
          :title="t('inv.deposit.loadError.title')"
          :description="t('inv.deposit.loadError.desc')"
        />
        <div class="dv__error-actions">
          <CButton variant="outline" size="sm" @click="goBack">
            <ArrowLeft :size="16" />
            {{ t('inv.deposit.backToBalance') }}
          </CButton>
          <CButton variant="primary" size="sm" @click="load">
            {{ t('common.retry') }}
          </CButton>
        </div>
      </div>
    </template>

    <!-- Loaded -->
    <template v-else>
      <!-- iter 2.7 batch B2: inline page-header replaces view-CHeader.
           No hero on this view, so the title lives in a header block
           with the back-link. Reuses existing history-aware goBack().
           B3: button shape extracted to CBackLink; .dv__page-header
           padding handles spacing. -->
      <div class="dv__page-header">
        <CBackLink
          :label="t('inv.deposit.backLink')"
          @click="goBack"
        />
        <h1 class="dv__page-title">{{ t('inv.deposit.title') }}</h1>
      </div>

      <div class="dv__body">
        <!-- Network + hint -->
        <section class="dv__card">
          <div class="dv__network-row">
            <span class="dv__network-label">
              {{ t('inv.deposit.network') }}
            </span>
            <span class="dv__network-value">{{ NETWORK }}</span>
          </div>
          <p class="dv__hint">{{ t('inv.deposit.subtitle') }}</p>
        </section>

        <!-- QR + address -->
        <section class="dv__card dv__qr-section">
          <div
            v-if="qrSvg"
            class="dv__qr"
            v-html="qrSvg"
          ></div>
          <div v-else class="dv__qr dv__qr--fallback">
            <!-- QR library failed but address still loaded: the text
                 form below is enough to complete a deposit. -->
            <span>{{ t('inv.deposit.qrUnavailable') }}</span>
          </div>

          <div class="dv__address">
            {{ address }}
          </div>

          <CButton
            variant="primary"
            class="dv__copy"
            :disabled="copying"
            @click="copyAddress"
          >
            <Copy :size="16" />
            {{ t('inv.deposit.copy') }}
          </CButton>
        </section>

        <!-- Security warning -->
        <section class="dv__card dv__warning">
          <ShieldAlert :size="16" class="dv__warning-icon" />
          <p class="dv__warning-text">{{ t('inv.deposit.warning') }}</p>
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

/* iter 2.7 batch B2 -- inline page-header (back-link + title) replaces
   the previous view-CHeader. No hero on this view, so the title lives
   inside a header block at the top of the loaded branch. */
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

/* Card base */
.dv__card {
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

/* Network row */
.dv__network-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.dv__network-label {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.dv__network-value {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--accent);
  font-family: var(--font-mono);
}

.dv__hint {
  margin: var(--space-3) 0 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}

/* QR section */
.dv__qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
}

.dv__qr {
  padding: var(--space-4);
  background: #ffffff;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  /* Keep the QR square regardless of the inner SVG sizing. */
  min-width: 272px;
  min-height: 272px;
}
.dv__qr :deep(svg) {
  display: block;
  width: 240px;
  height: 240px;
}

.dv__qr--fallback {
  color: #333;
  font-size: var(--fs-xs);
  text-align: center;
  padding: var(--space-6-lg) var(--space-5);
}

.dv__address {
  width: 100%;
  padding: var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  word-break: break-all;
  text-align: center;
  user-select: all;
}

.dv__copy {
  width: 100%;
}

/* Warning */
.dv__warning {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  background: var(--warning-subtle);
  border: 1px solid var(--warning);
}

.dv__warning-icon {
  flex-shrink: 0;
  color: var(--warning);
  margin-top: var(--space-1);
}

.dv__warning-text {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text-primary);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.dv__hint { max-width: var(--maxw-prose); }
</style>
