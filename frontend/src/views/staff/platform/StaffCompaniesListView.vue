<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompaniesListView (iter 2.7 Block B)
// =============================================================================
//
// Lists every company (active / hidden / archived) with a status
// filter chip row, a name search, and pagination. Each row navigates
// to the company detail surface (/staff/platform/companies/:id) whose
// section tabs land in Block C.
//
// Source: api/staff-companies.ts::fetchStaffCompanies (company_manage
// gated server-side). This view is read + navigate only -- no company
// CRUD here; creation / editing live behind the detail sections.
//
// Search is debounced (300ms) so each keystroke doesn't fire a request;
// the timer resets page to 1 on a new term.
// =============================================================================

import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Building2 } from 'lucide-vue-next'
import { CBadge, CLoader, CButton, CEmptyState, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { fetchStaffCompanies } from '@/api/staff-companies'
import type { CompanyResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const router = useRouter()

const items = ref<CompanyResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const statusFilter = ref<'' | 'active' | 'hidden' | 'archived'>('')
const search = ref('')
const loading = ref(true)
const error = ref(false)

// Debounce handle for the search box.
let searchTimer: ReturnType<typeof setTimeout> | null = null

const totalPages = computed(() => Math.ceil(total.value / perPage))

const statusVariant = (s: string) => {
  if (s === 'active') return 'success'
  if (s === 'hidden') return 'warning'
  if (s === 'archived') return 'neutral'
  return 'neutral'
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

async function loadCompanies(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffCompanies({
      status: statusFilter.value || undefined,
      search: search.value.trim() || undefined,
      page: page.value,
      per_page: perPage,
    })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
    showToast(t('common.error'), 'error')
  } finally {
    loading.value = false
  }
}

function setStatusFilter(s: '' | 'active' | 'hidden' | 'archived'): void {
  statusFilter.value = s
  page.value = 1
}

function openCompany(id: string): void {
  void safeNavigate(
    router.push(`/staff/platform/companies/${id}`),
    `[StaffCompaniesListView] to company ${id}`,
  )
}

// Status chip + page changes reload immediately.
watch([statusFilter, page], () => loadCompanies())

// Search debounce: reset to page 1 and reload 300ms after the last
// keystroke. The watch on `page` above won't double-fire because we
// only assign page.value = 1 when it isn't already 1.
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (page.value !== 1) {
      page.value = 1 // triggers the [statusFilter, page] watcher -> reload
    } else {
      void loadCompanies()
    }
  }, 300)
})

onMounted(loadCompanies)
</script>

<template>
  <div class="scl">
    <h2 class="scl__title">{{ t('staff.platform.companies.title') }}</h2>

    <!-- Status filter chips -->
    <div class="scl__filters">
      <button
        class="filter-chip"
        :class="{ active: !statusFilter }"
        @click="setStatusFilter('')"
      >{{ t('staff.platform.companies.filterAll') }}</button>
      <button
        v-for="s in (['active', 'hidden', 'archived'] as const)"
        :key="s"
        class="filter-chip"
        :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >{{ t(`staff.platform.companies.filter.${s}`) }}</button>
    </div>

    <!-- Search -->
    <CInput
      v-model="search"
      :placeholder="t('staff.platform.companies.searchPlaceholder')"
    />

    <!-- Loading -->
    <div v-if="loading" class="scl__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scl__center">
      <CButton variant="secondary" size="sm" @click="loadCompanies">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.companies.empty')">
      <template #icon><Building2 :size="40" /></template>
    </CEmptyState>

    <!-- List -->
    <template v-else>
      <div class="company-list">
        <div
          v-for="c in items"
          :key="c.id"
          class="company-item"
          @click="openCompany(c.id)"
        >
          <div class="company-item__info">
            <div class="company-item__name">{{ c.name }}</div>
            <div class="company-item__detail">
              {{ formatPrice(c.price_per_unit_cents) }} &bull;
              {{ t('staff.platform.companies.supply', { n: c.total_supply }) }}
            </div>
          </div>
          <CBadge :variant="statusVariant(c.status)" :text="c.status" />
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="scl__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">&larr;</CButton>
        <span class="scl__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">&rarr;</CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.scl { padding: var(--space-4); }
.scl__title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-3); }

.scl__filters {
  display: flex; gap: var(--space-2); overflow-x: auto; margin-bottom: var(--space-3); padding-bottom: var(--space-1);
}
.filter-chip {
  padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-page); color: var(--text-secondary); font-size: var(--fs-xs); font-weight: 600;
  cursor: pointer; white-space: nowrap; text-transform: capitalize;
}
.filter-chip.active { background: var(--primary); color: var(--on-primary); border-color: var(--primary); }

.scl__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: var(--center-md); gap: var(--space-4);
}

.company-list { display: flex; flex-direction: column; }
.company-item {
  display: flex; align-items: center; gap: var(--space-3); padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default); cursor: pointer; transition: background 0.15s;
}
.company-item:hover { background: var(--bg-subtle); }
.company-item__info { flex: 1; min-width: 0; }
.company-item__name {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.company-item__detail { font-size: var(--fs-xs); color: var(--text-tertiary); margin-top: var(--space-1); }

.scl__pagination {
  display: flex; align-items: center; justify-content: center;
  gap: var(--space-3); margin-top: var(--space-4);
}
.scl__page { font-size: var(--fs-xs); color: var(--text-secondary); }
</style>
