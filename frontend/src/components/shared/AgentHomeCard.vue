<script setup lang="ts">
// The integrator's card on Home, under the buyer's own Home: the commission of
// the month, the rank and the registrations -- each tile opens its section of
// Partners -- and the main button, "Copy link", one click.

import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Coins, Copy, Trophy, UserPlus } from 'lucide-vue-next'

import { CButton, CLoader } from '@/components/ui'
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
    <h2 class="ahc__title">
      {{ t('agent.home.title') }}
    </h2>

    <div class="ahc__tiles">
      <button type="button" class="ahc__tile" @click="go('agent-commissions')">
        <Coins :size="16" class="ahc__icon ahc__icon--accent" />
        <CLoader v-if="agentStore.commissionSummaryLoading" :size="16" />
        <span v-else class="ahc__value">
          {{
            agentStore.commissionSummaryError ? '—' : formatPrice(agentStore.monthCommissionCents)
          }}
        </span>
        <span class="ahc__label">{{ t('agent.home.monthCommission') }}</span>
      </button>

      <button type="button" class="ahc__tile" @click="go('agent-leaderboard')">
        <Trophy :size="16" class="ahc__icon ahc__icon--gold" />
        <CLoader v-if="agentStore.leaderboardLoading" :size="16" />
        <span v-else class="ahc__value">
          {{
            agentStore.leaderboardError || agentStore.myRank === null
              ? '—'
              : `#${agentStore.myRank}`
          }}
        </span>
        <span class="ahc__label">{{ t('agent.home.rank') }}</span>
      </button>

      <button type="button" class="ahc__tile" @click="go('agent-referrals')">
        <UserPlus :size="16" class="ahc__icon ahc__icon--teal" />
        <CLoader v-if="agentStore.statsLoading" :size="16" />
        <span v-else class="ahc__value">
          {{
            agentStore.statsError || !agentStore.stats
              ? '—'
              : formatNumber(agentStore.stats.total_registrations, locale)
          }}
        </span>
        <span class="ahc__label">{{ t('agent.home.registrations') }}</span>
      </button>
    </div>

    <CButton v-if="link" variant="primary" class="ahc__copy" @click="copy()">
      <Copy :size="16" />
      {{ t('agent.link.copy') }}
    </CButton>
  </section>
</template>

<style scoped>
.ahc {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ahc__title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.ahc__tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}

.ahc__tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  min-height: 92px;
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.ahc__tile:active {
  background: var(--bg-surface);
}

.ahc__icon--accent {
  color: var(--accent);
}

.ahc__icon--gold {
  color: var(--warning);
}

.ahc__icon--teal {
  color: var(--success);
}

.ahc__value {
  font-size: var(--fs-h4);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.ahc__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.ahc__copy {
  align-self: stretch;
}

@media (min-width: 820px) {
  .ahc__tiles {
    max-width: calc(3 * var(--tile-max));
  }
  .ahc__copy {
    align-self: flex-start;
  }
}
</style>
