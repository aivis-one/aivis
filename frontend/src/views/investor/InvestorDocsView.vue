<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorDocsView (Phase F4.4 B4 + B5-post)
// =============================================================================
//
// User's legal documents list with read + sign flow. Rendered by
// InvestorShell at /investor/docs. Top-level tab reached via CTabBar
// (the "Documents" tab promoted from InvestorMoreView in a previous
// iter). Client-owned state, no Pinia store -- the list is never read
// by another view, so a store would only duplicate the ref.
//
// DATA.
//   Two sources, one list. listDocuments() returns the documents the
//   role must sign (the cabinet terms and the privacy policy, signed by
//   the registration ticks), resolved by the backend to the caller's
//   locale with `en` fallback; `is_signed` tells whether each was signed.
//   READ_TYPES names every legal document the role reads -- a document
//   no role signs is not in that list, so each is fetched by type
//   (GET /documents/by-type/{type}); a type with no active document
//   (404) is left out. The list follows READ_TYPES' order; a required
//   type outside it comes last. Every row opens for reading and can be
//   downloaded; only a required, unsigned row offers "Sign".
//
// LAYOUT.
//   The title is the frame's header (K25, `useScreenHeader`). As a top-level
//   tab the view has no originating screen to navigate back to.
//   Body: the system's document rows (K44 on the Row list, K23): icon + title
//   + meta + status badge (signed / pending). The row's link is the document's
//   own static file; a tap opens it in the detail window instead.
//
// DETAIL WINDOW (the system's Document viewer, K36, placement modal; B5-post hardening).
//   B4 rendered the legal HTML via v-html after stripping the doc
//   chrome with DOMParser. That gave the mounted node full access to
//   the SPA origin (localStorage, auth token), which is unacceptable
//   once legal content starts being templated (investor name, date,
//   certificate number all become user-reachable injection points).
//   B5-post replaces v-html with a sandboxed iframe -- identical
//   pattern to CertificateSheet.vue:
//     - fetch /legal/{language}/{type}.html
//     - wrap the response body in a Blob(text/html)
//     - URL.createObjectURL -> iframe src
//     - sandbox="" (empty value) forbids scripts, forms, same-origin
//       access, navigation, storage; the legal text is static and
//       needs none of these. See TD-F11b.
//   URL lifecycle: revoke-before-overwrite on each openDoc() and a
//   final revoke on modal close / component unmount.
//
//   Path safety. doc.type and doc.language are backend-driven free-
//   form strings. A seed misconfig with "../../index" in either field
//   would let fetch() leave /legal/. Even though the fetch() URL is
//   always same-origin and the response would still be interpreted
//   as text/html for the Blob wrap, we narrow to a strict token regex
//   before touching the path. encodeURIComponent is applied on top as
//   a belt-and-braces pass for any character that slips through the
//   regex by accident.
//
// DETAIL MODAL -- ACTIONS.
//   - Pending doc -> Sign CTA. POST /documents/{id}/sign.
//     201 success | 409 treated as idempotent success (concurrent
//     tab, replayed request). Local is_signed flipped on the row in
//     the list without a refetch; modal closes; toast on success.
//   - Signed doc -> Close button, read-only.
//   - Any other error on sign -> toast, button re-enables.
//
// ERROR HANDLING.
//   List fetch fail: CEmptyState + Retry (common.retry key). Silent
//   refresh on return is not needed -- docs rarely change mid-session.
//   Modal body fetch fail: inline CEmptyState + Retry.
//
// EMPTY.
//   Zero required documents for the role (backend returns []) is a
//   valid state, rendered with a short CEmptyState. Not an error.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, Download, FileText, X } from '@/components/ui/icons'

import { CBadge, CButton, CEmptyState, CLoader, CListSkeleton } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useDialog } from '@/composables/useDialog'
import { ApiResponseError } from '@/api/client'
import { getDocumentByType, listDocuments, signDocument } from '@/api/documents'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type { DocumentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const authStore = useAuthStore()

useScreenHeader({ title: () => t('inv.docs.title') })

// Strict token for both doc.type and doc.language. Backend currently
// emits plain identifiers (privacy_policy, terms_of_service, en, ru,
// etc.); anything outside this shape indicates a seed misconfig and
// must not be turned into a fetch path.
const SAFE_TOKEN = /^[a-z0-9_-]{1,64}$/i

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

// Every legal document a buyer reads in the cabinet, in display order.
// The AML policy is the staff's; the licence agreement and the company
// agreement are not a buyer's.
const BUYER_READ_TYPES: readonly string[] = [
  'cabinet_terms',
  'privacy_policy',
  'buyer_agreement',
  'pre_purchase_disclosure',
  'kyc_notice',
  'index_rules',
]

// An integrator reads the buyer's documents and, after them, their own
// integrator-agent agreement. One screen, the list extended by role.
const AGENT_READ_TYPES: readonly string[] = [...BUYER_READ_TYPES, 'agent_integrator_agreement']

// The project account reads the company's legal documents only: the cabinet
// terms and the privacy policy. Its own agreements and the buyers' papers are
// not listed here.
const COMPANY_READ_TYPES: readonly string[] = ['cabinet_terms', 'privacy_policy']

// A staff member reads the AML and screening policy, their document; nothing
// of it is required of them to sign.
const STAFF_READ_TYPES: readonly string[] = ['aml_policy']

const READ_TYPES: readonly string[] =
  authStore.role === 'agent'
    ? AGENT_READ_TYPES
    : authStore.role === 'company'
      ? COMPANY_READ_TYPES
      : authStore.role === 'staff'
        ? STAFF_READ_TYPES
        : BUYER_READ_TYPES

const documents = ref<DocumentResponse[]>([])
// Ids of the documents the role must sign (from listDocuments()).
const requiredIds = ref<Set<string>>(new Set())
const loading = ref<boolean>(false)
const errored = ref<boolean>(false)

async function fetchReadable(type: string): Promise<DocumentResponse | null> {
  try {
    return await getDocumentByType(type)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) return null
    throw err
  }
}

async function fetchDocuments(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const required = await listDocuments()
    const byType = new Map(required.map((d) => [d.type, d]))
    const readable = await Promise.all(
      READ_TYPES.filter((type) => !byType.has(type)).map((type) => fetchReadable(type)),
    )
    for (const doc of readable) {
      if (doc) byType.set(doc.type, doc)
    }
    const ordered: DocumentResponse[] = []
    for (const type of READ_TYPES) {
      const doc = byType.get(type)
      if (doc) ordered.push(doc)
    }
    for (const doc of required) {
      if (!READ_TYPES.includes(doc.type)) ordered.push(doc)
    }
    requiredIds.value = new Set(required.map((d) => d.id))
    documents.value = ordered
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}

function needsSigning(doc: DocumentResponse): boolean {
  return requiredIds.value.has(doc.id) && !doc.is_signed
}

// The static file of a document, the same one the reader shows; null when
// the type or language is not a plain token.
function fileUrl(doc: DocumentResponse): string | null {
  if (!SAFE_TOKEN.test(doc.language) || !SAFE_TOKEN.test(doc.type)) return null
  return `${import.meta.env.BASE_URL}legal/${encodeURIComponent(doc.language)}/${encodeURIComponent(doc.type)}.html`
}

onMounted(() => {
  void fetchDocuments()
})

// ---------------------------------------------------------------------------
// Modal + iframe blob lifecycle
// ---------------------------------------------------------------------------

const viewingDoc = ref<DocumentResponse | null>(null)
const viewLoading = ref<boolean>(false)
const viewError = ref<boolean>(false)
const viewBlobUrl = ref<string | null>(null)
const signing = ref<boolean>(false)

const modalOpen = computed<boolean>(() => viewingDoc.value !== null)

// Escape, focus containment and focus restore for the window.
const dialogEl = ref<HTMLElement | null>(null)
const titleId = useId()

// Monotonic per-view counter, same pattern as useCertificateBlob:
// a second openDoc() call while the first fetch is still in flight
// must not publish the losing result, and must revoke the losing
// blob URL it just created.
let openEpoch = 0

function _revokeBlob(): void {
  if (viewBlobUrl.value) {
    URL.revokeObjectURL(viewBlobUrl.value)
    viewBlobUrl.value = null
  }
}

async function openDoc(doc: DocumentResponse): Promise<void> {
  // Bump epoch BEFORE the SAFE_TOKEN guard so a still-in-flight
  // previous openDoc() is invalidated even when the current call
  // bails out early. Without this, a parallel valid openDoc() could
  // resolve later and overwrite the error state we just set.
  const mine = ++openEpoch

  // Reject malformed identifiers before they become a fetch path.
  if (!SAFE_TOKEN.test(doc.language) || !SAFE_TOKEN.test(doc.type)) {
    viewingDoc.value = doc
    viewError.value = true
    viewLoading.value = false
    _revokeBlob()
    return
  }
  viewingDoc.value = doc
  viewError.value = false
  viewLoading.value = true
  _revokeBlob()

  let nextUrl: string | null = null
  try {
    const lang = encodeURIComponent(doc.language)
    const type = encodeURIComponent(doc.type)
    const resp = await fetch(`${import.meta.env.BASE_URL}legal/${lang}/${type}.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
    // Wrap the raw HTML in a text/html blob so the iframe renders it
    // as a standalone document. No DOMParser/innerHTML trickery --
    // iframe is sandboxed so the document chrome is harmless.
    const blob = new Blob([raw], { type: 'text/html' })
    nextUrl = URL.createObjectURL(blob)
  } catch {
    if (mine === openEpoch) {
      viewError.value = true
    }
  } finally {
    if (mine === openEpoch) {
      viewLoading.value = false
    }
  }

  if (mine !== openEpoch) {
    // Superseded -- another openDoc() started after us. Revoke our
    // blob so the browser reclaims it.
    if (nextUrl) URL.revokeObjectURL(nextUrl)
    return
  }
  viewBlobUrl.value = nextUrl
}

async function retryModalBody(): Promise<void> {
  if (viewingDoc.value) {
    await openDoc(viewingDoc.value)
  }
}

function closeModal(): void {
  openEpoch += 1
  viewingDoc.value = null
  viewError.value = false
  viewLoading.value = false
  signing.value = false
  _revokeBlob()
}

useDialog(modalOpen, dialogEl, () => closeModal())

onUnmounted(() => {
  _revokeBlob()
})

// ---------------------------------------------------------------------------
// Sign flow
// ---------------------------------------------------------------------------

async function onSign(): Promise<void> {
  if (!viewingDoc.value || signing.value) return
  signing.value = true
  const docId = viewingDoc.value.id

  try {
    await signDocument(docId)
  } catch (err: unknown) {
    // 409 -- already signed (concurrent tab, replayed request).
    // Treat as idempotent success and fall through. Any other
    // response is a real failure.
    if (!(err instanceof ApiResponseError && err.status === 409)) {
      showToast(t('inv.docs.modal.signError'), 'error')
      signing.value = false
      return
    }
  }

  // Flip the local flag so the row badge updates without a refetch.
  const idx = documents.value.findIndex((d) => d.id === docId)
  if (idx !== -1) {
    const prev = documents.value[idx]!
    documents.value[idx] = { ...prev, is_signed: true }
  }

  showToast(t('inv.docs.modal.signSuccess'), 'success')
  closeModal()
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

function statusVariant(doc: DocumentResponse): 'success' | 'warning' {
  return doc.is_signed ? 'success' : 'warning'
}

function statusLabel(doc: DocumentResponse): string {
  return doc.is_signed ? t('inv.docs.status.signed') : t('inv.docs.status.pending')
}

// A row shows a status badge only when it was signed or is still to be
// signed; a document that is only read carries none.
function showsStatus(doc: DocumentResponse): boolean {
  return doc.is_signed === true || needsSigning(doc)
}

function metaLabel(doc: DocumentResponse): string {
  // DocumentResponse does not carry a signed_at timestamp (is_signed
  // is a derived flag built by the backend on list), so the row says
  // signed, to sign, or to read.
  if (doc.is_signed) return t('inv.docs.meta.signed')
  return needsSigning(doc) ? t('inv.docs.meta.pending') : t('inv.docs.meta.read')
}
</script>

<template>
  <div class="docs">
    <!-- First load: the placeholder rows of the list that will arrive (K19) -->
    <CListSkeleton v-if="loading && documents.length === 0" :rows="4" />

    <!-- Error state -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.docs.errorTitle')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="fetchDocuments">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty state -->
    <CEmptyState
      v-else-if="documents.length === 0"
      :title="t('inv.docs.empty.title')"
      :description="t('inv.docs.empty.description')"
    />

    <!-- List (K44): a row's link is the document's own file; a tap opens the window -->
    <ul v-else class="ds-rows">
      <li v-for="doc in documents" :key="doc.id" class="ds-row ds-docrow">
        <span class="ds-row__lead"><FileText size="sm" /></span>
        <span class="ds-row__body">
          <a
            v-if="fileUrl(doc)"
            class="ds-row__link"
            :href="fileUrl(doc) ?? undefined"
            @click.prevent="openDoc(doc)"
          >
            <span class="ds-row__title">{{ doc.title }}</span>
            <span class="ds-row__meta">{{ metaLabel(doc) }}</span>
          </a>
          <template v-else>
            <span class="ds-row__title">{{ doc.title }}</span>
            <span class="ds-row__meta">{{ metaLabel(doc) }}</span>
          </template>
        </span>
        <span v-if="showsStatus(doc)" class="ds-row__trail">
          <CBadge :variant="statusVariant(doc)" :text="statusLabel(doc)" />
        </span>
      </li>
    </ul>

    <!-- Detail window: the Document viewer (K36), placement modal -->
    <Teleport to="body">
      <div v-if="modalOpen" class="ds-docviewer" data-variant="modal" @click.self="closeModal">
        <div
          ref="dialogEl"
          class="ds-docviewer__dialog"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          tabindex="-1"
        >
          <div class="ds-docviewer__head">
            <h2 :id="titleId" class="ds-docviewer__title">{{ viewingDoc?.title }}</h2>
            <button
              type="button"
              class="ds-button ds-button--ghost ds-button--icon"
              data-size="sm"
              :aria-label="t('inv.docs.modal.close')"
              @click="closeModal"
            >
              <X size="sm" />
            </button>
          </div>

          <div
            class="ds-docviewer__body"
            tabindex="0"
            role="region"
            :aria-labelledby="titleId"
            :aria-busy="viewLoading ? 'true' : undefined"
          >
            <!-- Loading body -->
            <template v-if="viewLoading">
              <CLoader :size="24" />
              <p class="ds-docviewer__status">
                {{ t('inv.docs.modal.loading') }}
              </p>
            </template>

            <!-- Error body -->
            <div v-else-if="viewError" class="ds-alert ds-alert--danger" role="alert">
              <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
              <div class="ds-alert__content">
                <p class="ds-alert__title">{{ t('inv.docs.modal.errorTitle') }}</p>
                <div class="ds-alert__actions">
                  <CButton variant="outline" size="sm" inline @click="retryModalBody">
                    {{ t('inv.docs.modal.errorRetry') }}
                  </CButton>
                </div>
              </div>
            </div>

            <!--
              Loaded body. Rendered in a sandboxed iframe via blob URL,
              mirroring CertificateSheet.vue. `sandbox=""` (empty value)
              forbids scripts, forms, same-origin access, navigation,
              and storage. Legal documents are static text -- none of
              those are needed. See TD-F11b.
            -->
            <iframe
              v-else-if="viewBlobUrl"
              :src="viewBlobUrl"
              sandbox=""
              class="ds-docviewer__frame"
              :title="viewingDoc?.title"
            />
          </div>

          <!-- Footer actions. Hidden while loading so the user does not
               tap "Sign" on a document body that has not rendered yet. -->
          <div v-if="viewingDoc && !viewLoading && !viewError" class="ds-docviewer__actions">
            <a
              v-if="fileUrl(viewingDoc)"
              class="ds-button ds-button--secondary"
              :href="fileUrl(viewingDoc) ?? undefined"
              :download="`${viewingDoc.type}.${viewingDoc.language}.html`"
            >
              <Download size="sm" />
              <span>{{ t('inv.docs.modal.download') }}</span>
            </a>
            <CButton
              v-if="needsSigning(viewingDoc)"
              variant="primary"
              inline
              :loading="signing"
              @click="onSign"
            >
              {{ signing ? t('inv.docs.modal.signing') : t('inv.docs.modal.sign') }}
            </CButton>
            <CButton v-else variant="outline" inline @click="closeModal">
              {{ t('inv.docs.modal.close') }}
            </CButton>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
}
</style>
