<script setup lang="ts">
import { ExternalLink } from '@/components/ui/icons'
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
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import { postEntryTarget } from '@/utils/postAuthReturn'
import { updateMe } from '@/api/users'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'

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

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

function isChecked(doc: DocumentResponse): boolean {
  return doc.is_signed === true || checkedIds.value.has(doc.id)
}

const checkedCount = computed(() => documents.value.filter(isChecked).length)

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

// LegalDocModal fetches the exact localised HTML the backend selected.
function openDocument(doc: DocumentResponse): void {
  viewingDoc.value = doc
}

function closeModal(): void {
  viewingDoc.value = null
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

    // An account left on an older step with every document already signed
    // has no signing to advance it: a profile save that changes nothing asks
    // the server to re-check the step.
    if (authStore.user && authStore.user.onboarding_step !== 'onboarding_complete') {
      await updateMe({ language: authStore.user.language })
      await authStore.fetchMe()
    }

    // Root resolves to the role-based dashboard via guard.
    // safeNavigate is no-throw by contract -- critical here so a benign
    // NavigationFailure does NOT bubble into the outer docs-signing-error
    // catch and surface as a generic-error toast after successful signing.
    await safeNavigate(
      router.push(postEntryTarget(authStore.user?.onboarding_step)),
      '[OnboardingDocsView] post-sign to home',
    )
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
      <h1 class="auth-title">
        {{ t('auth.docs.title') }}
      </h1>
      <p class="auth-subtitle">
        {{ t('auth.docs.subtitle') }}
      </p>

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
            <!--
              A11y: the ROW carries @click and used to be the only way to toggle
              this, which made it mouse-only. It cannot become role="button" --
              it contains the "open document" button, and an ARIA button must not
              hold interactive descendants.
              What the row actually IS is a checkbox, so the box itself takes the
              role, the state and the keyboard, and the link stays a sibling.
            -->
            <div
              class="doc-checkbox"
              :class="{ checked: isChecked(doc), locked: doc.is_signed }"
              role="checkbox"
              :aria-checked="isChecked(doc)"
              :aria-label="doc.title"
              :tabindex="doc.is_signed ? -1 : 0"
              @click.stop="toggleCheck(doc)"
              @keydown.enter.prevent="toggleCheck(doc)"
              @keydown.space.prevent="toggleCheck(doc)"
            >
              <span v-if="isChecked(doc)">✓</span>
            </div>
            <div class="doc-info">
              <div class="doc-title">
                {{ doc.title }}
              </div>
              <div class="doc-meta">
                <span class="doc-required">{{ t('auth.docs.required') }}</span>
              </div>
            </div>
            <button type="button" class="doc-link" @click.stop="openDocument(doc)">
              <ExternalLink :size="16" />
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

        <div v-if="error" class="auth-error">
          {{ error }}
        </div>

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

        <div class="entry-logout">
          <AuthLogoutLink />
        </div>
      </template>
    </div>

    <!-- Document preview modal -->
    <LegalDocModal
      :open="viewingDoc !== null"
      :title="viewingDoc ? viewingDoc.title : ''"
      :lang="viewingDoc ? viewingDoc.language : ''"
      :type="viewingDoc ? viewingDoc.type : ''"
      @close="closeModal"
    />
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex;
  flex-direction: column;
  min-block-size: 100vh;
  min-block-size: 100dvh;
  background: var(--bg-page);
}
.auth-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4) var(--space-5);
}
.auth-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
  overflow-y: auto;
}
.auth-title {
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  margin-block-end: var(--space-2);
  text-align: center;
}
.auth-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-block-end: var(--space-6);
  text-align: center;
  line-height: 1.5;
}
.auth-error {
  font-size: var(--fs-xs);
  color: var(--danger);
  text-align: center;
  margin-block-end: var(--space-4);
  max-inline-size: var(--maxw-form-wide);
}

.docs-loading {
  display: flex;
  justify-content: center;
  padding: var(--space-6-lg);
}

.no-docs {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  text-align: center;
  margin-block-end: var(--space-5);
}

.doc-list {
  inline-size: 100%;
  max-inline-size: var(--maxw-form-wide);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-block-end: var(--space-4);
}
.doc-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--bg-page);
  border: thin solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--dur-base);
}
.doc-item:hover {
  border-color: var(--primary-hover);
  background: var(--bg-surface);
}
.doc-item.signed {
  cursor: default;
}

.doc-checkbox {
  position: relative;
  inline-size: var(--size-xs);
  block-size: var(--size-xs);
  min-inline-size: var(--size-xs);
  border: calc(var(--border-input-width) * 2) solid var(--border-default);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--dur-base);
  margin-block-start: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--on-primary);
}

/* A5: 24x24 painted. It only became visible to a hit test once it was given
   role="checkbox" -- before that no interactive-element query could select
   it at all. The painted box stays; the hit area is expanded past it. */
.doc-checkbox::after {
  content: '';
  position: absolute;
  inset-inline-start: 50%;
  inset-block-start: 50%;
  transform: translate(-50%, -50%);
  inline-size: max(100%, var(--tap-min));
  block-size: max(100%, var(--tap-min));
}
.doc-checkbox.checked {
  background: var(--primary);
  border-color: var(--primary);
}
.doc-checkbox.locked {
  opacity: 0.8;
}

/* A flex item defaults to min-width:auto, so it will not shrink below its
   content. With a long document title this pushed .doc-info to 435px against
   a 390 viewport -- and documentElement.scrollWidth stayed 390, so the
   overflow was CLIPPED and unreachable, on all eight rows. min-width:0 lets
   it shrink; overflow-wrap lets a long unbroken title break rather than push.
   Found only on a direct load: the push sweep renders no documents here.
   Same idiom already used by .event-card__body and .company-item__info. */
.doc-info {
  flex: 1;
  min-inline-size: 0;
}
.doc-title {
  overflow-wrap: anywhere;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-block-end: var(--space-1);
}
.doc-meta {
  display: flex;
  gap: var(--space-2);
}
.doc-required {
  font-size: var(--fs-xs);
  color: var(--danger);
  font-weight: 500;
}

.doc-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-tertiary);
  margin-block-start: var(--space-1);
  background: none;
  border: none;
  padding: var(--space-1) var(--space-1);
  cursor: pointer;
  font-family: inherit;
  font-size: var(--fs-xs);
  transition: color var(--dur-base);
}

/* A5: 8 of these failed the 44px area test -- found ONLY by loading
   /onboarding/docs directly; the push sweep renders no documents here and
   reported the route clean. The painted link stays inline beside the row
   text, so the hit area is expanded past it. */
.doc-link::after {
  content: '';
  position: absolute;
  inset-inline-start: 50%;
  inset-block-start: 50%;
  transform: translate(-50%, -50%);
  inline-size: max(100%, var(--tap-min));
  block-size: max(100%, var(--tap-min));
}
.doc-link:hover {
  color: var(--primary);
}

.doc-counter {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin-block-end: var(--space-4);
}

.doc-actions {
  inline-size: 100%;
  max-inline-size: var(--maxw-form-wide);
}

.btn {
  inline-size: 100%;
}
.btn-primary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 600;
  font-size: var(--fs-sm);
  font-family: inherit;
  border: none;
  cursor: pointer;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-spinner {
  /* currentColor, not white: the spinner sits inside a primary button whose
     colour is --on-primary, which is #FFFFFF in light and #04243E in dark.
     A white ring on the dark theme's light-azure button is near-invisible. */
  inline-size: var(--size-2xs);
  block-size: var(--size-2xs);
  border: calc(var(--border-input-width) * 2) solid currentColor;
  opacity: 0.35;
  border-block-start-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.entry-logout {
  display: flex;
  justify-content: center;
  margin-block-start: var(--space-5);
}
</style>
