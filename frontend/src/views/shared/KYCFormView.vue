<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CInput from '@/components/ui/CInput.vue'
import KYCUploadView from './KYCUploadView.vue'
import { useForm } from '@/composables/useForm'
import { useToast } from '@/composables/useToast'
import { useKycStore } from '@/stores/kyc'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const kycStore = useKycStore()
const authStore = useAuthStore()
const { addToast } = useToast()

const currentStep = ref(1)
const totalSteps = 4

const stepTitles = computed(() => [
  t('kyc.form.step1_title'),
  t('kyc.form.step2_title'),
  t('kyc.form.step3_title'),
  t('kyc.form.step4_title'),
])

const { values, errors, handleSubmit } = useForm({
  initialValues: {
    full_name: '',
    date_of_birth: '',
    nationality: '',
    address: '',
    tax_id: '',
  },
  validate(v) {
    const errs: Record<string, string> = {}
    if (!v.full_name) errs.full_name = t('validation.required')
    if (!v.date_of_birth) errs.date_of_birth = t('validation.required')
    if (!v.nationality) errs.nationality = t('validation.required')
    if (!v.address) errs.address = t('validation.required')
    return errs
  },
  async onSubmit() {
    // Submit handled in step 4
  },
})

function canAdvance(): boolean {
  if (currentStep.value === 1) {
    return !!values.full_name && !!values.date_of_birth && !!values.nationality && !!values.address
  }
  if (currentStep.value === 2) {
    return kycStore.hasDocuments
  }
  return true
}

function nextStep() {
  if (currentStep.value === 1) {
    handleSubmit()
    if (Object.keys(errors).some((k) => errors[k as keyof typeof errors])) return
  }
  if (!canAdvance()) return
  if (currentStep.value < totalSteps) currentStep.value++
}

function prevStep() {
  if (currentStep.value > 1) currentStep.value--
}

async function submitKyc() {
  const docIds = kycStore.documents.map((d) => d.id)
  const success = await kycStore.submitKyc({
    personal_data: {
      full_name: values.full_name as string,
      date_of_birth: values.date_of_birth as string,
      nationality: values.nationality as string,
      address: values.address as string,
      tax_id: values.tax_id as string,
    },
    document_ids: docIds,
  })
  if (success) {
    addToast('success', t('kyc.form.submit'))
    const role = authStore.userRole ?? 'investor'
    router.push(`/${role}/kyc`)
  } else {
    addToast('error', kycStore.error ?? t('common.error'))
  }
}
</script>

<template>
  <div class="kyc-form">
    <h1 class="kyc-form__title">{{ stepTitles[currentStep - 1] }}</h1>

    <!-- Step indicator -->
    <div class="kyc-form__steps">
      <div
        v-for="step in totalSteps"
        :key="step"
        :class="[
          'kyc-form__step',
          { 'kyc-form__step--active': step === currentStep },
          { 'kyc-form__step--done': step < currentStep },
        ]"
      >
        {{ step }}
      </div>
    </div>

    <!-- Step 1: Personal Data -->
    <form v-if="currentStep === 1" class="kyc-form__fields" @submit.prevent="nextStep">
      <CInput
        v-model="values.full_name"
        :label="t('kyc.form.field_full_name')"
        :error="errors.full_name"
      />
      <CInput
        v-model="values.date_of_birth"
        type="date"
        :label="t('kyc.form.field_date_of_birth')"
        :error="errors.date_of_birth"
      />
      <CInput
        v-model="values.nationality"
        :label="t('kyc.form.field_nationality')"
        :error="errors.nationality"
      />
      <CInput
        v-model="values.address"
        :label="t('kyc.form.field_address')"
        :error="errors.address"
      />
      <CInput v-model="values.tax_id" :label="t('kyc.form.field_tax_id')" :error="errors.tax_id" />
    </form>

    <!-- Step 2: Documents -->
    <KYCUploadView v-if="currentStep === 2" embedded @complete="nextStep" @back="prevStep" />

    <!-- Step 3: Review -->
    <div v-if="currentStep === 3" class="kyc-form__review">
      <div class="kyc-form__review-section">
        <div class="kyc-form__review-row">
          <span class="kyc-form__review-label">{{ t('kyc.form.field_full_name') }}</span>
          <bdi class="kyc-form__review-value">{{ values.full_name }}</bdi>
        </div>
        <div class="kyc-form__review-row">
          <span class="kyc-form__review-label">{{ t('kyc.form.field_date_of_birth') }}</span>
          <span class="kyc-form__review-value">{{ values.date_of_birth }}</span>
        </div>
        <div class="kyc-form__review-row">
          <span class="kyc-form__review-label">{{ t('kyc.form.field_nationality') }}</span>
          <bdi class="kyc-form__review-value">{{ values.nationality }}</bdi>
        </div>
        <div class="kyc-form__review-row">
          <span class="kyc-form__review-label">{{ t('kyc.form.field_address') }}</span>
          <bdi class="kyc-form__review-value">{{ values.address }}</bdi>
        </div>
        <div class="kyc-form__review-row">
          <span class="kyc-form__review-label">{{ t('kyc.form.field_tax_id') }}</span>
          <span class="kyc-form__review-value">{{ values.tax_id || '—' }}</span>
        </div>
      </div>
      <p class="kyc-form__review-docs">
        {{ kycStore.documents.length }} {{ t('kyc.upload.title').toLowerCase() }}
      </p>
    </div>

    <!-- Step 4: Confirm & Submit -->
    <div v-if="currentStep === 4" class="kyc-form__confirm">
      <p>{{ t('kyc.form.review_confirm') }}</p>
    </div>

    <!-- Navigation (except step 2 which has its own) -->
    <div v-if="currentStep !== 2" class="kyc-form__nav">
      <CButton v-if="currentStep > 1" variant="ghost" @click="prevStep">
        {{ t('kyc.form.back') }}
      </CButton>
      <div v-else />
      <CButton
        v-if="currentStep < totalSteps"
        variant="primary"
        :disabled="!canAdvance()"
        @click="nextStep"
      >
        {{ t('kyc.form.next') }}
      </CButton>
      <CButton v-else variant="primary" :loading="kycStore.loading" @click="submitKyc">
        {{ t('kyc.form.submit') }}
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.kyc-form {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.kyc-form__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.kyc-form__steps {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  justify-content: center;
}

.kyc-form__step {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-caption);
  font-weight: 600;
  border: 2px solid var(--border);
  color: var(--text-tertiary);
  background: var(--bg);
}

.kyc-form__step--active {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--t-tint-8);
}

.kyc-form__step--done {
  border-color: var(--success);
  color: var(--text-on-accent);
  background: var(--success);
}

.kyc-form__fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.kyc-form__review {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.kyc-form__review-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.kyc-form__review-row {
  display: flex;
  justify-content: space-between;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
}

.kyc-form__review-label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
}

.kyc-form__review-value {
  font-size: var(--text-base);
  color: var(--text);
}

.kyc-form__review-docs {
  font-size: var(--text-caption);
  color: var(--text-secondary);
}

.kyc-form__confirm {
  padding: var(--space-lg);
  text-align: center;
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.kyc-form__nav {
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
}
</style>
