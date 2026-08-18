<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyDetailView (iter 2.7 Block B1 scaffolding)
// =============================================================================
//
// Detail shell for a single company under the Staff Platform tab.
// Renders an inline page-header (back-link + company name h1, per
// FP-19 + FP-20) and a horizontal scrollable tab strip for the six
// per-company sections (R1 §4.3 + R2 §6):
//
//   profile / price / roadmap / posts / documents / templates
//
// Each tab maps to a nested child route; selected section renders
// in the inner <router-view>. Mobile-first horizontal-scroll over
// sidebar -- iPhone viewport 380px is too narrow for a vertical
// sidebar, confirmed in iter 2.6c review.
//
// iter 2.7 Block C: the header now fetches the real company via
//   fetchStaffCompany (staff detail endpoint, any status) and shows
//   its name. While the fetch is in flight or on error, the header
//   falls back to the "Company <id8>" placeholder so the tab strip
//   and navigation never block on the name. Per-section content is
//   filled by the section components rendered in <router-view>.
//
// FP-21 goBack. History-aware: prefers router.back() so the
// originating screen (StaffCompaniesListView most commonly) keeps
// scroll state for free; falls back to the companies list when no
// prior history (deep-link).
// =============================================================================

import { computed, ref, onMounted, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { CBackLink } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'
import { fetchStaffCompany } from '@/api/staff-companies'
import type { CompanyDetailResponse } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// The company id from the route params. Read reactively so a
// future ":id" change (unlikely in MVP, but free) re-resolves
// section paths without a remount.
const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// Tab definitions. Each path is the absolute child route under the
// detail view. `name` is the labelKey under staff.platform.company.tabs.
// Order matches the spec sequence in R1 §4.3 + R2 §6.
const sections = computed(() => {
  const id = companyId.value
  return [
    { id: 'profile',   path: `/staff/platform/companies/${id}/profile`,   labelKey: 'staff.platform.company.tabs.profile' },
    { id: 'price',     path: `/staff/platform/companies/${id}/price`,     labelKey: 'staff.platform.company.tabs.price' },
    { id: 'roadmap',   path: `/staff/platform/companies/${id}/roadmap`,   labelKey: 'staff.platform.company.tabs.roadmap' },
    { id: 'posts',     path: `/staff/platform/companies/${id}/posts`,     labelKey: 'staff.platform.company.tabs.posts' },
    { id: 'documents', path: `/staff/platform/companies/${id}/documents`, labelKey: 'staff.platform.company.tabs.documents' },
    { id: 'templates', path: `/staff/platform/companies/${id}/templates`, labelKey: 'staff.platform.company.tabs.templates' },
  ] as const
})

const activeId = computed<string>(() => {
  const match = sections.value.find((s) => route.path.startsWith(s.path))
  return match?.id ?? 'profile'
})

function goSection(path: string): void {
  if (route.path === path) return
  void safeNavigate(router.push(path), `[StaffCompanyDetailView] to ${path}`)
}

// FP-21 history-aware back: prefer router.back() so the originating
// list (with its scroll/filter state) restores for free; fall back
// to an explicit push only on deep-link entry.
function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: 'staff-platform-companies' }),
    '[StaffCompanyDetailView] back fallback to companies list',
  )
}

// Company name fetch (iter 2.7 Block C). The detail endpoint returns
// any-status companies, so a hidden / archived company still resolves
// its name here. We keep the id-based placeholder as the fallback for
// the in-flight and error states -- the header must never block the
// tab strip or back navigation on a slow / failed name lookup.
const company = ref<CompanyDetailResponse | null>(null)
const companyLoading = ref(true)
const companyError = ref(false)

const placeholderTitle = computed<string>(() => {
  const id = companyId.value
  return id
    ? `${t('staff.platform.company.headerPrefix')} ${id.slice(0, 8)}`
    : t('staff.platform.company.headerPrefix')
})

const headerTitle = computed<string>(() =>
  company.value?.name ?? placeholderTitle.value,
)

async function loadCompany(): Promise<void> {
  const id = companyId.value
  if (!id) return
  companyLoading.value = true
  companyError.value = false
  try {
    company.value = await fetchStaffCompany(id)
  } catch {
    // Leave company null -- headerTitle falls back to the placeholder.
    // The header staying on the id placeholder is a benign degraded
    // state; injected sections surface the error / retry through
    // companyError.
    company.value = null
    companyError.value = true
  } finally {
    companyLoading.value = false
  }
}

// PERF-40-01: expose the loaded company (+ load state + reload) to
// the child sections rendered in <router-view>. ProfileSection and
// PriceSection consume this instead of issuing duplicate detail GETs.
provide(STAFF_COMPANY_KEY, {
  company,
  loading: companyLoading,
  error: companyError,
  reload: loadCompany,
})

// Re-fetch if the route id changes (rare, but keeps the header honest).
watch(companyId, () => {
  company.value = null
  companyError.value = false
  companyLoading.value = true
  void loadCompany()
})

onMounted(loadCompany)
</script>

<template>
  <div class="scd">
    <!-- Inline page-header: back-link + company name h1.
         FP-19 (single CHeader; StaffShell owns the only one).
         FP-20 (CBackLink shared component).
         FP-21 (goBack history-aware with deep-link fallback). -->
    <div class="scd__page-header">
      <CBackLink
        :label="t('staff.platform.company.backLink')"
        @click="goBack"
      />
      <h1 class="scd__page-title">{{ headerTitle }}</h1>
    </div>

    <!-- Horizontal scrollable tab strip across the 6 sections. -->
    <nav class="scd__tabs" aria-label="Company sections">
      <button
        v-for="s in sections"
        :key="s.id"
        type="button"
        class="scd__tab"
        :class="{ 'scd__tab--active': activeId === s.id }"
        @click="goSection(s.path)"
      >
        {{ t(s.labelKey) }}
      </button>
    </nav>

    <!-- Selected section content. -->
    <div class="scd__content">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.scd {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* Inline page-header block (iter 2.7 batch B2 pattern):
   padding owns spacing, CBackLink and h1 stack vertically. */
.scd__page-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--space-4, 16px);
}
.scd__page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.3;
}

/* Horizontal scrollable tab strip. Mobile-first: at 380px iPhone
   viewport six labels won't fit; user swipes horizontally. */
.scd__tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 0 var(--space-4, 16px) 12px;
  border-bottom: 1px solid var(--border-default);
  position: sticky;
  top: 0;
  z-index: 9;
  background: var(--bg-page);
}
.scd__tabs::-webkit-scrollbar { display: none; }
.scd__tabs { scrollbar-width: none; }

.scd__tab {
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.scd__tab:hover {
  background: var(--bg-subtle);
}
.scd__tab--active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.scd__content {
  flex: 1;
}
</style>
