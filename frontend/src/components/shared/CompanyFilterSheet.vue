<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- CompanyFilterSheet (Phase F4.1 + F4.1.3 polish)
// =============================================================================
//
// Bottom-sheet dialog for picking a company filter on the storefront.
//
// Flow:
//   - opens: reset search, fetch initial page of companies UNLESS the
//     store already has unfiltered results from a prior open (saves a
//     round trip on repeated open/close cycles)
//   - search input: debounced 250ms -> companiesStore.searchCompanies
//   - pick an item: emit @select with company id (or null for "All")
//                   and close the sheet
//
// At 500+ companies we never ship the whole catalogue; search on the
// backend narrows the set via ILIKE (metachar-escaped in F4.1.1).
//
// F4.1.3 polish:
//   - Skip the on-open refetch when the store already holds an
//     unfiltered page. Trade-off: brand-new companies added during
//     the session won't appear until the user types something or
//     reloads the app. Acceptable -- companies are slow-changing
//     catalogue entries, not notifications.
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, Search } from 'lucide-vue-next'
import { CBottomSheet, CLoader, CEmptyState } from '@/components/ui'
import { useCompaniesStore } from '@/stores/companies'

const props = defineProps<{
  open: boolean
  selectedId: string | null
}>()

const emit = defineEmits<{
  close: []
  select: [companyId: string | null]
}>()

const { t } = useI18n()
const companiesStore = useCompaniesStore()

const localQuery = ref('')

// Debounce handle so rapid typing doesn't flood the API.
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// On open, reset the local query. Only hit the network if the store
// doesn't already have a fresh unfiltered list from a prior open.
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    localQuery.value = ''
    const hasCachedUnfilteredList =
      companiesStore.items.length > 0 && companiesStore.search === ''
    if (!hasCachedUnfilteredList) {
      void companiesStore.searchCompanies('')
    }
  },
)

// Debounced search on typing.
watch(localQuery, (q) => {
  if (debounceTimer !== null) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    void companiesStore.searchCompanies(q)
  }, 250)
})

const items = computed(() => companiesStore.items)
const loading = computed(() => companiesStore.loading)

function choose(companyId: string | null): void {
  emit('select', companyId)
  emit('close')
}
</script>

<template>
  <CBottomSheet
    :open="open"
    :title="t('inv.market.filter.title')"
    @close="emit('close')"
  >
    <div class="filter-sheet">
      <!-- Search input -->
      <label class="filter-sheet__search">
        <Search :size="16" class="filter-sheet__search-icon" />
        <input
          v-model="localQuery"
          type="text"
          :placeholder="t('inv.market.filter.search')"
          class="filter-sheet__input"
        />
      </label>

      <!-- "All companies" (clear filter) always on top -->
      <button
        class="filter-sheet__item"
        :class="{ 'filter-sheet__item--active': selectedId === null }"
        @click="choose(null)"
      >
        <span class="filter-sheet__item-label">
          {{ t('inv.market.filter.all') }}
        </span>
        <Check
          v-if="selectedId === null"
          :size="18"
          class="filter-sheet__check"
        />
      </button>

      <!-- Initial load spinner -->
      <div
        v-if="loading && items.length === 0"
        class="filter-sheet__center"
      >
        <CLoader :size="24" />
      </div>

      <!-- Company list -->
      <button
        v-for="company in items"
        :key="company.id"
        class="filter-sheet__item"
        :class="{ 'filter-sheet__item--active': selectedId === company.id }"
        @click="choose(company.id)"
      >
        <span class="filter-sheet__item-label">{{ company.name }}</span>
        <Check
          v-if="selectedId === company.id"
          :size="18"
          class="filter-sheet__check"
        />
      </button>

      <!-- No results for the current search query -->
      <div
        v-if="!loading && items.length === 0 && localQuery"
        class="filter-sheet__center"
      >
        <CEmptyState :title="t('inv.market.filter.empty')" />
      </div>
    </div>
  </CBottomSheet>
</template>

<style scoped>
.filter-sheet { display: flex; flex-direction: column; gap: 4px; }

.filter-sheet__search {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
}
.filter-sheet__search-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.filter-sheet__input {
  flex: 1;
  border: none; outline: none; background: transparent;
  font-size: 14px; color: var(--text);
  font-family: inherit;
}
.filter-sheet__input::placeholder { color: var(--text-tertiary); }

.filter-sheet__item {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  background: none; border: none; cursor: pointer;
  border-radius: var(--radius-md);
  text-align: start;
  font-family: inherit;
  transition: background 0.15s;
}
.filter-sheet__item:hover { background: var(--bg-subtle); }
.filter-sheet__item--active { background: var(--bg-subtle); }

.filter-sheet__item-label {
  font-size: 14px; color: var(--text);
  flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.filter-sheet__check {
  color: var(--primary);
  flex-shrink: 0;
}

.filter-sheet__center {
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
</style>
