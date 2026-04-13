<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CInput from '@/components/ui/CInput.vue'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { useDocumentsStore } from '@/stores/documents'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const store = useDocumentsStore()
const authStore = useAuthStore()
const { addToast } = useToast()

const docId = route.params.id as string
const agreed = ref(false)
const signatureText = ref('')
const submitting = ref(false)
const signatureError = ref('')

onMounted(() => {
  store.fetchDocument(docId)
})

async function handleSign() {
  signatureError.value = ''
  if (!agreed.value) return
  if (signatureText.value.trim().length < 2) {
    signatureError.value = t('validation.required')
    return
  }

  submitting.value = true
  const success = await store.signDocument(docId, {
    agreement_accepted: agreed.value,
    signature_text: signatureText.value.trim(),
  })
  submitting.value = false

  if (success) {
    addToast('success', t('documents.sign.success'))
    goBack()
  } else {
    addToast('error', store.error ?? t('documents.sign.error'))
  }
}

function goBack() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/documents/${docId}`)
}
</script>

<template>
  <div class="doc-sign">
    <h1 class="doc-sign__title">{{ t('documents.sign.title') }}</h1>

    <CSkeleton v-if="store.loading && !store.currentDocument" variant="card" />

    <template v-else-if="store.currentDocument">
      <div class="doc-sign__content">
        <h2 class="doc-sign__doc-title">{{ store.currentDocument.title }}</h2>
        <div class="doc-sign__agreement-text">
          {{ store.currentDocument.description }}
        </div>
      </div>

      <label class="doc-sign__checkbox">
        <input v-model="agreed" type="checkbox" />
        <span>{{ t('documents.sign.agreement') }}</span>
      </label>

      <CInput
        v-model="signatureText"
        :label="t('documents.sign.signature')"
        :placeholder="t('documents.sign.signaturePlaceholder')"
        :error="signatureError"
        :disabled="!agreed"
      />

      <div class="doc-sign__actions">
        <CButton
          variant="primary"
          :disabled="!agreed || signatureText.trim().length < 2"
          :loading="submitting"
          @click="handleSign"
        >
          {{ t('documents.sign.submit') }}
        </CButton>
        <CButton variant="ghost" @click="goBack">
          {{ t('documents.sign.back') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.doc-sign {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.doc-sign__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.doc-sign__doc-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text);
  margin-bottom: var(--space-sm);
}

.doc-sign__agreement-text {
  max-height: 300px;
  overflow-y: auto;
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  font-size: var(--text-base);
  color: var(--text-secondary);
  line-height: 1.6;
}

.doc-sign__checkbox {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  font-size: var(--text-base);
  color: var(--text);
  cursor: pointer;
}

.doc-sign__checkbox input {
  margin-top: 3px;
  accent-color: var(--primary);
}

.doc-sign__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
</style>
