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
// FP notes:
//   FP-19 -- shell owns the header; inline more__header h1. No back-link:
//            /agent/more is a top-level tab (AGENT_TABS).
//   FP-18 -- tiles navigate via safeNavigate.
// =============================================================================

import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Settings as SettingsIcon, Trophy, Users } from 'lucide-vue-next'
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
] as const

function openTile(tile: Tile): void {
  void safeNavigate(router.push(tile.route), `[AgentMoreView] to ${tile.route}`)
}
</script>

<template>
  <div class="more">
    <!-- Inline page header, no CHeader (shell renders it). -->
    <div class="more__header">
      <h1 class="more__title">{{ t('agent.more.title') }}</h1>
      <p class="more__subtitle">{{ t('agent.more.subtitle') }}</p>
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
          <component :is="tile.icon" :size="22" />
        </div>
        <div class="more__tile-body">
          <div class="more__tile-title">{{ t(tile.labelKey) }}</div>
          <div class="more__tile-desc">{{ t(tile.descKey) }}</div>
        </div>
        <ChevronRight :size="18" class="more__tile-chev" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.more {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.more__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.more__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}
.more__subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.more__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.more__tile {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
  min-height: 72px;
}
.more__tile:hover {
  border-color: var(--primary-light);
  background: var(--bg-subtle);
  box-shadow: var(--shadow-sm);
}
.more__tile:active {
  transform: translateY(1px);
}

.more__tile-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  background: var(--primary-tint, rgba(26, 107, 106, 0.12));
  color: var(--primary);
  flex-shrink: 0;
}

.more__tile-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.more__tile-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.more__tile-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.more__tile-chev {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
</style>
