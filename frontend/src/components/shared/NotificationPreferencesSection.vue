<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- NotificationPreferencesSection (TASK-38 item 4)
// =============================================================================
//
// Shared across InvestorSettingsView / AgentSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// EmailChangeSection.vue / ActiveSessionsSection.vue / DeactivateAccountSection.vue.
// Backend: notifications/router.py + service.py's preferences pair,
// a thin proxy over comms (D:/02_Projects/comms/app/api/prefs.py).
//
// i18n: every string is read from `${props.tPrefix}.notifications.*`,
// matching the established "no shared settings-string namespace"
// convention (see EmailChangeSection.vue's own header) -- category
// labels are duplicated per role rather than hoisted into a common
// namespace that does not exist in this codebase.
//
// CATEGORY LIST IS SERVER-DRIVEN, NOT HARDCODED. The row of toggles is
// built from `Object.keys(preferences.categories)` -- whatever comms'
// loaded profile currently declares (comms-profile/types.yaml) -- not
// a fixed local list. A category this build has no translation for
// yet still renders (tOrRaw falls back to the raw key), so a new
// category landing in types.yaml never produces a blank or a missing
// row, only an untranslated one until the next i18n pass.
//
// SAVE IS A FULL-FORM RESEND, NOT A DIFF. Every Save sends the
// complete current `categories` map (comms' contract allows a partial
// map, but sending the full map is equally valid -- "only listed
// toggles change" and every toggle is listed) and the complete
// `schedule` (or explicit `null` to clear it) rather than tracking
// which fields the user actually touched. Simpler, and safe: comms'
// own contract note calls a resend of what GET just returned a fixed
// point, so resending unedited fields is a no-op on the stored state.
//
// QUIET HOURS: a single "enable" checkbox gates the from/to/day
// fields. Unticking it and saving sends `schedule: null` (clear);
// leaving it unticked with no prior window sends `schedule: null`
// too (idempotent, matches "no window" being the natural default).
// Times are plain `<input type="time">` values (already "HH:MM",
// exactly the wire format -- see api/notifications.ts's
// NotificationSchedule on why no local time-object conversion
// happens on this side).
//
// TIMEZONE is shown as read-only caption text ONLY when comms has one
// for this recipient (null on an unconfigured box, or before comms
// has synced timezone context) -- never an editable field, per
// comms' own contract note that it is sync-owned.
// =============================================================================

import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bell, ChevronRight } from 'lucide-vue-next'

import { CButton, CCheckbox, CInput, CLoader, CModal } from '@/components/ui'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  type CategoryToggles,
} from '@/api/notifications'
import { ApiResponseError, ApiNetworkError, ApiTimeoutError } from '@/api/client'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'

const props = defineProps<{
  /** i18n prefix, e.g. "inv.settings.actions" -- keys read from `${tPrefix}.notifications.*`. */
  tPrefix: string
}>()

const { t } = useI18n()
const { showToast } = useToast()

// mon..sun, ISO week order -- matches comms' own day-code convention
// (comms/app/api/prefs.py _DAY_CODES) so the checkbox row reads left
// to right the same way the backend orders it back.
const DAY_CODES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

const open = ref(false)
const loading = ref(false)
const loadError = ref(false)
const saving = ref(false)
const error = ref('')

const categories = reactive<CategoryToggles>({})
const categoryOrder = ref<string[]>([])
const timezone = ref<string | null>(null)

const scheduleEnabled = ref(false)
const scheduleFrom = ref('22:00')
const scheduleTo = ref('08:00')
const scheduleDays = reactive<Record<string, boolean>>({})

function tk(key: string, params?: Record<string, unknown>): string {
  return params
    ? t(`${props.tPrefix}.notifications.${key}`, params)
    : t(`${props.tPrefix}.notifications.${key}`)
}

function categoryLabel(category: string): string {
  return tOrRaw(t, `${props.tPrefix}.notifications.categories.${category}`, category)
}

function dayLabel(day: string): string {
  return tOrRaw(t, `${props.tPrefix}.notifications.days.${day}`, day)
}

function resetScheduleDays(selected: readonly string[]): void {
  for (const day of DAY_CODES) {
    scheduleDays[day] = selected.includes(day)
  }
}

async function fetchPreferences(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const prefs = await getNotificationPreferences()

    for (const key of Object.keys(categories)) delete categories[key]
    Object.assign(categories, prefs.categories)
    categoryOrder.value = Object.keys(prefs.categories).sort()

    timezone.value = prefs.timezone

    if (prefs.schedule) {
      scheduleEnabled.value = true
      scheduleFrom.value = prefs.schedule.from
      scheduleTo.value = prefs.schedule.to
      resetScheduleDays(prefs.schedule.days)
    } else {
      scheduleEnabled.value = false
      resetScheduleDays([])
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function openPreferences(): void {
  open.value = true
  error.value = ''
  void fetchPreferences()
}

function close(): void {
  if (saving.value) return
  open.value = false
}

const selectedDays = computed(() => DAY_CODES.filter((d) => scheduleDays[d]))

const canSave = computed(() => {
  if (!scheduleEnabled.value) return true
  return scheduleFrom.value.length > 0 && scheduleTo.value.length > 0 && selectedDays.value.length > 0
})

function mapError(err: unknown): string {
  if (err instanceof ApiResponseError) {
    return err.detail || tk('errorGeneric')
  }
  if (err instanceof ApiNetworkError) return t('auth.error.networkError')
  if (err instanceof ApiTimeoutError) return t('auth.error.timeout')
  return tk('errorGeneric')
}

async function save(): Promise<void> {
  if (!canSave.value || saving.value) return
  error.value = ''
  saving.value = true
  try {
    const prefs = await updateNotificationPreferences({
      categories: { ...categories },
      schedule: scheduleEnabled.value
        ? { from: scheduleFrom.value, to: scheduleTo.value, days: [...selectedDays.value] }
        : null,
    })

    Object.assign(categories, prefs.categories)
    timezone.value = prefs.timezone
    if (prefs.schedule) {
      scheduleEnabled.value = true
      scheduleFrom.value = prefs.schedule.from
      scheduleTo.value = prefs.schedule.to
      resetScheduleDays(prefs.schedule.days)
    } else {
      scheduleEnabled.value = false
    }

    open.value = false
    showToast(tk('saveSuccess'), 'success')
  } catch (err) {
    error.value = mapError(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <button type="button" class="nps__row" @click="openPreferences">
    <span class="nps__row-label">
      <Bell :size="16" />
      {{ tk('cta') }}
    </span>
    <ChevronRight :size="16" />
  </button>

  <CModal :open="open" @close="close">
    <h3 class="nps__title">
      {{ tk('title') }}
    </h3>

    <div v-if="loading" class="nps__center">
      <CLoader :size="24" />
    </div>

    <div v-else-if="loadError" class="nps__center nps__center--column">
      <p class="nps__load-error">
        {{ tk('loadError') }}
      </p>
      <CButton variant="outline" size="sm" inline @click="fetchPreferences">
        {{ tk('retry') }}
      </CButton>
    </div>

    <template v-else>
      <section class="nps__section">
        <h4 class="nps__section-title">
          {{ tk('categoriesTitle') }}
        </h4>
        <div class="nps__categories">
          <CCheckbox
            v-for="category in categoryOrder"
            :key="category"
            v-model="categories[category]"
            :label="categoryLabel(category)"
          />
        </div>
      </section>

      <section class="nps__section">
        <CCheckbox v-model="scheduleEnabled" :label="tk('scheduleEnableLabel')" />
        <p class="nps__hint">
          {{ tk('scheduleDescription') }}
        </p>

        <template v-if="scheduleEnabled">
          <div class="nps__time-row">
            <CInput v-model="scheduleFrom" type="time" :label="tk('fromLabel')" />
            <CInput v-model="scheduleTo" type="time" :label="tk('toLabel')" />
          </div>

          <p class="nps__days-label">
            {{ tk('daysLabel') }}
          </p>
          <div class="nps__days">
            <label v-for="day in DAY_CODES" :key="day" class="nps__day">
              <input v-model="scheduleDays[day]" type="checkbox" />
              <span>{{ dayLabel(day) }}</span>
            </label>
          </div>

          <p v-if="timezone" class="nps__hint">
            {{ tk('timezoneNote', { timezone }) }}
          </p>
        </template>
      </section>

      <p v-if="error" class="nps__error">
        {{ error }}
      </p>

      <div class="nps__actions">
        <CButton variant="outline" size="sm" :disabled="saving" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="saving"
          :disabled="!canSave"
          @click="save"
        >
          {{ tk('saveBtn') }}
        </CButton>
      </div>
    </template>
  </CModal>
</template>

<style scoped>
.nps__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  min-height: var(--size-3xl);
  width: 100%;
  background: transparent;
  border-left: 0;
  border-right: 0;
  border-top: 0;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}
.nps__row:hover {
  background: var(--bg-subtle);
}
.nps__row-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--primary);
}

.nps__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}

.nps__center {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5) 0;
}
.nps__center--column {
  flex-direction: column;
  gap: var(--space-3);
}
.nps__load-error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  text-align: center;
}

.nps__section {
  margin-bottom: var(--space-4);
}
.nps__section-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}
.nps__categories {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.nps__hint {
  margin: var(--space-2) 0 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.4;
}

.nps__time-row {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.nps__time-row > * {
  flex: 1;
  min-width: 0;
}

.nps__days-label {
  margin: var(--space-3) 0 var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
}
.nps__days {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.nps__day {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  cursor: pointer;
}

.nps__error {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  background: var(--danger-subtle);
  border: 1px solid var(--danger);
  color: var(--danger);
}

.nps__actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-4);
}
</style>
