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
//   Four live tiles: Documents, Notifications, Settings, Support (Ф-2).
//   The agent-application entry was considered and dropped at the time:
//     - Agent application: already lives inside InvestorSettingsView
//       as a dedicated section, so a parallel top-level entry here
//       would split the mental model and make two tap paths for the
//       same action.
//
//   TASK-39 item 5 REVISITS that call. The owner considered giving a
//   plain investor a referral link of their own and ruled against it
//   (option B) -- referral links stay representative-only. Instead:
//   make the EXISTING "become a representative" path easier to find,
//   because today it is buried a few sections down inside Settings
//   with no hint from this hub that it exists. This is a discoverability
//   fix, not the second flow the B6 note above worried about: the new
//   `agentTile` below is a SIGNPOST, not a duplicate action -- it has no
//   submit logic of its own, reads its label from the exact same
//   composable (useAgentApplicationStatus) InvestorSettingsView now
//   also uses, and its click handler just router.pushes to
//   /investor/settings, the same screen, where applyForAgent() (the
//   ONLY call site of submitAgentApplication()) still lives unchanged.
//   Kept out of the static TILES array below because unlike its
//   neighbours it must react to application state -- absent while
//   still loading, and its desc line must never invite a tap to apply
//   while an application is already pending/in cooldown.
//
//   Notifications (Phase 6): originally dropped here with "no route
//   exists yet, module lands in F9.2" -- that module has landed
//   (/investor/notifications, NotificationsInboxView.vue) and the tile
//   is back. It is a SECOND entry point to the same screen the header
//   bell already opens on every shell (CHeader.vue) -- kept for
//   discoverability from the More tab the same way Support and
//   Documents are, not because the bell is hard to find.
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

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Bell,
  ChevronRight,
  CreditCard,
  FileText,
  MessageCircle,
  Settings as SettingsIcon,
  UserPlus,
} from 'lucide-vue-next'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAgentApplicationStatus } from '@/composables/useAgentApplicationStatus'

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
  // TASK-39 item 1: installment plans had ZERO frontend entry point
  // before this -- listMyPlans/getPlanDetail existed unused since
  // F4.2. Portfolio (holdings-adjacent) was considered as the host
  // but a plan is a payment obligation, not a holding, so this tile
  // is the more honest placement; same tile-grid pattern as its
  // neighbours, one-line addition per the TILES comment above.
  {
    id: 'installments',
    labelKey: 'inv.more.installments.title',
    descKey: 'inv.more.installments.desc',
    route: '/investor/installments',
    icon: CreditCard,
  },
  // Ф-2: the comment above TILES promised this would be a one-line
  // addition, not a template rewrite -- it is.
  {
    id: 'support',
    labelKey: 'inv.more.support.title',
    descKey: 'inv.more.support.desc',
    route: '/investor/support',
    icon: MessageCircle,
  },
  // Phase 6: restored -- see the header note above on why it was
  // dropped and why it is back.
  {
    id: 'notifications',
    labelKey: 'inv.more.notifications.title',
    descKey: 'inv.more.notifications.desc',
    route: '/investor/notifications',
    icon: Bell,
  },
] as const

function openTile(tile: Tile): void {
  void safeNavigate(router.push(tile.route), `[InvestorMoreView] to ${tile.route}`)
}

// ---------------------------------------------------------------------------
// Agent programme tile (TASK-39 item 5) -- discoverability signpost only.
// ---------------------------------------------------------------------------
//
// Reads the SAME state machine InvestorSettingsView's "Agent programme"
// section renders from (see useAgentApplicationStatus.ts for the state
// table) so this tile's status line can never disagree with what the user
// sees one tap later. It never submits an application itself -- clicking it
// just navigates to /investor/settings, where the one real submit control
// (applyForAgent -> submitAgentApplication) lives.
const { state: agentState, cooldownDaysLeft, fetch: fetchAgentStatus } = useAgentApplicationStatus()

// descKey per state, deliberately worded so a pending/cooldown investor is
// never invited to "apply" again -- it reads as a status line, not a CTA,
// in those states.
const agentDescKey = computed<string>(() => {
  switch (agentState.value) {
    case 'kyc_required':
      return 'inv.more.agent.desc.kycRequired'
    case 'pending':
      return 'inv.more.agent.desc.pending'
    case 'cooldown':
      return 'inv.more.agent.desc.cooldown'
    case 'can_reapply':
      return 'inv.more.agent.desc.canReapply'
    case 'load_error':
      return 'inv.more.agent.desc.loadError'
    case 'can_apply':
    default:
      return 'inv.more.agent.desc.canApply'
  }
})

// Absent while the underlying fetch is still in flight -- showing a
// placeholder status line for an instant reads worse than the tile simply
// appearing a beat after its neighbours.
const showAgentTile = computed<boolean>(() => agentState.value !== 'loading')

function openAgentTile(): void {
  void safeNavigate(router.push('/investor/settings'), '[InvestorMoreView] to agent programme')
}

onMounted(() => {
  void fetchAgentStatus()
})
</script>

<template>
  <div class="more">
    <!-- Inline page header, no CHeader (shell renders it). -->
    <div class="more__header">
      <h1 class="more__title">
        {{ t('inv.more.title') }}
      </h1>
      <p class="more__subtitle">
        {{ t('inv.more.subtitle') }}
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

      <!-- TASK-39 item 5: discoverability signpost for the existing
           "become a representative" path -- see the header comment
           and openAgentTile() above. Not part of the static TILES
           array because its label reacts to application state. -->
      <button
        v-if="showAgentTile"
        type="button"
        class="more__tile"
        @click="openAgentTile"
      >
        <div class="more__tile-icon">
          <UserPlus :size="24" />
        </div>
        <div class="more__tile-body">
          <div class="more__tile-title">
            {{ t('inv.more.agent.title') }}
          </div>
          <div class="more__tile-desc">
            {{ t(agentDescKey, { days: cooldownDaysLeft }) }}
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

/* Header -- MarketView / TransactionsView pattern */
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

/* Grid auto-grows as tiles are added. minmax(220px, 1fr) keeps each
   tile readable on phones while allowing 2-up layouts on wider
   viewports without a media query ladder. */
.more__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

/* Tile -- button reset + flexbox row (icon / body / chevron). */
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
