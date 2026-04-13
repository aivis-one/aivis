<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { useDocumentsStore } from '@/stores/documents'
import { useAuthStore } from '@/stores/auth'
import { getDocumentStatusColor } from '@/utils/display'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const store = useDocumentsStore()
const authStore = useAuthStore()

const docId = route.params.id as string

onMounted(() => {
  store.fetchDocument(docId)
})

function goToSign() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/documents/${docId}/sign`)
}

function goBack() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/documents`)
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <div class="doc-detail">
    <CSkeleton v-if="store.loading && !store.currentDocument" variant="card" />

    <template v-else-if="store.currentDocument">
      <h1 class="doc-detail__title">{{ store.currentDocument.title }}</h1>

      <span
        class="doc-detail__status"
        :style="{ color: getDocumentStatusColor(store.currentDocument.status) }"
      >
        {{ t(`documents.status.${store.currentDocument.status}`) }}
      </span>

      <p v-if="store.currentDocument.description" class="doc-detail__desc">
        {{ store.currentDocument.description }}
      </p>

      <div class="doc-detail__meta">
        <div class="doc-detail__row">
          <span class="doc-detail__label">{{ t('documents.detail.type') }}</span>
          <span class="doc-detail__value">
            {{ t(`documents.type.${store.currentDocument.type}`) }}
          </span>
        </div>
        <div class="doc-detail__row">
          <span class="doc-detail__label">{{ t('documents.detail.created') }}</span>
          <span class="doc-detail__value">{{ store.currentDocument.created_at }}</span>
        </div>
        <div v-if="store.currentDocument.signed_at" class="doc-detail__row">
          <span class="doc-detail__label">{{ t('documents.detail.signed') }}</span>
          <span class="doc-detail__value">{{ store.currentDocument.signed_at }}</span>
        </div>
        <div v-if="store.currentDocument.expires_at" class="doc-detail__row">
          <span class="doc-detail__label">{{ t('documents.detail.expires') }}</span>
          <span class="doc-detail__value">{{ store.currentDocument.expires_at }}</span>
        </div>
        <div v-if="store.currentDocument.file_size" class="doc-detail__row">
          <span class="doc-detail__label">{{ t('documents.detail.fileSize') }}</span>
          <span class="doc-detail__value">{{ formatBytes(store.currentDocument.file_size) }}</span>
        </div>
      </div>

      <div class="doc-detail__actions">
        <CButton
          v-if="store.currentDocument.status === 'pending_signature'"
          variant="primary"
          @click="goToSign"
        >
          {{ t('documents.detail.sign') }}
        </CButton>
        <CButton v-if="store.currentDocument.file_url" variant="secondary" @click="() => {}">
          {{ t('documents.detail.download') }}
        </CButton>
        <CButton variant="ghost" @click="goBack">
          {{ t('documents.detail.back') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.doc-detail {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.doc-detail__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.doc-detail__status {
  font-size: var(--text-lg);
  font-weight: 700;
  text-transform: uppercase;
}

.doc-detail__desc {
  font-size: var(--text-base);
  color: var(--text-secondary);
  line-height: 1.6;
}

.doc-detail__meta {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.doc-detail__row {
  display: flex;
  justify-content: space-between;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
}

.doc-detail__label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
}

.doc-detail__value {
  font-size: var(--text-base);
  color: var(--text);
}

.doc-detail__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
</style>
