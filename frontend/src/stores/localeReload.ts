// =============================================================================
// AIVIS.ONE Frontend -- re-read project data on a locale switch (H38 P-132)
// =============================================================================
//
// The backend answers project data (names, descriptions, roadmap, news,
// picture variants) in the reader's language -- the Accept-Language of the
// request, the current locale. A store that already holds such data holds
// it in the OLD language after a switch; this re-reads each one that has
// something loaded, in place, through its own fetch (epoch-guarded there).
// A store with nothing loaded is left alone: its first load will already
// carry the new language.
//
// Subscribed once, in main.ts, through i18n's onLocaleChange(). Views with a
// fetch of their own use composables/useReloadOnLocale instead.
//
// THE STORES AND WHY:
//   companyProfile    the project's own profile (name, description, pictures)
//   companyDashboard  the project's dashboard (product names)
//   dashboard         the investor's dashboard (project names, logos)
//   companyList       the storefront's project list
//   products          the storefront's product list
//   portfolio         the investor's positions and the open position's detail
// NOT here: attachments (a document carries its own language and the screen
// picks it), notifications (their texts are written once, in English -- out
// of H38), transactions, support, agent, terms (no project texts).
//
// Same import rule as sessionReset.ts: no store imported here imports auth.
// =============================================================================

import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useCompanyListStore } from '@/stores/companyList'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useDashboardStore } from '@/stores/dashboard'
import { usePortfolioStore } from '@/stores/portfolio'
import { useProductsStore } from '@/stores/products'

/** Re-read every project-data store that has something loaded. Never throws. */
export function reloadProjectStores(): void {
  const profile = useCompanyProfileStore()
  if (profile.profile !== null) void profile.refresh()

  const companyDashboard = useCompanyDashboardStore()
  if (companyDashboard.summary !== null) void companyDashboard.refresh()

  const dashboard = useDashboardStore()
  if (dashboard.summary !== null) void dashboard.refresh()

  const companyList = useCompanyListStore()
  if (companyList.items.length > 0) void companyList.fetchFirstPage()

  const products = useProductsStore()
  if (products.items.length > 0) void products.fetchFirstPage()

  const portfolio = usePortfolioStore()
  if (portfolio.positionsLoaded) void portfolio.fetchPortfolio()
  if (portfolio.currentCompanyId !== null) void portfolio.setCompanyId(portfolio.currentCompanyId)
}
