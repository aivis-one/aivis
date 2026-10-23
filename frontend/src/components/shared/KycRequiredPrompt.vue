<script setup lang="ts">
// The message a closed action answers with when the person has not passed
// identity verification: what is needed, what it costs, and a button to the
// verification screen. Mounted once, in App.vue; opened by main.ts when the
// gate answers 402 (see composables/useKycPrompt.ts).

import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CModal } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'
import { useKycPrompt } from '@/composables/useKycPrompt'

const { t } = useI18n()
const router = useRouter()
const { open, action, close } = useKycPrompt()

function toVerification(): void {
  close()
  void safeNavigate(router.push('/verification'), '[KycRequiredPrompt] to verification')
}
</script>

<template>
  <CModal :open="open" @close="close">
    <div class="kyc-prompt">
      <h3 class="kyc-prompt__title">
        {{ t(`kyc.prompt.${action}`) }}
      </h3>
      <p class="kyc-prompt__text">
        {{ t('kyc.prompt.text') }}
      </p>
      <div class="kyc-prompt__actions">
        <CButton variant="outline" size="sm" @click="close">
          {{ t('kyc.prompt.later') }}
        </CButton>
        <CButton variant="primary" size="sm" @click="toVerification">
          {{ t('kyc.prompt.go') }}
        </CButton>
      </div>
    </div>
  </CModal>
</template>

<style scoped>
.kyc-prompt {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.kyc-prompt__title {
  margin: 0;
  padding-inline-end: var(--space-5);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.kyc-prompt__text {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.kyc-prompt__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
