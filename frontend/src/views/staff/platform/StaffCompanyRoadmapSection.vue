<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyRoadmapSection (iter 2.7 Block D / D1)
// =============================================================================
//
// Roadmap CRUD + reorder for one company (R1 §5). Flat list in order
// ASC, kind/status badges, up/down reorder, a create modal with a
// kind tab strip (milestone / event / announcement), an edit modal
// (kind locked), and soft-delete.
//
// DATA SOURCE. There is no standalone GET /staff/companies/{id}/roadmap
// endpoint -- the roadmap arrives inline on CompanyDetailResponse.roadmap
// via the parent StaffCompanyDetailView, which loads the company once
// and shares it through STAFF_COMPANY_KEY (PERF-40-01). This section
// reads ctx.company.value.roadmap and calls ctx.reload() after every
// mutation. No duplicate detail fetch here.
//
// PER-KIND RULES (R1 §5.4, enforced server-side; mirrored in the form
// to avoid an obvious 4xx):
//   milestone     -- title required; valid_until forbidden; optional
//                    target_date + status (planned/in_progress/completed).
//   event         -- title + target_date + valid_until required;
//                    valid_until must be AFTER target_date; no status.
//   announcement  -- title required; target_date / valid_until / status
//                    all forbidden.
// `kind` is immutable after create -- the edit modal shows it as a
// locked badge, never a tab.
//
// MILESTONE STATE MACHINE (R1 §5.6). completed is terminal: the backend
// 400s on completed -> anything-else. The error text carries no
// machine-readable prefix, so we PREVENT it in the UI -- a completed
// milestone renders its status select disabled with a hint -- rather
// than parsing the 400 message. Any 400 that still slips through
// surfaces as a generic error toast.
//
// REORDER (up/down, not drag-drop -- buttons beat drag on a 380px touch
// screen and need no dependency). Each click swaps two adjacent items,
// then submits the COMPLETE id list in the new order. Per-company scope
// (NOT per-kind). The roadmap reorder endpoint's set-mismatch error has
// NO prefix (unlike attachments), so any ApiResponseError from the
// reorder is treated as a stale-list signal: toast + reload.
//
// FP-23. Every mutating CTA (add / edit / delete / reorder) is gated on
// canDo('company_manage') -- template guard on the control plus a
// defensive check in the handler. A staffer without company_manage
// still reads the list (the parent route only enforces requireStaff).
//
// FP-25. Empty optional fields self-hide in the card (cover, description,
// external_url, target_date, valid_until, linked post, linked product).
//
// NOT in D1: cover upload (D2), and post/product linking. The backend
// accepts post_id / linked_product_id optionally, but the target UX
// (R1 §5.7) is a search combobox over the company's posts/products, not
// a raw UUID field -- tracked as post-MVP tech debt, so the form omits
// both and the backend leaves them null.
// =============================================================================

import { ref, computed, onMounted, inject } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronUp,
  ChevronDown,
  Pencil,
  Trash2,
  Map as MapIcon,
  ImageUp,
  X,
} from 'lucide-vue-next'
import {
  CLoader,
  CButton,
  CBadge,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CSelect,
} from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { ApiResponseError } from '@/api/client'
import {
  createRoadmapItem,
  updateRoadmapItem,
  deleteRoadmapItem,
  reorderRoadmap,
  uploadRoadmapCover,
  deleteRoadmapCover,
} from '@/api/staff-companies'
import type {
  RoadmapItemResponse,
  RoadmapItemKind,
  CreateRoadmapItemRequest,
  UpdateRoadmapItemRequest,
} from '@/api/types'
import { STAFF_COMPANY_KEY } from './staffCompanyContext'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// FP-23: every roadmap mutation requires company_manage.
const canManage = canDo('company_manage')

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

// Roadmap data comes from the parent detail view via inject. We read
// the list from there and reload it after mutations.
const ctx = inject(STAFF_COMPANY_KEY)

// Sorted view of the injected roadmap (order ASC). The backend returns
// it ordered already, but sort defensively so a reorder race can't
// briefly show rows out of sequence.
const items = computed<RoadmapItemResponse[]>(() => {
  const list = ctx?.company.value?.roadmap ?? []
  return [...list].sort((a, b) => a.order - b.order)
})

// Loading / error mirror the parent fetch state so this section shows a
// spinner / retry exactly like the sibling sections do.
const loading = computed<boolean>(() => ctx?.loading.value ?? false)
const errored = computed<boolean>(() => ctx?.error.value ?? false)

async function reload(): Promise<void> {
  await ctx?.reload()
}

// ---------------------------------------------------------------------------
// Kind + status value lists
//
// RoadmapItemStatus is not emitted as a TS type (status is bare `str`
// on the wire), so the status values live here as an `as const` tuple
// -- the single source for the select options and the badge variant
// map. KIND_VALUES drives the create tab strip.
// ---------------------------------------------------------------------------

const KIND_VALUES = ['milestone', 'event', 'announcement'] as const
const STATUS_VALUES = ['planned', 'in_progress', 'completed'] as const

// kind / status -> i18n label
function kindLabel(kind: string): string {
  switch (kind) {
    case 'milestone':
      return t('staff.platform.roadmap.kindMilestone')
    case 'event':
      return t('staff.platform.roadmap.kindEvent')
    case 'announcement':
      return t('staff.platform.roadmap.kindAnnouncement')
    default:
      return kind
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'planned':
      return t('staff.platform.roadmap.statusPlanned')
    case 'in_progress':
      return t('staff.platform.roadmap.statusInProgress')
    case 'completed':
      return t('staff.platform.roadmap.statusCompleted')
    default:
      return status
  }
}

// CBadge variant helpers. NOTE: no explicit `: string` return annotation
// -- the literal-union inference is what CBadge's `variant` prop expects;
// annotating as string widens it and trips TS2322 (lesson from the C
// cleanup fix / kycVariant in StaffUsersView).
function kindVariant(kind: string) {
  switch (kind) {
    case 'event':
      return 'accent'
    case 'announcement':
      return 'warning'
    case 'milestone':
    default:
      return 'neutral'
  }
}

function statusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'in_progress':
      return 'accent'
    case 'planned':
    default:
      return 'neutral'
  }
}

// Status select options (milestone only).
const statusOptions = computed<{ value: string; label: string }[]>(() =>
  STATUS_VALUES.map((s) => ({ value: s, label: statusLabel(s) })),
)

// ---------------------------------------------------------------------------
// Card helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  // Wire value is 'YYYY-MM-DD'. Render in the user's locale, date-only.
  // Append T00:00 so it is parsed as local midnight, not UTC (which
  // could shift the day backwards in negative-offset zones).
  return new Date(`${iso}T00:00:00`).toLocaleDateString()
}

// ---------------------------------------------------------------------------
// Create / edit modal
//
// One modal, two modes. `editingId` null => create (kind tab strip
// active); non-null => edit (kind locked, shown as a badge). The draft
// holds every field; per-kind visibility decides what renders and what
// is sent.
// ---------------------------------------------------------------------------

const showForm = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)

// Draft fields. Dates are 'YYYY-MM-DD' strings (native date input).
// draftStatus is a plain string (not the RoadmapStatus union) so the
// CSelect v-model -- which emits string -- type-checks without a
// computed boundary; it only ever holds one of STATUS_VALUES because
// the select options are built from that tuple.
const draftKind = ref<RoadmapItemKind>('milestone')
const draftTitle = ref('')
const draftDescription = ref('')
const draftTargetDate = ref('')
const draftValidUntil = ref('')
const draftStatus = ref<string>('planned')
const draftExternalUrl = ref('')

// Snapshot of the item being edited -- used to send only changed fields
// (the backend's exclude_unset contract: omit = keep, null = clear).
const editingOriginal = ref<RoadmapItemResponse | null>(null)

const isEditing = computed<boolean>(() => editingId.value !== null)

// Per-kind field visibility (mirrors R1 §5.4).
const showTargetDate = computed<boolean>(
  () => draftKind.value === 'milestone' || draftKind.value === 'event',
)
const showValidUntil = computed<boolean>(() => draftKind.value === 'event')
const showStatus = computed<boolean>(() => draftKind.value === 'milestone')

// A completed milestone cannot change status (R1 §5.6). Only relevant
// when editing -- on create the status starts at planned.
const statusLocked = computed<boolean>(
  () =>
    isEditing.value &&
    draftKind.value === 'milestone' &&
    editingOriginal.value?.status === 'completed',
)

// Reset all draft fields to defaults for a given kind.
function resetDraft(kind: RoadmapItemKind): void {
  draftKind.value = kind
  draftTitle.value = ''
  draftDescription.value = ''
  draftTargetDate.value = ''
  draftValidUntil.value = ''
  draftStatus.value = 'planned'
  draftExternalUrl.value = ''
}

// Switch kind in create mode. Clears the other-kind fields so a hidden
// field can't smuggle a value the backend would reject.
function selectKind(kind: RoadmapItemKind): void {
  if (isEditing.value) return // kind is locked while editing
  if (kind === draftKind.value) return
  resetDraft(kind)
}

function openCreate(): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] openCreate blocked: no company_manage')
    return
  }
  editingId.value = null
  editingOriginal.value = null
  coverPreviewUrl.value = ''
  resetDraft('milestone')
  showForm.value = true
}

function openEdit(item: RoadmapItemResponse): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] openEdit blocked: no company_manage')
    return
  }
  editingId.value = item.id
  editingOriginal.value = item
  coverPreviewUrl.value = item.cover_url ?? ''
  draftKind.value = item.kind as RoadmapItemKind
  draftTitle.value = item.title
  draftDescription.value = item.description ?? ''
  draftTargetDate.value = item.target_date ?? ''
  draftValidUntil.value = item.valid_until ?? ''
  draftStatus.value = item.status || 'planned'
  draftExternalUrl.value = item.external_url ?? ''
  showForm.value = true
}

function closeForm(): void {
  showForm.value = false
}

// Trimmed helpers.
const trimmedTitle = computed<string>(() => draftTitle.value.trim())
const trimmedExternalUrl = computed<string>(() => draftExternalUrl.value.trim())

// External URL is optional, but if present must be http(s) -- mirror the
// backend validator so we don't round-trip a guaranteed 422.
const externalUrlValid = computed<boolean>(() => {
  const v = trimmedExternalUrl.value
  if (!v) return true
  return v.startsWith('http://') || v.startsWith('https://')
})

// valid_until must be after target_date for events.
const eventDatesValid = computed<boolean>(() => {
  if (draftKind.value !== 'event') return true
  if (!draftTargetDate.value || !draftValidUntil.value) return false
  return draftValidUntil.value > draftTargetDate.value
})

// Submit gate. Title always required; per-kind date requirements; URL
// shape; event date ordering.
const canSubmit = computed<boolean>(() => {
  if (!trimmedTitle.value) return false
  if (!externalUrlValid.value) return false
  if (draftKind.value === 'event') {
    if (!eventDatesValid.value) return false
  }
  return true
})

// Build the create body from the draft, honouring per-kind rules: only
// send fields the kind allows so we never trip a Pydantic invariant.
function buildCreateBody(): CreateRoadmapItemRequest {
  const body: CreateRoadmapItemRequest = {
    kind: draftKind.value,
    title: trimmedTitle.value,
  }
  const desc = draftDescription.value.trim()
  if (desc) body.description = desc
  if (trimmedExternalUrl.value) body.external_url = trimmedExternalUrl.value

  if (draftKind.value === 'milestone') {
    if (draftTargetDate.value) body.target_date = draftTargetDate.value
    // status optional; service defaults to planned when omitted.
    if (draftStatus.value && draftStatus.value !== 'planned') {
      body.status = draftStatus.value
    }
  } else if (draftKind.value === 'event') {
    body.target_date = draftTargetDate.value
    body.valid_until = draftValidUntil.value
  }
  // announcement: nothing date/status related.
  return body
}

// Build the update body as a DIFF against the original -- the backend
// distinguishes "omitted" (keep) from "null" (clear). We send a field
// only when it actually changed; clearing an optional value sends null.
function buildUpdateBody(): UpdateRoadmapItemRequest {
  const orig = editingOriginal.value
  const body: UpdateRoadmapItemRequest = {}
  if (!orig) return body

  if (trimmedTitle.value !== orig.title) {
    body.title = trimmedTitle.value
  }

  const desc = draftDescription.value.trim()
  const origDesc = orig.description ?? ''
  if (desc !== origDesc) {
    body.description = desc ? desc : null
  }

  const url = trimmedExternalUrl.value
  const origUrl = orig.external_url ?? ''
  if (url !== origUrl) {
    body.external_url = url ? url : null
  }

  // target_date: relevant for milestone + event. Compare 'YYYY-MM-DD'.
  if (draftKind.value === 'milestone' || draftKind.value === 'event') {
    const td = draftTargetDate.value
    const origTd = orig.target_date ?? ''
    if (td !== origTd) {
      body.target_date = td ? td : null
    }
  }

  // valid_until: event only.
  if (draftKind.value === 'event') {
    const vu = draftValidUntil.value
    const origVu = orig.valid_until ?? ''
    if (vu !== origVu) {
      body.valid_until = vu ? vu : null
    }
  }

  // status: milestone only, and never when locked (completed).
  if (draftKind.value === 'milestone' && !statusLocked.value) {
    const origStatus = orig.status ?? 'planned'
    if (draftStatus.value !== origStatus) {
      body.status = draftStatus.value
    }
  }

  return body
}

async function handleSave(): Promise<void> {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] handleSave blocked: no company_manage')
    return
  }
  if (!canSubmit.value) return

  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      const body = buildUpdateBody()
      // Nothing changed -- close without a redundant PATCH.
      if (Object.keys(body).length === 0) {
        showForm.value = false
        return
      }
      await updateRoadmapItem(companyId.value, editingId.value, body)
      showToast(t('staff.platform.roadmap.updated'), 'success')
    } else {
      await createRoadmapItem(companyId.value, buildCreateBody())
      showToast(t('staff.platform.roadmap.created'), 'success')
    }
    showForm.value = false
    await reload()
  } catch (e) {
    // Surface the backend message when present (e.g. the completed-
    // milestone 400, or an event date-order 422 that slipped past the
    // client guard); otherwise a generic error.
    if (e instanceof ApiResponseError && e.detail) {
      showToast(e.detail, 'error')
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// Reorder (up/down)
// ---------------------------------------------------------------------------

const reordering = ref(false)

// Move the item at `index` by `delta` (-1 up, +1 down), then submit the
// full id list in the new order.
async function move(index: number, delta: number): Promise<void> {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] move blocked: no company_manage')
    return
  }
  const rows = items.value
  const target = index + delta
  if (target < 0 || target >= rows.length) return
  if (reordering.value) return

  const ids = rows.map((r) => r.id)
  const tmp = ids[index]
  ids[index] = ids[target]
  ids[target] = tmp

  reordering.value = true
  try {
    await reorderRoadmap(companyId.value, { item_ids: ids })
    await reload()
  } catch (e) {
    // The roadmap reorder set-mismatch error carries NO machine prefix,
    // so any ApiResponseError here is treated as "someone else changed
    // the list": tell the user and reload to the committed order.
    if (e instanceof ApiResponseError) {
      showToast(t('staff.platform.roadmap.reorderStale'), 'error')
      await reload()
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    reordering.value = false
  }
}

// ---------------------------------------------------------------------------
// Soft-delete
// ---------------------------------------------------------------------------

const deleteTarget = ref<RoadmapItemResponse | null>(null)
const deleting = ref(false)

function openDelete(item: RoadmapItemResponse): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] openDelete blocked: no company_manage')
    return
  }
  deleteTarget.value = item
}

async function handleDelete(): Promise<void> {
  if (!canManage.value || !deleteTarget.value) {
    if (!canManage.value) {
      console.warn('[StaffCompanyRoadmapSection] handleDelete blocked: no company_manage')
    }
    return
  }
  deleting.value = true
  try {
    await deleteRoadmapItem(companyId.value, deleteTarget.value.id)
    showToast(t('staff.platform.roadmap.deleted'), 'success')
    deleteTarget.value = null
    await reload()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

// ---------------------------------------------------------------------------
// Cover image (D2, R1 §5.5)
//
// Cover operations are IMMEDIATE -- upload and remove hit the API on
// click, independent of the form's Save button (the cover has its own
// item-scoped endpoints and there is no item to attach a cover to until
// the row exists, so covers are edit-only). coverPreviewUrl mirrors the
// item's presigned cover_url so the modal updates without waiting on the
// list reload; the reload still runs so the card thumbnail stays in sync.
// ---------------------------------------------------------------------------

const COVER_MIME_WHITELIST = ['image/png', 'image/jpeg', 'image/webp'] as const
const COVER_MAX_BYTES = 10 * 1024 * 1024 // 10 MiB, mirrors backend cap

// Hidden file input ref (clicked via the upload button).
const coverInputEl = ref<HTMLInputElement | null>(null)

// Presigned URL of the current cover for the item being edited, or '' if
// none. Seeded in openEdit, updated from the upload response, cleared on
// remove. Separate from editingOriginal because reload() swaps the
// underlying roadmap array, detaching the original reference.
const coverPreviewUrl = ref('')

const coverUploading = ref(false)
const coverRemoving = ref(false)

// Remove-confirm modal target (the item id being cleared).
const coverRemoveTarget = ref<string | null>(null)

function triggerCoverPicker(): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] cover picker blocked: no company_manage')
    return
  }
  coverInputEl.value?.click()
}

async function onCoverSelected(e: Event): Promise<void> {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] cover upload blocked: no company_manage')
    return
  }
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  // Reset the input value so selecting the same file again re-triggers
  // change (browsers suppress change when the value is identical).
  input.value = ''
  if (!file) return
  if (!editingId.value) return

  // Client-side validation (defence in depth; backend re-validates).
  if (!(COVER_MIME_WHITELIST as readonly string[]).includes(file.type)) {
    showToast(t('staff.platform.roadmap.cover.errorMime'), 'error')
    return
  }
  if (file.size > COVER_MAX_BYTES) {
    showToast(t('staff.platform.roadmap.cover.errorSize'), 'error')
    return
  }

  coverUploading.value = true
  try {
    const updated = await uploadRoadmapCover(companyId.value, editingId.value, file)
    coverPreviewUrl.value = updated.cover_url ?? ''
    showToast(t('staff.platform.roadmap.cover.uploaded'), 'success')
    // Refresh the list so the card thumbnail reflects the new cover.
    await reload()
  } catch (e) {
    if (e instanceof ApiResponseError && e.detail) {
      showToast(e.detail, 'error')
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    coverUploading.value = false
  }
}

function openCoverRemove(): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyRoadmapSection] cover remove blocked: no company_manage')
    return
  }
  if (!editingId.value) return
  coverRemoveTarget.value = editingId.value
}

async function handleCoverRemove(): Promise<void> {
  if (!canManage.value || !coverRemoveTarget.value) {
    if (!canManage.value) {
      console.warn('[StaffCompanyRoadmapSection] cover remove blocked: no company_manage')
    }
    return
  }
  coverRemoving.value = true
  try {
    await deleteRoadmapCover(companyId.value, coverRemoveTarget.value)
    coverPreviewUrl.value = ''
    coverRemoveTarget.value = null
    showToast(t('staff.platform.roadmap.cover.removed'), 'success')
    await reload()
  } catch (e) {
    // A 404 means the cover was already gone -- treat as success-ish:
    // clear the preview and reload rather than alarming the user.
    if (e instanceof ApiResponseError && e.status === 404) {
      coverPreviewUrl.value = ''
      coverRemoveTarget.value = null
      await reload()
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    coverRemoving.value = false
  }
}

// No watch(companyId) here. The parent StaffCompanyDetailView owns the
// reload on an :id change (it re-fetches the company and the injected
// context updates); this section reads the roadmap reactively from that
// context through the `items` computed, so it re-renders without its own
// watcher. onMounted only covers the first-paint case where the parent
// has not started loading yet (e.g. a deep-link straight into this tab).
onMounted(() => {
  // If the parent hasn't loaded yet, its own onMounted will; if it has,
  // items is already populated from the injected company. No-op fetch
  // avoided -- we only reload if the parent exposes the hook and has no
  // company yet.
  if (ctx && !ctx.company.value && !ctx.loading.value) {
    void reload()
  }
})
</script>

<template>
  <div class="scr">
    <!-- Loading -->
    <div v-if="loading" class="scr__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="scr__center">
      <CButton variant="secondary" size="sm" @click="reload">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <!-- Add CTA (FP-23) -->
      <div v-if="canManage" class="scr__toolbar">
        <CButton variant="primary" size="sm" @click="openCreate">
          {{ t('staff.platform.roadmap.addCta') }}
        </CButton>
      </div>

      <!-- Empty -->
      <CEmptyState
        v-if="!items.length"
        :title="t('staff.platform.roadmap.empty')"
      >
        <template #icon><MapIcon :size="40" /></template>
      </CEmptyState>

      <!-- List (order ASC) -->
      <div v-else class="rm-list">
        <div
          v-for="(item, idx) in items"
          :key="item.id"
          class="rm-item"
        >
          <!-- Reorder (FP-23) -->
          <div v-if="canManage" class="rm-item__reorder">
            <button
            :aria-label="t('common.moveUp')"
              class="rm-item__move"
              :disabled="idx === 0 || reordering"
              @click="move(idx, -1)"
            >
              <ChevronUp :size="16" />
            </button>
            <button
            :aria-label="t('common.moveDown')"
              class="rm-item__move"
              :disabled="idx === items.length - 1 || reordering"
              @click="move(idx, 1)"
            >
              <ChevronDown :size="16" />
            </button>
          </div>

          <!-- Cover thumbnail (FP-25 self-hide) -->
          <div v-if="item.cover_url" class="rm-item__cover">
            <img :src="item.cover_url" :alt="item.title" class="rm-item__cover-img" />
          </div>

          <!-- Body -->
          <div class="rm-item__body">
            <div class="rm-item__badges">
              <CBadge :variant="kindVariant(item.kind)" :text="kindLabel(item.kind)" />
              <CBadge
                v-if="item.kind === 'milestone'"
                :variant="statusVariant(item.status)"
                :text="statusLabel(item.status)"
              />
            </div>

            <div class="rm-item__title">{{ item.title }}</div>

            <!-- Dates (FP-25 self-hide) -->
            <div
              v-if="item.target_date || item.valid_until"
              class="rm-item__dates"
            >
              <span v-if="item.target_date">
                {{ t('staff.platform.roadmap.fieldTargetDate') }}: {{ formatDate(item.target_date) }}
              </span>
              <span v-if="item.valid_until">
                {{ t('staff.platform.roadmap.fieldValidUntil') }}: {{ formatDate(item.valid_until) }}
              </span>
            </div>

            <!-- Description (FP-25 self-hide) -->
            <p v-if="item.description" class="rm-item__desc">{{ item.description }}</p>

            <!-- External URL (FP-25 self-hide) -->
            <a
              v-if="item.external_url"
              :href="item.external_url"
              target="_blank"
              rel="noopener noreferrer"
              class="rm-item__link"
            >{{ item.external_url }}</a>

            <!-- Linked post / product (FP-25 self-hide). D1 has no picker
                 UI; these only ever appear if a link was set elsewhere. -->
            <div v-if="item.post" class="rm-item__rel">
              {{ item.post.title }}
            </div>
          </div>

          <!-- Row actions (FP-23) -->
          <div v-if="canManage" class="rm-item__actions">
            <button
            :aria-label="t('common.edit')" class="rm-item__action" @click="openEdit(item)">
              <Pencil :size="16" />
            </button>
            <button
            :aria-label="t('common.delete')" class="rm-item__action" @click="openDelete(item)">
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Create / edit modal -->
    <CModal :open="showForm" @close="closeForm">
      <h3 class="scr__modal-title">
        {{ isEditing
          ? t('staff.platform.roadmap.editTitle')
          : t('staff.platform.roadmap.createTitle') }}
      </h3>

      <!-- Kind: tab strip on create, locked badge on edit -->
      <div class="scr__kind">
        <span class="scr__kind-label">{{ t('staff.platform.roadmap.kindLabel') }}</span>
        <template v-if="isEditing">
          <CBadge :variant="kindVariant(draftKind)" :text="kindLabel(draftKind)" />
          <p class="scr__kind-hint">{{ t('staff.platform.roadmap.kindLockedHint') }}</p>
        </template>
        <div v-else class="scr__kind-tabs">
          <button
            v-for="k in KIND_VALUES"
            :key="k"
            class="scr__kind-tab"
            :class="{ 'scr__kind-tab--active': draftKind === k }"
            @click="selectKind(k)"
          >{{ kindLabel(k) }}</button>
        </div>
      </div>

      <!-- Title (all kinds) -->
      <CInput
        v-model="draftTitle"
        :label="t('staff.platform.roadmap.fieldTitle')"
        :placeholder="t('staff.platform.roadmap.fieldTitle')"
      />

      <!-- Description (all kinds, optional) -->
      <CTextarea
        v-model="draftDescription"
        :label="t('staff.platform.roadmap.fieldDescription')"
        :rows="4"
      />

      <!-- Event date hint -->
      <p v-if="draftKind === 'event'" class="scr__hint">
        {{ t('staff.platform.roadmap.eventDatesHint') }}
      </p>

      <!-- Target date (milestone optional, event required) -->
      <div v-if="showTargetDate" class="scr__field">
        <label class="scr__field-label">{{ t('staff.platform.roadmap.fieldTargetDate') }}</label>
        <input
          :aria-label="t('staff.platform.roadmap.fieldTargetDate')"
          v-model="draftTargetDate"
          type="date"
          class="scr__date"
        />
      </div>

      <!-- Valid until (event only, required) -->
      <div v-if="showValidUntil" class="scr__field">
        <label class="scr__field-label">{{ t('staff.platform.roadmap.fieldValidUntil') }}</label>
        <input
          :aria-label="t('staff.platform.roadmap.fieldValidUntil')"
          v-model="draftValidUntil"
          type="date"
          class="scr__date"
        />
        <div
          v-if="draftTargetDate && draftValidUntil && !eventDatesValid"
          class="scr__field-error"
        >
          {{ t('staff.platform.roadmap.validUntilAfterTargetError') }}
        </div>
      </div>

      <!-- Status (milestone only). A completed milestone is terminal
           (R1 §5.6): the select is replaced by a read-only badge + hint
           so the locked transition can't even be attempted. -->
      <template v-if="showStatus">
        <template v-if="statusLocked">
          <div class="scr__field">
            <label class="scr__field-label">{{ t('staff.platform.roadmap.fieldStatus') }}</label>
            <CBadge :variant="statusVariant(draftStatus)" :text="statusLabel(draftStatus)" />
          </div>
          <p class="scr__hint">
            {{ t('staff.platform.roadmap.completedLockedHint') }}
          </p>
        </template>
        <CSelect
          v-else
          v-model="draftStatus"
          :label="t('staff.platform.roadmap.fieldStatus')"
          :options="statusOptions"
        />
      </template>

      <!-- External URL (all kinds, optional) -->
      <CInput
        v-model="draftExternalUrl"
        :label="t('staff.platform.roadmap.fieldExternalUrl')"
        :placeholder="t('staff.platform.roadmap.fieldExternalUrlPlaceholder')"
        :error="!externalUrlValid ? t('staff.platform.roadmap.externalUrlError') : ''"
      />

      <!-- Cover image (D2). Edit-only: a cover needs an item id, and on
           create the row does not exist yet. Operations are immediate
           (not tied to Save). FP-23: gated on canManage (the whole
           section's controls only render for managers anyway). -->
      <div class="scr__cover">
        <label class="scr__field-label">{{ t('staff.platform.roadmap.cover.label') }}</label>

        <template v-if="isEditing">
          <!-- Preview (FP-25 self-hide when no cover) -->
          <div v-if="coverPreviewUrl" class="scr__cover-preview">
            <img :src="coverPreviewUrl" alt="" class="scr__cover-img" />
          </div>

          <div class="scr__cover-actions">
            <CButton
              variant="outline"
              size="sm"
              :loading="coverUploading"
              @click="triggerCoverPicker"
            >
              <ImageUp :size="16" />
              {{ coverPreviewUrl
                ? t('staff.platform.roadmap.cover.replace')
                : t('staff.platform.roadmap.cover.upload') }}
            </CButton>
            <CButton
              v-if="coverPreviewUrl"
              variant="outline"
              size="sm"
              :loading="coverRemoving"
              @click="openCoverRemove"
            >
              <X :size="16" />
              {{ t('staff.platform.roadmap.cover.remove') }}
            </CButton>
          </div>

          <!-- Hidden native picker (no CFileInput in the kit). -->
          <input
          :aria-label="t('staff.platform.roadmap.cover.remove')"
            ref="coverInputEl"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="scr__cover-input"
            @change="onCoverSelected"
          />
        </template>

        <!-- Create mode: cover not available until the item exists. -->
        <p v-else class="scr__hint">
          {{ t('staff.platform.roadmap.cover.createFirst') }}
        </p>
      </div>

      <div class="scr__modal-actions">
        <CButton variant="outline" size="sm" @click="closeForm">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >{{ t('common.save') }}</CButton>
      </div>
    </CModal>

    <!-- Delete confirm -->
    <CModal :open="!!deleteTarget" @close="deleteTarget = null">
      <h3 class="scr__modal-title">{{ t('staff.platform.roadmap.deleteTitle') }}</h3>
      <p class="scr__modal-hint">{{ t('staff.platform.roadmap.deleteConfirm') }}</p>
      <div class="scr__modal-actions">
        <CButton variant="outline" size="sm" @click="deleteTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          :loading="deleting"
          @click="handleDelete"
        >{{ t('common.delete') }}</CButton>
      </div>
    </CModal>

    <!-- Cover remove confirm (D2) -->
    <CModal :open="!!coverRemoveTarget" @close="coverRemoveTarget = null">
      <h3 class="scr__modal-title">{{ t('staff.platform.roadmap.cover.removeTitle') }}</h3>
      <p class="scr__modal-hint">{{ t('staff.platform.roadmap.cover.removeConfirm') }}</p>
      <div class="scr__modal-actions">
        <CButton variant="outline" size="sm" @click="coverRemoveTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          :loading="coverRemoving"
          @click="handleCoverRemove"
        >{{ t('staff.platform.roadmap.cover.remove') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scr { padding: var(--space-4); }

.scr__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: 140px; gap: var(--space-4);
}

.scr__toolbar {
  display: flex; justify-content: flex-end; margin-bottom: var(--space-4);
}

/* -- List -- */
.rm-list { display: flex; flex-direction: column; gap: var(--space-3); }

.rm-item {
  display: flex; align-items: flex-start; gap: var(--space-3);
  padding: var(--space-3); background: var(--bg-subtle);
  border-radius: var(--radius-md);
}

.rm-item__reorder {
  display: flex; flex-direction: column; gap: var(--space-1); flex: 0 0 auto;
}
.rm-item__move {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 24px; border: 1px solid var(--border-default);
  border-radius: var(--radius-sm); background: var(--bg-page);
  color: var(--text-secondary); cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.rm-item__move:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.rm-item__move:disabled { opacity: 0.4; cursor: default; }

.rm-item__cover { flex: 0 0 auto; }
.rm-item__cover-img {
  width: 56px; height: 56px; object-fit: cover;
  border-radius: var(--radius-sm); display: block;
}

.rm-item__body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--space-2); }
.rm-item__badges { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.rm-item__title { font-size: var(--fs-sm); font-weight: 700; color: var(--text-primary); }
.rm-item__dates {
  display: flex; gap: var(--space-3); flex-wrap: wrap;
  font-size: var(--fs-xs); color: var(--text-secondary);
}
.rm-item__desc { font-size: var(--fs-xs-lg); color: var(--text-secondary); margin: 0; line-height: 1.4; }
.rm-item__link {
  font-size: var(--fs-xs-lg); color: var(--primary); word-break: break-all;
  text-decoration: none;
}
.rm-item__link:hover { text-decoration: underline; }
.rm-item__rel { font-size: var(--fs-xs); color: var(--text-tertiary); }

.rm-item__actions {
  display: flex; flex-direction: column; gap: var(--space-1); flex: 0 0 auto;
}
.rm-item__action {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 28px; border: none; background: transparent;
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  transition: color 0.2s, background 0.2s;
}
.rm-item__action:hover { color: var(--text-primary); background: var(--bg-page); }

/* -- Modal -- */
.scr__modal-title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-2); }
.scr__modal-hint { font-size: var(--fs-xs-lg); color: var(--text-secondary); margin: 0 0 var(--space-4); }
.scr__modal-actions { display: flex; gap: var(--space-2); margin-top: var(--space-4); justify-content: flex-end; }

.scr__hint { font-size: var(--fs-xs); color: var(--text-secondary); margin: 0 0 var(--space-4); line-height: 1.4; }

/* Kind tab strip */
.scr__kind { margin-bottom: var(--space-4); }
.scr__kind-label { display: block; font-size: var(--fs-xs-lg); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-2); }
.scr__kind-hint { font-size: var(--fs-xs); color: var(--text-secondary); margin: var(--space-2) 0 0; line-height: 1.4; }
.scr__kind-tabs { display: flex; gap: var(--space-2); }
.scr__kind-tab {
  flex: 1; padding: var(--space-3) var(--space-2); border: 2px solid var(--border-default);
  border-radius: var(--radius-md); background: var(--bg-page);
  font-size: var(--fs-xs-lg); font-weight: 600; color: var(--text-secondary);
  cursor: pointer; transition: all 0.2s;
}
.scr__kind-tab--active { border-color: var(--primary); color: var(--primary); background: var(--bg-subtle); }

/* Native date field (no CDatePicker in the kit) */
.scr__field { margin-bottom: var(--space-4); }
.scr__field-label { display: block; font-size: var(--fs-xs-lg); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-2); }
.scr__date {
  width: 100%; padding: var(--space-4) var(--space-4); border: 2px solid var(--border-default);
  border-radius: var(--radius-md); font-size: var(--fs-sm); font-family: inherit;
  background: var(--bg-page); color: var(--text-primary);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.scr__date:focus { outline: none; border-color: var(--primary); box-shadow: var(--shadow-focus); }
.scr__field-error { font-size: var(--fs-xs); color: var(--danger); margin-top: var(--space-1); }

/* Cover block (D2) */
.scr__cover { margin-bottom: var(--space-4); }
.scr__cover-preview { margin-bottom: var(--space-2); }
.scr__cover-img {
  width: 100%; max-height: 180px; object-fit: cover;
  border-radius: var(--radius-md); display: block;
}
.scr__cover-actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.scr__cover-input { display: none; }

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.rm-item__desc { max-width: var(--maxw-prose); }
.scr__hint { max-width: var(--maxw-prose); }
</style>
