<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- InvestorDashboardView (Phase F4.4 B2 + B5-post)
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
//   2. Portfolio hero card -- the primary CTA. Full-width, gradient
//      background from mockups/investor-shell/mockup.html. Shows
//      total current value, number of products, unit count. Tap
//      navigates to /investor/portfolio. Source: dashboardStore.summary.
//
//   3. Balance card -- compact secondary card. Shows active.confirmed
//      with a frozen-hint when active.frozen > 0. Tap navigates to
//      /investor/balance. Source: dashboardStore.activeBalance.
//
//   4. Quick actions row -- two pill buttons: Deposit (/investor/balance/deposit)
//      and Market (/investor/market). Zero async, zero state.
//
//   5. Posts preview -- last 5 published posts via GET /api/v1/posts.
//      Title + date + optional cover. "See all" affordance deferred to
//      F9.2 when the full Posts page lands.
//
// DATA FLOW.
//   onMounted fires two parallel probes: dashboardStore.refresh() and
//   a local listPosts({ per_page: 5 }). Both are independent -- a
//   failure on one does not hide the other. Posts have their own
//   error state with a Retry button; the dashboard store surfaces
//   errors through `dashboardStore.error` which the balance card
//   shows inline (same pattern as BalanceView).
//
// EMPTY STATE FOR PORTFOLIO.
//   When the user has no purchases yet (companies_count === 0), the
//   hero card swaps to an inviting "Browse the market" CTA instead of
//   showing "$0.00 / 0 products". This is cheaper to implement than a
//   full empty-state screen and keeps the card at the same vertical
//   size so the rest of the dashboard doesn't jump on first purchase.
//
// AUTH ASSUMPTIONS.
//   Investor shell is already behind the auth + role guard, so the
//   component can assume an authenticated investor. Backend responds
//   with zeroed summary for a KYC-pending investor -- still safe to
//   render.
//
// B5-post: reactive greeting.
//   The greeting (Morning / Afternoon / Evening) depends on the local
//   clock. Keeping it as a bare `computed` reading `new Date()` meant
//   a tab left open across midnight or the morning->afternoon border
//   would never update without another render-triggering mutation.
//   The fix is a module-private `now` ref bumped by a setInterval.
//   60 s is fine -- greeting boundaries are hourly, and ticking every
//   minute is visually imperceptible cost. The interval is cleared on
//   unmount so the investor shell can rehydrate cleanly after logout
//   / role switch. The choice of 60 s also means the worst-case lag
//   between a boundary crossing and a UI update is 60 s, not 0 -- an
//   acceptable tradeoff against a per-second timer on the home screen.
// =============================================================================

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowDownToLine,
  Briefcase,
  ChevronRight,
  Store,
  Wallet,
} from 'lucide-vue-next'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { listPosts } from '@/api/posts'
import { useDashboardStore } from '@/stores/dashboard'
import { formatNumber, formatPrice } from '@/utils/format'
import type { PostResponse } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()
const dashboardStore = useDashboardStore()

// ---------------------------------------------------------------------------
// Posts widget (local state -- one probe, no reuse, no pagination)
// ---------------------------------------------------------------------------

const POSTS_PREVIEW_LIMIT = 5

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

const totalCurrentValue = computed<number>(
  () => dashboardStore.summary?.current_value_cents ?? 0,
)

const totalUnits = computed<number>(
  () => dashboardStore.summary?.total_units ?? 0,
)

const productsCount = computed<number>(
  () => dashboardStore.summary?.companies_count ?? 0,
)

// ---------------------------------------------------------------------------
// Balance -- thin getter over the store's convenience property
// ---------------------------------------------------------------------------

const activeConfirmed = computed<number>(
  () => dashboardStore.activeBalance.confirmed,
)
const activeFrozen = computed<number>(
  () => dashboardStore.activeBalance.frozen,
)
const hasFrozen = computed<boolean>(() => activeFrozen.value > 0)

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

function goPortfolio(): void {
  router
    .push({ name: 'investor-portfolio' })
    .catch((err: unknown) => {
      // Benign vue-router rejection types stay silent so real
      // issues (unknown route, thrown guard) remain visible.
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error(
        '[InvestorDashboardView] navigation to portfolio failed:',
        err,
      )
    })
}
function goBalance(): void {
  router
    .push({ name: 'investor-balance' })
    .catch((err: unknown) => {
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error(
        '[InvestorDashboardView] navigation to balance failed:',
        err,
      )
    })
}
function goDeposit(): void {
  router
    .push({ name: 'investor-deposit' })
    .catch((err: unknown) => {
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error(
        '[InvestorDashboardView] navigation to deposit failed:',
        err,
      )
    })
}
function goMarket(): void {
  // iter 2.6.x hotfix: route renamed in iter 2.5 batch 9 -- the
  // marketplace catalogue moved to /investor/companies (CompanyListView).
  // Function name kept as `goMarket` to minimise refactor scope.
  router
    .push({ name: 'investor-companies' })
    .catch((err: unknown) => {
      if (
        isNavigationFailure(err, NavigationFailureType.duplicated)
        || isNavigationFailure(err, NavigationFailureType.cancelled)
        || isNavigationFailure(err, NavigationFailureType.aborted)
      ) {
        return
      }
      console.error(
        '[InvestorDashboardView] navigation to companies list failed:',
        err,
      )
    })
}

// ---------------------------------------------------------------------------
// Date formatting -- shared between posts list, matches BalanceView's
// locale-aware pattern without pulling in a dedicated util (one call-
// site, no reason to extract yet).
// ---------------------------------------------------------------------------

function formatPostDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(locale.value, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  // Two independent probes -- posts failure must not hide the
  // dashboard figures, and a slow summary must not block the posts
  // widget. The store's own loading flag drives the portfolio +
  // balance spinners; posts have their own local flags.
  void dashboardStore.refresh()
  void loadPosts()

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
      <h1 class="dash__title">{{ greeting }}</h1>
      <p class="dash__subtitle">{{ t('inv.dashboard.title') }}</p>
    </div>

    <!-- Portfolio hero card -->
    <button
      type="button"
      class="dash__portfolio"
      :class="{ 'dash__portfolio--empty': portfolioEmpty }"
      @click="goPortfolio"
    >
      <div class="dash__portfolio-head">
        <span class="dash__portfolio-label">
          <Briefcase :size="14" />
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
          <ChevronRight :size="14" />
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

    <!-- Balance card -->
    <button type="button" class="dash__balance" @click="goBalance">
      <div class="dash__balance-head">
        <span class="dash__balance-label">
          <Wallet :size="14" />
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
        <ArrowDownToLine :size="18" />
        <span>{{ t('inv.dashboard.actions.deposit') }}</span>
      </button>
      <button type="button" class="dash__action" @click="goMarket">
        <Store :size="18" />
        <span>{{ t('inv.dashboard.actions.market') }}</span>
      </button>
    </div>

    <!-- Posts preview -->
    <section class="dash__posts">
      <h2 class="dash__posts-title">
        {{ t('inv.dashboard.posts.title') }}
      </h2>

      <!-- Loading -->
      <div
        v-if="postsLoading && posts.length === 0 && !postsErrored"
        class="dash__posts-center"
      >
        <CLoader :size="24" />
      </div>

      <!-- Error -->
      <div
        v-else-if="postsErrored && posts.length === 0"
        class="dash__posts-center"
      >
        <CEmptyState
          :title="t('inv.dashboard.posts.errorTitle')"
        />
        <CButton variant="outline" size="sm" @click="loadPosts">
          {{ t('inv.dashboard.posts.errorRetry') }}
        </CButton>
      </div>

      <!-- Empty -->
      <div
        v-else-if="!postsLoading && posts.length === 0"
        class="dash__posts-center"
      >
        <CEmptyState :title="t('inv.dashboard.posts.empty')" />
      </div>

      <!-- List -->
      <ul v-else class="dash__posts-list">
        <li v-for="post in posts" :key="post.id" class="dash__post">
          <img
            v-if="post.cover_url"
            :src="post.cover_url"
            :alt="post.title"
            class="dash__post-cover"
            loading="lazy"
          />
          <div class="dash__post-body">
            <div class="dash__post-title">{{ post.title }}</div>
            <div class="dash__post-date">
              {{ formatPostDate(post.published_at ?? post.created_at) }}
            </div>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.dash {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Header */
.dash__header { display: flex; flex-direction: column; gap: 4px; }
.dash__title {
  font-size: 22px; font-weight: 700;
  color: var(--text); margin: 0;
}
.dash__subtitle {
  font-size: 13px; color: var(--text-secondary); margin: 0;
}

/* Portfolio hero */
.dash__portfolio {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  color: var(--on-primary, #fff);
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: transform 0.15s;
}
.dash__portfolio:hover { transform: translateY(-1px); }
.dash__portfolio:active { transform: translateY(0); }

.dash__portfolio-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  opacity: 0.9;
}
.dash__portfolio-label {
  display: inline-flex; align-items: center; gap: 6px;
}
.dash__portfolio-chev { opacity: 0.8; }

.dash__portfolio-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
}
.dash__portfolio-stats {
  display: flex;
  gap: 24px;
}
.dash__portfolio-stat-label {
  font-size: 11px;
  opacity: 0.8;
  margin-bottom: 2px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.dash__portfolio-stat-value {
  font-size: 15px;
  font-weight: 600;
}

/* Empty portfolio -- still in the hero card to avoid layout shift */
.dash__portfolio--empty {
  /* No visual change beyond the empty content below. Class reserved
     for future tweaks (lighter gradient, etc.). */
}
.dash__portfolio-empty {
  font-size: 16px;
  font-weight: 600;
  opacity: 0.95;
}
.dash__portfolio-empty-cta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  opacity: 0.9;
}

/* Balance card */
.dash__balance {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: var(--radius);
  background: var(--bg-elevated, var(--bg));
  border: 1px solid var(--border);
  color: var(--text);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: border-color 0.15s;
}
.dash__balance:hover { border-color: var(--primary); }

.dash__balance-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}
.dash__balance-label {
  display: inline-flex; align-items: center; gap: 6px;
}
.dash__balance-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
}
.dash__balance-frozen {
  font-size: 12px;
  color: var(--warning, var(--text-secondary));
}

/* Quick actions row */
.dash__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.dash__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.dash__action:hover {
  border-color: var(--primary);
  color: var(--primary);
}

/* Posts */
.dash__posts { display: flex; flex-direction: column; gap: 10px; }
.dash__posts-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin: 4px 0 0;
}
.dash__posts-center {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 10px;
  min-height: 80px;
  padding: 16px 8px;
}
.dash__posts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dash__post {
  display: flex;
  gap: 12px;
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
}
.dash__post-cover {
  width: 56px; height: 56px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.dash__post-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.dash__post-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  /* Two-line clamp so long titles don't blow up the card height. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dash__post-date {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
