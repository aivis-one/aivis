<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- NotificationPreferencesSection (TASK-38 item 4)
// =============================================================================
//
// Shared across InvestorSettingsView /
// CompanySettingsView's Actions section, same drop-in-row pattern as
// TwoFactorSection.vue / ActiveSessionsSection.vue / DeactivateAccountSection.vue.
// Backend: notifications/router.py + service.py's preferences pair,
// a thin proxy over comms (the comms service's preferences API).
//
// i18n: every string is read from `${props.tPrefix}.notifications.*`,
// matching the established "no shared settings-string namespace"
// convention every sibling section in this folder follows, each under
// its own sub-key of the caller's prefix -- category
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
import { AlertTriangle, Bell, Check, ChevronRight } from '@/components/ui/icons'

import { CButton, CCheckbox, CEmptyState, CInput, CModal } from '@/components/ui'
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
  return (
    scheduleFrom.value.length > 0 && scheduleTo.value.length > 0 && selectedDays.value.length > 0
  )
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
  <!-- The settings row that opens the window (K23) -->
  <ul class="ds-rows">
    <li class="ds-row">
      <span class="ds-row__lead"><Bell size="sm" /></span>
      <span class="ds-row__body">
        <button type="button" class="ds-row__link" @click="openPreferences">
          <span class="ds-row__title">{{ tk('cta') }}</span>
        </button>
      </span>
      <span class="ds-row__trail"><ChevronRight size="sm" /></span>
    </li>
  </ul>

  <CModal :open="open" :title="tk('title')" @close="close">
    <div v-if="loading" class="ds-loader ds-loader--centered" role="status">
      <span class="ds-loader__ring" aria-hidden="true" />
      <span>{{ t('common.loading') }}</span>
    </div>

    <CEmptyState v-else-if="loadError" tone="danger" :title="tk('loadError')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="fetchPreferences">
          {{ tk('retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else>
      <fieldset class="ds-fieldset">
        <legend class="ds-fieldset__legend">
          {{ tk('categoriesTitle') }}
        </legend>
        <CCheckbox
          v-for="category in categoryOrder"
          :key="category"
          v-model="categories[category]"
          :label="categoryLabel(category)"
        />
      </fieldset>

      <fieldset class="ds-fieldset">
        <CCheckbox v-model="scheduleEnabled" :label="tk('scheduleEnableLabel')" />
        <p class="ds-field__hint">
          {{ tk('scheduleDescription') }}
        </p>

        <template v-if="scheduleEnabled">
          <CInput v-model="scheduleFrom" type="time" :label="tk('fromLabel')" />
          <CInput v-model="scheduleTo" type="time" :label="tk('toLabel')" />

          <p id="nps-days-label" class="ds-field__label">
            {{ tk('daysLabel') }}
          </p>
          <div class="ds-chip-row" role="group" aria-labelledby="nps-days-label">
            <button
              v-for="day in DAY_CODES"
              :key="day"
              type="button"
              class="ds-chip"
              :aria-pressed="scheduleDays[day] ? 'true' : 'false'"
              @click="scheduleDays[day] = !scheduleDays[day]"
            >
              <Check class="ds-chip__check" size="sm" />
              <span>{{ dayLabel(day) }}</span>
            </button>
          </div>

          <p v-if="timezone" class="ds-field__hint">
            {{ tk('timezoneNote', { timezone }) }}
          </p>
        </template>
      </fieldset>

      <div v-if="error" class="ds-alert ds-alert--danger" role="alert">
        <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ error }}</p>
        </div>
      </div>

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline :disabled="saving" @click="close">
          {{ tk('cancelBtn') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
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
