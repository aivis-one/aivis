<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorDashboardView (Phase F4.4 B2 + B5-post)
// =============================================================================
//
// Investor home screen. Rendered by InvestorShell at /investor/dashboard
// (the "home" tab). Shell already paints CHeader + CTabBar, so this
// view is a plain content column -- no embedded CHeader (see
// CompanyListView for the canonical top-level-tab-view pattern).
//
// Widgets, in render order:
//
//   1. Greeting row -- time-of-day greeting, no data call.
//
//   2. Identity-verification card, straight under the greeting while the
//      verification is not passed: "not passed -- verify ($10)", "under
//      review", "rejected -- the reason". It leaves the screen once the
//      verification is approved. A tap opens the verification screen.
//
//   3. A gift waiting for acceptance, when staff granted one: one card to
//      the portfolio, where it is accepted.
//
//   4. Portfolio hero card -- total current value, number of projects, unit
//      count. Tap navigates to /investor/portfolio. Source: dashboardStore.
//
//   5. Buyer-account card -- the ONE account of the buyer: what is on it, and
//      what is awaiting confirmation. It is spent on parts of AIVIS and comes
//      back only through support. A holder has accruals and payouts and no
//      balance of their own, so no second balance is drawn here.
//
//   6. Quick actions row -- Deposit and Store.
//
//   7. "News and events" -- always shown. The three latest posts (the common
//      feed of the platform and all projects) and the three nearest events,
//      each tappable and opening its own screen; the row's header opens the
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
  ArrowDownToLine,
  Briefcase,
  ChevronRight,
  Gift,
  ShieldCheck,
  Store,
  Wallet,
} from 'lucide-vue-next'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import EventCard from '@/components/shared/EventCard.vue'
import { listPosts } from '@/api/posts'
import { listUpcomingEvents } from '@/api/events'
import { getKycStatus } from '@/api/kyc'
import { listPendingGifts } from '@/api/purchases'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate, formatNumber, formatPrice } from '@/utils/format'
import type { PostResponse, EventResponse } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()

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

function goKyc(): void {
  void safeNavigate(router.push('/verification'), '[InvestorDashboardView] to verification')
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

function goPortfolio(): void {
  void safeNavigate(
    router.push({ name: 'investor-portfolio' }),
    '[InvestorDashboardView] to portfolio',
  )
}
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

function goNews(): void {
  void safeNavigate(router.push({ name: 'investor-news' }), '[InvestorDashboardView] to news')
}

function openPost(post: PostResponse): void {
  void safeNavigate(
    router.push({ name: 'investor-post', params: { id: post.id } }),
    '[InvestorDashboardView] to post',
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
    <!-- Greeting -->
    <div class="dash__header">
      <h1 class="dash__title">
        {{ greeting }}
      </h1>
      <p class="dash__subtitle">
        {{ t('inv.dashboard.title') }}
      </p>
    </div>

    <!-- Identity verification: right under the greeting until it is passed -->
    <button
      v-if="kycCardState"
      type="button"
      class="dash__kyc"
      :class="`dash__kyc--${kycCardState}`"
      @click="goKyc"
    >
      <ShieldCheck :size="20" class="dash__kyc-icon" />
      <span class="dash__kyc-body">
        <span class="dash__kyc-title">
          {{ t(`inv.dashboard.kyc.${kycCardState}`) }}
        </span>
        <span v-if="kycCardState === 'rejected' && rejectionReason" class="dash__kyc-sub">
          {{ rejectionReason }}
        </span>
      </span>
      <ChevronRight :size="16" />
    </button>

    <!-- A gift waiting for acceptance -->
    <button v-if="pendingGifts > 0" type="button" class="dash__gift" @click="goPortfolio">
      <Gift :size="20" class="dash__gift-icon" />
      <span class="dash__gift-text">
        {{ t('inv.dashboard.gift', { n: pendingGifts }) }}
      </span>
      <ChevronRight :size="16" />
    </button>

    <!-- Portfolio hero card -->
    <button
      type="button"
      class="dash__portfolio"
      :class="{ 'dash__portfolio--empty': portfolioEmpty }"
      @click="goPortfolio"
    >
      <div class="dash__portfolio-head">
        <span class="dash__portfolio-label">
          <Briefcase :size="16" />
          {{ t('inv.dashboard.portfolio.title') }}
        </span>
        <ChevronRight :size="16" class="dash__portfolio-chev" />
      </div>

      <template v-if="portfolioEmpty">
        <div class="dash__portfolio-empty">
          {{ t('inv.dashboard.portfolio.empty') }}
        </div>
        <div class="dash__portfolio-empty-cta">
          {{ t('inv.dashboard.portfolio.emptyCta') }}
          <ChevronRight :size="16" />
        </div>
      </template>

      <template v-else>
        <div class="dash__portfolio-value">
          {{ formatPrice(totalCurrentValue) }}
        </div>
        <div class="dash__portfolio-stats">
          <div class="dash__portfolio-stat">
            <div class="dash__portfolio-stat-label">
              {{ t('inv.dashboard.portfolio.products') }}
            </div>
            <div class="dash__portfolio-stat-value">
              {{ formatNumber(productsCount, locale) }}
            </div>
          </div>
          <div class="dash__portfolio-stat">
            <div class="dash__portfolio-stat-label">
              {{ t('inv.dashboard.portfolio.units') }}
            </div>
            <div class="dash__portfolio-stat-value">
              {{ formatNumber(totalUnits, locale) }}
            </div>
          </div>
        </div>
      </template>
    </button>

    <!-- Buyer account: the one account, with its awaiting-confirmation part -->
    <button type="button" class="dash__balance" @click="goBalance">
      <div class="dash__balance-head">
        <span class="dash__balance-label">
          <Wallet :size="16" />
          {{ t('inv.dashboard.balance.title') }}
        </span>
        <ChevronRight :size="16" />
      </div>
      <div class="dash__balance-value">
        {{ formatPrice(activeConfirmed) }}
      </div>
      <div v-if="hasFrozen" class="dash__balance-frozen">
        {{ t('inv.dashboard.balance.frozen') }}:
        {{ formatPrice(activeFrozen) }}
      </div>
    </button>

    <!-- Quick actions row -->
    <div class="dash__actions">
      <button type="button" class="dash__action" @click="goDeposit">
        <ArrowDownToLine :size="16" />
        <span>{{ t('inv.dashboard.actions.deposit') }}</span>
      </button>
      <button type="button" class="dash__action" @click="goMarket">
        <Store :size="16" />
        <span>{{ t('inv.dashboard.actions.market') }}</span>
      </button>
    </div>

    <!-- News and events: always shown -->
    <section class="dash__posts">
      <button type="button" class="dash__news-head" @click="goNews">
        <h2 class="dash__posts-title">
          {{ t('inv.dashboard.news.title') }}
        </h2>
        <ChevronRight :size="16" />
      </button>

      <!-- Loading -->
      <div v-if="postsLoading && posts.length === 0 && !postsErrored" class="dash__posts-center">
        <CLoader :size="24" />
      </div>

      <!-- Error -->
      <div v-else-if="postsErrored && posts.length === 0" class="dash__posts-center">
        <CEmptyState :title="t('inv.dashboard.posts.errorTitle')" />
        <CButton variant="outline" size="sm" @click="loadPosts">
          {{ t('inv.dashboard.posts.errorRetry') }}
        </CButton>
      </div>

      <!-- Empty -->
      <div v-else-if="!postsLoading && posts.length === 0" class="dash__posts-center">
        <CEmptyState :title="t('inv.dashboard.posts.empty')" />
      </div>

      <!-- List: each post opens its own screen -->
      <ul v-else class="dash__posts-list">
        <li v-for="post in posts" :key="post.id">
          <button type="button" class="dash__post" @click="openPost(post)">
            <img
              v-if="post.cover_url"
              :src="post.cover_url"
              :alt="post.title"
              class="dash__post-cover"
              loading="lazy"
            />
            <div class="dash__post-body">
              <div class="dash__post-title">
                {{ post.title }}
              </div>
              <div class="dash__post-date">
                {{ formatDate(post.published_at ?? post.created_at, locale) }}
              </div>
            </div>
          </button>
        </li>
      </ul>
    </section>

    <!-- Upcoming events (FP-25: whole section absent when settled-empty) -->
    <section v-if="showEventsSection" class="dash__events">
      <h2 class="dash__events-title">
        {{ t('inv.dashboard.events.title') }}
      </h2>

      <!-- Loading -->
      <div
        v-if="eventsLoading && events.length === 0 && !eventsErrored"
        class="dash__events-center"
      >
        <CLoader :size="24" />
      </div>

      <!-- Error (does NOT hide -- a failed fetch must not look like
           "no events"; offer a retry instead) -->
      <div v-else-if="eventsErrored && events.length === 0" class="dash__events-center">
        <CEmptyState :title="t('inv.dashboard.events.errorTitle')" />
        <CButton variant="outline" size="sm" @click="loadEvents">
          {{ t('inv.dashboard.events.errorRetry') }}
        </CButton>
      </div>

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
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Header */
.dash__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.dash__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.dash__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

/* Portfolio hero */
.dash__portfolio {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: var(--on-primary);
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: transform 0.15s;
}
.dash__portfolio:hover {
  transform: translateY(-1px);
}
.dash__portfolio:active {
  transform: translateY(0);
}

.dash__portfolio-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--fs-sm);
  font-weight: 600;
  opacity: 0.9;
}
.dash__portfolio-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.dash__portfolio-chev {
  opacity: 0.8;
}

.dash__portfolio-value {
  font-size: var(--fs-2xl);
  font-weight: 700;
  line-height: 1.1;
}
.dash__portfolio-stats {
  display: flex;
  gap: var(--space-5);
}
.dash__portfolio-stat-label {
  font-size: var(--fs-xs);
  opacity: 0.8;
  margin-bottom: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.dash__portfolio-stat-value {
  font-size: var(--fs-sm);
  font-weight: 600;
}

/* Empty portfolio -- still in the hero card to avoid layout shift */
.dash__portfolio--empty {
  /* No visual change beyond the empty content below. Class reserved
     for future tweaks (lighter gradient, etc.). */
}
.dash__portfolio-empty {
  font-size: var(--fs-body);
  font-weight: 600;
  opacity: 0.95;
}
.dash__portfolio-empty-cta {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--fs-sm);
  font-weight: 600;
  opacity: 0.9;
}

/* Balance card */
.dash__balance {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-4);
  border-radius: var(--radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: border-color 0.15s;
}
.dash__balance:hover {
  border-color: var(--primary);
}

.dash__balance-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__balance-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.dash__balance-value {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.dash__balance-frozen {
  font-size: var(--fs-xs);
  color: var(--warning);
}

/* Quick actions row */
.dash__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}
.dash__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition:
    border-color 0.15s,
    color 0.15s;
}
.dash__action:hover {
  border-color: var(--primary);
  color: var(--primary);
}

/* Posts */
.dash__posts {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.dash__posts-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0 0;
}
.dash__posts-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-sm);
  padding: var(--space-4) var(--space-2);
}
.dash__posts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.dash__post {
  display: flex;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: inherit;
  font-family: inherit;
  text-align: start;
  cursor: pointer;
  transition: border-color 0.15s;
}
.dash__post:hover {
  border-color: var(--primary);
}

/* The "News and events" header is a button into the whole feed. */
.dash__news-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-primary);
  font-family: inherit;
  cursor: pointer;
}

/* Identity verification card, and the gift card: a full-width row, tappable. */
.dash__kyc,
.dash__gift {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-family: inherit;
  text-align: start;
  cursor: pointer;
}
.dash__kyc--not_started {
  border-color: var(--warning);
  background: var(--warning-subtle);
}
.dash__kyc--submitted {
  border-color: var(--primary);
  background: var(--primary-subtle);
}
.dash__kyc--rejected {
  border-color: var(--danger);
  background: var(--danger-subtle);
}
.dash__kyc-icon,
.dash__gift-icon {
  flex-shrink: 0;
}
.dash__kyc-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}
.dash__kyc-title,
.dash__gift-text {
  flex: 1;
  font-size: var(--fs-sm);
  font-weight: 600;
}
.dash__kyc-sub {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}
.dash__post-cover {
  width: var(--size-4xl);
  height: var(--size-4xl);
  object-fit: cover;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.dash__post-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}
.dash__post-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  /* Two-line clamp so long titles don't blow up the card height. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dash__post-date {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

/* Upcoming events widget */
.dash__events {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.dash__events-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0 0;
}
.dash__events-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-sm);
  padding: var(--space-4) var(--space-2);
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
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 820px) {
  .dash__actions {
    max-width: calc(2 * var(--tile-max));
  }
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.dash__subtitle {
  max-width: var(--maxw-prose);
}
</style>
