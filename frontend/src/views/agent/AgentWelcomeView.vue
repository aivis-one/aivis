<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentWelcomeView
// =============================================================================
//
// The full screen an approved integrator meets first, and the only screen open
// to them until the agent-integrator agreement is accepted (the router guard
// sends every other integrator route here). It congratulates them, lists what
// the role gives, offers the agreement to read behind a link, and opens the
// cabinet only through the button "I accept the agreement", which is enabled
// with the tick alone. Pressing it records the acceptance of the agreement
// (the document of type agent_integrator_agreement) and asks the platform for
// the integrator's one link; only then does the cabinet open.
//
// If the agreement document does not exist nothing can be accepted: the screen
// says so, points to support and requests no link. Sign-out stays reachable.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Coins, Link2, Users, Wallet } from '@/components/ui/icons'

import { CButton, CCheckbox, CLoader } from '@/components/ui'
import AuthShell from '@/components/layout/AuthShell.vue'
import AuthLogoutLink from '@/components/shared/AuthLogoutLink.vue'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { useAgentLink } from '@/composables/useAgentLink'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAgentAgreementStore } from '@/stores/agentAgreement'

const router = useRouter()
const { t, locale } = useI18n()
const agreementStore = useAgentAgreementStore()
const { accepting, accept } = useAgentLink()

const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))
const ticked = ref(false)
const reading = ref(false)
const checking = ref(true)

const status = computed(() => agreementStore.status)

async function check(): Promise<void> {
  checking.value = true
  await agreementStore.ensure()
  checking.value = false
  if (agreementStore.status === 'signed') {
    void safeNavigate(router.replace({ name: 'agent-dashboard' }), '[AgentWelcomeView] to cabinet')
  }
}

async function onAccept(): Promise<void> {
  if (!ticked.value) return
  const done = await accept()
  if (done) {
    void safeNavigate(router.replace({ name: 'agent-dashboard' }), '[AgentWelcomeView] to cabinet')
  }
}

function toSupport(): void {
  void safeNavigate(router.push({ name: 'agent-support' }), '[AgentWelcomeView] to support')
}

onMounted(() => {
  void check()
})
</script>

<template>
  <AuthShell>
    <div v-if="checking" aria-busy="true">
      <CLoader />
    </div>

    <!-- The agreement document is not published: nothing can be accepted -->
    <template v-else-if="status === 'missing'">
      <h1 class="ds-auth__title">
        {{ t('agent.welcome.unavailableTitle') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('agent.welcome.unavailableText') }}
      </p>
      <CButton variant="primary" @click="toSupport">
        {{ t('agent.welcome.toSupport') }}
      </CButton>
    </template>

    <!-- The state could not be read -->
    <template v-else-if="status === 'error'">
      <h1 class="ds-auth__title">
        {{ t('agent.welcome.errorTitle') }}
      </h1>
      <CButton variant="outline" @click="check">
        {{ t('common.retry') }}
      </CButton>
    </template>

    <template v-else>
      <h1 class="ds-auth__title">
        {{ t('agent.welcome.title') }}
      </h1>
      <p class="ds-auth__subtitle">
        {{ t('agent.welcome.intro') }}
      </p>
      <ul class="ds-rows">
        <li class="ds-row">
          <span class="ds-row__lead"><Link2 size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ t('agent.welcome.possLink') }}</span>
          </span>
        </li>
        <li class="ds-row">
          <span class="ds-row__lead"><Users size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ t('agent.welcome.possPartners') }}</span>
          </span>
        </li>
        <li class="ds-row">
          <span class="ds-row__lead"><Coins size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ t('agent.welcome.possCommission') }}</span>
          </span>
        </li>
        <li class="ds-row">
          <span class="ds-row__lead"><Wallet size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">{{ t('agent.welcome.possWithdrawal') }}</span>
          </span>
        </li>
      </ul>

      <form class="ds-auth__form" @submit.prevent="onAccept">
        <CButton variant="link" type="button" @click="reading = true">
          {{ t('agent.welcome.readAgreement') }}
        </CButton>

        <CCheckbox v-model="ticked" :label="t('agent.welcome.tick')" />

        <CButton variant="primary" type="submit" :disabled="!ticked" :loading="accepting">
          {{ t('agent.welcome.accept') }}
        </CButton>
      </form>
    </template>

    <div class="ds-auth__foot">
      <AuthLogoutLink />
    </div>

    <LegalDocModal
      :open="reading"
      :title="t('agent.link.agreementTitle')"
      :lang="docLang"
      type="agent_integrator_agreement"
      @close="reading = false"
    />
  </AuthShell>
</template>
