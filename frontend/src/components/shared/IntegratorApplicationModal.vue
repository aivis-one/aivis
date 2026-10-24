<script setup lang="ts">
// The integrator application window, opened from Settings once identity
// verification is passed. It has two faces:
//   - before the application: who an integrator is and what he does, links to
//     read the agent-integrator agreement and the integrator FAQ, and the
//     button that sends the application;
//   - after it ("sent"): the application is not reviewed until the person
//     writes to support, with a link to the support screen. The same face is
//     shown again when the person opens the button that reads "under review".
// Sending is the parent's (it owns the request); this component only draws.

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { CButton, CModal } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'

defineProps<{
  open: boolean
  sent: boolean
  submitting: boolean
}>()
const emit = defineEmits<{ close: []; submit: [] }>()

const { t, locale } = useI18n()
const router = useRouter()

// The legal texts and the FAQ ship in English and Russian.
const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
const faqUrl = computed(() => `${import.meta.env.BASE_URL}faq/${docLang.value}/agent.html`)
const reading = ref(false)
const baseUrl = import.meta.env.BASE_URL

function toSupport(): void {
  emit('close')
  void safeNavigate(
    router.push({ name: 'investor-support' }),
    '[IntegratorApplicationModal] support',
  )
}
</script>

<template>
  <CModal
    :open="open"
    :title="sent ? t('inv.settings.agent.modal.sentTitle') : t('inv.settings.agent.modal.title')"
    @close="emit('close')"
  >
    <template v-if="sent">
      <p class="ds-dialog__text">
        {{ t('inv.settings.agent.modal.sentText') }}
      </p>
      <CButton variant="primary" @click="toSupport">
        {{ t('inv.settings.agent.modal.toSupport') }}
      </CButton>
    </template>

    <template v-else>
      <p class="ds-dialog__text">
        {{ t('inv.settings.agent.modal.what') }}
      </p>
      <ul class="iam__list">
        <li>{{ t('inv.settings.agent.modal.pointLink') }}</li>
        <li>{{ t('inv.settings.agent.modal.pointCommission') }}</li>
        <li>{{ t('inv.settings.agent.modal.pointWithdrawal') }}</li>
      </ul>
      <div class="ds-dialog__actions">
        <a
          class="ds-button ds-button--ghost"
          data-size="sm"
          :href="`${baseUrl}legal/${docLang}/agent_integrator_agreement.html`"
          @click.prevent="reading = true"
          >{{ t('inv.settings.agent.modal.readAgreement') }}</a
        >
        <a
          class="ds-button ds-button--ghost"
          data-size="sm"
          :href="faqUrl"
          target="_blank"
          rel="noopener"
          >{{ t('inv.settings.agent.modal.readFaq') }}</a
        >
      </div>
      <CButton variant="primary" :loading="submitting" @click="emit('submit')">
        {{ t('inv.settings.agent.modal.submit') }}
      </CButton>
    </template>

    <LegalDocModal
      :open="reading"
      :title="t('agent.link.agreementTitle')"
      :lang="docLang"
      type="agent_integrator_agreement"
      @close="reading = false"
    />
  </CModal>
</template>

<style scoped>
/* The dialog body has no list of its own (NEED): plain bullets, set from tokens
   in the dialog text's own size and colour. */
.iam__list {
  margin: 0;
  padding-inline-start: var(--space-5);
  list-style: disc;
  display: grid;
  gap: var(--space-1);
  font-size: var(--fs-sm);
  line-height: var(--lh-normal);
  color: var(--text-secondary);
}
</style>
