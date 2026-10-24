<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- ReferralsView (Task 3 Block B, Phase F6.1)
// =============================================================================
//
// Replaces the F6.1 stub. The agent's downline -- two server-assembled
// collections from GET /referrals/downline/me:
//   - investors at commission-mirror levels L1-L3 (the levels the
//     agent is actually paid on; L4+ is excluded backend-side)
//   - sub-agents at agent-hop depth 1-3
//
// Both come from ONE endpoint, so there is ONE view-level loading /
// error gate (stores/agent.ts downline group, its own FP-17 epoch).
//
// FIELD HONESTY (decisions #4 / #8).
//   A sub-agent row carries three DISTINCT numbers that must never be
//   conflated into one "volume":
//     - recruited_investor_count -- how many investors the sub-agent
//       directly recruited (count, non-recursive)
//     - direct_volume_cents      -- ACTIVE purchase volume of the
//       sub-agent's DIRECT investors
//     - own_purchase_volume_cents -- the sub-agent's OWN purchases
//       (agents buy too; this feeds the requesting agent's commission)
//   Each gets its own labelled metric, never summed.
//
// MASKING.
//   display_name arrives MASKED from the server (decision #5 -- no
//   email / phone / KYC leaked). The view renders it verbatim and does
//   NO masking of its own.
//
// FP notes:
//   FP-19 -- the frame owns the header (useScreenHeader);
//            no header component here.
//   FP-20 -- /agent/referrals is a SUB-ROUTE (not in AGENT_TABS), so a
//            CBackLink is mandatory. goBack is history-aware and falls
//            through to Partners on a cold deep-link.
//   FP-18 -- the back fallback navigates via safeNavigate (router.back
//            is neither push nor replace, so it stays bare).
//   FP-25 -- self-hiding: an empty collection hides its section; both
//            empty renders a single CEmptyState, no scaffolding.
//
// ENTRY POINT (open note, Task 3 report).
//   Reached from the Partners tab (AgentPartnersView, the "My network"
//   row), where the rating lives as well.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useAgentStore } from '@/stores/agent'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'

const { t, locale } = useI18n()
const agentStore = useAgentStore()

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const investors = computed(() => agentStore.downline?.investors ?? [])
const subAgents = computed(() => agentStore.downline?.sub_agents ?? [])

// Whole-screen empty only when the payload is in AND both collections
// are empty -- a brand-new agent with no downline at all.
const isEmpty = computed(
  () =>
    !agentStore.downlineLoading &&
    !agentStore.downlineError &&
    agentStore.downline !== null &&
    investors.value.length === 0 &&
    subAgents.value.length === 0,
)

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

// The frame's header carries the title, the line under it and the way back:
// history-aware (Partners in the wired flow), a cold deep-link falls through to
// Partners (FP-20).
useScreenHeader({
  title: () => t('agent.referrals.title'),
  lead: () => t('agent.referrals.subtitle'),
  back: () => (window.history.state?.back ? true : { name: 'agent-partners' }),
})

function retry(): void {
  void agentStore.fetchDownline()
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  void agentStore.fetchDownline()
})
</script>

<template>
  <!-- Loading (first load only) -->
  <div
    v-if="agentStore.downlineLoading && agentStore.downline === null"
    class="ds-empty"
    aria-busy="true"
  >
    <CLoader :size="24" />
  </div>

  <!-- Error -->
  <CEmptyState
    v-else-if="agentStore.downlineError && agentStore.downline === null"
    tone="danger"
    :title="t('agent.referrals.errorTitle')"
  >
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- FP-25: whole-screen empty (both collections empty) -->
  <CEmptyState
    v-else-if="isEmpty"
    :title="t('agent.referrals.empty.title')"
    :description="t('agent.referrals.empty.desc')"
  />

  <!-- Loaded -->
  <template v-else>
    <!-- Investors (self-hiding when empty) -->
    <section v-if="investors.length > 0" class="ref__section" aria-labelledby="ref-investors">
      <h2 id="ref-investors" class="ref__section-title">
        {{ t('agent.referrals.investors.title') }}
      </h2>
      <article v-for="inv in investors" :key="inv.user_id" class="ds-card" data-size="sm">
        <header class="ds-card__head">
          <h3 class="ds-card__title">{{ inv.display_name }}</h3>
          <CBadge
            :variant="inv.level === 1 ? 'primary' : 'neutral'"
            :text="t('agent.referrals.level', { n: inv.level })"
          />
        </header>
        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.investors.volume') }}</dt>
            <dd>{{ formatPrice(inv.purchase_volume_cents) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.joined') }}</dt>
            <dd>{{ formatDate(inv.registered_at, locale) }}</dd>
          </div>
        </dl>
      </article>
    </section>

    <!-- Sub-agents (self-hiding when empty) -->
    <section v-if="subAgents.length > 0" class="ref__section" aria-labelledby="ref-subagents">
      <h2 id="ref-subagents" class="ref__section-title">
        {{ t('agent.referrals.subAgents.title') }}
      </h2>
      <article v-for="sa in subAgents" :key="sa.user_id" class="ds-card" data-size="sm">
        <header class="ds-card__head">
          <h3 class="ds-card__title">{{ sa.display_name }}</h3>
          <CBadge
            :variant="sa.level === 1 ? 'primary' : 'neutral'"
            :text="t('agent.referrals.level', { n: sa.level })"
          />
        </header>
        <!-- Three honest, never-summed metrics (decisions #4 / #8) -->
        <dl class="ds-kv">
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.subAgents.recruited') }}</dt>
            <dd>{{ formatNumber(sa.recruited_investor_count, locale) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.subAgents.directVolume') }}</dt>
            <dd>{{ formatPrice(sa.direct_volume_cents) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.subAgents.ownVolume') }}</dt>
            <dd>{{ formatPrice(sa.own_purchase_volume_cents) }}</dd>
          </div>
          <div class="ds-kv__row">
            <dt>{{ t('agent.referrals.joined') }}</dt>
            <dd>{{ formatDate(sa.registered_at, locale) }}</dd>
          </div>
        </dl>
      </article>
    </section>
  </template>
</template>

<style scoped>
/* A section: its heading over its cards, on the frame's rhythm. */
.ref__section {
  display: grid;
  gap: var(--space-3);
}
.ref__section-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  line-height: var(--lh-snug);
  color: var(--text-primary);
}
</style>
