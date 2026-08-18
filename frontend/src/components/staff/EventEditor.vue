<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EventEditor (iter 2.7 Block B)
// =============================================================================
//
// Shared list + create/edit surface for calendar events. Used by
// StaffEventsView. Backend: api/staff-events.ts (content_manage gated).
//
// FP-23: parent passes `canEdit` (content_manage). CTAs hidden when
// false; handlers bail with console.warn defensively.
//
// Datetime handling. The backend serialises starts_at / ends_at as
// ISO-8601 strings. The UI uses a native <input type="datetime-local">,
// whose value is a "YYYY-MM-DDTHH:mm" local-time string with no zone.
// We bridge in two helpers:
//   isoToLocalInput(iso)  -- ISO -> datetime-local value (for edit
//                            prefill), rendered in the browser's local
//                            zone.
//   localInputToIso(v)    -- datetime-local value -> ISO (UTC) for the
//                            request body.
// MVP scope: no timezone picker; events are authored and read in the
// staffer's local zone, round-tripped through UTC on the wire.
// =============================================================================

import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Pencil, Trash2 } from 'lucide-vue-next'
import {
  CBadge,
  CLoader,
  CButton,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CCheckbox,
} from '@/components/ui'
import { useToast } from '@/composables/useToast'
import {
  fetchStaffEvents,
  createStaffEvent,
  updateStaffEvent,
  deleteStaffEvent,
} from '@/api/staff-events'
import type {
  EventResponse,
  CreateEventRequest,
  UpdateEventRequest,
} from '@/api/types'

const props = defineProps<{
  /** content_manage gate from the parent (FP-23). */
  canEdit: boolean
}>()

const { t } = useI18n()
const { showToast } = useToast()

// -- List state --
const items = ref<EventResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const error = ref(false)

// upcoming filter: '' (all) | 'true' (future) | 'false' (past).
// Stored as string to map straight onto filter chips; converted to
// boolean | undefined at the API boundary.
const upcomingFilter = ref<'' | 'true' | 'false'>('')

// -- Editor modal --
const showEditor = ref(false)
const editId = ref<string | null>(null)
const saving = ref(false)

// -- Delete confirm --
const deleteTarget = ref<EventResponse | null>(null)
const deleting = ref(false)

const form = reactive({
  title: '',
  description: '',
  cover_url: '',
  starts_at: '', // datetime-local string
  ends_at: '', // datetime-local string
  location: '',
  url: '',
  is_published: false,
})

const totalPages = computed(() => Math.ceil(total.value / perPage))

// -- Datetime bridges --

function isoToLocalInput(iso: string): string {
  // Render an ISO instant as a local-zone "YYYY-MM-DDTHH:mm" string.
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  // Offset to local time, then slice off seconds/zone for the input.
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

function localInputToIso(v: string): string {
  // datetime-local value is interpreted in the browser's local zone;
  // new Date(v) does exactly that, and toISOString() normalises to UTC.
  const d = new Date(v)
  return d.toISOString()
}

async function loadEvents(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const upcoming =
      upcomingFilter.value === '' ? undefined : upcomingFilter.value === 'true'
    const resp = await fetchStaffEvents({
      upcoming,
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

function resetForm(): void {
  form.title = ''
  form.description = ''
  form.cover_url = ''
  form.starts_at = ''
  form.ends_at = ''
  form.location = ''
  form.url = ''
  form.is_published = false
}

function openCreate(): void {
  if (!props.canEdit) {
    console.warn('[EventEditor] openCreate blocked: no content_manage')
    return
  }
  editId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(ev: EventResponse): void {
  if (!props.canEdit) {
    console.warn('[EventEditor] openEdit blocked: no content_manage')
    return
  }
  editId.value = ev.id
  form.title = ev.title
  form.description = ev.description ?? ''
  form.cover_url = ev.cover_url ?? ''
  form.starts_at = isoToLocalInput(ev.starts_at)
  form.ends_at = ev.ends_at ? isoToLocalInput(ev.ends_at) : ''
  form.location = ev.location ?? ''
  form.url = ev.url ?? ''
  form.is_published = ev.is_published
  showEditor.value = true
}

// title + starts_at are required; ends_at (when present) must be after
// starts_at -- mirrors the backend schema validator so the user gets
// immediate feedback instead of a 422.
const canSubmit = computed<boolean>(() => {
  if (!form.title.trim() || !form.starts_at) return false
  if (form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)) {
    return false
  }
  return true
})

async function handleSave(): Promise<void> {
  if (!props.canEdit) {
    console.warn('[EventEditor] handleSave blocked: no content_manage')
    return
  }
  if (!canSubmit.value) return

  saving.value = true
  try {
    if (editId.value === null) {
      const payload: CreateEventRequest = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        cover_url: form.cover_url.trim() || null,
        starts_at: localInputToIso(form.starts_at),
        ends_at: form.ends_at ? localInputToIso(form.ends_at) : null,
        location: form.location.trim() || null,
        url: form.url.trim() || null,
        is_published: form.is_published,
      }
      await createStaffEvent(payload)
      showToast(t('staff.platform.event.created'), 'success')
    } else {
      const payload: UpdateEventRequest = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        cover_url: form.cover_url.trim() || null,
        starts_at: localInputToIso(form.starts_at),
        ends_at: form.ends_at ? localInputToIso(form.ends_at) : null,
        location: form.location.trim() || null,
        url: form.url.trim() || null,
        is_published: form.is_published,
      }
      await updateStaffEvent(editId.value, payload)
      showToast(t('staff.platform.event.updated'), 'success')
    }
    showEditor.value = false
    await loadEvents()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    saving.value = false
  }
}

function openDelete(ev: EventResponse): void {
  if (!props.canEdit) {
    console.warn('[EventEditor] openDelete blocked: no content_manage')
    return
  }
  deleteTarget.value = ev
}

async function handleDelete(): Promise<void> {
  if (!props.canEdit || !deleteTarget.value) {
    if (!props.canEdit) {
      console.warn('[EventEditor] handleDelete blocked: no content_manage')
    }
    return
  }
  deleting.value = true
  try {
    await deleteStaffEvent(deleteTarget.value.id)
    showToast(t('staff.platform.event.deleted'), 'success')
    deleteTarget.value = null
    // BUG-38-01: stepping the page back triggers the page watcher,
    // which reloads on its own. Only reload inline when the page is
    // unchanged -- otherwise both this call and the watcher fire and
    // race two requests for the same list.
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await loadEvents()
    }
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

function setUpcomingFilter(v: '' | 'true' | 'false'): void {
  upcomingFilter.value = v
  page.value = 1
}

watch([upcomingFilter, page], () => loadEvents())
onMounted(loadEvents)
</script>

<template>
  <div class="evd">
    <!-- Filter chips + create CTA -->
    <div class="evd__toolbar">
      <div class="evd__filters">
        <button
          class="filter-chip"
          :class="{ active: upcomingFilter === '' }"
          @click="setUpcomingFilter('')"
        >{{ t('staff.platform.event.filterAll') }}</button>
        <button
          class="filter-chip"
          :class="{ active: upcomingFilter === 'true' }"
          @click="setUpcomingFilter('true')"
        >{{ t('staff.platform.event.filterUpcoming') }}</button>
        <button
          class="filter-chip"
          :class="{ active: upcomingFilter === 'false' }"
          @click="setUpcomingFilter('false')"
        >{{ t('staff.platform.event.filterPast') }}</button>
      </div>
      <CButton v-if="canEdit" variant="primary" size="sm" @click="openCreate">
        <Plus :size="16" />
        {{ t('staff.platform.event.createCta') }}
      </CButton>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="evd__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="evd__center">
      <CButton variant="secondary" size="sm" @click="loadEvents">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.event.empty')" />

    <!-- List -->
    <template v-else>
      <div class="event-list">
        <div v-for="ev in items" :key="ev.id" class="event-item">
          <div class="event-item__info">
            <div class="event-item__top">
              <CBadge
                :variant="ev.is_published ? 'success' : 'neutral'"
                :text="ev.is_published
                  ? t('staff.platform.event.published')
                  : t('staff.platform.event.draft')"
              />
            </div>
            <div class="event-item__title">{{ ev.title }}</div>
            <div class="event-item__date">{{ formatDateTime(ev.starts_at) }}</div>
            <div v-if="ev.location" class="event-item__loc">{{ ev.location }}</div>
          </div>
          <div v-if="canEdit" class="event-item__actions">
            <button class="event-item__icon-btn" @click="openEdit(ev)">
              <Pencil :size="16" />
            </button>
            <button class="event-item__icon-btn event-item__icon-btn--danger" @click="openDelete(ev)">
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="evd__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">&larr;</CButton>
        <span class="evd__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">&rarr;</CButton>
      </div>
    </template>

    <!-- Editor modal -->
    <CModal :open="showEditor" @close="showEditor = false">
      <h3 class="evd__modal-title">
        {{ editId === null
          ? t('staff.platform.event.createTitle')
          : t('staff.platform.event.editTitle') }}
      </h3>

      <CInput
        v-model="form.title"
        :label="t('staff.platform.event.fieldTitle')"
        :placeholder="t('staff.platform.event.fieldTitle')"
      />
      <CTextarea
        v-model="form.description"
        :label="t('staff.platform.event.fieldDescription')"
        :placeholder="t('staff.platform.event.fieldDescription')"
        :rows="4"
      />

      <!-- Native datetime-local inputs (no UI-kit date picker exists). -->
      <div class="evd__field">
        <label class="evd__label">{{ t('staff.platform.event.fieldStartsAt') }}</label>
        <input v-model="form.starts_at" type="datetime-local" class="evd__datetime" />
      </div>
      <div class="evd__field">
        <label class="evd__label">{{ t('staff.platform.event.fieldEndsAt') }}</label>
        <input v-model="form.ends_at" type="datetime-local" class="evd__datetime" />
        <p
          v-if="form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)"
          class="evd__field-error"
        >{{ t('staff.platform.event.endsAfterStartsError') }}</p>
      </div>

      <CInput
        v-model="form.location"
        :label="t('staff.platform.event.fieldLocation')"
        :placeholder="t('staff.platform.event.fieldLocation')"
      />
      <CInput
        v-model="form.url"
        :label="t('staff.platform.event.fieldUrl')"
        :placeholder="t('staff.platform.event.fieldUrlPlaceholder')"
      />
      <CInput
        v-model="form.cover_url"
        :label="t('staff.platform.event.fieldCover')"
        :placeholder="t('staff.platform.event.fieldCoverPlaceholder')"
      />

      <div class="evd__toggles">
        <CCheckbox v-model="form.is_published" :label="t('staff.platform.event.isPublished')" />
      </div>

      <div class="evd__modal-actions">
        <CButton variant="outline" size="sm" @click="showEditor = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Delete confirm -->
    <CModal :open="!!deleteTarget" @close="deleteTarget = null">
      <h3 class="evd__modal-title">{{ t('staff.platform.event.deleteTitle') }}</h3>
      <p class="evd__modal-text">{{ t('staff.platform.event.deleteConfirm') }}</p>
      <p v-if="deleteTarget" class="evd__modal-target">{{ deleteTarget.title }}</p>
      <div class="evd__modal-actions">
        <CButton variant="outline" size="sm" @click="deleteTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="deleting" @click="handleDelete">
          {{ t('common.delete') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.evd { padding: 0; }

.evd__toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 12px;
}
.evd__filters { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
.filter-chip {
  padding: 6px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-page); color: var(--text-secondary); font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap;
}
.filter-chip.active { background: var(--primary); color: white; border-color: var(--primary); }

.evd__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: 200px; gap: 16px;
}

.event-list { display: flex; flex-direction: column; }
.event-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 0;
  border-bottom: 1px solid var(--border-default);
}
.event-item__info { flex: 1; min-width: 0; }
.event-item__top { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.event-item__title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.event-item__date { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.event-item__loc { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.event-item__actions { display: flex; gap: 4px; flex-shrink: 0; }
.event-item__icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: none; background: none;
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  transition: background 0.15s, color 0.15s;
}
.event-item__icon-btn:hover { background: var(--bg-subtle); }
.event-item__icon-btn--danger:hover { color: var(--danger); }

.evd__pagination {
  display: flex; align-items: center; justify-content: center;
  gap: 12px; margin-top: 16px;
}
.evd__page { font-size: 13px; color: var(--text-secondary); }

.evd__modal-title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 16px; }
.evd__modal-text { font-size: 14px; color: var(--text-secondary); margin: 0 0 8px; }
.evd__modal-target { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0 0 16px; }
.evd__modal-actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }

.evd__field { margin-bottom: 16px; }
.evd__label {
  display: block; font-size: 13px; font-weight: 600;
  color: var(--text-primary); margin-bottom: 6px;
}
.evd__datetime {
  width: 100%; padding: 14px 16px; border: 2px solid var(--border-default);
  border-radius: var(--radius-md); font-size: 15px; font-family: inherit;
  background: var(--bg-page); color: var(--text-primary);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.evd__datetime:focus { outline: none; border-color: var(--primary); box-shadow: var(--shadow-focus); }
.evd__field-error { font-size: 12px; color: var(--danger); margin-top: 4px; }

.evd__toggles { display: flex; flex-direction: column; gap: 12px; margin-bottom: 8px; }
</style>
