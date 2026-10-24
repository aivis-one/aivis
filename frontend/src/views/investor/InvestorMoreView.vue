<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorMoreView (Phase F4.4 B6)
// =============================================================================
//
// Top-level "More" tab -- navigation hub for screens that don't warrant
// their own bottom-bar slot. Replaces the F2.2 stub.
//
// SHELL PATTERN.
//   Top-level tab view. The frame's header (K25) holds the title and the
//   line under it, set here with `useScreenHeader`; this view adds no header
//   of its own.
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
//   also uses, and it just links to
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
//   Tiles are links (the system's Nav tile, K34: one anchor each), so they
//   are keyboard-reachable, can be opened in a new tab, and are named by their
//   visible title text. No extra aria-* needed.
//
// SETTINGS REACHABILITY.
//   Before B6, /investor/settings was effectively orphaned -- the
//   tab bar pointed to /investor/more (F2.2 tabs config), but the
//   More screen was a stub with no links. Adding the Settings tile
//   here is what wires the route back into the UI.
// =============================================================================

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Bell,
  ChevronRight,
  CreditCard,
  FileText,
  HelpCircle,
  MessageCircle,
  Settings as SettingsIcon,
  UserPlus,
} from '@/components/ui/icons'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useAgentApplicationStatus } from '@/composables/useAgentApplicationStatus'

interface Tile {
  id: string
  labelKey: string
  descKey: string
  route: string
  icon: typeof FileText
}

const { t } = useI18n()

useScreenHeader({
  title: () => t('inv.more.title'),
  lead: () => t('inv.more.subtitle'),
})

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
  // TASK-39 item 3: FAQ framework -- one-line addition per the TILES
  // comment above. Investor + agent share this FAQ (owner ruling);
  // see InvestorFaqView.vue for the full ruling.
  {
    id: 'faq',
    labelKey: 'inv.more.faq.title',
    descKey: 'inv.more.faq.desc',
    route: '/investor/faq',
    icon: HelpCircle,
  },
] as const

// ---------------------------------------------------------------------------
// Agent programme tile (TASK-39 item 5) -- discoverability signpost only.
// ---------------------------------------------------------------------------
//
// Reads the SAME state machine InvestorSettingsView's "Agent programme"
// section renders from (see useAgentApplicationStatus.ts for the state
// table) so this tile's status line can never disagree with what the user
// sees one tap later. It never submits an application itself -- it
// just links to /investor/settings, where the one real submit control
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

onMounted(() => {
  void fetchAgentStatus()
})
</script>

<template>
  <div class="more">
    <div class="ds-navtiles">
      <RouterLink v-for="tile in TILES" :key="tile.id" :to="tile.route" class="ds-navtile">
        <span class="ds-navtile__icon">
          <component :is="tile.icon" />
        </span>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">
            {{ t(tile.labelKey) }}
          </span>
          <span class="ds-navtile__desc">
            {{ t(tile.descKey) }}
          </span>
        </span>
        <ChevronRight size="sm" class="ds-navtile__go" />
      </RouterLink>

      <!-- TASK-39 item 5: discoverability signpost for the existing
           "become a representative" path -- see the header comment
           above. Not part of the static TILES array because its
           label reacts to application state. -->
      <RouterLink v-if="showAgentTile" to="/investor/settings" class="ds-navtile">
        <span class="ds-navtile__icon">
          <UserPlus />
        </span>
        <span class="ds-navtile__text">
          <span class="ds-navtile__title">
            {{ t('inv.more.agent.title') }}
          </span>
          <span class="ds-navtile__desc">
            {{ t(agentDescKey, { days: cooldownDaysLeft }) }}
          </span>
        </span>
        <ChevronRight size="sm" class="ds-navtile__go" />
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.more {
  display: flex;
  flex-direction: column;
}
</style>
