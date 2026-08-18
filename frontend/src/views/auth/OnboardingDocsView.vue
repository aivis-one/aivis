<script setup lang="ts">
// Document signing screen.
// Flow:
//   1. GET /api/v1/documents -> list for user's role, already resolved
//      to the user's locale (backend picks user_language or falls back
//      to 'en', and 500s if a required type is missing in both).
//   2. User ticks a checkbox per unsigned doc (checkbox is locked-checked
//      for docs already signed earlier). Click on "Read" opens a modal
//      that fetches /legal/{doc.language}/{doc.type}.html -- the exact
//      localised copy the backend returned -- and renders the body via
//      v-html. No sanitisation: the legal folder ships with our own
//      repo. HTML is parsed and the <body> innerHTML is extracted so
//      the rendered node does not contain <html>, <head> or <meta>.
//   3. "Sign documents" button is disabled until every unsigned doc
//      is ticked. Click -> POST /documents/{id}/sign for each unsigned
//      doc, then fetchMe() (backend advanced onboarding_step on the
//      last signing), then router.push('/') so the guard routes to the
//      role dashboard.

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError } from '@/api/client'
import { safeNavigate } from '@/composables/safeNavigate'
import type { DocumentResponse } from '@/api/types'
import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CModal } from '@/components/ui'

const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()

// -- List state --
const documents = ref<DocumentResponse[]>([])
const loadingDocs = ref(true)
const error = ref('')

// User-ticked checkboxes for currently-unsigned docs. Using a Set keyed
// by document UUID so toggling stays O(1).
const checkedIds = ref<Set<string>>(new Set())

// -- Sign flow --
const signing = ref(false)

// -- Modal state --
const viewingDoc = ref<DocumentResponse | null>(null)
const viewContent = ref('')
const viewLoading = ref(false)
const viewError = ref('')

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

function isChecked(doc: DocumentResponse): boolean {
  return doc.is_signed === true || checkedIds.value.has(doc.id)
}

const checkedCount = computed(
  () => documents.value.filter(isChecked).length,
)

// All unsigned docs have a tick, or there are no docs at all.
const canSignAll = computed(() => {
  if (documents.value.length === 0) return true
  return documents.value.every(isChecked)
})

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

onMounted(async () => {
  await fetchDocuments()
})

async function fetchDocuments(): Promise<void> {
  loadingDocs.value = true
  error.value = ''
  try {
    documents.value = await api.get<DocumentResponse[]>('/api/v1/documents')
  } catch {
    error.value = t('common.error')
  } finally {
    loadingDocs.value = false
  }
}

// ---------------------------------------------------------------------------
// Checkbox toggle
// ---------------------------------------------------------------------------

function toggleCheck(doc: DocumentResponse): void {
  // Already-signed docs are locked.
  if (doc.is_signed) return
  // Rebuild the Set so Vue reactivity picks up the change.
  const next = new Set(checkedIds.value)
  if (next.has(doc.id)) {
    next.delete(doc.id)
  } else {
    next.add(doc.id)
  }
  checkedIds.value = next
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

async function openDocument(doc: DocumentResponse): Promise<void> {
  viewingDoc.value = doc
  viewContent.value = ''
  viewError.value = ''
  viewLoading.value = true
  try {
    // Fetch the exact localised HTML the backend selected for this user.
    const resp = await fetch(`/legal/${doc.language}/${doc.type}.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
    // Parse the full HTML document and pull the body innerHTML so the
    // mounted node contains just the legal content, not <html>, <head>,
    // <title>, <meta>, etc.
    const dom = new DOMParser().parseFromString(raw, 'text/html')
    viewContent.value = dom.body.innerHTML
  } catch {
    viewError.value = t('common.error')
  } finally {
    viewLoading.value = false
  }
}

function closeModal(): void {
  viewingDoc.value = null
  viewContent.value = ''
  viewError.value = ''
}

// ---------------------------------------------------------------------------
// Sign-all
// ---------------------------------------------------------------------------

async function handleSignAll(): Promise<void> {
  if (!canSignAll.value || signing.value) return
  signing.value = true
  error.value = ''

  try {
    // Sign every currently-unsigned doc sequentially. A 409 from the
    // backend means "already signed" -- treat as success and move on.
    for (const doc of documents.value) {
      if (doc.is_signed) continue
      try {
        await api.post(`/api/v1/documents/${doc.id}/sign`)
      } catch (err) {
        if (err instanceof ApiResponseError && err.status === 409) {
          continue
        }
        throw err
      }
    }

    // Backend auto-advanced onboarding_step on the last signing; pull
    // the new user state so the router guard sees onboarding_complete.
    await authStore.fetchMe()

    // Root resolves to the role-based dashboard via guard.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer docs-signing-error
    // catch and surface as a generic-error toast after successful signing.
    await safeNavigate(router.push('/'), '[OnboardingDocsView] post-sign to home')
  } catch (err) {
    if (err instanceof ApiResponseError) {
      error.value = err.detail
    } else {
      error.value = t('common.error')
    }
  } finally {
    signing.value = false
  }
}
</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <AivisLogo :height="28" />
      <CAppControls />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.docs.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.docs.subtitle') }}</p>

      <!-- Loading -->
      <div v-if="loadingDocs" class="docs-loading">
        <span class="btn-spinner" />
      </div>

      <!-- Document list / empty state -->
      <template v-else>
        <div v-if="documents.length > 0" class="doc-list">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="doc-item"
            :class="{ signed: doc.is_signed }"
            @click="toggleCheck(doc)"
          >
            <div
              class="doc-checkbox"
              :class="{ checked: isChecked(doc), locked: doc.is_signed }"
            >
              <span v-if="isChecked(doc)">✓</span>
            </div>
            <div class="doc-info">
              <div class="doc-title">{{ doc.title }}</div>
              <div class="doc-meta">
                <span class="doc-required">{{ t('auth.docs.required') }}</span>
              </div>
            </div>
            <button
              type="button"
              class="doc-link"
              @click.stop="openDocument(doc)"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                width="16"
                height="16"
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              <span class="doc-link-label">{{ t('auth.docs.read') }}</span>
            </button>
          </div>
        </div>

        <!-- Counter -->
        <div v-if="documents.length > 0" class="doc-counter">
          {{ t('auth.docs.checkedOf', { checked: checkedCount, total: documents.length }) }}
        </div>

        <!-- No docs required for this role -->
        <div v-if="documents.length === 0" class="no-docs">
          {{ t('auth.docs.noDocs') }}
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <div class="doc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="!canSignAll || signing"
            @click="handleSignAll"
          >
            <span v-if="signing" class="btn-spinner" />
            <span v-else>{{ t('auth.docs.signDocumentsBtn') }}</span>
          </button>
        </div>
      </template>
    </div>

    <!-- Document preview modal -->
    <CModal :open="viewingDoc !== null" @close="closeModal">
      <h3 class="doc-modal__title">
        {{ viewingDoc ? viewingDoc.title : '' }}
      </h3>
      <div class="doc-modal__body">
        <div v-if="viewLoading" class="doc-modal__center">
          <span class="btn-spinner" />
        </div>
        <p v-else-if="viewError" class="auth-error">{{ viewError }}</p>
        <!-- Trusted content: HTML authored in our own repo. Body innerHTML
             was extracted via DOMParser above, so <html>/<head>/<meta>
             are not in the mounted subtree. -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-else class="doc-modal__content" v-html="viewContent" />
      </div>
      <div class="doc-modal__actions">
        <button type="button" class="btn btn-primary" @click="closeModal">
          {{ t('common.close') }}
        </button>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex; flex-direction: column;
  min-height: 100vh; min-height: 100dvh;
  background: var(--bg-page);
}
.auth-header {
  display: flex; align-items: center; justify-content: center;
  padding: 16px 24px;
}
.auth-content {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 24px; overflow-y: auto;
}
.auth-title {
  font-size: 24px; font-weight: 700; color: var(--text-primary);
  margin-bottom: 8px; text-align: center;
}
.auth-subtitle {
  font-size: 14px; color: var(--text-secondary);
  margin-bottom: 32px; text-align: center; line-height: 1.5;
}
.auth-error {
  font-size: 13px; color: var(--danger); text-align: center;
  margin-bottom: 16px; max-width: 400px;
}

.docs-loading {
  display: flex; justify-content: center; padding: 40px;
}

.no-docs {
  font-size: 14px; color: var(--text-secondary);
  text-align: center; margin-bottom: 24px;
}

.doc-list {
  width: 100%; max-width: 400px;
  display: flex; flex-direction: column; gap: 12px;
  margin-bottom: 16px;
}
.doc-item {
  display: flex; align-items: flex-start; gap: 14px; padding: 16px;
  background: var(--bg-page); border: 1px solid var(--border-default);
  border-radius: var(--radius-md); cursor: pointer;
  transition: all 0.2s;
}
.doc-item:hover { border-color: var(--primary-hover); background: var(--bg-surface); }
.doc-item.signed { cursor: default; }

.doc-checkbox {
  width: 22px; height: 22px; min-width: 22px;
  border: 2px solid var(--border-default); border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; margin-top: 2px;
  font-size: 13px; color: white;
}
.doc-checkbox.checked {
  background: var(--primary); border-color: var(--primary);
}
.doc-checkbox.locked {
  opacity: 0.8;
}

.doc-info { flex: 1; }
.doc-title {
  font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;
}
.doc-meta { display: flex; gap: 8px; }
.doc-required {
  font-size: 11px; color: var(--danger); font-weight: 500;
}

.doc-link {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--text-tertiary); margin-top: 2px;
  background: none; border: none; padding: 2px 4px; cursor: pointer;
  font-family: inherit; font-size: 12px;
  transition: color 0.2s;
}
.doc-link:hover { color: var(--primary); }

.doc-counter {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 16px;
}

.doc-actions { width: 100%; max-width: 400px; }

.btn { width: 100%; }
.btn-primary {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 14px; border-radius: var(--radius-md);
  background: var(--primary); color: var(--on-primary);
  font-weight: 600; font-size: 15px; font-family: inherit;
  border: none; cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white; border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* --- Document preview modal --- */
.doc-modal__title {
  font-size: 18px; font-weight: 700; color: var(--text-primary);
  margin: 0 0 12px; padding-right: 24px;  /* room for close button */
}
.doc-modal__body {
  min-height: 120px; max-height: 60vh; overflow-y: auto;
  border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  padding: 16px; background: var(--bg-subtle, var(--bg-page));
  margin-bottom: 16px;
}
.doc-modal__center {
  display: flex; align-items: center; justify-content: center;
  min-height: 120px;
}
.doc-modal__content {
  font-size: 14px; color: var(--text-primary); line-height: 1.6;
}
.doc-modal__content :deep(h1) { font-size: 20px; margin: 0 0 12px; }
.doc-modal__content :deep(h2) { font-size: 16px; margin: 16px 0 8px; }
.doc-modal__content :deep(p) { margin: 0 0 12px; }
.doc-modal__content :deep(ul),
.doc-modal__content :deep(ol) { margin: 0 0 12px; padding-left: 20px; }
.doc-modal__content :deep(li) { margin-bottom: 4px; }

.doc-modal__actions {
  display: flex; justify-content: flex-end;
}
.doc-modal__actions .btn-primary {
  width: auto; min-width: 120px;
}
</style>
