// =============================================================================
// AIVIS.ONE Frontend -- Staff Company Context (iter 2.7 PERF-40-01)
// =============================================================================
//
// Shared provide/inject contract for the staff company detail surface.
// StaffCompanyDetailView loads the company once (for the header) and
// provides this context; the child sections rendered in its
// <router-view> (ProfileSection, PriceSection) inject it instead of
// each firing their own GET /staff/companies/{id}.
//
// Lives in its own module (not inside the .vue) because Vue's
// <script setup> forbids top-level `export` -- an InjectionKey shared
// across components has to come from a plain TS module.
// =============================================================================

import type { Ref, InjectionKey } from 'vue'
import type { CompanyDetailResponse } from '@/api/types'

export interface StaffCompanyContext {
  // The loaded company, or null while loading / on error.
  company: Ref<CompanyDetailResponse | null>
  // True while the detail fetch is in flight.
  loading: Ref<boolean>
  // True if the detail fetch failed (company stays null).
  error: Ref<boolean>
  // Re-run the detail fetch (used by a section's retry button).
  reload: () => Promise<void>
}

export const STAFF_COMPANY_KEY: InjectionKey<StaffCompanyContext> = Symbol('staffCompany')
