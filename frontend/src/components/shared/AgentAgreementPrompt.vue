<script setup lang="ts">
// The integrator's one click after approval: the integrator-agent agreement is
// read behind a link and accepted by a single button; accepting it is also what
// issues the integrator's referral link. Shown on Home and on Partners while
// the agreement is not accepted. The click itself is the parent's
// (useAgentLink().accept) -- this component only draws it.

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileSignature } from 'lucide-vue-next'

import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { CButton } from '@/components/ui'

defineProps<{ loading: boolean }>()
const emit = defineEmits<{ accept: [] }>()

const { t, locale } = useI18n()

const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
const reading = ref(false)
const baseUrl = import.meta.env.BASE_URL
</script>

<template>
  <section class="aap">
    <div class="aap__head">
      <FileSignature :size="20" class="aap__icon" />
      <h2 class="aap__title">
        {{ t('agent.link.agreementTitle') }}
      </h2>
    </div>
    <p class="aap__text">
      {{ t('agent.link.agreementText') }}
    </p>
    <p class="aap__read">
      <a
        :href="`${baseUrl}legal/${docLang}/agent_integrator_agreement.html`"
        @click.prevent="reading = true"
        >{{ t('agent.link.agreementRead') }}</a
      >
    </p>
    <CButton variant="primary" :loading="loading" :disabled="loading" @click="emit('accept')">
      {{ t('agent.link.accept') }}
    </CButton>

    <LegalDocModal
      :open="reading"
      :title="t('agent.link.agreementTitle')"
      :lang="docLang"
      type="agent_integrator_agreement"
      @close="reading = false"
    />
  </section>
</template>

<style scoped>
.aap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.aap__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.aap__icon {
  color: var(--primary);
}

.aap__title {
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--text-primary);
}

.aap__text {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.aap__read {
  margin: 0;
  font-size: var(--fs-sm);
}

.aap__read a {
  color: var(--primary);
}
</style>
