// =============================================================================
// AIVIS.ONE Frontend -- Router (Phase F2.2 + F4.1.4 + F4.3 B2 + F4.4 B3
//                              + iter 2.5 batch 9 + iter 2.6 batch 2
//                              + iter 2.6 R22 FE-22-01 + iter 2.6 batch 3
//                              + iter 2.7 Block A2 + B1)
// =============================================================================
//
// Full route map. The frame (AppShell) is the one layout wrapper.
// All view imports are lazy-loaded via () => import().
//
// Structure:
//   /                — redirect to role dashboard or /login (beforeEnter)
//   /login, /register, /loading — public auth routes
//   /verify, /onboarding/*     — onboarding (auth required, no role check)
//   /portfolio/:id             -- document link from an email; redirects into
//                                the reader's own shell (P-106)
//   /investor/*                — AppShell (investor | agent)
//   /agent/*                   — AppShell (agent only, includes investor screens)
//   /company/*                 — AppShell (company only)
//   /staff/*                   — AppShell (staff only)
//   /public/*                  — AppShell (anonymous storefront)
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
//   - ADDED /staff/platform subtree under StaffShell (the Staff Platform
//     tab, R1 §4); its sections are now news / events / projects / settings,
//     and the project detail view nests profile / price / pool / products /
//     roadmap / audit / posts / documents / templates.
//
// Cabinets 1.5, staff role: five tabs (home / users / finance / platform /
//   settings). Users, Finance and Platform are hubs (StaffHubView) whose
//   sections carry the permission each needs from utils/staffRights.ts; the
//   old single-purpose addresses redirect to the section that replaced them.
// =============================================================================

import { createRouter, createWebHistory } from 'vue-router'

import { API_BASE_URL } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { captureReferralFromPath } from '@/composables/useAuth'
import { globalGuard, getRoleDashboard } from './guards'
import { documentLinkTarget } from './documentLink'
import { hubStart, sectionMeta } from './staffHubs'
import { FINANCE_SECTIONS, PLATFORM_SECTIONS, USERS_SECTIONS } from '@/utils/staffRights'

// ---------------------------------------------------------------------------
// Router instance
// ---------------------------------------------------------------------------

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),

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
    // The Telegram Mini App entry: a person whose Telegram id no account holds
    // yet, and a returning person with two-factor on. Public, because no session
    // exists yet; globalGuard holds the person here while the sign-in is
    // unfinished and leads a visit without the store's token to /login.
    {
      path: '/telegram/entry',
      name: 'telegram-entry',
      component: () => import('@/views/auth/TelegramEntryView.vue'),
      meta: { public: true },
    },
    {
      path: '/telegram/second-code',
      name: 'telegram-second-code',
      component: () => import('@/views/auth/TelegramSecondCodeView.vue'),
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
    // There is no profile screen and no role card: the name, phone and country
    // are asked on the identity-verification screen, and a new account is an
    // investor from its first entry. The two old addresses lead to the
    // documents step, the one entry step that is left.
    {
      path: '/onboarding/profile',
      name: 'onboarding-profile',
      redirect: '/onboarding/docs',
    },
    {
      path: '/onboarding/role',
      name: 'onboarding-role',
      redirect: '/onboarding/docs',
    },
    {
      // H10: the KYC gate's destination -- main.ts sends every 402 here,
      // and the gate answers 402 only on the money routes (H21 P-111).
      // skipOnboarding because the screen must load for whoever the
      // gate refused, onboarded or not; bouncing them back into
      // onboarding instead of showing the refusal would be a self-lock.
      path: '/verification',
      name: 'kyc-verification',
      component: () => import('@/views/auth/KYCVerificationView.vue'),
      meta: { skipOnboarding: true },
    },
    {
      path: '/onboarding/docs',
      name: 'onboarding-docs',
      component: () => import('@/views/auth/OnboardingDocsView.vue'),
      meta: { skipOnboarding: true },
    },

    // -----------------------------------------------------------------
    // Document link -- /portfolio/:id (P-106)
    //
    // Where a document email lands. The backend builds the address
    // (document_utils.py::documents_link) without knowing the reader's
    // role, so this route has no shell and no role list: globalGuard
    // still sends an anonymous reader to /login with `?next=`, and once
    // signed in, beforeEnter hands the reader to the position screen of
    // their own shell with the query intact. The query names the
    // document the screen opens -- see router/documentLink.ts.
    // -----------------------------------------------------------------
    {
      path: '/portfolio/:id',
      name: 'document-link',
      component: () => import('@/views/auth/LoadingView.vue'),
      beforeEnter: (to) => {
        const authStore = useAuthStore()
        return documentLinkTarget(authStore.role, to.params.id as string, to.query)
      },
    },

    // -----------------------------------------------------------------
    // Investor shell — investor + agent access
    // -----------------------------------------------------------------
    {
      path: '/investor',
      component: () => import('@/components/layout/AppShell.vue'),
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
          // skipOnboarding (H10): the verification screen, itself
          // skipOnboarding, links here to fund the fee, and without this
          // the onboarding guard would bounce a person who has not
          // finished onboarding back into it before they could top up.
          path: 'balance/deposit',
          name: 'investor-deposit',
          component: () => import('@/views/investor/InvestorDepositView.vue'),
          meta: { skipOnboarding: true },
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
          // "News and events": the common feed of posts and events, reached
          // from the home screen and from the side menu on the web.
          path: 'news',
          name: 'investor-news',
          component: () => import('@/views/investor/InvestorNewsView.vue'),
        },
        {
          // One event in full; reached from the home screen, the events list
          // and a notification about an event.
          path: 'events/:id',
          name: 'investor-event',
          component: () => import('@/views/investor/EventDetailView.vue'),
        },
        {
          // One post in full; reached from the home screen, a roadmap entry
          // linked to a post and a notification about a post.
          path: 'posts/:id',
          name: 'investor-post',
          component: () => import('@/views/investor/PostDetailView.vue'),
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
          // TASK-39 item 3: FAQ framework. Investor + agent share one
          // view, each with its own text (investor.html / agent.html) -- same InvestorFaqView, mirrored below
          // under the agent shell as agent-faq. Reached from the FAQ
          // tile in InvestorMoreView.
          path: 'faq',
          name: 'investor-faq',
          component: () => import('@/views/investor/InvestorFaqView.vue'),
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
    // The acceptance screen of the agent-integrator agreement: a full screen
    // outside every shell. The guard holds an integrator here until the
    // agreement is accepted (router/guards.ts).
    // -----------------------------------------------------------------
    {
      path: '/agent-welcome',
      name: 'agent-welcome',
      component: () => import('@/views/agent/AgentWelcomeView.vue'),
      meta: { roles: ['agent'] },
    },

    // -----------------------------------------------------------------
    // The project account's first screen: the documents its role signs are
    // accepted here before any other project screen opens (router/guards.ts).
    // -----------------------------------------------------------------
    {
      path: '/company-welcome',
      name: 'company-welcome',
      component: () => import('@/views/company/CompanyWelcomeView.vue'),
      meta: { roles: ['company'] },
    },

    // -----------------------------------------------------------------
    // Agent shell — agent only
    // Includes duplicated investor screens (market, portfolio,
    // products, purchase, installment) under AgentShell layout
    // so agent keeps their own tab bar.
    // -----------------------------------------------------------------
    {
      path: '/agent',
      component: () => import('@/components/layout/AppShell.vue'),
      meta: { roles: ['agent'], shell: 'agent' },
      children: [
        {
          path: '',
          redirect: '/agent/dashboard',
        },
        // --- Integrator-specific: the Partners tab and what lies inside it ---
        {
          path: 'partners',
          name: 'agent-partners',
          component: () => import('@/views/agent/AgentPartnersView.vue'),
        },
        {
          path: 'partners/network',
          name: 'agent-referrals',
          component: () => import('@/views/agent/ReferralsView.vue'),
        },
        {
          path: 'partners/commissions',
          name: 'agent-commissions',
          component: () => import('@/views/agent/CommissionsView.vue'),
        },
        {
          path: 'partners/rating',
          name: 'agent-leaderboard',
          component: () => import('@/views/agent/LeaderboardView.vue'),
        },
        {
          path: 'partners/balance',
          name: 'agent-balance',
          component: () => import('@/views/agent/AgentBalanceView.vue'),
        },
        {
          // The top-up screen of the integrator's account; the same screen
          // as the buyer's, in the integrator's shell.
          path: 'partners/balance/deposit',
          name: 'agent-deposit',
          component: () => import('@/views/investor/InvestorDepositView.vue'),
          meta: { skipOnboarding: true },
        },
        {
          path: 'partners/balance/transactions',
          name: 'agent-transactions',
          component: () => import('@/views/investor/TransactionsView.vue'),
        },
        // Paths of the screens that lay outside the five tabs before.
        { path: 'hub', redirect: '/agent/partners' },
        { path: 'referrals', redirect: '/agent/partners/network' },
        { path: 'commissions', redirect: '/agent/partners/commissions' },
        { path: 'leaderboard', redirect: '/agent/partners/rating' },
        { path: 'balance', redirect: '/agent/partners/balance' },
        { path: 'more', redirect: '/agent/settings' },
        // --- Screens shared with the buyer (one view each, integrator shell) ---
        {
          path: 'dashboard',
          name: 'agent-dashboard',
          component: () => import('@/views/investor/InvestorDashboardView.vue'),
        },
        {
          path: 'settings',
          name: 'agent-settings',
          component: () => import('@/views/investor/InvestorSettingsView.vue'),
        },
        {
          path: 'news',
          name: 'agent-news',
          component: () => import('@/views/investor/InvestorNewsView.vue'),
        },
        {
          path: 'events/:id',
          name: 'agent-event',
          component: () => import('@/views/investor/EventDetailView.vue'),
        },
        {
          path: 'posts/:id',
          name: 'agent-post',
          component: () => import('@/views/investor/PostDetailView.vue'),
        },
        {
          path: 'docs',
          name: 'agent-docs',
          component: () => import('@/views/investor/InvestorDocsView.vue'),
        },
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
          // An integrator is a buyer too and holds their own instalment plans.
          path: 'installments',
          name: 'agent-installment-plans',
          component: () => import('@/views/investor/InstallmentPlansView.vue'),
        },
        {
          path: 'installments/:id',
          name: 'agent-installment-plan-detail',
          component: () => import('@/views/investor/InstallmentPlanDetailView.vue'),
        },
        {
          path: 'events',
          name: 'agent-events',
          component: () => import('@/views/investor/InvestorEventsView.vue'),
        },
        {
          path: 'support',
          name: 'agent-support',
          component: () => import('@/views/investor/InvestorSupportView.vue'),
        },
        {
          // Opens agent.html for this route.
          path: 'faq',
          name: 'agent-faq',
          component: () => import('@/views/investor/InvestorFaqView.vue'),
        },
        {
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
      component: () => import('@/components/layout/AppShell.vue'),
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
          // All operations of the project's balance: the buyer's operations
          // screen, in the project's wording.
          path: 'balance/transactions',
          name: 'company-transactions',
          component: () => import('@/views/investor/TransactionsView.vue'),
        },
        {
          path: 'settings',
          name: 'company-settings',
          component: () => import('@/views/company/CompanySettingsView.vue'),
        },
        {
          // The Publications tab: posts, the roadmap and documents, each a
          // screen of its own under it.
          path: 'publications',
          name: 'company-publications',
          component: () => import('@/views/company/CompanyPublicationsView.vue'),
        },
        {
          path: 'publications/roadmap',
          name: 'company-roadmap',
          component: () => import('@/views/company/CompanyRoadmapView.vue'),
        },
        {
          path: 'publications/documents',
          name: 'company-attachments',
          component: () => import('@/views/company/CompanyAttachmentsView.vue'),
        },
        {
          path: 'publications/posts',
          name: 'company-posts',
          component: () => import('@/views/company/CompanyPostsView.vue'),
        },
        { path: 'roadmap', redirect: '/company/publications/roadmap' },
        { path: 'attachments', redirect: '/company/publications/documents' },
        { path: 'posts', redirect: '/company/publications/posts' },
        {
          // The project's legal documents to read (Settings, Documents): the
          // buyer's documents screen, listing the papers of the project role.
          path: 'docs',
          name: 'company-docs',
          component: () => import('@/views/investor/InvestorDocsView.vue'),
        },
        {
          // Phase 6: the bell -- reached from CHeader's notifications
          // icon. Reuses the same investor-owned view as every other
          // shell (see router notes on investor-notifications).
          path: 'notifications',
          name: 'company-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
        {
          // TASK-39 item 4: mirror of investor-support -- same
          // InvestorSupportView, company layout. CompanyShell has no
          // More tab (COMPANY_TABS has 5 fixed slots), so this is
          // reached from a row inside CompanySettingsView, same
          // placement reasoning as the roadmap/posts/attachments/
          // notifications rows above. The backend already served this
          // role with no gap (support/router.py has no role check);
          // this route is what makes it reachable.
          path: 'support',
          name: 'company-support',
          component: () => import('@/views/investor/InvestorSupportView.vue'),
        },
        {
          // TASK-39 item 3: FAQ framework. Company gets its OWN,
          // SEPARATE FAQ from investor/agent (owner ruling) -- its
          // own CompanyFaqView + its own file set under
          // /faq/{lang}/company.html. CompanyShell has no More tab
          // (COMPANY_TABS has 5 fixed slots), so this is reached from
          // a row inside CompanySettingsView, same placement
          // reasoning as the roadmap/posts/attachments/support rows
          // above.
          path: 'faq',
          name: 'company-faq',
          component: () => import('@/views/company/CompanyFaqView.vue'),
        },
        {
          // TASK-39 item 7: company self-service read of its own
          // write history (GET /api/v1/company/audit -- audit/
          // company_router.py). Same placement reasoning as
          // roadmap/posts/attachments/support above -- reached from a
          // row inside CompanySettingsView, not a bottom tab.
          path: 'audit',
          name: 'company-audit',
          component: () => import('@/views/company/CompanyAuditFeedView.vue'),
        },
      ],
    },

    // -----------------------------------------------------------------
    // Staff shell — staff only
    //
    // Five tabs: Home, Users, Finance, Platform, Settings. Users, Finance and
    // Platform are hubs (StaffHubView: a chip row over the section's screen);
    // each section's record carries the right it needs from the same table
    // the tab bar and the chips read (utils/staffRights.ts), and the global
    // guard turns a member without it away before the screen mounts. The
    // old single-purpose addresses (/staff/payments, /staff/withdrawals,
    // /staff/agent-apps, /staff/avatar, /staff/support, /staff/more,
    // /staff/platform/companies) redirect to the section that replaced them.
    // -----------------------------------------------------------------
    {
      path: '/staff',
      component: () => import('@/components/layout/AppShell.vue'),
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
        // -----------------------------------------------------------
        // Users: the people, identity checks (a filter of the list),
        // integrator applications, the avatar, support. Opens on the list.
        // -----------------------------------------------------------
        {
          path: 'users',
          component: () => import('@/views/staff/StaffHubView.vue'),
          meta: { hub: 'users' as const },
          children: [
            {
              path: '',
              name: 'staff-users',
              component: () => import('@/views/staff/StaffUsersView.vue'),
            },
            {
              path: 'agent-apps',
              name: 'staff-agent-apps',
              meta: sectionMeta(USERS_SECTIONS, 'agent-apps'),
              component: () => import('@/views/staff/StaffAgentAppsView.vue'),
            },
            {
              path: 'avatar',
              name: 'staff-avatar',
              meta: sectionMeta(USERS_SECTIONS, 'avatar'),
              component: () => import('@/views/staff/StaffAvatarView.vue'),
            },
            {
              // H40: the list of support tickets -- every operator sees
              // every ticket (StaffSupportView's own header).
              path: 'support',
              name: 'staff-support',
              component: () => import('@/views/staff/StaffSupportView.vue'),
            },
            {
              // H40: one ticket's card, by its comms thread id -- opened
              // from the list and from an operator signal, which carries
              // only the id (utils/notificationTarget.ts). Inside the
              // support section, so its chip stays current.
              path: 'support/:id',
              name: 'staff-support-ticket',
              component: () => import('@/views/staff/StaffSupportTicketView.vue'),
            },
          ],
        },
        // -----------------------------------------------------------
        // Finance: payments (with the queue of top-ups still in their
        // hour), withdrawals, gifts, the money check. Opens on the first
        // section the member may use.
        // -----------------------------------------------------------
        {
          path: 'finance',
          component: () => import('@/views/staff/StaffHubView.vue'),
          meta: { hub: 'finance' as const },
          children: [
            {
              // Opens on the first section the member may use. Decided in
              // beforeEnter, which runs AFTER the global guard has waited for
              // the signed-in user: a `redirect` is resolved before any guard
              // and, on a page reload, would see a member whose rights are not
              // loaded yet.
              path: '',
              component: () => import('@/views/auth/LoadingView.vue'),
              beforeEnter: () => hubStart(FINANCE_SECTIONS),
            },
            {
              path: 'payments',
              name: 'staff-payments',
              meta: sectionMeta(FINANCE_SECTIONS, 'payments'),
              component: () => import('@/views/staff/StaffPaymentsView.vue'),
            },
            {
              path: 'withdrawals',
              name: 'staff-withdrawals',
              meta: sectionMeta(FINANCE_SECTIONS, 'withdrawals'),
              component: () => import('@/views/staff/StaffWithdrawalsView.vue'),
            },
            {
              path: 'purchases',
              name: 'staff-purchases',
              meta: sectionMeta(FINANCE_SECTIONS, 'purchases'),
              component: () => import('@/views/staff/StaffPurchasesView.vue'),
            },
            {
              path: 'gifts',
              name: 'staff-gifts',
              meta: sectionMeta(FINANCE_SECTIONS, 'gifts'),
              component: () => import('@/views/staff/StaffGiftsView.vue'),
            },
            {
              path: 'reconciliation',
              name: 'staff-reconciliation',
              meta: sectionMeta(FINANCE_SECTIONS, 'reconciliation'),
              component: () => import('@/views/staff/StaffReconciliationView.vue'),
            },
          ],
        },
        // -----------------------------------------------------------
        // Platform tab: news, events, projects, the platform's settings.
        //
        // Nested tree: the hub carries the chip row; the detail view under
        // projects/:id is itself a nested surface with its own <router-view>
        // -- one route per section (profile / price / roadmap / posts /
        // documents / templates / products). Deep-linkable, browser back
        // works.
        //
        // All children inherit meta.roles=['staff'] from the StaffShell
        // record above (Vue Router meta merge). "Platform" opens on the
        // first section the member may use (hubStart), not on a fixed one.
        // -----------------------------------------------------------
        {
          path: 'platform',
          component: () => import('@/views/staff/StaffHubView.vue'),
          meta: { hub: 'platform' as const },
          children: [
            {
              // Opens on the first section the member may use (see Finance).
              path: '',
              component: () => import('@/views/auth/LoadingView.vue'),
              beforeEnter: () => hubStart(PLATFORM_SECTIONS),
            },
            {
              path: 'news',
              name: 'staff-platform-news',
              meta: sectionMeta(PLATFORM_SECTIONS, 'news'),
              component: () => import('@/views/staff/platform/StaffNewsView.vue'),
            },
            {
              path: 'events',
              name: 'staff-platform-events',
              meta: sectionMeta(PLATFORM_SECTIONS, 'events'),
              component: () => import('@/views/staff/platform/StaffEventsView.vue'),
            },
            {
              path: 'projects',
              name: 'staff-platform-companies',
              meta: sectionMeta(PLATFORM_SECTIONS, 'projects'),
              component: () => import('@/views/staff/platform/StaffCompaniesListView.vue'),
            },
            {
              // H12: platform-wide settings staff change from the UI
              // rather than from .env. One subsection, one setting so
              // far -- the verification mode.
              //
              // P-88: the permission lives here and nowhere else. The
              // hub's chip row reads it from the same table, so the chip
              // and the lock cannot drift apart.
              path: 'settings',
              name: 'staff-platform-settings',
              meta: sectionMeta(PLATFORM_SECTIONS, 'settings'),
              component: () =>
                import('@/views/staff/platform/StaffVerificationSettingsSection.vue'),
            },
            {
              path: 'projects/:id',
              meta: sectionMeta(PLATFORM_SECTIONS, 'projects'),
              component: () => import('@/views/staff/platform/StaffCompanyDetailView.vue'),
              children: [
                {
                  path: '',
                  redirect: (to) => `/staff/platform/projects/${to.params.id}/profile`,
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
                  // The pool of parts for sale: read, and create it when the
                  // project has none.
                  path: 'pool',
                  name: 'staff-platform-company-pool',
                  component: () => import('@/views/staff/platform/StaffCompanyPoolSection.vue'),
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
                {
                  path: 'products',
                  name: 'staff-platform-company-products',
                  component: () => import('@/views/staff/platform/StaffCompanyProductsSection.vue'),
                },
              ],
            },
          ],
        },
        // Settings: the member's own profile, security, notifications.
        {
          path: 'settings',
          name: 'staff-settings',
          component: () => import('@/views/staff/StaffSettingsView.vue'),
        },
        {
          // The staff member's own legal documents to read (Settings,
          // Documents): the AML policy and the cabinet's papers.
          path: 'docs',
          name: 'staff-docs',
          component: () => import('@/views/investor/InvestorDocsView.vue'),
        },
        {
          // Phase 6: the bell -- reached from CHeader's notifications
          // icon and from the Notifications line of the Settings tab.
          // Reuses the same investor-owned view as every other shell.
          path: 'notifications',
          name: 'staff-notifications',
          component: () => import('@/views/investor/NotificationsInboxView.vue'),
        },
        // The addresses the old layout used, kept so a bookmark or an
        // old link lands on the section that replaced them.
        { path: 'payments', redirect: '/staff/finance/payments' },
        { path: 'withdrawals', redirect: '/staff/finance/withdrawals' },
        { path: 'agent-apps', redirect: '/staff/users/agent-apps' },
        { path: 'avatar', redirect: '/staff/users/avatar' },
        { path: 'support', redirect: '/staff/users/support' },
        { path: 'more', redirect: '/staff/settings' },
        { path: 'platform/companies', redirect: '/staff/platform/projects' },
        {
          path: 'platform/companies/:rest(.*)',
          redirect: (to) => `/staff/platform/projects/${String(to.params.rest ?? '')}`,
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
      component: () => import('@/components/layout/AppShell.vue'),
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
        {
          // A post opened from a company's public roadmap.
          path: 'posts/:id',
          name: 'public-post',
          component: () => import('@/views/investor/PostDetailView.vue'),
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
        // A link taken at the storefront names a project: `?p=<project id>`.
        const project = to.query.p
        if (
          typeof project === 'string' &&
          /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
            project,
          )
        ) {
          next({ path: `/public/companies/${project}` })
          return
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
