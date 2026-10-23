<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentPartnersView
// =============================================================================
//
// The integrator's "Partners" tab: their one link with the counters, and the
// four sections that lie inside the tab on a phone, each a row of its own --
// the network (the integrator's buyers and sub-integrators by three levels),
// the commissions, the rating and the balance. The web side menu lists the
// balance as a line of its own as well.
//
// THE LINK. An integrator has exactly one link, issued by the platform once,
// after the agent-integrator agreement is accepted (useAgentLink; the
// acceptance screen comes before the cabinet). The link has two buttons, "Copy
// link" and "Share" (the system menu of the phone; on a device without one it
// copies). There is no "create link" button and no list of links.
//
// DATA. Each source is an independent probe of the agent store and the shared
// dashboard store; a failure of one leaves its figure as a dash and hides
// nothing else.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Coins, Copy, Share2, Trophy, Users, Wallet } from 'lucide-vue-next'

import { CButton, CLoader } from '@/components/ui'
import { useAgentLink } from '@/composables/useAgentLink'
import { useAgentStore } from '@/stores/agent'
import { useDashboardStore } from '@/stores/dashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatNumber, formatPrice } from '@/utils/format'

const router = useRouter()
const { t, locale } = useI18n()
const agentStore = useAgentStore()
const dashboardStore = useDashboardStore()
const { agreement, link, copy, share, shareUrl, load } = useAgentLink()

const registrations = computed<string>(() =>
  agentStore.statsError || !agentStore.stats
    ? '—'
    : formatNumber(agentStore.stats.total_registrations, locale.value),
)

const rankText = computed<string>(() =>
  agentStore.leaderboardError || agentStore.myRank === null
    ? t('agent.partners.rankNone')
    : `#${agentStore.myRank}`,
)

function go(name: string): void {
  void safeNavigate(router.push({ name }), `[AgentPartnersView] to ${name}`)
}

onMounted(() => {
  void load()
  void agentStore.fetchStats()
  void agentStore.fetchCommissionSummary()
  void agentStore.fetchLeaderboard()
  void dashboardStore.refresh()
})
</script>

<template>
  <div class="partners">
    <div class="partners__header">
      <h1 class="partners__title">
        {{ t('agent.partners.title') }}
      </h1>
      <p class="partners__subtitle">
        {{ t('agent.partners.subtitle') }}
      </p>
    </div>

    <!-- The link -->
    <div v-if="agreement === 'loading'" class="partners__center">
      <CLoader :size="24" />
    </div>

    <section v-else-if="link" class="partners__link">
      <h2 class="partners__link-title">
        {{ t('agent.partners.linkTitle') }}
      </h2>
      <div class="partners__url">
        <span class="partners__code">{{ link.code }}</span>
        <span class="partners__address">{{ shareUrl() }}</span>
      </div>
      <div class="partners__buttons">
        <CButton variant="primary" @click="copy()">
          <Copy :size="16" />
          {{ t('agent.link.copy') }}
        </CButton>
        <CButton variant="outline" @click="share()">
          <Share2 :size="16" />
          {{ t('agent.link.share') }}
        </CButton>
      </div>
      <div class="partners__counters">
        <div class="partners__counter">
          <span class="partners__counter-value">{{ formatNumber(link.click_count, locale) }}</span>
          <span class="partners__counter-label">{{ t('agent.partners.clicks') }}</span>
        </div>
        <div class="partners__counter">
          <span class="partners__counter-value">
            {{ formatNumber(link.registration_count, locale) }}
          </span>
          <span class="partners__counter-label">{{ t('agent.partners.registrations') }}</span>
        </div>
        <div class="partners__counter">
          <span class="partners__counter-value">
            {{ formatNumber(link.purchase_count, locale) }}
          </span>
          <span class="partners__counter-label">{{ t('agent.partners.purchases') }}</span>
        </div>
      </div>
    </section>

    <p v-else class="partners__empty">
      {{ t('agent.partners.linkError') }}
    </p>

    <!-- The sections that lie inside the tab -->
    <ul class="partners__rows">
      <li>
        <button type="button" class="partners__row" @click="go('agent-referrals')">
          <Users :size="20" class="partners__row-icon" />
          <span class="partners__row-body">
            <span class="partners__row-title">{{ t('agent.partners.network') }}</span>
            <span class="partners__row-sub">
              {{ t('agent.partners.networkSub', { n: registrations }) }}
            </span>
          </span>
          <ChevronRight :size="16" />
        </button>
      </li>
      <li>
        <button type="button" class="partners__row" @click="go('agent-commissions')">
          <Coins :size="20" class="partners__row-icon" />
          <span class="partners__row-body">
            <span class="partners__row-title">{{ t('agent.partners.commissions') }}</span>
            <span class="partners__row-sub">
              {{
                t('agent.partners.commissionsSub', {
                  amount: agentStore.commissionSummaryError
                    ? '—'
                    : formatPrice(agentStore.monthCommissionCents),
                })
              }}
            </span>
          </span>
          <ChevronRight :size="16" />
        </button>
      </li>
      <li>
        <button type="button" class="partners__row" @click="go('agent-leaderboard')">
          <Trophy :size="20" class="partners__row-icon" />
          <span class="partners__row-body">
            <span class="partners__row-title">{{ t('agent.partners.rating') }}</span>
            <span class="partners__row-sub">
              {{ t('agent.partners.ratingSub', { rank: rankText }) }}
            </span>
          </span>
          <ChevronRight :size="16" />
        </button>
      </li>
      <li>
        <button type="button" class="partners__row" @click="go('agent-balance')">
          <Wallet :size="20" class="partners__row-icon" />
          <span class="partners__row-body">
            <span class="partners__row-title">{{ t('agent.partners.balance') }}</span>
            <span class="partners__row-sub">
              {{
                t('agent.partners.balanceSub', {
                  amount: dashboardStore.error
                    ? '—'
                    : formatPrice(dashboardStore.passiveBalance.confirmed),
                })
              }}
            </span>
          </span>
          <ChevronRight :size="16" />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.partners {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
  padding-bottom: var(--space-5);
}

.partners__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.partners__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.partners__subtitle {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.partners__center {
  display: flex;
  justify-content: center;
  padding: var(--space-4);
}

.partners__link {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.partners__link-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.partners__url {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.partners__code {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.partners__address {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.partners__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.partners__counters {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}

.partners__counter {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.partners__counter-value {
  font-size: var(--fs-h4);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.partners__counter-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.partners__empty {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.partners__rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.partners__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  min-height: 44px;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.partners__row:active {
  background: var(--bg-surface);
}

.partners__row-icon {
  color: var(--primary);
  flex-shrink: 0;
}

.partners__row-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.partners__row-title {
  font-size: var(--fs-sm);
  font-weight: 600;
}

.partners__row-sub {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

@media (min-width: 880px) {
  .partners__link,
  .partners__rows {
    max-width: calc(3 * var(--tile-max));
  }
}
</style>
