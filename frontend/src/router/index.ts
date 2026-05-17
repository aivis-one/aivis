// =============================================================================
// CBSHOME Frontend -- Router (Phase F2.2 + F4.1.4 + F4.3 B2 + F4.4 B3
//                              + iter 2.5 batch 9 + iter 2.6 batch 2
//                              + iter 2.6 R22 FE-22-01)
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
//   /r/:code path now carries a regex constraint matching the same
//   character class as REFERRAL_PATH_RE in useAuth.ts -- letters,
//   digits, underscore, hyphen. Without the constraint, paths like
//   /r/../../foo were matched by the route, calling
//   captureReferralFromPath("../../foo") and writing junk into
//   sessionStorage. The constraint pushes malformed URLs to the
//   catch-all (/404). The two definitions stay in sync conceptually,
//   not via runtime sharing -- vue-router accepts only string regex
//   syntax in path segments and useAuth.ts needs a real RegExp for
//   `exec()` over `window.location.pathname` in cold-reload scans.
// =============================================================================

import { createRouter, createWebHistory } from 'vue-router'

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
      ],
    },

    // -----------------------------------------------------------------
    // Staff shell — staff only
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
          path: 'kyc',
          name: 'staff-kyc',
          component: () => import('@/views/staff/StaffKYCView.vue'),
        },
        {
          path: 'payments',
          name: 'staff-payments',
          component: () => import('@/views/staff/StaffPaymentsView.vue'),
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
          path: 'avatar',
          name: 'staff-avatar',
          component: () => import('@/views/staff/StaffAvatarView.vue'),
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
    // -----------------------------------------------------------------
    {
      path: '/public',
      component: () => import('@/layouts/PublicShell.vue'),
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
    // Without the constraint, `/r/../../foo` matched this route, fed
    // junk to captureReferralFromPath, and stored it in sessionStorage
    // -- harmless at the backend (it max_length-rejects on registration)
    // but visually leaks attribution noise into devtools and into the
    // referral lookup logs.
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
