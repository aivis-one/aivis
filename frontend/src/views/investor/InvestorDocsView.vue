<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- InvestorDocsView (Phase F4.4 B4)
// =============================================================================
//
// User's legal documents list with read + sign flow. Rendered by
// InvestorShell at /investor/docs. Not a top-level tab -- entered via
// InvestorMoreView (B6, stub today). Sub-route with back pattern:
// CHeader with back button, client-owned state, no Pinia store (the
// list is never read by another view, so a store would only duplicate
// the ref).
//
// DATA.
//   listDocuments() returns rows already resolved by the backend to
//   the caller's locale (user_language with `en` fallback). One row
//   per required type; `is_signed` tells whether this specific row
//   was signed. Server-side order is preserved (decision Q3 in chat:
//   no client-side sorting).
//
// LAYOUT.
//   Top: CHeader with title + built-in back (router.back() or `/` on
//   deep-link, which redirects to the role dashboard -- an acceptable
//   fallback for deep entry).
//   Body: list of .doc-item rows. Icon + title + meta + status badge
//   (signed / pending). Tap opens the detail modal.
//
// DETAIL MODAL (CModal -- decision Q2 in chat).
//   - Body: HTML fetched from /legal/{doc.language}/{doc.type}.html,
//     the exact localised copy the backend selected. Parsed via
//     DOMParser, body.innerHTML extracted so the mount node contains
//     just the legal content, no <html>/<head>/<meta>. Rendered with
//     v-html. No sanitisation -- the legal folder ships with our own
//     repo, not user input.
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

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CModal } from '@/components/ui'
import CHeader from '@/components/layout/CHeader.vue'
import { ApiResponseError } from '@/api/client'
import { listDocuments, signDocument } from '@/api/documents'
import { useToast } from '@/composables/useToast'
import type { DocumentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

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
// Modal state
// ---------------------------------------------------------------------------

const viewingDoc = ref<DocumentResponse | null>(null)
const viewContent = ref<string>('')
const viewLoading = ref<boolean>(false)
const viewError = ref<boolean>(false)
const signing = ref<boolean>(false)

const modalOpen = computed<boolean>(() => viewingDoc.value !== null)

async function openDoc(doc: DocumentResponse): Promise<void> {
  viewingDoc.value = doc
  viewContent.value = ''
  viewError.value = false
  viewLoading.value = true
  try {
    const resp = await fetch(`/legal/${doc.language}/${doc.type}.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
    // Parse the full HTML document and pull the body innerHTML so
    // the mounted node contains just the legal content, not
    // <html>/<head>/<title>/<meta>.
    const dom = new DOMParser().parseFromString(raw, 'text/html')
    viewContent.value = dom.body.innerHTML
  } catch {
    viewError.value = true
  } finally {
    viewLoading.value = false
  }
}

async function retryModalBody(): Promise<void> {
  if (viewingDoc.value) {
    await openDoc(viewingDoc.value)
  }
}

function closeModal(): void {
  viewingDoc.value = null
  viewContent.value = ''
  viewError.value = false
  signing.value = false
}

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
  return doc.is_signed
    ? t('inv.docs.status.signed')
    : t('inv.docs.status.pending')
}

function metaLabel(doc: DocumentResponse): string {
  // DocumentResponse does not carry a signed_at timestamp (is_signed
  // is a derived flag built by the backend on list). Showing just a
  // signed/pending label here; a per-signature timestamp would need
  // a second endpoint and is out of B4 scope.
  return doc.is_signed
    ? t('inv.docs.meta.signed')
    : t('inv.docs.meta.pending')
}
</script>

<template>
  <div class="docs">
    <CHeader
      :show-back="true"
      :show-logo="false"
      :title="t('inv.docs.title')"
    />

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
      <li
        v-for="doc in documents"
        :key="doc.id"
        class="docs__item"
        @click="openDoc(doc)"
      >
        <div class="docs__icon">
          <FileText :size="18" />
        </div>
        <div class="docs__body">
          <div class="docs__title">{{ doc.title }}</div>
          <div class="docs__meta">{{ metaLabel(doc) }}</div>
        </div>
        <span class="docs__status" :class="statusClass(doc)">
          {{ statusLabel(doc) }}
        </span>
      </li>
    </ul>

    <!-- Detail modal -->
    <CModal :open="modalOpen" @close="closeModal">
      <div v-if="viewingDoc" class="docs-modal">
        <h2 class="docs-modal__title">{{ viewingDoc.title }}</h2>

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

        <!-- Loaded body. No sanitisation: legal folder is repo-owned
             content, not user-supplied. DOMParser already stripped
             the document chrome. -->
        <div v-else class="docs-modal__body" v-html="viewContent" />

        <!-- Footer actions -->
        <div v-if="!viewLoading && !viewError" class="docs-modal__actions">
          <CButton
            v-if="!viewingDoc.is_signed"
            variant="primary"
            size="md"
            :loading="signing"
            @click="onSign"
          >
            {{ signing ? t('inv.docs.modal.signing') : t('inv.docs.modal.sign') }}
          </CButton>
          <CButton
            v-else
            variant="outline"
            size="md"
            @click="closeModal"
          >
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
  padding-bottom: 24px;
}

.docs__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 240px;
  padding: 24px;
}

.docs__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  list-style: none;
  margin: 0;
}

.docs__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.docs__item:hover {
  border-color: var(--primary-light);
  background: var(--bg-subtle);
}

.docs__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  /* Tinted primary background. Fallback keeps the icon chip legible
     even if the CSS variable isn't defined for this theme. */
  background: var(--primary-tint, rgba(26, 107, 106, 0.12));
  color: var(--primary);
  flex-shrink: 0;
}

.docs__body {
  flex: 1;
  min-width: 0;
}
.docs__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.docs__meta {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.docs__status {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  white-space: nowrap;
  flex-shrink: 0;
}
.docs__status--signed {
  background: var(--success-dim, rgba(34, 197, 94, 0.14));
  color: var(--success, #22c55e);
}
.docs__status--pending {
  background: var(--warning-dim, rgba(245, 158, 11, 0.14));
  color: var(--warning, #f59e0b);
}

/* Modal */
.docs-modal__title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 16px;
  /* Leave room on the right for the CModal close (X) button. */
  padding-right: 32px;
}

.docs-modal__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-height: 160px;
  padding: 16px 0;
}
.docs-modal__hint {
  font-size: 13px;
  color: var(--text-tertiary);
}

.docs-modal__body {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  max-height: 55vh;
  overflow-y: auto;
  padding-right: 4px;
}

/* Legal HTML markup passes through v-html. Basic typography for
   the tags we actually use in the seeded documents. */
.docs-modal__body :deep(h1),
.docs-modal__body :deep(h2),
.docs-modal__body :deep(h3) {
  margin-top: 12px;
  margin-bottom: 8px;
  font-weight: 700;
}
.docs-modal__body :deep(p) {
  margin: 8px 0;
}

.docs-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
</style>
