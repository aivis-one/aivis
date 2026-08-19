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
//   FP-19 -- the shell owns the header; this view renders an inline
//            page-header (h1 + subtitle), no header component here.
//   FP-20 -- /agent/referrals is a SUB-ROUTE (not in AGENT_TABS), so a
//            CBackLink is mandatory. goBack is history-aware and falls
//            through to the Hub on a cold deep-link.
//   FP-18 -- the back fallback navigates via safeNavigate (router.back
//            is neither push nor replace, so it stays bare).
//   FP-25 -- self-hiding: an empty collection hides its section; both
//            empty renders a single CEmptyState, no scaffolding.
//
// ENTRY POINT (open note, Task 3 report).
//   Nothing in the shipped Hub / Dashboard links here yet; the entry
//   point is expected from AgentMoreView (Block D), where Leaderboard
//   also lives. Tracked there -- AgentHubView is not rewritten for it.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { useAgentStore } from '@/stores/agent'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'

const router = useRouter()
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
    !agentStore.downlineLoading
    && !agentStore.downlineError
    && agentStore.downline !== null
    && investors.value.length === 0
    && subAgents.value.length === 0,
)

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function goBack(): void {
  // History-aware: return to wherever the user came from (the More tab
  // in the wired flow). On a cold deep-link there is no back entry --
  // fall through to the Hub. router.back() is neither push nor replace,
  // so it does not need safeNavigate; the fallback push does (FP-18).
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'agent-hub' }),
    '[ReferralsView] back fallback to agent-hub',
  )
}

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
  <div class="ref">
    <!-- Page header (FP-19: shell owns CHeader; FP-20: sub-route back-link) -->
    <div class="ref__page-header">
      <CBackLink :label="t('agent.referrals.backLink')" @click="goBack" />
      <h1 class="ref__title">{{ t('agent.referrals.title') }}</h1>
      <p class="ref__subtitle">{{ t('agent.referrals.subtitle') }}</p>
    </div>

    <!-- Loading (first load only) -->
    <div
      v-if="agentStore.downlineLoading && agentStore.downline === null"
      class="ref__center"
    >
      <CLoader :size="24" />
    </div>

    <!-- Error -->
    <div
      v-else-if="agentStore.downlineError && agentStore.downline === null"
      class="ref__center"
    >
      <CEmptyState :title="t('agent.referrals.errorTitle')" />
      <CButton variant="outline" size="sm" @click="retry">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- FP-25: whole-screen empty (both collections empty) -->
    <div v-else-if="isEmpty" class="ref__center">
      <CEmptyState
        :title="t('agent.referrals.empty.title')"
        :description="t('agent.referrals.empty.desc')"
      />
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Investors (self-hiding when empty) -->
      <section v-if="investors.length > 0" class="ref__section">
        <h2 class="ref__section-title">
          {{ t('agent.referrals.investors.title') }}
        </h2>
        <ul class="ref__list">
          <li v-for="inv in investors" :key="inv.user_id" class="ref__card">
            <div class="ref__card-head">
              <span class="ref__card-name">{{ inv.display_name }}</span>
              <span class="ref__level" :class="`ref__level--l${inv.level}`">
                {{ t('agent.referrals.level', { n: inv.level }) }}
              </span>
            </div>
            <div class="ref__card-foot">
              <div class="ref__metric">
                <span class="ref__metric-value">
                  {{ formatPrice(inv.purchase_volume_cents) }}
                </span>
                <span class="ref__metric-label">
                  {{ t('agent.referrals.investors.volume') }}
                </span>
              </div>
              <div class="ref__joined">
                {{ t('agent.referrals.joined') }}
                {{ formatDate(inv.registered_at, locale) }}
              </div>
            </div>
          </li>
        </ul>
      </section>

      <!-- Sub-agents (self-hiding when empty) -->
      <section v-if="subAgents.length > 0" class="ref__section">
        <h2 class="ref__section-title">
          {{ t('agent.referrals.subAgents.title') }}
        </h2>
        <ul class="ref__list">
          <li v-for="sa in subAgents" :key="sa.user_id" class="ref__card">
            <div class="ref__card-head">
              <span class="ref__card-name">{{ sa.display_name }}</span>
              <span class="ref__level" :class="`ref__level--l${sa.level}`">
                {{ t('agent.referrals.level', { n: sa.level }) }}
              </span>
            </div>

            <!-- Three honest, never-summed metrics (decisions #4 / #8) -->
            <div class="ref__card-counters">
              <div class="ref__metric">
                <span class="ref__metric-value">
                  {{ formatNumber(sa.recruited_investor_count, locale) }}
                </span>
                <span class="ref__metric-label">
                  {{ t('agent.referrals.subAgents.recruited') }}
                </span>
              </div>
              <div class="ref__metric">
                <span class="ref__metric-value">
                  {{ formatPrice(sa.direct_volume_cents) }}
                </span>
                <span class="ref__metric-label">
                  {{ t('agent.referrals.subAgents.directVolume') }}
                </span>
              </div>
              <div class="ref__metric">
                <span class="ref__metric-value">
                  {{ formatPrice(sa.own_purchase_volume_cents) }}
                </span>
                <span class="ref__metric-label">
                  {{ t('agent.referrals.subAgents.ownVolume') }}
                </span>
              </div>
            </div>

            <div class="ref__joined">
              {{ t('agent.referrals.joined') }}
              {{ formatDate(sa.registered_at, locale) }}
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.ref {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ref__page-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ref__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-2) 0 0;
}

.ref__subtitle {
  font-size: var(--fs-xs-lg);
  color: var(--text-secondary);
  margin: 0;
}

.ref__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) 0;
}

/* -- Section -- */

.ref__section-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}

.ref__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* -- Card -- */

.ref__card {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ref__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.ref__card-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref__level {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  font-weight: 700;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
}

.ref__level--l1 {
  color: var(--primary);
}

.ref__level--l2 {
  color: var(--text-secondary);
}

.ref__level--l3 {
  color: var(--text-tertiary);
}

.ref__card-foot {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
}

.ref__card-counters {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
}

.ref__metric {
  display: flex;
  flex-direction: column;
}

.ref__metric-value {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.ref__metric-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.ref__joined {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 820px) {
  .ref__card-counters { max-width: calc(3 * var(--tile-max)); }
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.ref__subtitle { max-width: var(--maxw-prose); }
</style>
