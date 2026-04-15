<script setup lang="ts">
// Document signing — list required docs, sign each, complete onboarding.
// GET  /api/v1/documents → DocumentResponse[]
// POST /api/v1/documents/{id}/sign → DocumentSigningResponse
// After all signed: fetchMe() → guard redirects to role dashboard.

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api, ApiResponseError } from '@/api/client'
import type { DocumentResponse } from '@/api/types'
import CbsLogo from '@/components/ui/CbsLogo.vue'

const { t } = useI18n()
const authStore = useAuthStore()

const documents = ref<DocumentResponse[]>([])
const loadingDocs = ref(true)
const signingId = ref<string | null>(null)
const completing = ref(false)
const error = ref('')

const signedCount = computed(() =>
  documents.value.filter((d) => d.is_signed).length,
)
const allSigned = computed(() =>
  documents.value.length > 0 && signedCount.value === documents.value.length,
)

onMounted(async () => {
  await fetchDocuments()
})

async function fetchDocuments(): Promise<void> {
  loadingDocs.value = true
  try {
    documents.value = await api.get<DocumentResponse[]>('/api/v1/documents')
  } catch {
    error.value = t('common.error')
  } finally {
    loadingDocs.value = false
  }
}

async function signDocument(doc: DocumentResponse): Promise<void> {
  if (doc.is_signed || signingId.value) return
  error.value = ''
  signingId.value = doc.id

  try {
    await api.post<unknown>(`/api/v1/documents/${doc.id}/sign`)
    // Update local state.
    const idx = documents.value.findIndex((d) => d.id === doc.id)
    if (idx !== -1) {
      documents.value[idx] = { ...documents.value[idx], is_signed: true }
    }
  } catch (err) {
    if (err instanceof ApiResponseError) {
      // 409 = already signed — update local state.
      if (err.status === 409) {
        const idx = documents.value.findIndex((d) => d.id === doc.id)
        if (idx !== -1) {
          documents.value[idx] = { ...documents.value[idx], is_signed: true }
        }
      } else {
        error.value = err.detail
      }
    } else {
      error.value = t('common.error')
    }
  } finally {
    signingId.value = null
  }
}

async function handleComplete(): Promise<void> {
  if (!allSigned.value) return
  completing.value = true
  await authStore.fetchMe()
  completing.value = false
  // Guard will redirect to role dashboard.
}
</script>

<template>
  <div class="auth-screen">
    <header class="auth-header">
      <CbsLogo :height="28" />
    </header>

    <div class="auth-content">
      <h1 class="auth-title">{{ t('auth.docs.title') }}</h1>
      <p class="auth-subtitle">{{ t('auth.docs.subtitle') }}</p>

      <!-- Loading -->
      <div v-if="loadingDocs" class="docs-loading">
        <span class="btn-spinner" />
      </div>

      <!-- Document list -->
      <template v-else>
        <div class="doc-list">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="doc-item"
            :class="{ signed: doc.is_signed }"
            @click="signDocument(doc)"
          >
            <div
              class="doc-checkbox"
              :class="{ checked: doc.is_signed }"
            >
              <span v-if="doc.is_signed">✓</span>
              <span
                v-else-if="signingId === doc.id"
                class="doc-spinner"
              />
            </div>
            <div class="doc-info">
              <div class="doc-title">{{ doc.title }}</div>
              <div class="doc-meta">
                <span class="doc-required">{{ t('auth.docs.required') }}</span>
              </div>
            </div>
            <a
              class="doc-link"
              :href="doc.content_url"
              target="_blank"
              rel="noopener"
              @click.stop
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
            </a>
          </div>
        </div>

        <!-- Counter -->
        <div v-if="documents.length > 0" class="doc-counter">
          {{ t('auth.docs.checkedOf', { checked: signedCount, total: documents.length }) }}
        </div>

        <div v-if="error" class="auth-error">{{ error }}</div>

        <div class="doc-actions">
          <button
            class="btn btn-primary"
            type="button"
            :disabled="!allSigned || completing"
            @click="handleComplete"
          >
            <span v-if="completing" class="btn-spinner" />
            <span v-else>{{ t('auth.docs.signDocumentsBtn') }}</span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.auth-screen {
  display: flex; flex-direction: column;
  min-height: 100vh; min-height: 100dvh;
  background: var(--bg);
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
  font-size: 24px; font-weight: 700; color: var(--text);
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

.doc-list {
  width: 100%; max-width: 400px;
  display: flex; flex-direction: column; gap: 12px;
  margin-bottom: 16px;
}
.doc-item {
  display: flex; align-items: flex-start; gap: 14px; padding: 16px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius-md); cursor: pointer;
  transition: all 0.2s;
}
.doc-item:hover { border-color: var(--primary-light); background: var(--bg-elevated); }
.doc-item.signed { cursor: default; }

.doc-checkbox {
  width: 22px; height: 22px; min-width: 22px;
  border: 2px solid var(--border); border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; margin-top: 2px;
  font-size: 13px; color: white;
}
.doc-checkbox.checked {
  background: var(--primary); border-color: var(--primary);
}

.doc-spinner {
  width: 12px; height: 12px;
  border: 2px solid var(--border); border-top-color: var(--primary);
  border-radius: 50%; animation: spin 0.6s linear infinite;
}

.doc-info { flex: 1; }
.doc-title {
  font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 4px;
}
.doc-meta { display: flex; gap: 8px; }
.doc-required {
  font-size: 11px; color: var(--danger); font-weight: 500;
}

.doc-link {
  color: var(--text-tertiary); margin-top: 2px;
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
  background: var(--accent); color: white;
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
</style>
