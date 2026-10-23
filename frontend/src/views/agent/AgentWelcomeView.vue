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
import { Coins, Link2, Users, Wallet } from 'lucide-vue-next'

import AivisLogo from '@/components/ui/AivisLogo.vue'
import CAppControls from '@/components/ui/CAppControls.vue'
import { CButton, CCheckbox, CLoader } from '@/components/ui'
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
  <div class="welcome">
    <div class="welcome__bar">
      <AivisLogo :height="28" :show-text="false" />
      <CAppControls />
    </div>

    <div class="welcome__card">
      <div v-if="checking" class="welcome__center">
        <CLoader :size="28" />
      </div>

      <!-- The agreement document is not published: nothing can be accepted -->
      <template v-else-if="status === 'missing'">
        <h1 class="welcome__title">
          {{ t('agent.welcome.unavailableTitle') }}
        </h1>
        <p class="welcome__text">
          {{ t('agent.welcome.unavailableText') }}
        </p>
        <CButton variant="primary" @click="toSupport">
          {{ t('agent.welcome.toSupport') }}
        </CButton>
      </template>

      <!-- The state could not be read -->
      <template v-else-if="status === 'error'">
        <h1 class="welcome__title">
          {{ t('agent.welcome.errorTitle') }}
        </h1>
        <CButton variant="outline" @click="check">
          {{ t('common.retry') }}
        </CButton>
      </template>

      <template v-else>
        <h1 class="welcome__title">
          {{ t('agent.welcome.title') }}
        </h1>
        <p class="welcome__text">
          {{ t('agent.welcome.intro') }}
        </p>
        <ul class="welcome__list">
          <li>
            <Link2 :size="18" class="welcome__icon" />
            <span>{{ t('agent.welcome.possLink') }}</span>
          </li>
          <li>
            <Users :size="18" class="welcome__icon" />
            <span>{{ t('agent.welcome.possPartners') }}</span>
          </li>
          <li>
            <Coins :size="18" class="welcome__icon" />
            <span>{{ t('agent.welcome.possCommission') }}</span>
          </li>
          <li>
            <Wallet :size="18" class="welcome__icon" />
            <span>{{ t('agent.welcome.possWithdrawal') }}</span>
          </li>
        </ul>

        <p class="welcome__read">
          <a href="#agreement" @click.prevent="reading = true">{{
            t('agent.welcome.readAgreement')
          }}</a>
        </p>

        <CCheckbox v-model="ticked" :label="t('agent.welcome.tick')" />

        <CButton variant="primary" :disabled="!ticked" :loading="accepting" @click="onAccept">
          {{ t('agent.welcome.accept') }}
        </CButton>
      </template>

      <div class="welcome__logout">
        <AuthLogoutLink />
      </div>
    </div>

    <LegalDocModal
      :open="reading"
      :title="t('agent.link.agreementTitle')"
      :lang="docLang"
      type="agent_integrator_agreement"
      @close="reading = false"
    />
  </div>
</template>

<style scoped>
.welcome {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
}

.welcome__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
}

.welcome__card {
  width: 100%;
  max-width: var(--maxw-prose, 560px);
  margin: 0 auto;
  padding: var(--space-5) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.welcome__center {
  display: flex;
  justify-content: center;
  padding: var(--space-6, 32px) 0;
}

.welcome__title {
  margin: 0;
  font-size: var(--fs-h3, 1.375rem);
  font-weight: 700;
  color: var(--text-primary);
}

.welcome__text {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.welcome__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.welcome__list li {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  line-height: 1.4;
}

.welcome__icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--primary);
}

.welcome__read {
  margin: 0;
  font-size: var(--fs-sm);
}

.welcome__read a {
  color: var(--primary);
}

.welcome__logout {
  display: flex;
  justify-content: center;
  padding-top: var(--space-2);
}
</style>
