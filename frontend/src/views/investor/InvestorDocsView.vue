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
//   listDocuments() returns rows already resolved by the backend to
//   the caller's locale (user_language with `en` fallback). One row
//   per required type; `is_signed` tells whether this specific row
//   was signed. Server-side order is preserved (decision Q3 in chat:
//   no client-side sorting).
//
// LAYOUT.
//   Top: inline page-header (h1 title, no back-link) -- iter 2.7
//   batch B2 dropped the view-CHeader in favour of the single-shell-
//   header paradigm. As a top-level tab the view has no originating
//   screen to navigate back to; the shell's CHeader covers brand
//   identity, the inline <h1> labels the tab.
//   Body: list of .doc-item rows. Icon + title + meta + status badge
//   (signed / pending). Tap opens the detail modal.
//
// DETAIL MODAL (CModal, B5-post hardening).
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

import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CModal } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { listDocuments, signDocument } from '@/api/documents'
import { useToast } from '@/composables/useToast'
import type { DocumentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

// Strict token for both doc.type and doc.language. Backend currently
// emits plain identifiers (privacy_policy, terms_of_service, en, ru,
// etc.); anything outside this shape indicates a seed misconfig and
// must not be turned into a fetch path.
const SAFE_TOKEN = /^[a-z0-9_-]{1,64}$/i

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const documents = ref<DocumentResponse[]>([])
const loading = ref<boolean>(false)
const errored = ref<boolean>(false)

async function fetchDocuments(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    documents.value = await listDocuments()
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
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
    const resp = await fetch(`/legal/${lang}/${type}.html`)
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

function statusClass(doc: DocumentResponse): string {
  return doc.is_signed ? 'docs__status--signed' : 'docs__status--pending'
}

function statusLabel(doc: DocumentResponse): string {
  return doc.is_signed ? t('inv.docs.status.signed') : t('inv.docs.status.pending')
}

function metaLabel(doc: DocumentResponse): string {
  // DocumentResponse does not carry a signed_at timestamp (is_signed
  // is a derived flag built by the backend on list). Showing just a
  // signed/pending label here; a per-signature timestamp would need
  // a second endpoint and is out of B4 scope.
  return doc.is_signed ? t('inv.docs.meta.signed') : t('inv.docs.meta.pending')
}
</script>

<template>
  <div class="docs">
    <!-- iter 2.7 batch B2: inline page-header replaces view-CHeader.
         No back-link: this is a top-level tab reached via CTabBar,
         not a drill-down with originating context. Same paradigm as
         InvestorMoreView / InvestorSettingsView. -->
    <div class="docs__page-header">
      <h1 class="docs__page-title">
        {{ t('inv.docs.title') }}
      </h1>
    </div>

    <!-- First-load spinner -->
    <div v-if="loading && documents.length === 0" class="docs__center">
      <CLoader :size="32" />
    </div>

    <!-- Error state -->
    <div v-else-if="errored" class="docs__center">
      <CEmptyState :title="t('inv.docs.errorTitle')" />
      <CButton variant="outline" size="sm" @click="fetchDocuments">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty state -->
    <div v-else-if="documents.length === 0" class="docs__center">
      <CEmptyState
        :title="t('inv.docs.empty.title')"
        :description="t('inv.docs.empty.description')"
      />
    </div>

    <!-- List -->
    <ul v-else class="docs__list">
      <li v-for="doc in documents" :key="doc.id">
        <button type="button" class="docs__item" @click="openDoc(doc)">
          <div class="docs__icon">
            <FileText :size="16" />
          </div>
          <div class="docs__body">
            <div class="docs__title">
              {{ doc.title }}
            </div>
            <div class="docs__meta">
              {{ metaLabel(doc) }}
            </div>
          </div>
          <span class="docs__status" :class="statusClass(doc)">
            {{ statusLabel(doc) }}
          </span>
        </button>
      </li>
    </ul>

    <!-- Detail modal -->
    <CModal :open="modalOpen" @close="closeModal">
      <div v-if="viewingDoc" class="docs-modal">
        <h2 class="docs-modal__title">
          {{ viewingDoc.title }}
        </h2>

        <!-- Loading body -->
        <div v-if="viewLoading" class="docs-modal__center">
          <CLoader :size="24" />
          <div class="docs-modal__hint">
            {{ t('inv.docs.modal.loading') }}
          </div>
        </div>

        <!-- Error body -->
        <div v-else-if="viewError" class="docs-modal__center">
          <CEmptyState :title="t('inv.docs.modal.errorTitle')" />
          <CButton variant="outline" size="sm" @click="retryModalBody">
            {{ t('inv.docs.modal.errorRetry') }}
          </CButton>
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
          class="docs-modal__iframe"
          :title="viewingDoc.title"
        />

        <!-- Footer actions. Hidden while loading so the user does not
             tap "Sign" on a document body that has not rendered yet. -->
        <div v-if="!viewLoading && !viewError" class="docs-modal__actions">
          <CButton
            v-if="!viewingDoc.is_signed"
            variant="primary"
            :loading="signing"
            @click="onSign"
          >
            {{ signing ? t('inv.docs.modal.signing') : t('inv.docs.modal.sign') }}
          </CButton>
          <CButton v-else variant="outline" @click="closeModal">
            {{ t('inv.docs.modal.close') }}
          </CButton>
        </div>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

/* iter 2.7 batch B2 -- inline page-header replaces the previous
   view-CHeader. Title-only (no back-link): this is a top-level tab.
   Same paradigm as InvestorMoreView's .more__header / InvestorSettings'
   .sett__page-title. Class name `docs__page-title` chosen so it does
   not clash with `docs__title` already used for individual document
   item titles in the list. */
.docs__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-4) var(--space-2);
}
.docs__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.docs__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.docs__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  list-style: none;
  margin: 0;
}

.docs__item {
  appearance: none;
  background: none;
  border: none;
  margin: 0;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: start;
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition:
    border-color 0.2s,
    background 0.2s;
}
.docs__item:hover {
  border-color: var(--primary-hover);
  background: var(--bg-subtle);
}

.docs__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-lg);
  height: var(--size-lg);
  border-radius: var(--radius-sm);
  background: var(--primary-subtle);
  color: var(--primary);
  flex-shrink: 0;
}

.docs__body {
  flex: 1;
  min-width: 0;
}
.docs__title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.docs__meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.docs__status {
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  flex-shrink: 0;
}
.docs__status--signed {
  background: var(--success-subtle);
  color: var(--success);
}
.docs__status--pending {
  background: var(--warning-subtle);
  color: var(--warning);
}

/* Modal */
.docs-modal__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
  padding-right: var(--space-6);
}

.docs-modal__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--center-md);
  padding: var(--space-4) 0;
}
.docs-modal__hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.docs-modal__iframe {
  width: 100%;
  height: 55vh;
  height: 55dvh;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: #fff;
}

.docs-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-default);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.docs-modal__hint {
  max-width: var(--maxw-prose);
}
</style>
