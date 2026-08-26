<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- UserPicker (TASK-30 admin-capability gap, item 4)
// =============================================================================
//
// Search-by-email/name user picker with the target's UUID never typed by
// hand. Before this component, the only way for a staffer to find a
// user's id through the product was StaffUsersView's list (which never
// renders `id` in its template) or StaffAvatarView's bare "enter user
// ID" CInput -- neither is a real way to find anyone. Built once, used
// in both places: the W0 assign-company modal (StaffCompaniesListView)
// and StaffAvatarView.
//
// Backed by GET /api/v1/staff/users?search= (admin.ts::fetchUsers),
// itself new -- list_users had no search filter before this gap fix.
//
// v-model carries the selected user's id (string, '' = none). `select`
// additionally emits the full UserListItem so a caller that wants the
// role/email for its own validation (e.g. W0 warning on an already-
// company target) doesn't have to re-fetch it.
//
// Debounced (300ms, matches StaffCompaniesListView's search box) and
// gated at 2+ chars -- a 1-char query against every user's email/name
// is a table scan for a result list nobody can use anyway.

import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, X } from 'lucide-vue-next'
import { CInput, CLoader, CAvatar } from '@/components/ui'
import { fetchUsers } from '@/api/admin'
import type { UserListItem } from '@/api/types'

const MIN_QUERY_LENGTH = 2
const SEARCH_DEBOUNCE_MS = 300
const RESULT_LIMIT = 8

const props = withDefaults(
  defineProps<{
    modelValue?: string
    /** Optional role filter passed straight through to fetchUsers (e.g. 'investor'). */
    roleFilter?: string
  }>(),
  { modelValue: '' },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  select: [user: UserListItem | null]
}>()

const { t } = useI18n()

const query = ref('')
const results = ref<UserListItem[]>([])
const loading = ref(false)
const searched = ref(false)
const selectedUser = ref<UserListItem | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function fullName(item: { first_name?: string | null; last_name?: string | null }): string {
  const parts = [item.first_name, item.last_name].filter(Boolean)
  return parts.length ? parts.join(' ') : '—'
}

async function runSearch(): Promise<void> {
  const needle = query.value.trim()
  if (needle.length < MIN_QUERY_LENGTH) {
    results.value = []
    searched.value = false
    return
  }
  loading.value = true
  try {
    const resp = await fetchUsers({
      search: needle,
      role: props.roleFilter,
      per_page: RESULT_LIMIT,
    })
    results.value = resp.items
  } catch {
    results.value = []
  } finally {
    searched.value = true
    loading.value = false
  }
}

watch(query, () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS)
})

function selectUser(user: UserListItem): void {
  selectedUser.value = user
  query.value = ''
  results.value = []
  searched.value = false
  emit('update:modelValue', user.id)
  emit('select', user)
}

function clearSelection(): void {
  selectedUser.value = null
  emit('update:modelValue', '')
  emit('select', null)
}

// A caller resetting the form (v-model set back to '' externally) drops
// the selected-user chip too -- otherwise the chip would keep showing a
// stale user after e.g. the parent modal reopens for a fresh assign.
watch(
  () => props.modelValue,
  (v) => {
    if (!v) selectedUser.value = null
  },
)
</script>

<template>
  <div class="user-picker">
    <!-- Selected chip -->
    <div v-if="selectedUser" class="user-picker__chip">
      <CAvatar :name="fullName(selectedUser)" :size="32" />
      <div class="user-picker__chip-info">
        <div class="user-picker__chip-name">{{ fullName(selectedUser) }}</div>
        <div class="user-picker__chip-detail">
          {{ selectedUser.email ?? '—' }} &bull; {{ selectedUser.role }}
        </div>
      </div>
      <button
        type="button"
        class="user-picker__chip-clear"
        :aria-label="t('common.clear')"
        @click="clearSelection"
      >
        <X :size="16" />
      </button>
    </div>

    <!-- Search box (hidden once a user is selected) -->
    <template v-else>
      <CInput
        v-model="query"
        :placeholder="t('staff.userPicker.searchPlaceholder')"
        autocomplete="off"
      />

      <div v-if="loading" class="user-picker__center">
        <CLoader :size="20" />
      </div>

      <div v-else-if="results.length" class="user-picker__results">
        <button
          v-for="item in results"
          :key="item.id"
          type="button"
          class="user-picker__result"
          @click="selectUser(item)"
        >
          <CAvatar :name="fullName(item)" :size="32" />
          <div class="user-picker__result-info">
            <div class="user-picker__result-name">{{ fullName(item) }}</div>
            <div class="user-picker__result-detail">
              {{ item.email ?? '—' }} &bull; {{ item.role }}
            </div>
          </div>
        </button>
      </div>

      <p v-else-if="searched && query.trim().length >= MIN_QUERY_LENGTH" class="user-picker__hint">
        {{ t('staff.userPicker.noResults') }}
      </p>

      <p v-else class="user-picker__hint">
        <Search :size="14" />
        {{ t('staff.userPicker.hint') }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.user-picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.user-picker__chip {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
}
.user-picker__chip-info {
  flex: 1;
  min-width: 0;
}
.user-picker__chip-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.user-picker__chip-detail {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.user-picker__chip-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-sm);
  height: var(--size-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.user-picker__chip-clear:hover {
  color: var(--text-primary);
  background: var(--bg-page);
}

.user-picker__center {
  display: flex;
  justify-content: center;
  padding: var(--space-3);
}

.user-picker__results {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.user-picker__result {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: none;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-page);
  cursor: pointer;
  text-align: start;
  font: inherit;
  color: inherit;
}
.user-picker__result:last-child {
  border-bottom: none;
}
.user-picker__result:hover {
  background: var(--bg-subtle);
}
.user-picker__result-info {
  flex: 1;
  min-width: 0;
}
.user-picker__result-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.user-picker__result-detail {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.user-picker__hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0;
  padding: var(--space-1) 0;
}
</style>
