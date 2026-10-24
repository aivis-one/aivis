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
// acceptance screen comes before the cabinet). The link has a Share menu, "Copy
// link" and "Share via..." (the system menu of the phone; on a device without one it
// copies). There is no "create link" button and no list of links.
//
// DATA. Each source is an independent probe of the agent store and the shared
// dashboard store; a failure of one leaves its figure as a dash and hides
// nothing else.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Coins, Link, Share2, Trophy, Users, Wallet } from '@/components/ui/icons'

import { CEmptyState, CIconBox, CLoader, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CActionMenu from '@/components/ui/CActionMenu.vue'
import type { ActionMenuItem } from '@/components/ui/CActionMenu.vue'
import { useAgentLink } from '@/composables/useAgentLink'
import { useAgentStore } from '@/stores/agent'
import { useDashboardStore } from '@/stores/dashboard'
import { formatNumber, formatPrice } from '@/utils/format'

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

// The frame's header carries the title and the line under it.
useScreenHeader({
  title: () => t('agent.partners.title'),
  lead: () => t('agent.partners.subtitle'),
})

// The link's two share acts, as the system's Action menu (K26).
const shareItems = computed<ActionMenuItem[]>(() => [
  { value: 'copy', label: t('agent.link.copy'), icon: Link },
  { value: 'share', label: t('agent.link.shareVia'), icon: Share2 },
])

function onShareSelect(value: string): void {
  if (value === 'copy') void copy()
  else if (value === 'share') void share()
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
  <!-- The link -->
  <CLoader v-if="agreement === 'loading'" centered extent="page" />

  <section v-else-if="link" class="ds-card" aria-labelledby="partners-link-title">
    <header class="ds-card__head">
      <h2 id="partners-link-title" class="ds-card__title">{{ t('agent.partners.linkTitle') }}</h2>
      <CActionMenu
        :label="t('agent.link.share')"
        :icon="Share2"
        :items="shareItems"
        align="end"
        @select="onShareSelect"
      />
    </header>
    <p class="ds-card__figure">{{ link.code }}</p>
    <p class="ds-card__body partners__address">{{ shareUrl() }}</p>
    <div class="ds-stats">
      <CStatCard
        :label="t('agent.partners.clicks')"
        :value="formatNumber(link.click_count, locale)"
      />
      <CStatCard
        :label="t('agent.partners.registrations')"
        :value="formatNumber(link.registration_count, locale)"
      />
      <CStatCard
        :label="t('agent.partners.purchases')"
        :value="formatNumber(link.purchase_count, locale)"
      />
    </div>
  </section>

  <CEmptyState v-else framed :description="t('agent.partners.linkError')" />

  <!-- The sections that lie inside the tab -->
  <nav class="ds-navtiles" :aria-label="t('agent.partners.title')">
    <RouterLink class="ds-navtile" :to="{ name: 'agent-referrals' }">
      <CIconBox><Users /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('agent.partners.network') }}</span>
        <span class="ds-navtile__desc">
          {{ t('agent.partners.networkSub', { n: registrations }) }}
        </span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
    <RouterLink class="ds-navtile" :to="{ name: 'agent-commissions' }">
      <CIconBox><Coins /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('agent.partners.commissions') }}</span>
        <span class="ds-navtile__desc">
          {{
            t('agent.partners.commissionsSub', {
              amount: agentStore.commissionSummaryError
                ? '—'
                : formatPrice(agentStore.monthCommissionCents),
            })
          }}
        </span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
    <RouterLink class="ds-navtile" :to="{ name: 'agent-leaderboard' }">
      <CIconBox><Trophy /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('agent.partners.rating') }}</span>
        <span class="ds-navtile__desc">
          {{ t('agent.partners.ratingSub', { rank: rankText }) }}
        </span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
    <RouterLink class="ds-navtile" :to="{ name: 'agent-balance' }">
      <CIconBox><Wallet /></CIconBox>
      <span class="ds-navtile__text">
        <span class="ds-navtile__title">{{ t('agent.partners.balance') }}</span>
        <span class="ds-navtile__desc">
          {{
            t('agent.partners.balanceSub', {
              amount: dashboardStore.error
                ? '—'
                : formatPrice(dashboardStore.passiveBalance.confirmed),
            })
          }}
        </span>
      </span>
      <ChevronRight class="ds-navtile__go" size="sm" />
    </RouterLink>
  </nav>
</template>

<style scoped>
/* The link's address wraps anywhere, as a long token does. */
.partners__address {
  overflow-wrap: anywhere;
}
</style>
