// =============================================================================
// CBSHOME Frontend -- Tab Bar Configurations
// =============================================================================
//
// Each role has its own tab set. Used by CTabBar in shell components.
// Icons are Lucide component names imported in the shell.
//
// iter 2.7 Block A1 (R1 §2):
//   STAFF_TABS restructured -- `kyc` tab removed, `platform` tab added.
//   KYC functionality merged into Users (chips + detail-modal section).
//   New order: dashboard / users / payments / platform / more.
//   Direct URL /staff/kyc -> 404 (catch-all), no redirect (no legacy
//   deep-links to preserve, dev-only state).
// =============================================================================

export interface TabItem {
  id: string
  path: string
  labelKey: string
  icon: string
}

export const INVESTOR_TABS: TabItem[] = [
  { id: 'home', path: '/investor/dashboard', labelKey: 'tab.home', icon: 'Home' },
  { id: 'portfolio', path: '/investor/portfolio', labelKey: 'tab.portfolio', icon: 'Briefcase' },
  { id: 'market', path: '/investor/companies', labelKey: 'tab.market', icon: 'Store' },
  { id: 'balance', path: '/investor/balance', labelKey: 'tab.balance', icon: 'Wallet' },
  { id: 'more', path: '/investor/more', labelKey: 'tab.more', icon: 'Menu' },
]

export const AGENT_TABS: TabItem[] = [
  { id: 'home', path: '/agent/dashboard', labelKey: 'tab.agent.home', icon: 'Home' },
  { id: 'hub', path: '/agent/hub', labelKey: 'tab.agent.hub', icon: 'Link' },
  { id: 'commissions', path: '/agent/commissions', labelKey: 'tab.agent.commissions', icon: 'Coins' },
  { id: 'balance', path: '/agent/balance', labelKey: 'tab.agent.balance', icon: 'Wallet' },
  { id: 'more', path: '/agent/more', labelKey: 'tab.agent.more', icon: 'Menu' },
]

export const COMPANY_TABS: TabItem[] = [
  { id: 'home', path: '/company/dashboard', labelKey: 'tab.comp.home', icon: 'Home' },
  { id: 'products', path: '/company/products', labelKey: 'tab.comp.products', icon: 'Package' },
  { id: 'analytics', path: '/company/analytics', labelKey: 'tab.comp.analytics', icon: 'BarChart3' },
  { id: 'balance', path: '/company/balance', labelKey: 'tab.comp.balance', icon: 'Wallet' },
  { id: 'settings', path: '/company/settings', labelKey: 'tab.comp.settings', icon: 'Settings' },
]

// iter 2.7 Block A1: KYC tab removed (merged into Users), Platform tab added.
// Platform tab leads to /staff/platform which redirects to /staff/platform/news.
// Icon `LayoutGrid` chosen for Platform -- represents multi-section content
// surface (News / Events / Companies). Same Lucide set used elsewhere.
export const STAFF_TABS: TabItem[] = [
  { id: 'home', path: '/staff/dashboard', labelKey: 'tab.staff.home', icon: 'Home' },
  { id: 'users', path: '/staff/users', labelKey: 'tab.staff.users', icon: 'Users' },
  { id: 'payments', path: '/staff/payments', labelKey: 'tab.staff.payments', icon: 'CreditCard' },
  { id: 'platform', path: '/staff/platform', labelKey: 'tab.staff.platform', icon: 'LayoutGrid' },
  { id: 'more', path: '/staff/more', labelKey: 'tab.staff.more', icon: 'Menu' },
]
