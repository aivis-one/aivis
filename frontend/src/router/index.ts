// =============================================================================
// AIVIS.ONE Frontend -- Router (Phase F2.2 + F4.1.4 + F4.3 B2 + F4.4 B3
//                              + iter 2.5 batch 9 + iter 2.6 batch 2
//                              + iter 2.6 R22 FE-22-01 + iter 2.6 batch 3
//                              + iter 2.7 Block A2 + B1)
// =============================================================================
//
// Full route map. Shell components as layout wrappers.
// All view imports are lazy-loaded via () => import().
//
// Structure:
//   /                — redirect to role dashboard or /login (beforeEnter)
//   /login, /register, /loading — public auth routes
//   /verify, /onboarding/*     — onboarding (auth required, no role check)
//   /investor/*                — InvestorShell (investor | agent)
//   /agent/*                   — AgentShell (agent only, includes investor screens)
//   /company/*                 — CompanyShell (company only)
//   /staff/*                   — StaffShell (staff only)
//   /public/*                  — PublicShell (anonymous storefront)
//   /r/:code                   — referral capture + redirect to /public/companies
//   /404                       — not found
//   /:pathMatch(.*)*           — catch-all → /404
//
// F4.1.4 polish:
//   Each shell wrapper carries `meta.shell` so that shared views
//   (ProductDetailView / PurchaseView / future shared views) can pick
//   role-aware route names via router/helpers.ts without pattern-matching
//   on `route.path`. Vue Router merges meta from parent + child route
//   records, so the tag propagates to all nested views automatically.
//
// F4.3 B2:
//   Added `/investor/balance/deposit` -> `investor-deposit` child route
//   for the crypto deposit screen.
//
// F4.4 B3 (hotfix):
//   Added `portfolio/:id` -> `investor-company-position` and the
//   parallel `agent-company-position` child routes for PortfolioView.
//
// iter 2.5 batch 9:
//   - REMOVED legacy `/investor/market` and `/agent/market` routes.
//     The catalogue moved to /companies (R1 §1.3) and per-company
//     products live in /companies/:id/products (R1 §1.4). The deleted
//     MarketView.vue is no longer importable; dev-only state, no
//     production deep-links to preserve.
//   - ADDED three new investor routes (and the parallel three agent
//     routes that share the same shared views):
//       /companies                  -> investor-companies
//       /companies/:id              -> investor-company-overview
//       /companies/:id/products     -> investor-company-products
//     The :id route entries reuse the `meta.shell` propagation via
//     the parent shell record -- no per-route meta needed.
//
// iter 2.6 batch 2:
//   - ADDED /public/* subtree under PublicShell (R1 §1.6, Block A2):
//       /public/companies                                 -> public-companies
//       /public/companies/:id                             -> public-company-overview
//       /public/companies/:id/attachments/:attId          -> public-attachment-landing
//       /public/products/:id                              -> public-product-detail
//     All children carry `meta.public: true` (via parent shell merge),
//     so globalGuard lets unauthenticated visitors through.
//   - ADDED /r/:code referral capture route (Referral Patch §A7):
//     `beforeEnter` calls captureReferralFromPath() (useAuth.ts) and
//     redirects to /public/companies. No UI component.
//   - globalGuard propagates the requested URL as `?next=` when
//     redirecting an unauthenticated visitor to /login. LoginView
//     reads `next` and `router.replace`s back to it post-auth (§A4).
//
// iter 2.6 R22 FE-22-01:
//   /r/:code path carries a regex constraint matching the same
//   character class as REFERRAL_PATH_RE in useAuth.ts -- letters,
//   digits, underscore, hyphen. Without the constraint, paths like
//   /r/../../foo were matched by the route, calling
//   captureReferralFromPath("../../foo") and writing junk into
//   sessionStorage. The constraint pushes malformed URLs to the
//   catch-all (/404).
//
// iter 2.6 batch 3:
//   - PublicShell moved from `@/layouts/PublicShell.vue` to
//     `@/components/layout/PublicShell.vue`. The other four shells
//     (InvestorShell, AgentShell, CompanyShell, StaffShell) live in
//     components/layout/; PublicShell joining them gives the codebase
//     one consistent answer for where shell components live.
//     `frontend/src/layouts/` is removed.
//
// iter 2.7 Block A2 + B1 (R1 §2-§5 Staff Platform tab):
//   - REMOVED /staff/kyc route. KYC workflow merged into
//     StaffUsersView (chips + detail-modal section). The
//     StaffKYCView.vue file is deleted in the same commit. Direct
//     URL /staff/kyc -> catch-all -> /404; no redirect because no
//     production deep-links to preserve (dev-only state).
//   - ADDED /staff/platform subtree under StaffShell, the Block B
//     scaffolding for the Staff Platform tab (R1 §4):
//       /staff/platform                           -> redirect to /staff/platform/news
//       /staff/platform/news                      -> staff-platform-news
//       /staff/platform/events                    -> staff-platform-events
//       /staff/platform/companies                 -> staff-platform-companies
//       /staff/platform/companies/:id             -> staff-platform-company-detail
//         Nested children rendered via the detail view's own
//         <router-view>, one per company section (R1 §4.3 + R2 §6):
//         profile / price / roadmap / posts / documents / templates.
//     The StaffShell parent record already carries meta.roles =
//     ['staff'], so every nested child inherits the role check
//     through vue-router's meta merge -- no per-route meta needed.
//     All 11 view components are lazy-loaded stubs in this commit
//     (FP-24); real content lands in Blocks B / C / D.
// =============================================================================

import { createRouter, createWebHistory } from 'vue-router'

import { API_BASE_URL } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { captureReferralFromPath } from '@/composables/useAuth'
import { globalGuard, getRoleDashboard } from './guards'

// ---------------------------------------------------------------------------
// Router instance
// ---------------------------------------------------------------------------

export const router = createRouter({
  history: createWebHistory(),

  routes: [
    // -----------------------------------------------------------------
    // Root — redirect to role-based dashboard (or /login if anonymous)
    // -----------------------------------------------------------------
    {
      path: '/',
      name: 'root',
      component: () => import('@/views/auth/LoadingView.vue'),
      beforeEnter: () => {
        const authStore = useAuthStore()
        // getRoleDashboard(null) -> '/login'. Anonymous visitors who
        // hit `/` (e.g. App.vue mount after init with no token) land
        // on the login screen; the LoginView template carries a link
        // to RegisterView and, separately, /public/* is reachable by
        // explicit URL.
        return getRoleDashboard(authStore.role)
      },
    },

    // -----------------------------------------------------------------
    // Public auth routes
    // -----------------------------------------------------------------
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/auth/RegisterView.vue'),
      meta: { public: true },
    },
    {
      path: '/password-reset',
      name: 'password-reset-request',
      component: () => import('@/views/auth/PasswordResetRequestView.vue'),
      meta: { public: true },
    },
    {
      path: '/password-reset/confirm',
      name: 'password-reset-confirm',
      component: () => import('@/views/auth/PasswordResetConfirmView.vue'),
      meta: { public: true },
    },
    {
      path: '/loading',
      name: 'loading',
      component: () => import('@/views/auth/LoadingView.vue'),
      meta: { public: true },
    },

    // -----------------------------------------------------------------
    // Onboarding — auth required, onboarding guard skipped
    // -----------------------------------------------------------------
    {
      path: '/verify',
      name: 'verify',
      component: () => import('@/views/auth/VerifyEmailView.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/onboarding/profile',
      name: 'onboarding-profile',
      component: () => import('@/views/auth/OnboardingProfileView.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/onboarding/role',
      name: 'onboarding-role',
      component: () => import('@/views/auth/OnboardingRoleView.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/onboarding/kyc',
      name: 'onboarding-kyc',
      component: () => import('@/views/auth/OnboardingKYCView.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/onboarding/docs',
      name: 'onboarding-docs',
      component: () => import('@/views/auth/OnboardingDocsView.vue'),
      meta: { skipOnboarding: true },
    },

    // -----------------------------------------------------------------
    // Investor shell — investor + agent access
    // -----------------------------------------------------------------
    {
      path: '/investor',
      component: () => import('@/components/layout/InvestorShell.vue'),
      meta: { roles: ['investor', 'agent'], shell: 'investor' },
      children: [
        {
          path: '',
          redirect: '/investor/dashboard',
        },
        {
          path: 'dashboard',
          name: 'investor-dashboard',
          component: () => import('@/views/investor/InvestorDashboardView.vue'),
        },
        {
          path: 'portfolio',
          name: 'investor-portfolio',
          component: () => import('@/views/investor/PortfolioView.vue'),
        },
        {
          path: 'portfolio/:id',
          name: 'investor-company-position',
          component: () => import('@/views/investor/CompanyPositionView.vue'),
        },
        // iter 2.5 batch 9: companies tree (replaces deleted MarketView).
        // /companies            -> catalogue (R1 §1.3 CompanyListView)
        // /companies/:id        -> overview  (R1 §1.3 CompanyOverviewView)
        // /companies/:id/products -> per-company products (R1 §1.4
        //                          ProductsByCompanyView).
        {
          path: 'companies',
          name: 'investor-companies',
          component: () => import('@/views/investor/CompanyListView.vue'),
        },
        {
          path: 'companies/:id',
          name: 'investor-company-overview',
          component: () => import('@/views/investor/CompanyOverviewView.vue'),
        },
        {
          path: 'companies/:id/products',
          name: 'investor-company-products',
          component: () => import('@/views/investor/ProductsByCompanyView.vue'),
        },
        {
          path: 'products/:id',
          name: 'investor-product-detail',
          component: () => import('@/views/investor/ProductDetailView.vue'),
        },
        {
          path: 'purchase/:id',
          name: 'investor-purchase',
          component: () => import('@/views/investor/PurchaseView.vue'),
        },
        {
          path: 'installment/:id',
          name: 'investor-installment',
          component: () => import('@/views/investor/InstallmentView.vue'),
        },
        {
          // TASK-39 item 1: list of the buyer's ALREADY-CREATED
          // installment plans (GET /installments/me). Distinct from
          // 'investor-installment' above (plan CREATION, path
          // installment/:id where :id is a PRODUCT id) -- plural path
          // segment, no id. Reached from the "Installment plans" tile
          // in InvestorMoreView.
          path: 'installments',
          name: 'investor-installment-plans',
          component: () => import('@/views/investor/InstallmentPlansView.vue'),
        },
        {
          // TASK-39 item 1: single plan + tranche schedule
          // (GET /installments/{plan_id}). :id here is a PLAN id.
          path: 'installments/:id',
          name: 'investor-installment-plan-detail',
          component: () => import('@/views/investor/InstallmentPlanDetailView.vue'),
        },
        {
          path: 'balance',
          name: 'investor-balance',
          component: () => import('@/views/investor/BalanceView.vue'),
        },
        {
          path: 'balance/deposit',
          name: 'investor-deposit',
          component: () => import('@/views/investor/InvestorDepositView.vue'),
        },
        {
          path: 'transactions',
          name: 'investor-transactions',
          component: () => import('@/views/investor/TransactionsView.vue'),
        },
        {
          // iter 2.7b C: events surface (R1 §6.3). Shares
          // InvestorEventsView with the agent shell below.
          path: 'events',
          name: 'investor-events',
          component: () => import('@/views/investor/InvestorEventsView.vue'),
        },
        {
          path: 'docs',
          name: 'investor-docs',
          component: () => import('@/views/investor/InvestorDocsView.vue'),
        },
        {
          path: 'settings',
          name: 'investor-settings',
          component: () => import('@/views/investor/InvestorSettingsView.vue'),
        },
        {
          // Ф-2: reached from the Support tile in InvestorMoreView, same
          // shell/guard as its docs/settings neighbours above.
          path: 'support',
          name: 'investor-support',
          component: () => import('@/views/investor/InvestorSupportView.vue'),
        },
        {
          // Phase 6: the bell -- reached from CHeader's notifications
          // icon (every shell) and from the Notifications tile in
          // InvestorMoreView. Same shell/guard as its neighbours above.
          path: 'notifications',
          name: 'investor-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
        {
          path: 'more',
          name: 'investor-more',
          component: () => import('@/views/investor/InvestorMoreView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Agent shell — agent only
    // Includes duplicated investor screens (market, portfolio,
    // products, purchase, installment) under AgentShell layout
    // so agent keeps their own tab bar.
    // -----------------------------------------------------------------
    {
      path: '/agent',
      component: () => import('@/components/layout/AgentShell.vue'),
      meta: { roles: ['agent'], shell: 'agent' },
      children: [
        {
          path: '',
          redirect: '/agent/dashboard',
        },
        // --- Agent-specific ---
        {
          path: 'dashboard',
          name: 'agent-dashboard',
          component: () => import('@/views/agent/AgentDashboardView.vue'),
        },
        {
          path: 'hub',
          name: 'agent-hub',
          component: () => import('@/views/agent/AgentHubView.vue'),
        },
        {
          path: 'referrals',
          name: 'agent-referrals',
          component: () => import('@/views/agent/ReferralsView.vue'),
        },
        {
          path: 'commissions',
          name: 'agent-commissions',
          component: () => import('@/views/agent/CommissionsView.vue'),
        },
        {
          path: 'leaderboard',
          name: 'agent-leaderboard',
          component: () => import('@/views/agent/LeaderboardView.vue'),
        },
        {
          path: 'balance',
          name: 'agent-balance',
          component: () => import('@/views/agent/AgentBalanceView.vue'),
        },
        {
          path: 'settings',
          name: 'agent-settings',
          component: () => import('@/views/agent/AgentSettingsView.vue'),
        },
        {
          path: 'more',
          name: 'agent-more',
          component: () => import('@/views/agent/AgentMoreView.vue'),
        },
        // --- Investor screens (shared components, agent layout) ---
        {
          path: 'portfolio',
          name: 'agent-portfolio',
          component: () => import('@/views/investor/PortfolioView.vue'),
        },
        {
          path: 'portfolio/:id',
          name: 'agent-company-position',
          component: () => import('@/views/investor/CompanyPositionView.vue'),
        },
        // iter 2.5 batch 9: companies tree under agent shell.
        // Parallel to /investor/companies/* -- same views, agent layout.
        {
          path: 'companies',
          name: 'agent-companies',
          component: () => import('@/views/investor/CompanyListView.vue'),
        },
        {
          path: 'companies/:id',
          name: 'agent-company-overview',
          component: () => import('@/views/investor/CompanyOverviewView.vue'),
        },
        {
          path: 'companies/:id/products',
          name: 'agent-company-products',
          component: () => import('@/views/investor/ProductsByCompanyView.vue'),
        },
        {
          path: 'products/:id',
          name: 'agent-product-detail',
          component: () => import('@/views/investor/ProductDetailView.vue'),
        },
        {
          path: 'purchase/:id',
          name: 'agent-purchase',
          component: () => import('@/views/investor/PurchaseView.vue'),
        },
        {
          path: 'installment/:id',
          name: 'agent-installment',
          component: () => import('@/views/investor/InstallmentView.vue'),
        },
        {
          // TASK-39 item 1: mirror of investor-installment-plans --
          // same InstallmentPlansView, agent layout. An agent is a
          // buyer too (_BUYER_ROLES on the backend) and holds their
          // own installment plans.
          path: 'installments',
          name: 'agent-installment-plans',
          component: () => import('@/views/investor/InstallmentPlansView.vue'),
        },
        {
          // TASK-39 item 1: mirror of investor-installment-plan-detail.
          path: 'installments/:id',
          name: 'agent-installment-plan-detail',
          component: () => import('@/views/investor/InstallmentPlanDetailView.vue'),
        },
        {
          // iter 2.7b C: events mirror -- same InvestorEventsView,
          // agent layout. Parallel to /investor/events. meta.shell
          // ('agent') is inherited from the AgentShell record so the
          // view needs no per-route shell tag.
          path: 'events',
          name: 'agent-events',
          component: () => import('@/views/investor/InvestorEventsView.vue'),
        },
        {
          // Phase 6: the bell mirror -- same NotificationsInboxView,
          // agent layout. Parallel to /investor/notifications.
          path: 'notifications',
          name: 'agent-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Company shell — company only
    // -----------------------------------------------------------------
    {
      path: '/company',
      component: () => import('@/components/layout/CompanyShell.vue'),
      meta: { roles: ['company'], shell: 'company' },
      children: [
        {
          path: '',
          redirect: '/company/dashboard',
        },
        {
          path: 'dashboard',
          name: 'company-dashboard',
          component: () => import('@/views/company/CompanyDashboardView.vue'),
        },
        {
          path: 'products',
          name: 'company-products',
          component: () => import('@/views/company/CompanyProductsView.vue'),
        },
        {
          path: 'products/:id',
          name: 'company-product-edit',
          component: () => import('@/views/company/CompanyProductEditView.vue'),
        },
        {
          path: 'analytics',
          name: 'company-analytics',
          component: () => import('@/views/company/CompanyAnalyticsView.vue'),
        },
        {
          path: 'balance',
          name: 'company-balance',
          component: () => import('@/views/company/CompanyBalanceView.vue'),
        },
        {
          path: 'settings',
          name: 'company-settings',
          component: () => import('@/views/company/CompanySettingsView.vue'),
        },
        {
          // TASK-30 self-service: project-owned roadmap CRUD (§4).
          // Reached from a row inside Settings, not a bottom tab --
          // COMPANY_TABS already has 5 fixed slots. See
          // CompanyRoadmapView.vue's header comment for the full
          // placement rationale.
          path: 'roadmap',
          name: 'company-roadmap',
          component: () => import('@/views/company/CompanyRoadmapView.vue'),
        },
        {
          // TASK-30 self-service: project-owned attachment CRUD (§4).
          // Same placement reasoning as 'roadmap' above -- see
          // CompanyAttachmentsView.vue's header comment.
          path: 'attachments',
          name: 'company-attachments',
          component: () => import('@/views/company/CompanyAttachmentsView.vue'),
        },
        {
          // TASK-30 self-service: project-owned post CRUD (§4, W4).
          // Same placement reasoning as 'roadmap' / 'attachments' above --
          // see CompanyPostsView.vue's header comment.
          path: 'posts',
          name: 'company-posts',
          component: () => import('@/views/company/CompanyPostsView.vue'),
        },
        {
          // Phase 6: the bell -- reached from CHeader's notifications
          // icon. Reuses the same investor-owned view as every other
          // shell (see router notes on investor-notifications).
          path: 'notifications',
          name: 'company-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Staff shell — staff only
    //
    // iter 2.7 Block A2: /staff/kyc route removed (merged into Users);
    // /staff/platform subtree added (R1 §4 Staff Platform tab).
    // -----------------------------------------------------------------
    {
      path: '/staff',
      component: () => import('@/components/layout/StaffShell.vue'),
      meta: { roles: ['staff'], shell: 'staff' },
      children: [
        {
          path: '',
          redirect: '/staff/dashboard',
        },
        {
          path: 'dashboard',
          name: 'staff-dashboard',
          component: () => import('@/views/staff/StaffDashboardView.vue'),
        },
        {
          path: 'users',
          name: 'staff-users',
          component: () => import('@/views/staff/StaffUsersView.vue'),
        },
        {
          path: 'payments',
          name: 'staff-payments',
          component: () => import('@/views/staff/StaffPaymentsView.vue'),
        },
        {
          // Reached from the Tools section of StaffMoreView (not a bottom
          // tab -- STAFF_TABS already has 5 fixed slots, same placement
          // reasoning as agent-apps/support/avatar below).
          path: 'withdrawals',
          name: 'staff-withdrawals',
          component: () => import('@/views/staff/StaffWithdrawalsView.vue'),
        },
        // -----------------------------------------------------------
        // Platform tab (iter 2.7 Block B onwards)
        //
        // Nested tree: PlatformView is a thin wrapper carrying a
        // chip-row for News / Events / Companies and a <router-view>.
        // The detail view under companies/:id is itself a nested
        // surface with its own <router-view> -- one route per
        // section (profile / price / roadmap / posts / documents /
        // templates). Deep-linkable, browser back works.
        //
        // All children inherit meta.roles=['staff'] from the
        // StaffShell record above (Vue Router meta merge).
        // -----------------------------------------------------------
        {
          path: 'platform',
          component: () => import('@/views/staff/platform/PlatformView.vue'),
          children: [
            {
              path: '',
              redirect: '/staff/platform/news',
            },
            {
              path: 'news',
              name: 'staff-platform-news',
              component: () => import('@/views/staff/platform/StaffNewsView.vue'),
            },
            {
              path: 'events',
              name: 'staff-platform-events',
              component: () => import('@/views/staff/platform/StaffEventsView.vue'),
            },
            {
              path: 'companies',
              name: 'staff-platform-companies',
              component: () => import('@/views/staff/platform/StaffCompaniesListView.vue'),
            },
            {
              path: 'companies/:id',
              component: () => import('@/views/staff/platform/StaffCompanyDetailView.vue'),
              children: [
                {
                  path: '',
                  redirect: (to) => `/staff/platform/companies/${to.params.id}/profile`,
                },
                {
                  path: 'profile',
                  name: 'staff-platform-company-profile',
                  component: () => import('@/views/staff/platform/StaffCompanyProfileSection.vue'),
                },
                {
                  path: 'price',
                  name: 'staff-platform-company-price',
                  component: () => import('@/views/staff/platform/StaffCompanyPriceSection.vue'),
                },
                {
                  path: 'roadmap',
                  name: 'staff-platform-company-roadmap',
                  component: () => import('@/views/staff/platform/StaffCompanyRoadmapSection.vue'),
                },
                {
                  // TASK-30 batch 1 W3: read-only admin audit feed of
                  // this project's own writes (record_audit(target_type=
                  // "company")). See StaffCompanyAuditSection.vue's
                  // header comment.
                  path: 'audit',
                  name: 'staff-platform-company-audit',
                  component: () => import('@/views/staff/platform/StaffCompanyAuditSection.vue'),
                },
                {
                  path: 'posts',
                  name: 'staff-platform-company-posts',
                  component: () => import('@/views/staff/platform/StaffCompanyPostsSection.vue'),
                },
                {
                  path: 'documents',
                  name: 'staff-platform-company-documents',
                  component: () =>
                    import('@/views/staff/platform/StaffCompanyDocumentsSection.vue'),
                },
                {
                  path: 'templates',
                  name: 'staff-platform-company-templates',
                  component: () =>
                    import('@/views/staff/platform/StaffCompanyTemplatesSection.vue'),
                },
              ],
            },
          ],
        },
        {
          path: 'more',
          name: 'staff-more',
          component: () => import('@/views/staff/StaffMoreView.vue'),
        },
        {
          path: 'agent-apps',
          name: 'staff-agent-apps',
          component: () => import('@/views/staff/StaffAgentAppsView.vue'),
        },
        {
          // Ф-3: one route, list + conversation panel toggled by local
          // state inside the view -- no child route for a single
          // thread (see StaffSupportView's own header for why).
          path: 'support',
          name: 'staff-support',
          component: () => import('@/views/staff/StaffSupportView.vue'),
        },
        {
          path: 'avatar',
          name: 'staff-avatar',
          component: () => import('@/views/staff/StaffAvatarView.vue'),
        },
        {
          // Phase 6: the bell -- reached from CHeader's notifications
          // icon and from the Notifications entry in StaffMoreView's
          // Tools section. Reuses the same investor-owned view as
          // every other shell.
          path: 'notifications',
          name: 'staff-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Public shell — anonymous storefront (iter 2.6, R1 §1.6)
    //
    // All children inherit `meta.public: true` from the parent shell
    // record (vue-router merges meta) so globalGuard pre-empts the
    // unauthenticated-redirect branch and the visitor reaches the
    // view directly.
    //
    // iter 2.6 batch 3: PublicShell relocated to components/layout/
    // (alongside the four authenticated shells).
    // -----------------------------------------------------------------
    {
      path: '/public',
      component: () => import('@/components/layout/PublicShell.vue'),
      meta: { public: true },
      children: [
        {
          path: '',
          redirect: '/public/companies',
        },
        {
          path: 'companies',
          name: 'public-companies',
          component: () => import('@/views/public/PublicCompanyListView.vue'),
        },
        {
          path: 'companies/:id',
          name: 'public-company-overview',
          component: () => import('@/views/public/PublicCompanyOverviewView.vue'),
        },
        {
          // Per R2 §7.2: deep-link landing for a single attachment.
          // The view fetches the company's public attachment list and
          // finds the entry by attId (no single-attachment endpoint
          // exists on the backend); see iter 2.6 plan §A5.
          path: 'companies/:id/attachments/:attId',
          name: 'public-attachment-landing',
          component: () => import('@/views/public/PublicAttachmentLandingView.vue'),
        },
        {
          path: 'products/:id',
          name: 'public-product-detail',
          component: () => import('@/views/public/PublicProductDetailView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Referral capture link — /r/:code (iter 2.6, Referral Patch §A7)
    //
    // Marketing-friendly short URL. Captures the referral code into
    // sessionStorage (first-wins, FP-13) and redirects to the public
    // storefront. No UI component: beforeEnter fires before any view
    // is mounted.
    //
    // `meta.public: true` keeps globalGuard from kicking an
    // unauthenticated visitor to /login first. An already-authenticated
    // visitor who follows a referral link is harmlessly bounced to
    // /public/companies as well -- the capture call is a no-op due to
    // first-wins, and they can browse the storefront just like an
    // anonymous visitor (the auth wall logic kicks in only at the
    // purchase CTA).
    //
    // R22 FE-22-01: the path segment carries a regex constraint
    // matching [A-Za-z0-9_-]+. The same character class is used by
    // REFERRAL_PATH_RE in useAuth.ts for cold-reload path scans, so
    // both code paths reject the same shape of malformed input.
    //
    // Task 2 Block D: the same beforeEnter also fires the click
    // beacon -- POST /api/v1/public/referral-click (backend Task 1 B,
    // 204 always, per-IP rate limited). Fire-and-forget by contract:
    //   - NOT awaited; next() runs immediately, the redirect never
    //     waits on the network;
    //   - every error is swallowed (the endpoint is a metric, not a
    //     feature -- a failed beacon must not break the visit);
    //   - raw fetch WITHOUT the Authorization header (same no-auth
    //     raw-fetch convention as api/attachments.ts withAuth=false):
    //     the endpoint is public and an authenticated agent clicking
    //     a link must look like any other visitor;
    //   - keepalive lets the request survive an immediate unload on
    //     the off-chance the visitor closes the tab mid-redirect.
    // The beacon deliberately does NOT live in _saveReferralCode()
    // (useAuth.ts): a cold reload on /r/<code> runs both the initAuth
    // path scan AND this beforeEnter -- a beacon in both would double
    // count. clicks = visits to /r/<code>; the ?ref= and Telegram
    // start_param capture sources do not fire clicks by design.
    // -----------------------------------------------------------------
    {
      path: '/r/:code([A-Za-z0-9_-]+)',
      name: 'referral-link',
      meta: { public: true },
      // A component is technically optional for a route that always
      // redirects in beforeEnter, but vue-router warns without one in
      // some configurations. LoadingView is reused as a no-cost stub.
      component: () => import('@/views/auth/LoadingView.vue'),
      beforeEnter: (to, _from, next) => {
        const code = to.params.code
        if (typeof code === 'string' && code.length > 0) {
          captureReferralFromPath(code)

          // Fire-and-forget click beacon -- see the route comment
          // above. No await, no auth header, all errors swallowed.
          void fetch(`${API_BASE_URL}/api/v1/public/referral-click`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
            keepalive: true,
          }).catch(() => {
            // Metric-only endpoint: a lost beacon is acceptable,
            // a broken redirect is not.
          })
        }
        next({ name: 'public-companies' })
      },
    },

    // -----------------------------------------------------------------
    // 404
    // -----------------------------------------------------------------
    {
      path: '/404',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { public: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/404',
    },
  ],
})

// ---------------------------------------------------------------------------
// Register global guard
// ---------------------------------------------------------------------------

router.beforeEach(globalGuard)
