<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorDashboardView (Phase F4.4 B2 + B5-post)
// =============================================================================
//
// Investor home screen. Rendered by InvestorShell at /investor/dashboard
// (the "home" tab). The frame's header (K25) holds the greeting and the line
// under it, set here with `useScreenHeader`; this view is a plain content
// column.
//
// Widgets, in render order:
//
//   1. Greeting -- the time-of-day greeting is the header's title, no data call.
//
//   2. Identity-verification alert (K09), straight under the header while the
//      verification is not passed: "not passed -- verify ($10)", "under
//      review", "rejected -- the reason". It leaves the screen once the
//      verification is approved. Its action opens the verification screen.
//
//   2b. For an integrator only: the integrator card (AgentHomeCard) -- the
//      commission of the month, the rank, the registrations, "Copy link".
//
//   3. A gift waiting for acceptance, when staff granted one: an info alert
//      with an action to the portfolio, where it is accepted.
//
//   4. Portfolio summary -- the brand card (K07): total current value, number
//      of projects, unit count. Its title is the one link, to /investor/portfolio.
//      Source: dashboardStore.
//
//   5. Buyer-account tile (K46) -- the ONE account of the buyer: what is on it,
//      and what is awaiting confirmation. It is spent on parts of AIVIS and comes
//      back only through support. A holder has accruals and payouts and no
//      balance of their own, so no second balance is drawn here.
//
//   6. Quick actions row -- Deposit and Store.
//
//   7. "News and events" -- always shown. The three latest posts (the common
//      feed of the platform and all projects) as rows and the three nearest
//      events, each opening its own screen; the section's "See all" opens the
//      whole feed. The events block hides itself when there are no events.
//
// DATA FLOW.
//   onMounted fires independent probes: dashboardStore.refresh(), the posts,
//   the events, the pending gifts and -- only while verification is not
//   passed -- the verification status for the rejection reason. A failure on
//   one does not hide the others.
//
// EMPTY STATE FOR PORTFOLIO.
//   When the user has no purchases yet (companies_count === 0), the
//   hero card swaps to an inviting "Browse the store" CTA instead of
//   showing "$0.00 / 0 products". This is cheaper to implement than a
//   full empty-state screen and keeps the card at the same vertical
//   size so the rest of the dashboard doesn't jump on first purchase.
//
// B5-post: reactive greeting.
//   The greeting (Morning / Afternoon / Evening) depends on the local
//   clock; a module-private `now` ref bumped by a setInterval keeps a
//   long-open tab current. The interval is cleared on unmount.
// =============================================================================

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ArrowDownToLine,
  ChevronRight,
  FileText,
  Info,
  ShieldAlert,
  Store,
  Wallet,
} from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader, CStatCard } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import EventCard from '@/components/shared/EventCard.vue'
import AgentHomeCard from '@/components/shared/AgentHomeCard.vue'
import { listPosts } from '@/api/posts'
import { listUpcomingEvents } from '@/api/events'
import { getKycStatus } from '@/api/kyc'
import { listPendingGifts } from '@/api/purchases'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'
import type { PostResponse, EventResponse } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()

// An integrator sees the buyer's Home whole, plus their own card.
const isAgent = computed<boolean>(() => authStore.role === 'agent')

// ---------------------------------------------------------------------------
// Identity-verification card
// ---------------------------------------------------------------------------

// The fee is the platform's own constant (the verification screen reads the
// live figure); the card names it in dollars.
type KycCardState = 'not_started' | 'submitted' | 'rejected'

const kycCardState = computed<KycCardState | null>(() => {
  // The raw status, not the narrowed one: a withdrawn approval ('revoked') is
  // a status the narrowed type does not carry, and it reads as not passed.
  const raw = authStore.user?.kyc_status
  if (!raw || raw === 'approved') return null
  if (raw === 'submitted') return 'submitted'
  if (raw === 'rejected') return 'rejected'
  return 'not_started'
})

const rejectionReason = ref('')

async function loadRejectionReason(): Promise<void> {
  if (kycCardState.value !== 'rejected') return
  try {
    const status = await getKycStatus()
    rejectionReason.value = status.rejection_reason ?? ''
  } catch {
    // The card still says "rejected"; only the reason is missing.
    rejectionReason.value = ''
  }
}

// ---------------------------------------------------------------------------
// A gift waiting for acceptance
// ---------------------------------------------------------------------------

const pendingGifts = ref(0)

async function loadGifts(): Promise<void> {
  try {
    pendingGifts.value = (await listPendingGifts()).total
  } catch {
    pendingGifts.value = 0
  }
}

// ---------------------------------------------------------------------------
// Posts widget (local state -- one probe, no reuse, no pagination)
// ---------------------------------------------------------------------------

const POSTS_PREVIEW_LIMIT = 3

const posts = ref<PostResponse[]>([])
const postsLoading = ref(false)
const postsErrored = ref(false)

async function loadPosts(): Promise<void> {
  postsLoading.value = true
  postsErrored.value = false
  try {
    const resp = await listPosts({ per_page: POSTS_PREVIEW_LIMIT })
    posts.value = resp.items
  } catch {
    postsErrored.value = true
  } finally {
    postsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Upcoming-events widget (local state -- one probe, no reuse, no
// pagination). Independent of the posts probe: either can fail or be
// empty without affecting the other. Unlike posts, this widget SELF-
// HIDES when empty (FP-25) -- staff control the content, and an empty
// events list should leave no trace rather than show a placeholder.
// ---------------------------------------------------------------------------

const EVENTS_PREVIEW_LIMIT = 3

const events = ref<EventResponse[]>([])
const eventsLoading = ref(false)
const eventsErrored = ref(false)

// Show the section only while loading, on error, or when there are
// events to render. A settled-empty result removes it from the DOM.
const showEventsSection = computed<boolean>(
  () => eventsLoading.value || eventsErrored.value || events.value.length > 0,
)

async function loadEvents(): Promise<void> {
  eventsLoading.value = true
  eventsErrored.value = false
  try {
    events.value = await listUpcomingEvents(EVENTS_PREVIEW_LIMIT)
  } catch {
    eventsErrored.value = true
  } finally {
    eventsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Greeting -- reactive by the minute so a long-open tab flips morning /
// afternoon / evening as the local clock crosses the boundary.
// ---------------------------------------------------------------------------

const GREETING_TICK_MS = 60_000

const now = ref<number>(Date.now())
let tickHandle: ReturnType<typeof setInterval> | null = null

const greeting = computed<string>(() => {
  // Reading `now.value` ties this computed to the tick below.
  const hour = new Date(now.value).getHours()
  if (hour < 12) return t('inv.dashboard.greetingMorning')
  if (hour < 18) return t('inv.dashboard.greetingAfternoon')
  return t('inv.dashboard.greetingEvening')
})

// The frame's header: the greeting is the title, the screen's name the line under it.
useScreenHeader({
  title: greeting,
  lead: () => t('inv.dashboard.title'),
})

// The alert of the verification card: the system's severity for each state.
const KYC_ALERT = {
  not_started: { look: 'warning', role: 'alert', icon: AlertTriangle },
  submitted: { look: 'info', role: 'status', icon: Info },
  rejected: { look: 'danger', role: 'alert', icon: ShieldAlert },
} as const

// ---------------------------------------------------------------------------
// Portfolio hero -- reads from the dashboard store
// ---------------------------------------------------------------------------

const portfolioEmpty = computed<boolean>(() => {
  const s = dashboardStore.summary
  return s === null || s.companies_count === 0
})

const totalCurrentValue = computed<number>(() => dashboardStore.summary?.current_value_cents ?? 0)

const totalUnits = computed<number>(() => dashboardStore.summary?.total_units ?? 0)

const productsCount = computed<number>(() => dashboardStore.summary?.companies_count ?? 0)

// ---------------------------------------------------------------------------
// Buyer account -- thin getter over the store's convenience property
// ---------------------------------------------------------------------------

const activeConfirmed = computed<number>(() => dashboardStore.activeBalance.confirmed)
const activeFrozen = computed<number>(() => dashboardStore.activeBalance.frozen)
const hasFrozen = computed<boolean>(() => activeFrozen.value > 0)

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

function goBalance(): void {
  void safeNavigate(router.push({ name: 'investor-balance' }), '[InvestorDashboardView] to balance')
}
function goDeposit(): void {
  void safeNavigate(router.push({ name: 'investor-deposit' }), '[InvestorDashboardView] to deposit')
}
function goMarket(): void {
  // The store (the catalogue of projects) is /investor/companies.
  void safeNavigate(
    router.push({ name: 'investor-companies' }),
    '[InvestorDashboardView] to companies list',
  )
}

function openEvent(event: EventResponse): void {
  void safeNavigate(
    router.push({ name: 'investor-event', params: { id: event.id } }),
    '[InvestorDashboardView] to event',
  )
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadPosts())

onMounted(() => {
  // Independent probes -- a failure of one must not hide the others, and a
  // slow summary must not block the news. The store's own loading flag drives
  // the portfolio + account spinners; the rest have local flags.
  void dashboardStore.refresh()
  void loadPosts()
  void loadEvents()
  void loadGifts()
  void loadRejectionReason()

  // Start the greeting tick. 60 s matches the worst-case lag we're
  // willing to carry between a boundary crossing and the UI update.
  tickHandle = setInterval(() => {
    now.value = Date.now()
  }, GREETING_TICK_MS)
})

onBeforeUnmount(() => {
  if (tickHandle !== null) {
    clearInterval(tickHandle)
    tickHandle = null
  }
})
</script>

<template>
  <div class="dash">
    <!-- Identity verification: right under the header until it is passed -->
    <div
      v-if="kycCardState"
      class="ds-alert"
      :class="`ds-alert--${KYC_ALERT[kycCardState].look}`"
      :role="KYC_ALERT[kycCardState].role"
    >
      <span class="ds-alert__icon" aria-hidden="true">
        <component :is="KYC_ALERT[kycCardState].icon" size="sm" />
      </span>
      <div class="ds-alert__content">
        <p class="ds-alert__title">
          {{ t(`inv.dashboard.kyc.${kycCardState}`) }}
        </p>
        <p v-if="kycCardState === 'rejected' && rejectionReason" class="ds-alert__text">
          {{ rejectionReason }}
        </p>
        <div class="ds-alert__actions">
          <RouterLink class="ds-button ds-button--secondary" data-size="sm" to="/verification">
            <span>{{ t('kyc.title') }}</span>
          </RouterLink>
        </div>
      </div>
    </div>

    <!-- The integrator's card: commission of the month, rank, registrations, the link -->
    <AgentHomeCard v-if="isAgent" />

    <!-- A gift waiting for acceptance -->
    <div v-if="pendingGifts > 0" class="ds-alert ds-alert--info" role="status">
      <span class="ds-alert__icon" aria-hidden="true"><Info size="sm" /></span>
      <div class="ds-alert__content">
        <p class="ds-alert__text">
          {{ t('inv.dashboard.gift', { n: pendingGifts }) }}
        </p>
        <div class="ds-alert__actions">
          <RouterLink
            class="ds-button ds-button--secondary"
            data-size="sm"
            :to="{ name: 'investor-portfolio' }"
          >
            <span>{{ t('inv.dashboard.portfolio.title') }}</span>
          </RouterLink>
        </div>
      </div>
    </div>

    <!-- Portfolio summary: the brand card (K07), its title the one link -->
    <article class="ds-card ds-card--brand ds-card--interactive" aria-labelledby="dash-portfolio">
      <header class="ds-card__head">
        <h2 id="dash-portfolio" class="ds-card__title">
          <RouterLink class="ds-card__link" :to="{ name: 'investor-portfolio' }">
            {{ t('inv.dashboard.portfolio.title') }}
          </RouterLink>
        </h2>
        <ChevronRight size="sm" />
      </header>

      <template v-if="portfolioEmpty">
        <p class="ds-card__label">
          {{ t('inv.dashboard.portfolio.empty') }}
        </p>
        <p class="ds-card__delta">
          {{ t('inv.dashboard.portfolio.emptyCta') }}
        </p>
      </template>

      <template v-else>
        <p class="ds-card__figure">
          {{ formatPrice(totalCurrentValue) }}
        </p>
        <div class="dash__portfolio-stats">
          <div>
            <p class="ds-card__label">
              {{ t('inv.dashboard.portfolio.products') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(productsCount, locale) }}
            </p>
          </div>
          <div>
            <p class="ds-card__label">
              {{ t('inv.dashboard.portfolio.units') }}
            </p>
            <p class="ds-card__delta">
              {{ formatNumber(totalUnits, locale) }}
            </p>
          </div>
        </div>
      </template>
    </article>

    <!-- Buyer account: the one account, with its awaiting-confirmation part (K46) -->
    <CStatCard
      :label="t('inv.dashboard.balance.title')"
      :value="formatPrice(activeConfirmed)"
      :sub="
        hasFrozen ? `${t('inv.dashboard.balance.frozen')}: ${formatPrice(activeFrozen)}` : undefined
      "
      @click="goBalance"
    >
      <template #icon>
        <Wallet />
      </template>
    </CStatCard>

    <!-- Quick actions row -->
    <div class="dash__actions">
      <CButton variant="outline" @click="goDeposit">
        <ArrowDownToLine size="sm" />
        <span>{{ t('inv.dashboard.actions.deposit') }}</span>
      </CButton>
      <CButton variant="outline" @click="goMarket">
        <Store size="sm" />
        <span>{{ t('inv.dashboard.actions.market') }}</span>
      </CButton>
    </div>

    <!-- News and events: always shown -->
    <section class="dash__section" aria-labelledby="dash-news">
      <div class="dash__section-head">
        <h2 id="dash-news" class="ds-section-title">
          {{ t('inv.dashboard.news.title') }}
        </h2>
        <RouterLink
          class="ds-button ds-button--ghost"
          data-size="sm"
          :to="{ name: 'investor-news' }"
        >
          <span>{{ t('inv.dashboard.posts.seeAll') }}</span>
          <ChevronRight size="sm" />
        </RouterLink>
      </div>

      <!-- Loading -->
      <CLoader v-if="postsLoading && posts.length === 0 && !postsErrored" centered />

      <!-- Error -->
      <CEmptyState
        v-else-if="postsErrored && posts.length === 0"
        tone="danger"
        :title="t('inv.dashboard.posts.errorTitle')"
      >
        <template #actions>
          <CButton variant="outline" size="sm" inline @click="loadPosts">
            {{ t('inv.dashboard.posts.errorRetry') }}
          </CButton>
        </template>
      </CEmptyState>

      <!-- Empty -->
      <CEmptyState
        v-else-if="!postsLoading && posts.length === 0"
        :title="t('inv.dashboard.posts.empty')"
      />

      <!-- List: each post opens its own screen (K23) -->
      <ul v-else class="ds-rows">
        <li v-for="post in posts" :key="post.id" class="ds-row">
          <!-- The cover as the row's thumbnail (K23 .ds-thumb), else the post icon -->
          <span v-if="post.cover_url" class="ds-thumb">
            <img :src="post.cover_url" alt="" loading="lazy" />
          </span>
          <span v-else class="ds-row__lead"><FileText size="sm" /></span>
          <span class="ds-row__body">
            <RouterLink
              class="ds-row__link"
              :to="{ name: 'investor-post', params: { id: post.id } }"
            >
              <span class="ds-row__title">{{ post.title }}</span>
            </RouterLink>
            <span class="ds-row__meta">
              {{ formatDate(post.published_at ?? post.created_at, locale) }}
            </span>
          </span>
        </li>
      </ul>
    </section>

    <!-- Upcoming events (FP-25: whole section absent when settled-empty) -->
    <section v-if="showEventsSection" class="dash__section" aria-labelledby="dash-events">
      <h2 id="dash-events" class="ds-section-title">
        {{ t('inv.dashboard.events.title') }}
      </h2>

      <!-- Loading -->
      <CLoader v-if="eventsLoading && events.length === 0 && !eventsErrored" centered />

      <!-- Error (does NOT hide -- a failed fetch must not look like
           "no events"; offer a retry instead) -->
      <CEmptyState
        v-else-if="eventsErrored && events.length === 0"
        tone="danger"
        :title="t('inv.dashboard.events.errorTitle')"
      >
        <template #actions>
          <CButton variant="outline" size="sm" inline @click="loadEvents">
            {{ t('inv.dashboard.events.errorRetry') }}
          </CButton>
        </template>
      </CEmptyState>

      <!-- List: each card opens its own event screen -->
      <ul v-else class="dash__events-list">
        <li v-for="event in events" :key="event.id" class="dash__event">
          <EventCard :event="event" variant="compact" @click="openEvent(event)" />
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.dash__portfolio-stats {
  display: flex;
  gap: var(--space-5);
}

/* Quick actions row */
.dash__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

/* A section of the screen: its heading, and "See all" at the end of the row. */
.dash__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.dash__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.dash__events-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a desktop it stretches its contents to fill. Past a point the
   extra room should be whitespace, not wider furniture. The COLUMN COUNT IS
   DELIBERATELY UNCHANGED; only the ceiling is added. Mobile-first, so this is a
   min-width and the phone is untouched. */
@media (min-width: 880px) {
  .dash__actions {
    max-inline-size: calc(2 * var(--tile-max));
  }
}
</style>
