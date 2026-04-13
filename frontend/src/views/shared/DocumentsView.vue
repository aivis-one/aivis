<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { useDocumentsStore } from '@/stores/documents'
import { useAuthStore } from '@/stores/auth'
import { usePagination } from '@/composables/usePagination'
import { getDocumentStatusColor } from '@/utils/display'
import type { DocumentType, DocumentStatus } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const store = useDocumentsStore()
const authStore = useAuthStore()
const { page, totalPages, hasNext, hasPrev, next, prev, setTotal } = usePagination()

const filterType = ref<DocumentType | ''>('')
const filterStatus = ref<DocumentStatus | ''>('')

const docTypes: DocumentType[] = ['contract', 'agreement', 'disclosure', 'report', 'receipt']
const docStatuses: DocumentStatus[] = [
  'draft',
  'pending_signature',
  'signed',
  'expired',
  'rejected',
]

onMounted(() => loadDocuments())

watch([page, filterType, filterStatus], () => loadDocuments())

async function loadDocuments() {
  await store.fetchDocuments({
    type: filterType.value || undefined,
    status: filterStatus.value || undefined,
    page: page.value,
  })
  setTotal(store.total)
}

function viewDocument(id: string) {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/documents/${id}`)
}
</script>

<template>
  <div class="docs-view">
    <h1 class="docs-view__title">{{ t('documents.title') }}</h1>

    <div class="docs-view__filters">
      <select v-model="filterType" class="docs-view__select">
        <option value="">{{ t('documents.filter.all') }} — {{ t('documents.filter.type') }}</option>
        <option v-for="dt in docTypes" :key="dt" :value="dt">
          {{ t(`documents.type.${dt}`) }}
        </option>
      </select>
      <select v-model="filterStatus" class="docs-view__select">
        <option value="">
          {{ t('documents.filter.all') }} — {{ t('documents.filter.status') }}
        </option>
        <option v-for="ds in docStatuses" :key="ds" :value="ds">
          {{ t(`documents.status.${ds}`) }}
        </option>
      </select>
    </div>

    <CSkeleton v-if="store.loading && !store.hasDocuments" variant="list" />

    <p v-else-if="!store.hasDocuments" class="docs-view__empty">{{ t('documents.empty') }}</p>

    <div v-else class="docs-view__list">
      <div
        v-for="doc in store.documents"
        :key="doc.id"
        class="docs-view__item"
        @click="viewDocument(doc.id)"
      >
        <div class="docs-view__item-info">
          <span class="docs-view__item-title">{{ doc.title }}</span>
          <span class="docs-view__item-type">{{ t(`documents.type.${doc.type}`) }}</span>
        </div>
        <span class="docs-view__item-status" :style="{ color: getDocumentStatusColor(doc.status) }">
          {{ t(`documents.status.${doc.status}`) }}
        </span>
      </div>
    </div>

    <div v-if="totalPages > 1" class="docs-view__pagination">
      <CButton variant="ghost" size="sm" :disabled="!hasPrev" @click="prev">
        {{ t('documents.pagination.prev') }}
      </CButton>
      <span class="docs-view__page">
        {{ t('documents.pagination.page', { page, total: totalPages }) }}
      </span>
      <CButton variant="ghost" size="sm" :disabled="!hasNext" @click="next">
        {{ t('documents.pagination.next') }}
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.docs-view {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.docs-view__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.docs-view__filters {
  display: flex;
  gap: var(--space-sm);
}

.docs-view__select {
  flex: 1;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-size: var(--text-caption);
  font-family: var(--font);
}

.docs-view__empty {
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-base);
  padding: var(--space-xl) 0;
}

.docs-view__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.docs-view__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.2s;
}

.docs-view__item:hover {
  background: var(--bg-subtle);
}

.docs-view__item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.docs-view__item-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
}

.docs-view__item-type {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.docs-view__item-status {
  font-size: var(--text-caption);
  font-weight: 600;
}

.docs-view__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
}

.docs-view__page {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}
</style>
