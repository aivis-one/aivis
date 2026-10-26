<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyDetailView (iter 2.7 Block B1 scaffolding)
// =============================================================================
//
// Detail shell for a single project under the Staff Platform tab.
// The frame's header carries the project's name and the way back to the list
// (the screen header API); the screen draws the sub-navigation across the
// per-project sections (R1 §4.3 + R2 §6):
//
//   profile / price / pool / products / roadmap / audit / posts / documents / templates
//
// Each link maps to a nested child route; the selected section renders in the
// inner <router-view>. A strip that scrolls sideways beats a vertical sidebar
// on a phone (confirmed in iter 2.6c review).
//
// iter 2.7 Block C: the header now fetches the real company via
//   fetchStaffCompany (staff detail endpoint, any status) and shows
//   its name. While the fetch is in flight or on error, the header
//   falls back to the "Company <id8>" placeholder so the tab strip
//   and navigation never block on the name. Per-section content is
//   filled by the section components rendered in <router-view>.
//
// The way back is a link to the projects list (the frame's back control).
// =============================================================================

import { computed, ref, onMounted, watch, provide } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import SubNav from '@/components/layout/SubNav.vue'
import type { SubNavItem } from '@/components/layout/SubNav.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { fetchStaffCompany } from '@/api/staff-companies'
import type { CompanyDetailResponse } from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const { t } = useI18n()
const route = useRoute()

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
const { canDo } = useStaffPermissions()
const canManage = canDo('project_manage')
const canContent = canDo('content_manage')

interface DetailSection {
  id: string
  path: string
  labelKey: string
  /** True when the section is drawn only for a member who may manage projects. */
  needsManage?: boolean
  /** True when the section is drawn only for a member who may manage content. */
  needsContent?: boolean
}

// The project's sections, in order: profile, price (the history of
// revaluations), parts (the pool of parts for sale), products, roadmap, the
// audit of the project's writes (project_manage), posts, documents, templates.
const allSections = computed<readonly DetailSection[]>(() => {
  const id = companyId.value
  const base = `/staff/platform/projects/${id}`
  return [
    { id: 'profile', path: `${base}/profile`, labelKey: 'staff.platform.company.tabs.profile' },
    { id: 'price', path: `${base}/price`, labelKey: 'staff.platform.company.tabs.price' },
    { id: 'pool', path: `${base}/pool`, labelKey: 'staff.platform.company.tabs.pool' },
    {
      id: 'products',
      path: `${base}/products`,
      labelKey: 'staff.platform.company.tabs.products',
    },
    { id: 'roadmap', path: `${base}/roadmap`, labelKey: 'staff.platform.company.tabs.roadmap' },
    {
      id: 'audit',
      path: `${base}/audit`,
      labelKey: 'staff.platform.company.tabs.audit',
      needsManage: true,
    },
    {
      id: 'posts',
      path: `${base}/posts`,
      labelKey: 'staff.platform.company.tabs.posts',
      needsContent: true,
    },
    {
      id: 'documents',
      path: `${base}/documents`,
      labelKey: 'staff.platform.company.tabs.documents',
    },
    {
      id: 'templates',
      path: `${base}/templates`,
      labelKey: 'staff.platform.company.tabs.templates',
    },
  ]
})

// A section the member has no right to is not drawn.
const sections = computed(() =>
  allSections.value.filter(
    (section) =>
      (!section.needsManage || canManage.value) && (!section.needsContent || canContent.value),
  ),
)

const subNavItems = computed<SubNavItem[]>(() =>
  sections.value.map((s) => ({ id: s.id, to: s.path, label: t(s.labelKey) })),
)

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

const headerTitle = computed<string>(() => company.value?.name ?? placeholderTitle.value)

// The frame's header: the project's name (the placeholder while it loads) and the
// back control to the projects list.
useScreenHeader({
  title: () => headerTitle.value,
  back: { name: 'staff-platform-companies' },
})

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

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadCompany())

onMounted(loadCompany)
</script>

<template>
  <div class="scd">
    <!-- The sections across the project (the frame's sub-navigation, K25): links, the
         current one marked by the router. On a phone the strip scrolls sideways. -->
    <SubNav :label="t('staff.platform.company.sectionsLabel')" :items="subNavItems" />

    <!-- Selected section content. -->
    <RouterView />
  </div>
</template>

<style scoped>
.scd {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
  align-content: start;
}
</style>
