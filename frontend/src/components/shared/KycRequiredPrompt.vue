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
  <CModal :open="open" :title="t(`kyc.prompt.${action}`)" @close="close">
    <p class="ds-dialog__text">
      {{ t('kyc.prompt.text') }}
    </p>
    <div class="ds-dialog__actions">
      <CButton variant="outline" size="sm" inline @click="close">
        {{ t('kyc.prompt.later') }}
      </CButton>
      <CButton variant="primary" size="sm" inline @click="toVerification">
        {{ t('kyc.prompt.go') }}
      </CButton>
    </div>
  </CModal>
</template>
