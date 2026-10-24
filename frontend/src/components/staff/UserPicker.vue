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

import { computed, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, X } from '@/components/ui/icons'
import { CAvatar } from '@/components/ui'
import { fetchUsers } from '@/api/admin'
import type { UserListItem } from '@/api/types'
import { tOrRaw } from '@/utils/i18n'

const MIN_QUERY_LENGTH = 2
const SEARCH_DEBOUNCE_MS = 300
const RESULT_LIMIT = 8

const props = withDefaults(
  defineProps<{
    modelValue?: string
    /** Optional role filter passed straight through to fetchUsers (e.g. 'investor'). */
    roleFilter?: string
    /** The field's visible label (K38 names its combobox by a visible label). */
    label?: string
  }>(),
  { modelValue: '' },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  select: [user: UserListItem | null]
}>()

const { t, te } = useI18n()

const uid = useId()
const inputId = `${uid}-input`
const labelId = `${uid}-label`
const listId = `${uid}-list`
const hintId = `${uid}-hint`
function optionId(i: number): string {
  return `${uid}-option-${i}`
}

const query = ref('')
const results = ref<UserListItem[]>([])
const loading = ref(false)
const searched = ref(false)
const selectedUser = ref<UserListItem | null>(null)
// The list is shown while there are results and it has not been dismissed (Escape
// or a choice); typing opens it again. `active` is the option the arrow keys are on.
const dismissed = ref(false)
const active = ref(-1)

const listOpen = computed(() => !dismissed.value && results.value.length > 0)
const noResults = computed(
  () =>
    !loading.value &&
    searched.value &&
    !results.value.length &&
    query.value.trim().length >= MIN_QUERY_LENGTH,
)
const activeId = computed(() =>
  listOpen.value && active.value >= 0 ? optionId(active.value) : undefined,
)
// The polite status: the busy wait, the count of results (when the language file
// has the line) or the empty answer.
const statusText = computed(() => {
  if (loading.value) return t('common.loading')
  if (noResults.value) return t('staff.userPicker.noResults')
  if (listOpen.value && te('staff.userPicker.count')) {
    return t('staff.userPicker.count', { n: results.value.length })
  }
  return ''
})

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
    dismissed.value = false
    active.value = -1
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

// The combobox keys (K38): Down opens and moves on, Up moves back, Home and End go
// to the ends while the list is open, Enter chooses the active option, Escape
// closes the list and, pressed again, empties the text. Focus stays in the input.
function onKeydown(e: KeyboardEvent): void {
  const n = results.value.length
  if (e.key === 'ArrowDown' && n) {
    e.preventDefault()
    dismissed.value = false
    active.value = (active.value + 1) % n
  } else if (e.key === 'ArrowUp' && n) {
    e.preventDefault()
    dismissed.value = false
    active.value = active.value <= 0 ? n - 1 : active.value - 1
  } else if (e.key === 'Home' && listOpen.value) {
    e.preventDefault()
    active.value = 0
  } else if (e.key === 'End' && listOpen.value) {
    e.preventDefault()
    active.value = n - 1
  } else if (e.key === 'Enter' && listOpen.value && active.value >= 0) {
    e.preventDefault()
    const item = results.value[active.value]
    if (item) selectUser(item)
  } else if (e.key === 'Escape') {
    if (listOpen.value) {
      e.preventDefault()
      dismissed.value = true
    } else if (query.value) {
      e.preventDefault()
      query.value = ''
    }
  }
}

function selectUser(user: UserListItem): void {
  selectedUser.value = user
  query.value = ''
  results.value = []
  searched.value = false
  active.value = -1
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
  <div class="ds-field ds-combobox" :aria-busy="loading || undefined">
    <label v-if="label" :id="labelId" class="ds-field__label" :for="inputId">{{ label }}</label>

    <!-- Selected chip (K38: the chosen user with Clear) -->
    <div v-if="selectedUser" class="ds-combobox__chip">
      <span class="ds-combobox__chip-slot">
        <CAvatar :name="fullName(selectedUser)" :size="32" />
        <span class="ds-combobox__text">
          <span class="ds-combobox__name">{{ fullName(selectedUser) }}</span>
          <span class="ds-combobox__detail">
            {{ selectedUser.email ?? '—' }} &bull;
            {{ tOrRaw(t, `staff.roles.${selectedUser.role}`, selectedUser.role) }}
          </span>
        </span>
      </span>
      <button
        type="button"
        class="ds-combobox__clear"
        :aria-label="t('common.clear')"
        @click="clearSelection"
      >
        <X />
      </button>
    </div>

    <!-- Search box (hidden once a user is selected) -->
    <template v-else>
      <div class="ds-combobox__control">
        <Search />
        <input
          :id="inputId"
          v-model="query"
          class="ds-input ds-combobox__input"
          type="text"
          role="combobox"
          autocomplete="off"
          aria-autocomplete="list"
          :aria-expanded="listOpen ? 'true' : 'false'"
          :aria-controls="listId"
          :aria-activedescendant="activeId"
          :aria-describedby="hintId"
          :placeholder="t('staff.userPicker.searchPlaceholder')"
          @keydown="onKeydown"
        />
      </div>

      <ul
        v-if="listOpen"
        :id="listId"
        class="ds-combobox__list"
        role="listbox"
        :aria-labelledby="label ? labelId : undefined"
      >
        <li
          v-for="(item, i) in results"
          :id="optionId(i)"
          :key="item.id"
          class="ds-combobox__option"
          role="option"
          aria-selected="false"
          :data-active="i === active ? 'true' : undefined"
          @mousedown.prevent
          @click="selectUser(item)"
        >
          <CAvatar :name="fullName(item)" :size="32" />
          <span class="ds-combobox__text">
            <span class="ds-combobox__name">{{ fullName(item) }}</span>
            <span class="ds-combobox__detail">
              {{ item.email ?? '—' }} &bull; {{ tOrRaw(t, `staff.roles.${item.role}`, item.role) }}
            </span>
          </span>
        </li>
      </ul>

      <p v-else-if="noResults" class="ds-combobox__empty">
        {{ t('staff.userPicker.noResults') }}
      </p>

      <p class="ds-sr-only ds-combobox__status" role="status">{{ statusText }}</p>
      <p :id="hintId" class="ds-field__hint">
        {{ t('staff.userPicker.hint') }}
      </p>
    </template>
  </div>
</template>
