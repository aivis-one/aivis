// =============================================================================
// CBSHOME Frontend -- Router (Phase F2.2 + F4.1.4 + F4.3 B2 + F4.4 B3
//                              + iter 2.5 batch 9)
// =============================================================================
//
// Full route map. Shell components as layout wrappers.
// All view imports are lazy-loaded via () => import().
//
// Structure:
//   /                — redirect to role dashboard (beforeEnter)
//   /login, /register, /loading — public auth routes
//   /verify, /onboarding/*     — onboarding (auth required, no role check)
//   /investor/*                — InvestorShell (investor | agent)
//   /agent/*                   — AgentShell (agent only, includes investor screens)
//   /company/*                 — CompanyShell (company only)
//   /staff/*                   — StaffShell (staff only)
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
// =============================================================================

import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { globalGuard, getRoleDashboard } from './guards'

// ---------------------------------------------------------------------------
// Router instance
// ---------------------------------------------------------------------------

export const router = createRouter({
  history: createWebHistory(),

  routes: [
    // -----------------------------------------------------------------
    // Root — redirect to role-based dashboard
    // -----------------------------------------------------------------
    {
      path: '/',
      name: 'root',
      component: () => import('@/views/auth/LoadingView.vue'),
      beforeEnter: () => {
        const authStore = useAuthStore()
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
