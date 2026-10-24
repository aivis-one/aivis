<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgreementSheet
//                       (iter 2.5 R2 §5.5; replaces CertificateSheet)
// =============================================================================
//
// The design system's Document sheet and viewer (K36), placement sheet: it renders
// a document HTML (per-Purchase agreement OR per-investor-company ownership
// certificate) in a sandboxed iframe and exposes two actions on it: "Close" and
// "Download". There is no
// "send to my e-mail": a document is read and downloaded in the cabinet.
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
//   always a blob behind it. It is a real link (a.ds-button with
//   `download`), and the URL is NOT revoked after the click -- it is
//   still on screen, and the sheet's own close / unmount path
//   (useAgreementBlob) owns its lifetime. The file name comes from
//   utils/documentFilename.ts.
//
// =============================================================================

import { computed, ref, toRef, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { CLoader } from '@/components/ui'
import { AlertTriangle, X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'
import { fetchAgreementBlob, fetchOwnershipCertificateBlob } from '@/api/agreements'
import { useAgreementBlob } from '@/composables/useAgreementBlob'
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

// Pick the fetcher based on mode. The mode prop is
// expected to be stable for the lifetime of an AgreementSheet instance
// (parent mounts one instance per surface); we capture the choice at
// setup time instead of recomputing on every render.
const isOwnership = props.mode === 'ownership'

const { blobUrl, loading, errored, load, clear } = useAgreementBlob(
  isOwnership ? fetchOwnershipCertificateBlob : fetchAgreementBlob,
)

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

// The file the save link hands over: the blob the frame shows, named by
// utils/documentFilename.ts.
const fileName = computed<string>(() =>
  isOwnership
    ? documentFilename({ mode: 'ownership', companyName: props.companyName })
    : documentFilename({
        mode: 'agreement',
        purchaseId: props.id ?? '',
        legalBasis: props.legalBasis,
        companyName: props.companyName,
      }),
)

// Escape, focus containment and focus restore.
const titleId = useId()
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, onClose)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="ds-docviewer" data-variant="sheet" @click.self="onClose">
      <div
        ref="dialogEl"
        class="ds-docviewer__dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <div class="ds-docviewer__head">
          <h2 :id="titleId" class="ds-docviewer__title">{{ sheetTitle }}</h2>
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="t('common.close')"
            @click="onClose"
          >
            <X size="sm" />
          </button>
        </div>

        <div
          class="ds-docviewer__body"
          tabindex="0"
          role="region"
          :aria-labelledby="titleId"
          :aria-busy="loading && !errored ? 'true' : undefined"
        >
          <!-- Loading -->
          <template v-if="loading && !errored">
            <CLoader />
            <p class="ds-docviewer__status" role="status">
              {{ t('inv.agreement.loading') }}
            </p>
          </template>

          <!-- Error -->
          <div v-else-if="errored" class="ds-alert ds-alert--danger" role="alert">
            <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
            <div class="ds-alert__content">
              <p class="ds-alert__text">{{ t('inv.agreement.errorTitle') }}</p>
              <div class="ds-alert__actions">
                <button
                  type="button"
                  class="ds-button ds-button--secondary"
                  data-size="sm"
                  @click="onRetry"
                >
                  {{ t('inv.agreement.errorRetry') }}
                </button>
              </div>
            </div>
          </div>

          <!--
            sandbox="" MUST stay present. Removing it, or relaxing it
            to sandbox="allow-same-origin", would let any scripting in
            the document HTML read the SPA's localStorage + JWT. See
            TD-F11b in AIVIS-Frontend.md.
          -->
          <iframe
            v-else-if="blobUrl"
            :src="blobUrl"
            sandbox=""
            class="ds-docviewer__frame"
            :title="sheetTitle"
          />
        </div>

        <!-- The save is a real link to the very blob the frame shows (it exists only
             in the loaded state, so there is always a blob behind it). -->
        <div class="ds-docviewer__actions">
          <button type="button" class="ds-button ds-button--secondary" @click="onClose">
            {{ t('inv.agreement.close') }}
          </button>
          <a
            v-if="blobUrl && !loading && !errored"
            class="ds-button ds-button--primary"
            :href="blobUrl"
            :download="fileName"
            rel="noopener"
          >
            {{ t('inv.agreement.save') }}
          </a>
        </div>
      </div>
    </div>
  </Teleport>
</template>
