<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgreementSheet
//                       (iter 2.5 R2 §5.5; replaces CertificateSheet)
// =============================================================================
//
// Bottom-sheet that renders a document HTML (per-Purchase agreement OR
// per-investor-company ownership certificate) in a sandboxed iframe
// and exposes two actions on it: "Save" and "Email to me".
//
// Generic over the document surface via the `mode` prop. The two
// surfaces share identical UX -- inline iframe + save + email + retry
// on error + local cooldown on rapid clicks -- so factoring them into
// one component keeps wiring small in the consumers (CompanyPositionView
// uses one instance for the row-level agreement and a second instance
// for the header-level ownership cert).
//
// PROPS.
//   open       -- bottom-sheet visibility (parent owns)
//   mode       -- 'agreement' renders per-Purchase agreement;
//                 'ownership' renders per-investor-company cert
//   id         -- purchaseId when mode='agreement',
//                 companyId  when mode='ownership'
//                 null when parent is not pointing at a row (closed)
//   legalBasis -- optional. Drives the i18n title in agreement mode so
//                 'sale' renders as "Purchase agreement", 'gift' as
//                 "Gift certificate", 'installment_tranche' as
//                 "Installment subcontract". Ignored in ownership mode.
//   companyName -- optional. Only names the saved file; absent while
//                 the parent's position detail is still loading, and
//                 the file name then simply goes without it.
//
// DATA FLOW.
//   The sheet watches `[open, id, mode]` and calls
//   useAgreementBlob.load() on the open->true transition (with a non-
//   null id). The composable owns the blob URL lifecycle -- automatic
//   revoke on scope dispose + manual revoke-before-overwrite on each
//   new load. useAgreementBlob is epoch-guarded so two back-to-back
//   load() calls from prop churn cannot leak the first URL.
//
//   `mode` is read once via getCurrentInstance during script setup --
//   the fetcher closure is fixed when the composable is created. Mode
//   flips at runtime are not supported (the parent owns one instance
//   per surface; CompanyPositionView mounts two AgreementSheet's --
//   one for purchases, one for ownership).
//
// SANDBOX -- TD-F11b MUST fix.
//   The HTML returned by the backend is rendered in an iframe via a
//   blob URL. Blob URLs inherit the page's origin, so without sandbox
//   the iframe could read localStorage and the JWT token.
//   `sandbox=""` (empty attribute value) forbids every capability:
//   no scripts, no forms, no same-origin access, no top-level
//   navigation, no storage. The document HTML is a static Jinja2
//   render (backend env is `autoescape=True, undefined=StrictUndefined`,
//   R2 §5.4) and does not need any of these privileges. If a future
//   document variant legitimately needs CSS background-image url()
//   fetches from the API origin, the correct escalation is the
//   narrowest allow-list, not a blanket sandbox="allow-same-origin".
//
// ERROR HANDLING.
//   load() throw -> composable's `errored` flag + sheet error state +
//   toast suppressed (inline message is enough; the sheet is modal,
//   nothing else competes for attention). The Retry button calls
//   load() again. R2 §5.3 introduces 500 as a legitimate
//   non-recoverable backend state (template_id NULL / fallback miss);
//   retry on 500 keeps failing until Staff fixes the template. The sheet's "errorTitle" is intentionally generic
//   so we don't blame the user for an infrastructure issue.
//
// SAVE (P-106).
//   Hands the reader THE SAME BLOB the iframe shows, as a file: no new
//   request, nothing regenerated, no PDF (owner's decision: no PDF in
//   any form). The button exists only in the loaded branch, so there is
//   always a blob behind it. The anchor is synthesised the way
//   api/attachments.ts downloads, with one difference: the URL is NOT
//   revoked after the click -- it is still on screen, and the sheet's
//   own close / unmount path (useAgreementBlob) owns its lifetime. The
//   file name comes from utils/documentFilename.ts.
//
// EMAIL CTA.
//   The send endpoint is rate-limited on the backend
//   (`agreement_email:{user_id}` or `ownership_email:{user_id}`, both
//   at 5/60s). The button disables during the in-flight request and
//   during an additional cooldown window locally (see EMAIL_COOLDOWN_MS
//   below) so a frustrated double-tap doesn't burn the next quota
//   second. On success: toast 'sent'; on failure: toast 'could not
//   send' + unlock the button immediately so the user can retry.
//
//   Carried forward from CertificateSheet (B5-post): no narrowing on
//   the error class -- 429 / 500 / network all surface the same toast.
//   404 cannot happen once load() has succeeded (caller owns the
//   resource; backend re-checks ownership on email send but the user
//   would not have reached this button otherwise).
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import CBottomSheet from '@/components/ui/CBottomSheet.vue'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import {
  emailAgreement,
  emailOwnershipCertificate,
  fetchAgreementBlob,
  fetchOwnershipCertificateBlob,
} from '@/api/agreements'
import { useAgreementBlob } from '@/composables/useAgreementBlob'
import { useToast } from '@/composables/useToast'
import { documentFilename } from '@/utils/documentFilename'

type AgreementMode = 'agreement' | 'ownership'

const props = defineProps<{
  open: boolean
  mode: AgreementMode
  id: string | null
  legalBasis?: string
  companyName?: string
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const { showToast } = useToast()

// Pick the fetcher and email function based on mode. The mode prop is
// expected to be stable for the lifetime of an AgreementSheet instance
// (parent mounts one instance per surface); we capture the choice at
// setup time instead of recomputing on every render.
const isOwnership = props.mode === 'ownership'

const { blobUrl, loading, errored, load, clear } = useAgreementBlob(
  isOwnership ? fetchOwnershipCertificateBlob : fetchAgreementBlob,
)

const sendEmail = isOwnership ? emailOwnershipCertificate : emailAgreement

// Local cooldown after a send attempt so rapid taps don't hammer the
// rate-limited backend route. The number is conservative -- backend
// guards the actual ceiling, this is a UX nicety.
const EMAIL_COOLDOWN_MS = 3_000

const emailSending = ref(false)
const emailLockedUntil = ref<number>(0)

const emailDisabled = computed<boolean>(() => {
  if (emailSending.value) return true
  if (!blobUrl.value) return true
  return Date.now() < emailLockedUntil.value
})

// ---------------------------------------------------------------------------
// i18n title resolution
// ---------------------------------------------------------------------------

// Map a Purchase.legal_basis value onto an i18n title key. Backend
// emits the literal strings 'sale' / 'gift' / 'installment_tranche'
// (see backend constants). Anything else falls through to the generic
// 'document' label -- we don't want a hard crash if a future legal_basis
// reaches the UI before the i18n catalogue gets updated.
const sheetTitle = computed<string>(() => {
  if (isOwnership) {
    return t('inv.agreement.title.ownership')
  }
  switch (props.legalBasis) {
    case 'sale':
      return t('inv.agreement.title.purchaseAgreement')
    case 'gift':
      return t('inv.agreement.title.giftCertificate')
    case 'installment_tranche':
      return t('inv.agreement.title.installmentSubcontract')
    default:
      return t('inv.agreement.title.document')
  }
})

// ---------------------------------------------------------------------------
// Load on open transition
// ---------------------------------------------------------------------------

watch(
  () => [props.open, props.id] as const,
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
  if (!props.id) return
  try {
    await load(props.id)
  } catch {
    // swallow
  }
}

function onSave(): void {
  if (!blobUrl.value || !props.id) return
  const anchor = document.createElement('a')
  anchor.href = blobUrl.value
  anchor.download = isOwnership
    ? documentFilename({ mode: 'ownership', companyName: props.companyName })
    : documentFilename({
        mode: 'agreement',
        purchaseId: props.id,
        legalBasis: props.legalBasis,
        companyName: props.companyName,
      })
  anchor.rel = 'noopener'
  anchor.click()
}

async function onEmail(): Promise<void> {
  if (!props.id || emailDisabled.value) return
  emailSending.value = true
  try {
    await sendEmail(props.id)
    showToast(t('inv.agreement.emailSuccess'), 'success')
    emailLockedUntil.value = Date.now() + EMAIL_COOLDOWN_MS
  } catch {
    // 429 / 500 / network all surface the same toast. 404 cannot
    // happen once load() has succeeded.
    showToast(t('inv.agreement.emailError'), 'error')
    // Unlock immediately on failure -- the user should be able to
    // retry without waiting for the cooldown window.
    emailLockedUntil.value = 0
  } finally {
    emailSending.value = false
  }
}
</script>

<template>
  <CBottomSheet :open="open" :title="sheetTitle" @close="onClose">
    <div class="ags">
      <!-- Loading -->
      <div v-if="loading && !errored" class="ags__center">
        <CLoader :size="28" />
        <div class="ags__loading-hint">
          {{ t('inv.agreement.loading') }}
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="errored" class="ags__center">
        <CEmptyState :title="t('inv.agreement.errorTitle')" />
        <CButton variant="outline" size="sm" @click="onRetry">
          {{ t('inv.agreement.errorRetry') }}
        </CButton>
      </div>

      <!-- Loaded -->
      <template v-else-if="blobUrl">
        <!--
          sandbox="" MUST stay present. Removing it, or relaxing it
          to sandbox="allow-same-origin", would let any scripting in
          the document HTML read the SPA's localStorage + JWT. See
          TD-F11b in AIVIS-Frontend.md.
        -->
        <iframe :src="blobUrl" sandbox="" class="ags__iframe" :title="sheetTitle" />

        <div class="ags__actions">
          <CButton variant="outline" size="sm" @click="onClose">
            {{ t('inv.agreement.close') }}
          </CButton>
          <CButton variant="outline" size="sm" @click="onSave">
            {{ t('inv.agreement.save') }}
          </CButton>
          <CButton variant="primary" size="sm" :disabled="emailDisabled" @click="onEmail">
            {{ emailSending ? t('inv.agreement.emailSending') : t('inv.agreement.emailSend') }}
          </CButton>
        </div>
      </template>
    </div>
  </CBottomSheet>
</template>

<style scoped>
.ags {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-height: 320px;
}

.ags__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-lg);
}

.ags__loading-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.ags__iframe {
  width: 100%;
  height: 60vh;
  height: 60dvh;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: #fff; /* document HTML expects a white canvas */
}

.ags__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
