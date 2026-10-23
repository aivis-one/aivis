// =============================================================================
// AIVIS.ONE Frontend -- Tab Bar Configurations
// =============================================================================
//
// Each role has its own tab set. AppShell hands it to the one menu (AppNav) of the
// frame; `icon` is the name of an export of components/ui/icons.ts.
//
// The staff tabs: home / users / finance / platform / settings (STAFF_TABS below).
// =============================================================================

import type { Shell } from './helpers'

export interface TabItem {
  id: string
  path: string
  labelKey: string
  icon: string
}

// The tab order is the same for both roles that hold parts: Home, Store,
// Portfolio, then Balance (investor) or Partners (integrator), then Settings.
// There is no "More" tab: what it held lives inside the five.
export const INVESTOR_TABS: TabItem[] = [
  { id: 'home', path: '/investor/dashboard', labelKey: 'tab.home', icon: 'Home' },
  { id: 'market', path: '/investor/companies', labelKey: 'tab.market', icon: 'Store' },
  { id: 'portfolio', path: '/investor/portfolio', labelKey: 'tab.portfolio', icon: 'Briefcase' },
  { id: 'balance', path: '/investor/balance', labelKey: 'tab.balance', icon: 'Wallet' },
  { id: 'settings', path: '/investor/settings', labelKey: 'tab.settings', icon: 'Settings' },
]

// The integrator's five tabs, in the same order rule as the buyer's: Home,
// Storefront, Portfolio, Partners, Settings. There is no "More" tab.
export const AGENT_TABS: TabItem[] = [
  { id: 'home', path: '/agent/dashboard', labelKey: 'tab.home', icon: 'Home' },
  { id: 'market', path: '/agent/companies', labelKey: 'tab.market', icon: 'Store' },
  { id: 'portfolio', path: '/agent/portfolio', labelKey: 'tab.portfolio', icon: 'Briefcase' },
  { id: 'partners', path: '/agent/partners', labelKey: 'tab.partners', icon: 'Users' },
  { id: 'settings', path: '/agent/settings', labelKey: 'tab.settings', icon: 'Settings' },
]

// The project account's five tabs: Home (the balance and the summary), Products,
// Publications (posts, the roadmap, documents), Analytics, Settings. The balance
// stands in the top bar, as in the other cabinets, and opens its own screen.
export const COMPANY_TABS: TabItem[] = [
  { id: 'home', path: '/company/dashboard', labelKey: 'tab.comp.home', icon: 'Home' },
  { id: 'products', path: '/company/products', labelKey: 'tab.comp.products', icon: 'Package' },
  {
    id: 'publications',
    path: '/company/publications',
    labelKey: 'tab.comp.publications',
    icon: 'Newspaper',
  },
  {
    id: 'analytics',
    path: '/company/analytics',
    labelKey: 'tab.comp.analytics',
    icon: 'BarChart3',
  },
  { id: 'settings', path: '/company/settings', labelKey: 'tab.comp.settings', icon: 'Settings' },
]

// The staff member's five tabs: Home (a counter for every queue), Users (the
// people, identity checks, integrator applications, avatar, support), Finance
// (payments with the top-up queue, withdrawals, gifts, the money check),
// Platform (news, events, projects, the platform's settings) and Settings (the
// member's own profile, security, notifications). The Users, Finance and
// Platform tabs open a hub of sections; a tab whose sections the member has no
// right to use is not drawn (utils/staffRights.ts).
export const STAFF_TABS: TabItem[] = [
  { id: 'home', path: '/staff/dashboard', labelKey: 'tab.staff.home', icon: 'Home' },
  { id: 'users', path: '/staff/users', labelKey: 'tab.staff.users', icon: 'Users' },
  { id: 'finance', path: '/staff/finance', labelKey: 'tab.staff.finance', icon: 'Wallet' },
  { id: 'platform', path: '/staff/platform', labelKey: 'tab.staff.platform', icon: 'LayoutGrid' },
  { id: 'settings', path: '/staff/settings', labelKey: 'tab.staff.settings', icon: 'Settings' },
]

// The tabs of a shell, as the frame draws them; none for a route outside the four
// cabinets (the storefront has no menu). The staff list is filtered by the member's
// rights where it is drawn (AppShell).
export function tabsFor(shell: Shell | undefined): TabItem[] | undefined {
  switch (shell) {
    case 'investor':
      return INVESTOR_TABS
    case 'agent':
      return AGENT_TABS
    case 'company':
      return COMPANY_TABS
    case 'staff':
      return STAFF_TABS
    default:
      return undefined
  }
}
