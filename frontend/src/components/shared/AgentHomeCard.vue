<script setup lang="ts">
// The integrator's card on Home, under the buyer's own Home: the commission of
// the month, the rank and the registrations -- each tile opens its section of
// Partners -- and the main button, "Copy link", one click.

import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Coins, Copy, Trophy, UserPlus } from '@/components/ui/icons'

import { CButton, CStatCard } from '@/components/ui'
import { useAgentLink } from '@/composables/useAgentLink'
import { useAgentStore } from '@/stores/agent'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatNumber, formatPrice } from '@/utils/format'

const router = useRouter()
const { t, locale } = useI18n()
const agentStore = useAgentStore()
const { link, copy, load } = useAgentLink()

function go(name: string): void {
  void safeNavigate(router.push({ name }), `[AgentHomeCard] to ${name}`)
}

onMounted(() => {
  void agentStore.fetchCommissionSummary()
  void agentStore.fetchLeaderboard()
  void agentStore.fetchStats()
  void load()
})
</script>

<template>
  <section class="ahc">
    <h2 class="ds-section-title">
      {{ t('agent.home.title') }}
    </h2>

    <!-- Each tile opens its section of Partners (K46, the button form) -->
    <div class="ds-stats">
      <CStatCard
        :label="t('agent.home.monthCommission')"
        :pending="agentStore.commissionSummaryLoading"
        :value="
          agentStore.commissionSummaryError ? '—' : formatPrice(agentStore.monthCommissionCents)
        "
        @click="go('agent-commissions')"
      >
        <template #icon>
          <span class="ds-lead" data-tone="accent"><Coins size="sm" /></span>
        </template>
      </CStatCard>

      <CStatCard
        :label="t('agent.home.rank')"
        :pending="agentStore.leaderboardLoading"
        :value="
          agentStore.leaderboardError || agentStore.myRank === null ? '—' : `#${agentStore.myRank}`
        "
        @click="go('agent-leaderboard')"
      >
        <template #icon>
          <span class="ds-lead" data-tone="warning"><Trophy size="sm" /></span>
        </template>
      </CStatCard>

      <CStatCard
        :label="t('agent.home.registrations')"
        :pending="agentStore.statsLoading"
        :value="
          agentStore.statsError || !agentStore.stats
            ? '—'
            : formatNumber(agentStore.stats.total_registrations, locale)
        "
        @click="go('agent-referrals')"
      >
        <template #icon>
          <span class="ds-lead" data-tone="success"><UserPlus size="sm" /></span>
        </template>
      </CStatCard>
    </div>

    <CButton v-if="link" variant="primary" @click="copy()">
      <Copy size="sm" />
      {{ t('agent.link.copy') }}
    </CButton>
  </section>
</template>

<style scoped>
.ahc {
  display: grid;
  gap: var(--space-3);
}
</style>
