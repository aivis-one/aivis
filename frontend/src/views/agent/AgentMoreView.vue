<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentMoreView (Task 3 Block D, Phase F6.2)
// =============================================================================
//
// Top-level "More" tab for the agent shell -- navigation hub for the
// screens that don't have their own bottom-bar slot. Replaces the F6.2
// stub. Mirrors InvestorMoreView (tile grid, single v-for, safeNavigate).
//
// ENTRY-POINT CLOSURE (Task 3 open notes from Blocks B & C).
//   ReferralsView (/agent/referrals) and LeaderboardView
//   (/agent/leaderboard) are sub-routes that nothing linked to before
//   this view -- they were reachable only by deep link. The "My
//   network" and "Leaderboard" tiles here are what wire them into the
//   UI. The Settings tile does the same for /agent/settings.
//
// SCOPE (core-3, decided in chat).
//   My network, Leaderboard, Settings. Sign-out is NOT here -- it lives
//   in Settings as a deliberate action (same risk trade-off as
//   InvestorMoreView, a finance app should not surface logout on a tab
//   that can be hit by accident).
//
// Phase 6: +Notifications tile, mirroring InvestorMoreView's restored
// tile -- same tile-grid pattern, same route shape
// (/agent/notifications -> the same NotificationsInboxView.vue every
// shell reuses). A second entry point to what CHeader's bell already
// opens, kept here for the same "More tab as a catch-all" reason
// Settings/network/leaderboard are.
//
// FP notes:
//   FP-19 -- shell owns the header; inline more__header h1. No back-link:
//            /agent/more is a top-level tab (AGENT_TABS).
//   FP-18 -- tiles navigate via safeNavigate.
// =============================================================================

import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Bell,
  ChevronRight,
  CreditCard,
  HelpCircle,
  MessageCircle,
  Settings as SettingsIcon,
  Trophy,
  Users,
} from 'lucide-vue-next'
import { safeNavigate } from '@/composables/safeNavigate'

interface Tile {
  id: string
  labelKey: string
  descKey: string
  route: string
  icon: typeof Users
}

const { t } = useI18n()
const router = useRouter()

// Data + a single v-for so adding a tile later (documents, support) is
// a one-line array change, not template copy-paste.
const TILES: readonly Tile[] = [
  {
    id: 'network',
    labelKey: 'agent.more.network.title',
    descKey: 'agent.more.network.desc',
    route: '/agent/referrals',
    icon: Users,
  },
  {
    id: 'leaderboard',
    labelKey: 'agent.more.leaderboard.title',
    descKey: 'agent.more.leaderboard.desc',
    route: '/agent/leaderboard',
    icon: Trophy,
  },
  {
    id: 'settings',
    labelKey: 'agent.more.settings.title',
    descKey: 'agent.more.settings.desc',
    route: '/agent/settings',
    icon: SettingsIcon,
  },
  // TASK-39 item 1: an agent is a buyer too (_BUYER_ROLES on the
  // backend) and can hold their own installment plans -- same tile,
  // same route shape as InvestorMoreView's mirror
  // (/agent/installments -> the same InstallmentPlansView.vue every
  // shell reuses).
  {
    id: 'installments',
    labelKey: 'agent.more.installments.title',
    descKey: 'agent.more.installments.desc',
    route: '/agent/installments',
    icon: CreditCard,
  },
  {
    id: 'notifications',
    labelKey: 'agent.more.notifications.title',
    descKey: 'agent.more.notifications.desc',
    route: '/agent/notifications',
    icon: Bell,
  },
  // TASK-39 item 4: an agent has no path to support anywhere in the
  // product today (measured gap) -- same tile, same route shape as
  // InvestorMoreView's mirror (/agent/support -> the same
  // InvestorSupportView.vue every shell reuses). The backend already
  // serves this role (support/router.py has no role check); this
  // tile is what makes it reachable.
  {
    id: 'support',
    labelKey: 'agent.more.support.title',
    descKey: 'agent.more.support.desc',
    route: '/agent/support',
    icon: MessageCircle,
  },
  // TASK-39 item 3: FAQ framework -- one-line addition, same pattern
  // as InvestorMoreView's mirror. Investor + agent share this FAQ
  // (owner ruling); see InvestorFaqView.vue for the full ruling.
  {
    id: 'faq',
    labelKey: 'agent.more.faq.title',
    descKey: 'agent.more.faq.desc',
    route: '/agent/faq',
    icon: HelpCircle,
  },
] as const

function openTile(tile: Tile): void {
  void safeNavigate(router.push(tile.route), `[AgentMoreView] to ${tile.route}`)
}
</script>

<template>
  <div class="more">
    <!-- Inline page header, no CHeader (shell renders it). -->
    <div class="more__header">
      <h1 class="more__title">
        {{ t('agent.more.title') }}
      </h1>
      <p class="more__subtitle">
        {{ t('agent.more.subtitle') }}
      </p>
    </div>

    <div class="more__grid">
      <button
        v-for="tile in TILES"
        :key="tile.id"
        type="button"
        class="more__tile"
        @click="openTile(tile)"
      >
        <div class="more__tile-icon">
          <component :is="tile.icon" :size="24" />
        </div>
        <div class="more__tile-body">
          <div class="more__tile-title">
            {{ t(tile.labelKey) }}
          </div>
          <div class="more__tile-desc">
            {{ t(tile.descKey) }}
          </div>
        </div>
        <ChevronRight :size="16" class="more__tile-chev" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.more {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.more__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.more__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.more__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.more__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

.more__tile {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-primary);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s,
    box-shadow 0.15s;
  min-height: 72px;
}
.more__tile:hover {
  border-color: var(--primary-hover);
  background: var(--bg-subtle);
  box-shadow: var(--shadow-1);
}
.more__tile:active {
  transform: translateY(1px);
}

.more__tile-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-2xl);
  height: var(--size-2xl);
  border-radius: var(--radius-sm);
  background: var(--primary-subtle);
  color: var(--primary);
  flex-shrink: 0;
}

.more__tile-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.more__tile-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.more__tile-desc {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.more__tile-chev {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.more__subtitle {
  max-width: var(--maxw-prose);
}
</style>
