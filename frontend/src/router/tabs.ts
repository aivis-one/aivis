export interface TabConfig {
  key: string
  icon: string
  labelKey: string
  route: string
}

export const investorTabs: TabConfig[] = [
  { key: 'home', icon: 'home', labelKey: 'nav.home', route: '/investor/dashboard' },
  { key: 'portfolio', icon: 'briefcase', labelKey: 'nav.portfolio', route: '/investor/portfolio' },
  { key: 'balance', icon: 'wallet', labelKey: 'nav.balance', route: '/investor/balance' },
  { key: 'documents', icon: 'file-text', labelKey: 'nav.documents', route: '/investor/documents' },
  { key: 'settings', icon: 'settings', labelKey: 'nav.settings', route: '/investor/settings' },
]

export const agentTabs: TabConfig[] = [
  { key: 'home', icon: 'home', labelKey: 'nav.home', route: '/agent/dashboard' },
  { key: 'hub', icon: 'users', labelKey: 'nav.hub', route: '/agent/hub' },
  { key: 'commissions', icon: 'gem', labelKey: 'nav.commissions', route: '/agent/commissions' },
  { key: 'passive', icon: 'wallet', labelKey: 'nav.passive', route: '/agent/passive' },
  { key: 'settings', icon: 'settings', labelKey: 'nav.settings', route: '/agent/settings' },
]

export const companyTabs: TabConfig[] = [
  { key: 'home', icon: 'home', labelKey: 'nav.home', route: '/company/dashboard' },
  { key: 'products', icon: 'package', labelKey: 'nav.products', route: '/company/products' },
  { key: 'analytics', icon: 'bar-chart', labelKey: 'nav.analytics', route: '/company/analytics' },
  { key: 'settings', icon: 'settings', labelKey: 'nav.settings', route: '/company/settings' },
]

export const staffTabs: TabConfig[] = [
  { key: 'home', icon: 'home', labelKey: 'nav.home', route: '/staff/dashboard' },
  { key: 'users', icon: 'users', labelKey: 'nav.users', route: '/staff/users' },
  { key: 'kyc', icon: 'shield-check', labelKey: 'nav.kyc', route: '/staff/kyc' },
  { key: 'payments', icon: 'credit-card', labelKey: 'nav.payments', route: '/staff/payments' },
  { key: 'more', icon: 'settings', labelKey: 'nav.more', route: '/staff/more' },
]
