<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CButton from '@/components/ui/CButton.vue'
import CFileUpload from '@/components/ui/CFileUpload.vue'
import { useKycStore } from '@/stores/kyc'
import { useToast } from '@/composables/useToast'

withDefaults(
  defineProps<{
    embedded?: boolean
  }>(),
  { embedded: false },
)

const emit = defineEmits<{
  complete: []
  back: []
}>()

const { t } = useI18n()
const kycStore = useKycStore()
const { addToast } = useToast()

const docTypes = ['passport', 'national_id', 'drivers_license', 'utility_bill', 'bank_statement']
const selectedType = ref(docTypes[0])
const currentFile = ref<File | null>(null)

const hasIdDoc = computed(() =>
  kycStore.documents.some((d) => ['passport', 'national_id', 'drivers_license'].includes(d.type)),
)
const hasProofDoc = computed(() =>
  kycStore.documents.some((d) => ['utility_bill', 'bank_statement'].includes(d.type)),
)
const canProceed = computed(() => hasIdDoc.value && hasProofDoc.value)

async function handleUpload(file: File | File[] | null) {
  if (!file || Array.isArray(file)) return
  currentFile.value = file
  const success = await kycStore.uploadDocument(file, selectedType.value)
  if (success) {
    addToast('success', t('kyc.upload.title'))
    currentFile.value = null
  } else {
    addToast('error', kycStore.error ?? t('common.error'))
  }
}

async function handleDelete(id: string) {
  const success = await kycStore.deleteDocument(id)
  if (!success) {
    addToast('error', kycStore.error ?? t('common.error'))
  }
}
</script>

<template>
  <div class="kyc-upload">
    <h1 v-if="!embedded" class="kyc-upload__title">{{ t('kyc.upload.title') }}</h1>

    <div class="kyc-upload__type">
      <label class="kyc-upload__label">{{ t('kyc.upload.select_type') }}</label>
      <select v-model="selectedType" class="kyc-upload__select">
        <option v-for="dt in docTypes" :key="dt" :value="dt">
          {{ t(`kyc.upload.types.${dt}`) }}
        </option>
      </select>
    </div>

    <CFileUpload
      :model-value="currentFile"
      accept=".pdf,.jpg,.jpeg,.png"
      :max-size="5 * 1024 * 1024"
      :label="t('kyc.upload.hint')"
      :disabled="kycStore.loading"
      @update:model-value="handleUpload"
    />

    <div v-if="kycStore.documents.length" class="kyc-upload__list">
      <div v-for="doc in kycStore.documents" :key="doc.id" class="kyc-upload__doc">
        <div class="kyc-upload__doc-info">
          <span class="kyc-upload__doc-name">{{ doc.filename }}</span>
          <span class="kyc-upload__doc-type">{{ t(`kyc.upload.types.${doc.type}`) }}</span>
        </div>
        <button class="kyc-upload__doc-delete" @click="handleDelete(doc.id)">&times;</button>
      </div>
    </div>

    <p class="kyc-upload__hint">{{ t('kyc.upload.min_docs') }}</p>

    <div v-if="embedded" class="kyc-upload__actions">
      <CButton variant="ghost" @click="emit('back')">{{ t('kyc.form.back') }}</CButton>
      <CButton variant="primary" :disabled="!canProceed" @click="emit('complete')">
        {{ t('kyc.form.next') }}
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.kyc-upload {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.kyc-upload__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.kyc-upload__type {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.kyc-upload__label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
}

.kyc-upload__select {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-size: var(--text-md);
  font-family: var(--font);
}

.kyc-upload__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.kyc-upload__doc {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.kyc-upload__doc-info {
  display: flex;
  flex-direction: column;
}

.kyc-upload__doc-name {
  font-size: var(--text-caption);
  color: var(--text);
}

.kyc-upload__doc-type {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.kyc-upload__doc-delete {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: var(--text-xl);
  cursor: pointer;
  line-height: 1;
}

.kyc-upload__doc-delete:hover {
  color: var(--error);
}

.kyc-upload__hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.kyc-upload__actions {
  display: flex;
  gap: var(--space-sm);
  justify-content: space-between;
}
</style>
