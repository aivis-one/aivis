<script setup lang="ts">
import AuthShell from '@/components/layout/AuthShell.vue'
import CLoader from '@/components/ui/CLoader.vue'
import { CCheckbox } from '@/components/ui'
import { ExternalLink, ShieldAlert } from '@/components/ui/icons'
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
  <AuthShell>
    <h1 class="ds-auth__title">
      {{ t('auth.docs.title') }}
    </h1>
    <p class="ds-auth__subtitle">
      {{ t('auth.docs.subtitle') }}
    </p>

    <!-- Loading -->
    <div v-if="loadingDocs" class="ds-auth__icon">
      <CLoader />
    </div>

    <!-- Document list / empty state -->
    <template v-else>
      <!--
        A row of the Row list (K23) per document: the tick (K45) with the document's
        title, the word "required" under it, and a ghost button that opens the text.
        The tick is a real checkbox, so the box carries the role, the state and the
        keyboard; the button is a sibling, not inside the label.
      -->
      <ul v-if="documents.length > 0" class="ds-rows">
        <li v-for="doc in documents" :key="doc.id" class="ds-row">
          <span class="ds-row__body">
            <CCheckbox
              :model-value="isChecked(doc)"
              :disabled="doc.is_signed"
              :label="doc.title"
              @update:model-value="toggleCheck(doc)"
            />
            <span class="ds-row__meta">{{ t('auth.docs.required') }}</span>
          </span>
          <span class="ds-row__trail">
            <button
              type="button"
              class="ds-button ds-button--ghost"
              data-size="sm"
              @click="openDocument(doc)"
            >
              <ExternalLink size="sm" />
              <span>{{ t('auth.docs.read') }}</span>
            </button>
          </span>
        </li>
      </ul>

      <!-- Counter -->
      <p v-if="documents.length > 0" class="ds-auth__subtitle">
        {{ t('auth.docs.checkedOf', { checked: checkedCount, total: documents.length }) }}
      </p>

      <!-- No docs required for this role -->
      <p v-if="documents.length === 0" class="ds-auth__subtitle">
        {{ t('auth.docs.noDocs') }}
      </p>

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><ShieldAlert size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <div class="ds-auth__form">
        <button
          class="ds-button ds-button--primary ds-button--block"
          :aria-busy="signing || undefined"
          type="button"
          :disabled="!canSignAll || signing"
          @click="handleSignAll"
        >
          <span v-if="signing" class="ds-button__spinner" aria-hidden="true" />
          <span>{{ t('auth.docs.signDocumentsBtn') }}</span>
        </button>
      </div>

      <div class="ds-auth__foot">
        <AuthLogoutLink />
      </div>
    </template>

    <!-- Document preview modal -->
    <LegalDocModal
      :open="viewingDoc !== null"
      :title="viewingDoc ? viewingDoc.title : ''"
      :lang="viewingDoc ? viewingDoc.language : ''"
      :type="viewingDoc ? viewingDoc.type : ''"
      @close="closeModal"
    />
  </AuthShell>
</template>
