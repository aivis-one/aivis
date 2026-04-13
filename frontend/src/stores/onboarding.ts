import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'
import { useKycStore } from '@/stores/kyc'
import { useDocumentsStore } from '@/stores/documents'
import type { OnboardingStep, OnboardingStepDef } from '@/api/types'

const ROLE_STEPS: Record<string, OnboardingStep[]> = {
  investor: ['profile_filled', 'kyc_submitted', 'documents_signed', 'completed'],
  agent: ['profile_filled', 'kyc_submitted', 'documents_signed', 'completed'],
  company: ['profile_filled', 'kyc_submitted', 'completed'],
  staff: ['profile_filled', 'completed'],
}

export const useOnboardingStore = defineStore('onboarding', () => {
  const authStore = useAuthStore()
  const profileStore = useProfileStore()
  const kycStore = useKycStore()
  const documentsStore = useDocumentsStore()

  function isStepComplete(step: OnboardingStep): boolean {
    switch (step) {
      case 'profile_filled':
        return !!(profileStore.profile?.first_name && profileStore.profile?.last_name)
      case 'kyc_submitted':
        return kycStore.isApproved
      case 'documents_signed':
        return documentsStore.pendingDocuments.length === 0 && documentsStore.hasDocuments
      case 'completed':
        return false
      default:
        return false
    }
  }

  const steps = computed<OnboardingStepDef[]>(() => {
    const role = authStore.userRole ?? 'investor'
    const roleSteps = ROLE_STEPS[role] ?? ROLE_STEPS.investor
    return roleSteps.map((key) => ({
      key,
      labelKey: `onboarding.steps.${key}`,
      isComplete: key === 'completed' ? false : isStepComplete(key),
    }))
  })

  const currentStepIndex = computed(() => {
    const idx = steps.value.findIndex((s) => !s.isComplete)
    return idx === -1 ? steps.value.length : idx
  })

  const currentStep = computed<OnboardingStepDef | null>(() => {
    return steps.value[currentStepIndex.value] ?? null
  })

  const isComplete = computed(() => {
    return steps.value.filter((s) => s.key !== 'completed').every((s) => s.isComplete)
  })

  const progress = computed(() => {
    const actionSteps = steps.value.filter((s) => s.key !== 'completed')
    if (actionSteps.length === 0) return 100
    const done = actionSteps.filter((s) => s.isComplete).length
    return Math.round((done / actionSteps.length) * 100)
  })

  async function refreshAll() {
    await Promise.allSettled([
      profileStore.fetchProfile(),
      kycStore.fetchStatus(),
      documentsStore.fetchDocuments(),
    ])
  }

  return {
    steps,
    currentStepIndex,
    currentStep,
    isComplete,
    progress,
    refreshAll,
  }
})
