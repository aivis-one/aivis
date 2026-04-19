<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CertificateSheet (Phase F4.4 B3)
// =============================================================================
//
// Bottom-sheet that renders a per-purchase certificate HTML and
// exposes an "Email to me" CTA. Triggered from the per-purchase
// rows in CompanyPositionView.
//
// DATA FLOW.
//   Parent owns selection via `purchaseId` + `open`. The sheet
//   watches both and calls useCertificateBlob.load() on the
//   open->true transition (with a non-null id). The composable
//   owns the blob URL lifecycle -- automatic revoke on scope
//   dispose + manual revoke-before-overwrite on each new load.
//
// SANDBOX -- TD-F11b MUST fix.
//   The HTML returned by the backend is rendered in an iframe via
//   a blob URL. Blob URLs inherit the page's origin, so without
//   sandbox the iframe could read localStorage and the JWT token.
//   `sandbox=""` (empty attribute value) forbids every capability:
//   no scripts, no forms, no same-origin access, no top-level
//   navigation, no storage. The certificate is a static HTML
//   render (backend Jinja2 with autoescape=True) and does not
//   need any of these privileges. If a future certificate variant
//   legitimately needs CSS background-image url() fetches from
//   the API origin, the correct escalation is the narrowest
//   allow-list, not a blanket sandbox="allow-same-origin".
//
// ERROR HANDLING.
//   load() throw -> composable's `errored` flag + sheet error
//   state + toast suppressed (inline message is enough; the sheet
//   is modal, nothing else competes for attention). The Retry
//   button calls load() again; if the failure is 404 (caller does
//   not own the purchase) retry will keep failing -- expected,
//   the only way to hit that case is a state mismatch between the
//   list and the backend, in which case closing the sheet and
//   reloading the position is the right move.
//
// EMAIL CTA.
//   emailCertificate() is rate-limited on the backend. The button
//   disables during the in-flight request and during an additional
//   cooldown window locally (see EMAIL_COOLDOWN_MS below) so a
//   frustrated double-tap doesn't burn the next quota second. On
//   success: toast 'sent'; on failure: toast 'could not send' +
//   unlock the button immediately so the user can retry.
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import CBottomSheet from '@/components/ui/CBottomSheet.vue'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { emailCertificate } from '@/api/certificates'
import { useCertificateBlob } from '@/composables/useCertificateBlob'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  open: boolean
  purchaseId: string | null
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const { showToast } = useToast()

const { blobUrl, loading, errored, load, clear } = useCertificateBlob()

// Local cooldown after a send attempt so rapid taps don't hammer
// the rate-limited backend route. The number is conservative --
// backend guards the actual ceiling, this is a UX nicety.
const EMAIL_COOLDOWN_MS = 3_000

const emailSending = ref(false)
const emailLockedUntil = ref<number>(0)

const emailDisabled = computed<boolean>(() => {
  if (emailSending.value) return true
  if (!blobUrl.value) return true
  return Date.now() < emailLockedUntil.value
})

// ---------------------------------------------------------------------------
// Load on open transition
// ---------------------------------------------------------------------------

watch(
  () => [props.open, props.purchaseId] as const,
  async ([open, id]) => {
    if (open && id) {
      // Ignore the thrown error -- `errored` flag on the composable
      // drives the sheet's template; a toast would compete with the
      // sheet's own error state.
      try {
        await load(id)
      } catch {
        // swallow
      }
    }
    if (!open) {
      // Release the blob URL as soon as the sheet closes to avoid
      // keeping sensitive HTML pinned in memory for the full tab
      // lifetime. onScopeDispose in the composable also handles
      // full-unmount, but this is the common path.
      clear()
      emailSending.value = false
      emailLockedUntil.value = 0
    }
  },
  { immediate: true },
)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function onClose(): void {
  emit('close')
}

async function onRetry(): Promise<void> {
  if (!props.purchaseId) return
  try {
    await load(props.purchaseId)
  } catch {
    // swallow
  }
}

async function onEmail(): Promise<void> {
  if (!props.purchaseId || emailDisabled.value) return
  emailSending.value = true
  try {
    await emailCertificate(props.purchaseId)
    showToast(t('inv.certificate.emailSuccess'), 'success')
    emailLockedUntil.value = Date.now() + EMAIL_COOLDOWN_MS
  } catch (err: unknown) {
    // Same regex-free, status-driven branch policy as other F4.4
    // views: narrow to ApiResponseError but do not try to classify
    // the message. Email send has no recoverable sub-states
    // worth distinguishing in the UI -- 429 and 500 render the
    // same toast, and 404 cannot happen once load() has succeeded.
    if (err instanceof ApiResponseError) {
      showToast(t('inv.certificate.emailError'), 'error')
    } else {
      showToast(t('inv.certificate.emailError'), 'error')
    }
    // Unlock immediately on failure -- the user should be able to
    // retry without waiting for the cooldown window.
    emailLockedUntil.value = 0
  } finally {
    emailSending.value = false
  }
}
</script>

<template>
  <CBottomSheet
    :open="open"
    :title="t('inv.certificate.title')"
    @close="onClose"
  >
    <div class="cs">
      <!-- Loading -->
      <div v-if="loading && !errored" class="cs__center">
        <CLoader :size="28" />
        <div class="cs__loading-hint">
          {{ t('inv.certificate.loading') }}
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="errored" class="cs__center">
        <CEmptyState :title="t('inv.certificate.errorTitle')" />
        <CButton variant="outline" size="sm" @click="onRetry">
          {{ t('inv.certificate.errorRetry') }}
        </CButton>
      </div>

      <!-- Loaded -->
      <template v-else-if="blobUrl">
        <!--
          sandbox="" MUST stay present. Removing it, or relaxing it
          to sandbox="allow-same-origin", would let any scripting in
          the certificate HTML read the SPA's localStorage + JWT.
          See TD-F11b in CBSHOME-Frontend.md.
        -->
        <iframe
          :src="blobUrl"
          sandbox=""
          class="cs__iframe"
          :title="t('inv.certificate.title')"
        />

        <div class="cs__actions">
          <CButton
            variant="outline"
            size="sm"
            @click="onClose"
          >
            {{ t('inv.certificate.close') }}
          </CButton>
          <CButton
            variant="primary"
            size="sm"
            :disabled="emailDisabled"
            @click="onEmail"
          >
            {{
              emailSending
                ? t('inv.certificate.emailSending')
                : t('inv.certificate.emailSend')
            }}
          </CButton>
        </div>
      </template>
    </div>
  </CBottomSheet>
</template>

<style scoped>
.cs {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 320px;
}

.cs__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 260px;
}

.cs__loading-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.cs__iframe {
  width: 100%;
  height: 60vh;
  height: 60dvh;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff; /* certificate HTML expects a white canvas */
}

.cs__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
