<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import CButton from '@/components/ui/CButton.vue'
import CCard from '@/components/ui/CCard.vue'
import { useOnboardingStore } from '@/stores/onboarding'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const onboardingStore = useOnboardingStore()
const authStore = useAuthStore()

onMounted(async () => {
  await onboardingStore.refreshAll()
  if (onboardingStore.isComplete) {
    goToDashboard()
  }
})

function goToDashboard() {
  const role = authStore.userRole ?? 'investor'
  router.push(`/${role}/dashboard`)
}

function goToStep(stepKey: string) {
  const role = authStore.userRole ?? 'investor'
  switch (stepKey) {
    case 'profile_filled':
      router.push(`/${role}/profile/edit`)
      break
    case 'kyc_submitted':
      router.push(`/${role}/kyc`)
      break
    case 'documents_signed':
      router.push(`/${role}/documents`)
      break
  }
}
</script>

<template>
  <div class="onboarding">
    <h1 class="onboarding__title">{{ t('onboarding.title') }}</h1>
    <p class="onboarding__subtitle">{{ t('onboarding.subtitle') }}</p>

    <div class="onboarding__progress">
      <div class="onboarding__progress-bar" :style="{ width: `${onboardingStore.progress}%` }" />
    </div>
    <p class="onboarding__progress-text">
      {{
        t('onboarding.progress', {
          current: onboardingStore.currentStepIndex + 1,
          total: onboardingStore.steps.length,
        })
      }}
    </p>

    <div class="onboarding__steps">
      <CCard
        v-for="(step, idx) in onboardingStore.steps"
        :key="step.key"
        :class="[
          'onboarding__step',
          { 'onboarding__step--complete': step.isComplete },
          { 'onboarding__step--active': idx === onboardingStore.currentStepIndex },
        ]"
      >
        <div class="onboarding__step-header">
          <span class="onboarding__step-num">{{ idx + 1 }}</span>
          <span class="onboarding__step-label">{{ t(step.labelKey) }}</span>
        </div>
        <span v-if="step.isComplete" class="onboarding__step-status onboarding__step-status--done">
          {{ t('onboarding.status.complete') }}
        </span>
        <span
          v-else-if="idx === onboardingStore.currentStepIndex"
          class="onboarding__step-status onboarding__step-status--current"
        >
          {{ t('onboarding.status.current') }}
        </span>
        <span v-else class="onboarding__step-status onboarding__step-status--pending">
          {{ t('onboarding.status.pending') }}
        </span>

        <CButton
          v-if="step.key !== 'completed' && idx === onboardingStore.currentStepIndex"
          variant="primary"
          size="sm"
          @click="goToStep(step.key)"
        >
          {{
            t(
              `onboarding.actions.go_to_${step.key === 'profile_filled' ? 'profile' : step.key === 'kyc_submitted' ? 'kyc' : 'documents'}`,
            )
          }}
        </CButton>
      </CCard>
    </div>

    <div v-if="onboardingStore.isComplete" class="onboarding__success">
      <h2 class="onboarding__success-title">{{ t('onboarding.success.title') }}</h2>
      <p class="onboarding__success-message">{{ t('onboarding.success.message') }}</p>
      <CButton variant="primary" @click="goToDashboard">
        {{ t('onboarding.actions.continue') }}
      </CButton>
    </div>
  </div>
</template>

<style scoped>
.onboarding {
  min-height: 100vh;
  min-height: 100dvh;
  padding: var(--space-lg) var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  background: var(--bg);
}

.onboarding__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
  text-align: center;
}

.onboarding__subtitle {
  font-size: var(--text-base);
  color: var(--text-secondary);
  text-align: center;
  margin-top: calc(-1 * var(--space-sm));
}

.onboarding__progress {
  height: 6px;
  background: var(--bg-elevated);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.onboarding__progress-bar {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-full);
  transition: width 0.3s;
}

.onboarding__progress-text {
  font-size: var(--text-caption);
  color: var(--text-tertiary);
  text-align: center;
  margin-top: calc(-1 * var(--space-sm));
}

.onboarding__steps {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.onboarding__step {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  opacity: 0.6;
}

.onboarding__step--active {
  opacity: 1;
  border-color: var(--primary);
}

.onboarding__step--complete {
  opacity: 0.8;
}

.onboarding__step-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.onboarding__step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-caption);
  font-weight: 700;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.onboarding__step--complete .onboarding__step-num {
  background: var(--success);
  color: var(--text-on-accent);
}

.onboarding__step--active .onboarding__step-num {
  background: var(--primary);
  color: var(--text-on-accent);
}

.onboarding__step-label {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text);
}

.onboarding__step-status {
  font-size: var(--text-sm);
  font-weight: 500;
}

.onboarding__step-status--done {
  color: var(--success);
}

.onboarding__step-status--current {
  color: var(--primary);
}

.onboarding__step-status--pending {
  color: var(--text-tertiary);
}

.onboarding__success {
  text-align: center;
  padding: var(--space-lg) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  align-items: center;
}

.onboarding__success-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--success);
}

.onboarding__success-message {
  font-size: var(--text-base);
  color: var(--text-secondary);
}
</style>
