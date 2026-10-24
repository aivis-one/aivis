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
// REORDER (up/down, not drag-drop -- buttons beat drag on a narrow touch
// screen and need no dependency). Each click swaps two adjacent items,
// then submits the COMPLETE id list in the new order. Per-company scope
// (NOT per-kind). The roadmap reorder endpoint's set-mismatch error has
// NO prefix (unlike attachments), so any ApiResponseError from the
// reorder is treated as a stale-list signal: toast + reload.
//
// FP-23. Every mutating CTA (add / edit / delete / reorder) is gated on
// canDo('project_manage') -- narrowed from company_manage (TASK-30 §7) --
// template guard on the control plus a defensive check in the handler.
// A staffer without project_manage still reads the list (the parent
// route only enforces requireStaff).
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

import { ref, computed, onMounted, inject, useId } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ChevronUp,
  ChevronDown,
  Pencil,
  Trash2,
  Map as MapIcon,
  ExternalLink,
  ImageUp,
  X,
} from '@/components/ui/icons'
import { CButton, CBadge, CEmptyState, CModal, CInput, CTextarea, CSelect } from '@/components/ui'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
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

// FP-23: every roadmap mutation requires project_manage.
const canManage = canDo('project_manage')

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
const coverLabelId = useId()

// Presigned URL of the current cover for the item being edited, or '' if
// none. Seeded in openEdit, updated from the upload response, cleared on
// remove. Separate from editingOriginal because reload() swaps the
// underlying roadmap array, detaching the original reference.
const coverPreviewUrl = ref('')

const coverUploading = ref(false)
const coverRemoving = ref(false)

// Remove-confirm modal target (the item id being cleared).
const coverRemoveTarget = ref<string | null>(null)

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
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="reload">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded -->
    <template v-else>
      <!-- Add CTA (FP-23) -->
      <div v-if="canManage" class="scr__toolbar">
        <CButton variant="primary" size="sm" inline @click="openCreate">
          {{ t('staff.platform.roadmap.addCta') }}
        </CButton>
      </div>

      <!-- Empty -->
      <CEmptyState v-if="!items.length" :title="t('staff.platform.roadmap.empty')">
        <template #icon>
          <MapIcon />
        </template>
      </CEmptyState>

      <!-- List (order ASC; K39: the move buttons are named by the row) -->
      <ol v-else class="ds-reorder rm-list">
        <li v-for="(item, idx) in items" :key="item.id" class="ds-reorder__item rm-item">
          <!-- Reorder (FP-23) -->
          <div v-if="canManage" class="ds-reorder__controls">
            <button
              type="button"
              class="ds-reorder__move"
              :aria-label="`${t('common.moveUp')}: ${item.title}`"
              :disabled="idx === 0 || reordering"
              @click="move(idx, -1)"
            >
              <ChevronUp />
            </button>
            <button
              type="button"
              class="ds-reorder__move"
              :aria-label="`${t('common.moveDown')}: ${item.title}`"
              :disabled="idx === items.length - 1 || reordering"
              @click="move(idx, 1)"
            >
              <ChevronDown />
            </button>
          </div>
          <span class="ds-reorder__pos" aria-hidden="true">{{ idx + 1 }}</span>

          <!-- Cover thumbnail (FP-25 self-hide): the system's thumbnail (K23), the title beside it -->
          <span v-if="item.cover_url" class="ds-thumb">
            <img :src="item.cover_url" alt="" />
          </span>

          <!-- Body -->
          <div class="ds-reorder__body">
            <span class="ds-reorder__title">{{ item.title }}</span>

            <span class="ds-reorder__meta rm-item__badges">
              <CBadge :variant="kindVariant(item.kind)" :text="kindLabel(item.kind)" />
              <CBadge
                v-if="item.kind === 'milestone'"
                :variant="statusVariant(item.status)"
                :text="statusLabel(item.status)"
              />
            </span>

            <!-- Dates (FP-25 self-hide) -->
            <span v-if="item.target_date || item.valid_until" class="ds-reorder__meta">
              <template v-if="item.target_date">
                {{ t('staff.platform.roadmap.fieldTargetDate') }}:
                {{ formatDate(item.target_date) }}
              </template>
              <template v-if="item.valid_until">
                {{ t('staff.platform.roadmap.fieldValidUntil') }}:
                {{ formatDate(item.valid_until) }}
              </template>
            </span>

            <!-- Description (FP-25 self-hide) -->
            <span v-if="item.description" class="ds-reorder__meta rm-item__desc">
              {{ item.description }}
            </span>

            <!-- External URL (FP-25 self-hide) -->
            <span v-if="item.external_url" class="ds-reorder__meta rm-item__url">
              {{ item.external_url }}
            </span>

            <!-- Linked post / product (FP-25 self-hide). D1 has no picker
                 UI; these only ever appear if a link was set elsewhere. -->
            <span v-if="item.post" class="ds-reorder__meta">
              {{ item.post.title }}
            </span>
          </div>

          <!-- The item's own acts: K39's trailing slot -->
          <div class="ds-reorder__trail">
            <a
              v-if="item.external_url"
              :href="item.external_url"
              target="_blank"
              rel="noopener noreferrer"
              class="ds-button ds-button--ghost ds-button--icon"
              data-size="sm"
              :aria-label="t('staff.platform.roadmap.fieldExternalUrl')"
            >
              <ExternalLink />
            </a>
            <!-- Row actions (FP-23) -->
            <template v-if="canManage">
              <button
                type="button"
                class="ds-button ds-button--ghost ds-button--icon"
                data-size="sm"
                :aria-label="t('common.edit')"
                @click="openEdit(item)"
              >
                <Pencil />
              </button>
              <button
                type="button"
                class="ds-button ds-button--danger ds-button--icon"
                data-size="sm"
                :aria-label="t('common.delete')"
                @click="openDelete(item)"
              >
                <Trash2 />
              </button>
            </template>
          </div>
        </li>
      </ol>
    </template>

    <!-- Create / edit modal -->
    <CModal
      :open="showForm"
      :title="
        isEditing ? t('staff.platform.roadmap.editTitle') : t('staff.platform.roadmap.createTitle')
      "
      @close="closeForm"
    >
      <!-- Kind: segmented choice on create (K31), locked badge on edit -->
      <div v-if="isEditing" class="ds-field">
        <span class="ds-field__label">{{ t('staff.platform.roadmap.kindLabel') }}</span>
        <span>
          <CBadge :variant="kindVariant(draftKind)" :text="kindLabel(draftKind)" />
        </span>
        <p class="ds-field__hint">
          {{ t('staff.platform.roadmap.kindLockedHint') }}
        </p>
      </div>
      <fieldset v-else class="ds-segmented">
        <legend class="ds-field__label">{{ t('staff.platform.roadmap.kindLabel') }}</legend>
        <label v-for="k in KIND_VALUES" :key="k" class="ds-segmented__option">
          <input
            class="ds-segmented__input"
            type="radio"
            name="scr-kind"
            :value="k"
            :checked="draftKind === k"
            @change="selectKind(k)"
          />
          {{ kindLabel(k) }}
        </label>
      </fieldset>

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
      <p v-if="draftKind === 'event'" class="ds-dialog__text">
        {{ t('staff.platform.roadmap.eventDatesHint') }}
      </p>

      <!-- Target date (milestone optional, event required): the date input, K29 -->
      <CInput
        v-if="showTargetDate"
        v-model="draftTargetDate"
        :label="t('staff.platform.roadmap.fieldTargetDate')"
        type="date"
      />

      <!-- Valid until (event only, required) -->
      <CInput
        v-if="showValidUntil"
        v-model="draftValidUntil"
        :label="t('staff.platform.roadmap.fieldValidUntil')"
        type="date"
        :error="
          draftTargetDate && draftValidUntil && !eventDatesValid
            ? t('staff.platform.roadmap.validUntilAfterTargetError')
            : ''
        "
      />

      <!-- Status (milestone only). A completed milestone is terminal
           (R1 §5.6): the select is replaced by a read-only badge + hint
           so the locked transition can't even be attempted. -->
      <template v-if="showStatus">
        <template v-if="statusLocked">
          <div class="ds-field">
            <span class="ds-field__label">{{ t('staff.platform.roadmap.fieldStatus') }}</span>
            <span>
              <CBadge :variant="statusVariant(draftStatus)" :text="statusLabel(draftStatus)" />
            </span>
            <p class="ds-field__hint">
              {{ t('staff.platform.roadmap.completedLockedHint') }}
            </p>
          </div>
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

      <!-- Cover image (D2), the file input K30. Edit-only: a cover needs an item id,
           and on create the row does not exist yet. Operations are immediate
           (not tied to Save). FP-23: gated on canManage (the whole
           section's controls only render for managers anyway). -->
      <div v-if="isEditing" class="ds-field ds-file" :aria-busy="coverUploading || undefined">
        <span :id="coverLabelId" class="ds-field__label">
          {{ t('staff.platform.roadmap.cover.label') }}
        </span>
        <label class="ds-button ds-button--secondary ds-file__pick">
          <ImageUp size="sm" />
          <span>
            {{
              coverPreviewUrl
                ? t('staff.platform.roadmap.cover.replace')
                : t('staff.platform.roadmap.cover.upload')
            }}
          </span>
          <input
            class="ds-file__input"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :aria-labelledby="coverLabelId"
            :disabled="coverUploading"
            @change="onCoverSelected"
          />
        </label>
        <!-- Preview (FP-25 self-hide when no cover) -->
        <ul class="ds-file__list" aria-live="polite">
          <li v-if="coverPreviewUrl" class="ds-file__item" data-state="done">
            <span class="ds-file__thumb"><img :src="coverPreviewUrl" alt="" /></span>
            <span class="ds-file__body">
              <span class="ds-file__name">{{ t('staff.platform.roadmap.cover.label') }}</span>
            </span>
            <span class="ds-file__aside">
              <button
                type="button"
                class="ds-file__remove"
                :aria-label="t('staff.platform.roadmap.cover.remove')"
                :disabled="coverRemoving"
                @click="openCoverRemove"
              >
                <X size="sm" />
              </button>
            </span>
          </li>
        </ul>
      </div>

      <!-- Create mode: cover not available until the item exists. -->
      <div v-else class="ds-field">
        <span class="ds-field__label">{{ t('staff.platform.roadmap.cover.label') }}</span>
        <p class="ds-field__hint">
          {{ t('staff.platform.roadmap.cover.createFirst') }}
        </p>
      </div>

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="closeForm">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="saving"
          :disabled="!canSubmit"
          @click="handleSave"
        >
          {{ t('common.save') }}
        </CButton>
      </div>
    </CModal>

    <!-- Delete confirm -->
    <CModal
      :open="!!deleteTarget"
      :title="t('staff.platform.roadmap.deleteTitle')"
      @close="deleteTarget = null"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.roadmap.deleteConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="deleteTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" inline :loading="deleting" @click="handleDelete">
          {{ t('common.delete') }}
        </CButton>
      </div>
    </CModal>

    <!-- Cover remove confirm (D2) -->
    <CModal
      :open="!!coverRemoveTarget"
      :title="t('staff.platform.roadmap.cover.removeTitle')"
      @close="coverRemoveTarget = null"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.roadmap.cover.removeConfirm') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="coverRemoveTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="danger"
          size="sm"
          inline
          :loading="coverRemoving"
          @click="handleCoverRemove"
        >
          {{ t('staff.platform.roadmap.cover.remove') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scr {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.scr__toolbar {
  display: flex;
  justify-content: flex-end;
}

/* The badges sit in a line under the title. */
.rm-item__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.rm-item__desc {
  max-inline-size: var(--maxw-prose);
}
.rm-item__desc,
.rm-item__url {
  overflow-wrap: anywhere;
}
</style>
