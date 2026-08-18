<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorMoreView (Phase F4.4 B6)
// =============================================================================
//
// Top-level "More" tab -- navigation hub for screens that don't warrant
// their own bottom-bar slot. Replaces the F2.2 stub.
//
// SHELL PATTERN.
//   Top-level tab view. InvestorShell already renders CHeader, so this
//   view MUST NOT add one (double-header bug that bit BalanceView in
//   F4.3 B2). Inline page-header block with <h1> + <p>, matching the
//   MarketView / TransactionsView / BalanceView convention.
//
// SCOPE (Q1 = c in chat).
//   Two live tiles today: Documents, Settings. Notifications and the
//   agent-application entry were considered and dropped:
//     - Notifications: no route exists yet, module lands in F9.2.
//     - Agent application: already lives inside InvestorSettingsView
//       as a dedicated section, so a parallel top-level entry here
//       would split the mental model and make two tap paths for the
//       same action.
//   Sign-out is intentionally NOT surfaced here (Q2 = b): it lives in
//   Settings as a rare / deliberate action. Adding it to a tab that
//   can be hit accidentally is the wrong risk trade-off for a finance
//   app.
//
// VISUAL (Q3 = b).
//   Grid of large tappable tiles. Auto-fill / auto-fit with minmax so
//   the layout adapts from phone (1 column) to tablet (2 columns)
//   without an explicit breakpoint ladder -- and more importantly,
//   the grid grows to 3+ tiles without a CSS change. The "blank
//   placeholder" variant was rejected (Q-B6-a): empty "Soon" cards
//   are visual debt.
//
// ACCESSIBILITY.
//   Tiles are <button type="button"> elements, which are keyboard-
//   reachable and screen-reader-labelled by their visible title text.
//   No extra aria-* needed.
//
// SETTINGS REACHABILITY.
//   Before B6, /investor/settings was effectively orphaned -- the
//   tab bar pointed to /investor/more (F2.2 tabs config), but the
//   More screen was a stub with no links. Adding the Settings tile
//   here is what wires the route back into the UI.
// =============================================================================

import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, FileText, Settings as SettingsIcon } from 'lucide-vue-next'
import { safeNavigate } from '@/composables/safeNavigate'

interface Tile {
  id: string
  labelKey: string
  descKey: string
  route: string
  icon: typeof FileText
}

const { t } = useI18n()
const router = useRouter()

// Keeping the tile set as data + a single template v-for so future
// additions (notifications, referrals, support) are one-line changes
// to the array, not template copy-paste.
const TILES: readonly Tile[] = [
  {
    id: 'docs',
    labelKey: 'inv.more.docs.title',
    descKey: 'inv.more.docs.desc',
    route: '/investor/docs',
    icon: FileText,
  },
  {
    id: 'settings',
    labelKey: 'inv.more.settings.title',
    descKey: 'inv.more.settings.desc',
    route: '/investor/settings',
    icon: SettingsIcon,
  },
] as const

function openTile(tile: Tile): void {
  void safeNavigate(router.push(tile.route), `[InvestorMoreView] to ${tile.route}`)
}
</script>

<template>
  <div class="more">
    <!-- Inline page header, no CHeader (shell renders it). -->
    <div class="more__header">
      <h1 class="more__title">{{ t('inv.more.title') }}</h1>
      <p class="more__subtitle">{{ t('inv.more.subtitle') }}</p>
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

/* Header -- MarketView / TransactionsView pattern */
.more__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.more__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.more__subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

/* Grid auto-grows as tiles are added. minmax(220px, 1fr) keeps each
   tile readable on phones while allowing 2-up layouts on wider
   viewports without a media query ladder. */
.more__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

/* Tile -- button reset + flexbox row (icon / body / chevron). */
.more__tile {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-primary);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
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
  color: var(--text-primary);
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
