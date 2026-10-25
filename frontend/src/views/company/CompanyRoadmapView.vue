<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyRoadmapView (TASK-30 self-service)
// =============================================================================
//
// Roadmap CRUD + reorder for the CALLER'S OWN company (TASK-30-SPEC.md
// §4: "roadmap items" is listed under the set of things a project may
// edit about itself). Adapted from
// views/staff/platform/StaffCompanyRoadmapSection.vue -- same per-kind
// form logic, validation, milestone state machine, and cover-upload
// flow -- but:
//   - wired to api/company-roadmap.ts (companyId-free endpoints) instead
//     of api/staff-companies.ts's {companyId}-scoped ones;
//   - owns its OWN fetch/loading/error state (GET /company/roadmap)
//     instead of injecting a parent detail view's context -- there is no
//     company-side equivalent of StaffCompanyDetailView, and building one
//     just to host this list would be scope creep for a single section;
//   - drops the FP-23 `canDo('project_manage')` staff-permission gate --
//     every authenticated company user IS the project, backend
//     enforcement is get_current_company_profile (role=company), so
//     there is no separate "manage" permission to check on this side of
//     the fence, unlike a staff operator who may or may not hold
//     project_manage.
//
// WHERE THIS LIVES.
//   Reached from Settings (CompanySettingsView's new "Roadmap" row)
//   rather than a bottom tab -- COMPANY_TABS already has 5 fixed slots
//   (home/products/analytics/balance/settings) and roadmap management is
//   an occasional task, not a daily one, same tier as "edit profile via
//   support" used to be before this feature existed. Route:
//   /company/roadmap (router/index.ts, name 'company-roadmap').
//
// PER-KIND RULES / MILESTONE STATE MACHINE / REORDER SEMANTICS: see
// StaffCompanyRoadmapSection.vue's header comment -- identical rules,
// enforced by the SAME backend schema (CreateRoadmapItemRequest /
// UpdateRoadmapItemRequest, companies/schemas.py) reused as-is for this
// surface.
//
// LANGUAGES (H38 P-132): title and description are edited in every language
// of the interface (English the base, required), the cover per version --
// the common file or one language's variant (MediaLanguageSelect). The form
// starts from the item's base and translations, not the displayed texts.
// =============================================================================

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronUp, ChevronDown, Pencil, Trash2, Map as MapIcon } from '@/components/ui/icons'
import { CButton, CBadge, CEmptyState, CModal, CInput, CSelect } from '@/components/ui'
import MediaLanguageSelect from '@/components/shared/MediaLanguageSelect.vue'
import LocalizedTextFields from '@/components/shared/LocalizedTextFields.vue'
import type { LocalizedField } from '@/components/shared/LocalizedTextFields.vue'
import {
  BASE_LANGUAGE,
  baseText,
  emptyDraft,
  imageIn,
  makeDraft,
  sameTranslations,
  translationsFromDraft,
  variantLanguage,
} from '@/utils/projectTexts'
import type { TextDraft } from '@/utils/projectTexts'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CFileField from '@/components/ui/CFileField.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import {
  fetchOwnRoadmap,
  createOwnRoadmapItem,
  updateOwnRoadmapItem,
  deleteOwnRoadmapItem,
  reorderOwnRoadmap,
  uploadOwnRoadmapCover,
  deleteOwnRoadmapCover,
} from '@/api/company-roadmap'
import type {
  RoadmapItemResponse,
  RoadmapItemKind,
  CreateRoadmapItemRequest,
  UpdateRoadmapItemRequest,
} from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const { t } = useI18n()
const { showToast } = useToast()

// The frame's header carries the title, the line under it and the way back to Publications.
useScreenHeader({
  title: () => t('comp.roadmap.title'),
  lead: () => t('comp.roadmap.subtitle'),
  back: '/company/publications',
})

// ---------------------------------------------------------------------------
// Data source -- own fetch, own loading/error state (no parent context)
// ---------------------------------------------------------------------------

const rawItems = ref<RoadmapItemResponse[]>([])
const loading = ref(true)
const errored = ref(false)

// Sorted view (order ASC). The backend returns it ordered already; sort
// defensively so a reorder race can't briefly show rows out of sequence.
const items = computed<RoadmapItemResponse[]>(() =>
  [...rawItems.value].sort((a, b) => a.order - b.order),
)

async function reload(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    rawItems.value = await fetchOwnRoadmap()
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => reload())

onMounted(() => {
  void reload()
})

// ---------------------------------------------------------------------------
// Kind + status value lists
// ---------------------------------------------------------------------------

const KIND_VALUES = ['milestone', 'event', 'announcement'] as const
const STATUS_VALUES = ['planned', 'in_progress', 'completed'] as const

function kindLabel(kind: string): string {
  switch (kind) {
    case 'milestone':
      return t('comp.roadmap.kindMilestone')
    case 'event':
      return t('comp.roadmap.kindEvent')
    case 'announcement':
      return t('comp.roadmap.kindAnnouncement')
    default:
      return kind
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'planned':
      return t('comp.roadmap.statusPlanned')
    case 'in_progress':
      return t('comp.roadmap.statusInProgress')
    case 'completed':
      return t('comp.roadmap.statusCompleted')
    default:
      return status
  }
}

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

const statusOptions = computed<{ value: string; label: string }[]>(() =>
  STATUS_VALUES.map((s) => ({ value: s, label: statusLabel(s) })),
)

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(`${iso}T00:00:00`).toLocaleDateString()
}

// ---------------------------------------------------------------------------
// Create / edit modal
// ---------------------------------------------------------------------------

const showForm = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)

const draftKind = ref<RoadmapItemKind>('milestone')
const TEXT_FIELDS = ['title', 'description'] as const
const draftTexts = ref<TextDraft>(emptyDraft(TEXT_FIELDS))
const textFields = computed<LocalizedField[]>(() => [
  { key: 'title', label: t('comp.roadmap.fieldTitle'), maxlength: 500 },
  {
    key: 'description',
    label: t('comp.roadmap.fieldDescription'),
    multiline: true,
    rows: 4,
    maxlength: 5000,
  },
])
const draftTargetDate = ref('')
const draftValidUntil = ref('')
const draftStatus = ref<string>('planned')
const draftExternalUrl = ref('')

const editingOriginal = ref<RoadmapItemResponse | null>(null)

const isEditing = computed<boolean>(() => editingId.value !== null)

const showTargetDate = computed<boolean>(
  () => draftKind.value === 'milestone' || draftKind.value === 'event',
)
const showValidUntil = computed<boolean>(() => draftKind.value === 'event')
const showStatus = computed<boolean>(() => draftKind.value === 'milestone')

const statusLocked = computed<boolean>(
  () =>
    isEditing.value &&
    draftKind.value === 'milestone' &&
    editingOriginal.value?.status === 'completed',
)

function resetDraft(kind: RoadmapItemKind): void {
  draftKind.value = kind
  draftTexts.value = emptyDraft(TEXT_FIELDS)
  draftTargetDate.value = ''
  draftValidUntil.value = ''
  draftStatus.value = 'planned'
  draftExternalUrl.value = ''
}

function selectKind(kind: RoadmapItemKind): void {
  if (isEditing.value) return
  if (kind === draftKind.value) return
  resetDraft(kind)
}

function openCreate(): void {
  editingId.value = null
  editingOriginal.value = null
  coverVariants.value = null
  resetDraft('milestone')
  showForm.value = true
}

function openEdit(item: RoadmapItemResponse): void {
  editingId.value = item.id
  editingOriginal.value = item
  coverVariants.value = item.image_variants
  coverLanguage.value = BASE_LANGUAGE
  draftKind.value = item.kind as RoadmapItemKind
  draftTexts.value = makeDraft(TEXT_FIELDS, item.base, item.translations)
  draftTargetDate.value = item.target_date ?? ''
  draftValidUntil.value = item.valid_until ?? ''
  draftStatus.value = item.status || 'planned'
  draftExternalUrl.value = item.external_url ?? ''
  showForm.value = true
}

function closeForm(): void {
  showForm.value = false
}

const trimmedTitle = computed<string>(() => baseText(draftTexts.value, 'title').trim())
const trimmedExternalUrl = computed<string>(() => draftExternalUrl.value.trim())

const externalUrlValid = computed<boolean>(() => {
  const v = trimmedExternalUrl.value
  if (!v) return true
  return v.startsWith('http://') || v.startsWith('https://')
})

const eventDatesValid = computed<boolean>(() => {
  if (draftKind.value !== 'event') return true
  if (!draftTargetDate.value || !draftValidUntil.value) return false
  return draftValidUntil.value > draftTargetDate.value
})

const canSubmit = computed<boolean>(() => {
  if (!trimmedTitle.value) return false
  if (!externalUrlValid.value) return false
  if (draftKind.value === 'event') {
    if (!eventDatesValid.value) return false
  }
  return true
})

function buildCreateBody(): CreateRoadmapItemRequest {
  const body: CreateRoadmapItemRequest = {
    kind: draftKind.value,
    title: trimmedTitle.value,
  }
  const desc = baseText(draftTexts.value, 'description').trim()
  if (desc) body.description = desc
  const translations = translationsFromDraft(draftTexts.value, TEXT_FIELDS, {})
  if (Object.keys(translations).length > 0) body.translations = translations
  if (trimmedExternalUrl.value) body.external_url = trimmedExternalUrl.value

  if (draftKind.value === 'milestone') {
    if (draftTargetDate.value) body.target_date = draftTargetDate.value
    if (draftStatus.value && draftStatus.value !== 'planned') {
      body.status = draftStatus.value
    }
  } else if (draftKind.value === 'event') {
    body.target_date = draftTargetDate.value
    body.valid_until = draftValidUntil.value
  }
  return body
}

function buildUpdateBody(): UpdateRoadmapItemRequest {
  const orig = editingOriginal.value
  const body: UpdateRoadmapItemRequest = {}
  if (!orig) return body

  // Against the English base, not the displayed (reader's) texts.
  if (trimmedTitle.value !== (orig.base?.title ?? '')) {
    body.title = trimmedTitle.value
  }

  const desc = baseText(draftTexts.value, 'description').trim()
  const origDesc = orig.base?.description ?? ''
  if (desc !== origDesc) {
    body.description = desc ? desc : null
  }

  const translations = translationsFromDraft(draftTexts.value, TEXT_FIELDS, orig.translations)
  if (!sameTranslations(translations, orig.translations)) {
    body.translations = translations
  }

  const url = trimmedExternalUrl.value
  const origUrl = orig.external_url ?? ''
  if (url !== origUrl) {
    body.external_url = url ? url : null
  }

  if (draftKind.value === 'milestone' || draftKind.value === 'event') {
    const td = draftTargetDate.value
    const origTd = orig.target_date ?? ''
    if (td !== origTd) {
      body.target_date = td ? td : null
    }
  }

  if (draftKind.value === 'event') {
    const vu = draftValidUntil.value
    const origVu = orig.valid_until ?? ''
    if (vu !== origVu) {
      body.valid_until = vu ? vu : null
    }
  }

  if (draftKind.value === 'milestone' && !statusLocked.value) {
    const origStatus = orig.status ?? 'planned'
    if (draftStatus.value !== origStatus) {
      body.status = draftStatus.value
    }
  }

  return body
}

async function handleSave(): Promise<void> {
  if (!canSubmit.value) return

  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      const body = buildUpdateBody()
      if (Object.keys(body).length === 0) {
        showForm.value = false
        return
      }
      await updateOwnRoadmapItem(editingId.value, body)
      showToast(t('comp.roadmap.updated'), 'success')
    } else {
      await createOwnRoadmapItem(buildCreateBody())
      showToast(t('comp.roadmap.created'), 'success')
    }
    showForm.value = false
    await reload()
  } catch (e) {
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

async function move(index: number, delta: number): Promise<void> {
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
    await reorderOwnRoadmap({ item_ids: ids })
    await reload()
  } catch (e) {
    if (e instanceof ApiResponseError) {
      showToast(t('comp.roadmap.reorderStale'), 'error')
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
  deleteTarget.value = item
}

async function handleDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteOwnRoadmapItem(deleteTarget.value.id)
    showToast(t('comp.roadmap.deleted'), 'success')
    deleteTarget.value = null
    await reload()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

// ---------------------------------------------------------------------------
// Cover image
// ---------------------------------------------------------------------------

const COVER_MIME_WHITELIST = ['image/png', 'image/jpeg', 'image/webp'] as const
const COVER_MAX_BYTES = 10 * 1024 * 1024 // 10 MiB, mirrors backend cap

// The covers of the item being edited per language ("en" = the common file,
// H38) and the version edited.
const coverVariants = ref<unknown>(null)
const coverLanguage = ref<string>(BASE_LANGUAGE)
const coverPreviewUrl = computed<string>(
  () => imageIn(coverVariants.value, coverLanguage.value, 'cover_url') ?? '',
)

function dropCoverVariant(): void {
  const variants = { ...((coverVariants.value ?? {}) as Record<string, unknown>) }
  delete variants[coverLanguage.value]
  coverVariants.value = variants
}

const coverUploading = ref(false)
const coverRemoving = ref(false)
const coverRemoveTarget = ref<string | null>(null)

async function onCoverSelected(file: File): Promise<void> {
  if (!editingId.value) return

  if (!(COVER_MIME_WHITELIST as readonly string[]).includes(file.type)) {
    showToast(t('comp.roadmap.cover.errorMime'), 'error')
    return
  }
  if (file.size > COVER_MAX_BYTES) {
    showToast(t('comp.roadmap.cover.errorSize'), 'error')
    return
  }

  coverUploading.value = true
  try {
    const updated = await uploadOwnRoadmapCover(
      editingId.value,
      file,
      variantLanguage(coverLanguage.value),
    )
    coverVariants.value = updated.image_variants
    showToast(t('comp.roadmap.cover.uploaded'), 'success')
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
  if (!editingId.value) return
  coverRemoveTarget.value = editingId.value
}

async function handleCoverRemove(): Promise<void> {
  if (!coverRemoveTarget.value) return
  coverRemoving.value = true
  try {
    await deleteOwnRoadmapCover(coverRemoveTarget.value, variantLanguage(coverLanguage.value))
    dropCoverVariant()
    coverRemoveTarget.value = null
    showToast(t('comp.roadmap.cover.removed'), 'success')
    await reload()
  } catch (e) {
    if (e instanceof ApiResponseError && e.status === 404) {
      dropCoverVariant()
      coverRemoveTarget.value = null
      await reload()
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    coverRemoving.value = false
  }
}
</script>

<template>
  <!-- Loading -->
  <CListSkeleton v-if="loading" />

  <!-- Error -->
  <CEmptyState v-else-if="errored" tone="danger" :title="t('comp.roadmap.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="reload">
        {{ t('comp.roadmap.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else>
    <div class="ds-shell__toolbar">
      <div class="ds-shell__primary">
        <CButton variant="primary" size="sm" inline @click="openCreate">
          {{ t('comp.roadmap.addCta') }}
        </CButton>
      </div>
    </div>

    <CEmptyState v-if="!items.length" :title="t('comp.roadmap.empty')">
      <template #icon>
        <MapIcon />
      </template>
    </CEmptyState>

    <!-- Reorder list (K39): the move pair at the start, the item's edit and delete at the end -->
    <ol v-else class="ds-reorder" :aria-label="t('comp.roadmap.title')">
      <li v-for="(item, idx) in items" :key="item.id" class="ds-reorder__item">
        <div class="ds-reorder__controls">
          <button
            type="button"
            class="ds-reorder__move"
            :aria-label="`${t('common.moveUp')}: ${item.title}`"
            :disabled="idx === 0 || reordering"
            @click="move(idx, -1)"
          >
            <ChevronUp size="sm" />
          </button>
          <button
            type="button"
            class="ds-reorder__move"
            :aria-label="`${t('common.moveDown')}: ${item.title}`"
            :disabled="idx === items.length - 1 || reordering"
            @click="move(idx, 1)"
          >
            <ChevronDown size="sm" />
          </button>
        </div>
        <span class="ds-reorder__pos" aria-hidden="true">{{ idx + 1 }}</span>

        <span v-if="item.cover_url" class="ds-thumb"><img :src="item.cover_url" alt="" /></span>

        <div class="ds-reorder__body">
          <span class="ds-reorder__meta">
            <CBadge :variant="kindVariant(item.kind)" :text="kindLabel(item.kind)" />
            <CBadge
              v-if="item.kind === 'milestone'"
              :variant="statusVariant(item.status)"
              :text="statusLabel(item.status)"
            />
          </span>
          <span class="ds-reorder__title">{{ item.title }}</span>
          <span v-if="item.target_date || item.valid_until" class="ds-reorder__meta">
            <template v-if="item.target_date">
              {{ t('comp.roadmap.fieldTargetDate') }}: {{ formatDate(item.target_date) }}
            </template>
            <template v-if="item.valid_until">
              {{ t('comp.roadmap.fieldValidUntil') }}: {{ formatDate(item.valid_until) }}
            </template>
          </span>
          <span v-if="item.description" class="ds-reorder__meta">{{ item.description }}</span>
          <span v-if="item.external_url" class="ds-reorder__meta">
            <a :href="item.external_url" target="_blank" rel="noopener noreferrer">{{
              item.external_url
            }}</a>
          </span>
          <span v-if="item.post" class="ds-reorder__meta">{{ item.post.title }}</span>
        </div>

        <div class="ds-reorder__trail">
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="`${t('common.edit')}: ${item.title}`"
            @click="openEdit(item)"
          >
            <Pencil size="sm" />
          </button>
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="`${t('common.delete')}: ${item.title}`"
            @click="openDelete(item)"
          >
            <Trash2 size="sm" />
          </button>
        </div>
      </li>
    </ol>
  </template>

  <!-- Create / edit modal -->
  <CModal
    :open="showForm"
    :title="isEditing ? t('comp.roadmap.editTitle') : t('comp.roadmap.createTitle')"
    @close="closeForm"
  >
    <fieldset v-if="isEditing" class="ds-fieldset">
      <legend class="ds-fieldset__legend">{{ t('comp.roadmap.kindLabel') }}</legend>
      <div>
        <CBadge :variant="kindVariant(draftKind)" :text="kindLabel(draftKind)" />
      </div>
      <p class="ds-field__hint">
        {{ t('comp.roadmap.kindLockedHint') }}
      </p>
    </fieldset>
    <fieldset v-else class="ds-segmented">
      <legend class="ds-sr-only">{{ t('comp.roadmap.kindLabel') }}</legend>
      <label v-for="k in KIND_VALUES" :key="k" class="ds-segmented__option">
        <input
          class="ds-segmented__input"
          type="radio"
          name="croad-kind"
          :value="k"
          :checked="draftKind === k"
          @change="selectKind(k)"
        />
        {{ kindLabel(k) }}
      </label>
    </fieldset>

    <LocalizedTextFields v-model="draftTexts" :fields="textFields" />

    <p v-if="draftKind === 'event'" class="ds-field__hint">
      {{ t('comp.roadmap.eventDatesHint') }}
    </p>

    <!-- The dates are the Date picker (K29); a period is two inputs, the second's min is the first -->
    <CInput
      v-if="showTargetDate"
      v-model="draftTargetDate"
      :label="t('comp.roadmap.fieldTargetDate')"
      type="date"
    />

    <CInput
      v-if="showValidUntil"
      v-model="draftValidUntil"
      :label="t('comp.roadmap.fieldValidUntil')"
      type="date"
      :min="draftTargetDate || undefined"
      :error="
        draftTargetDate && draftValidUntil && !eventDatesValid
          ? t('comp.roadmap.validUntilAfterTargetError')
          : ''
      "
    />

    <template v-if="showStatus">
      <fieldset v-if="statusLocked" class="ds-fieldset">
        <legend class="ds-fieldset__legend">{{ t('comp.roadmap.fieldStatus') }}</legend>
        <div>
          <CBadge :variant="statusVariant(draftStatus)" :text="statusLabel(draftStatus)" />
        </div>
        <p class="ds-field__hint">
          {{ t('comp.roadmap.completedLockedHint') }}
        </p>
      </fieldset>
      <CSelect
        v-else
        v-model="draftStatus"
        :label="t('comp.roadmap.fieldStatus')"
        :options="statusOptions"
      />
    </template>

    <CInput
      v-model="draftExternalUrl"
      :label="t('comp.roadmap.fieldExternalUrl')"
      :placeholder="t('comp.roadmap.fieldExternalUrlPlaceholder')"
      :error="!externalUrlValid ? t('comp.roadmap.externalUrlError') : ''"
    />

    <!-- The cover image (K30), added to a saved item; per version (H38) -->
    <MediaLanguageSelect v-if="isEditing" v-model="coverLanguage" />
    <CFileField
      v-if="isEditing"
      :label="t('comp.roadmap.cover.label')"
      :button-label="
        coverPreviewUrl ? t('comp.roadmap.cover.replace') : t('comp.roadmap.cover.upload')
      "
      accept="image/png,image/jpeg,image/webp"
      :hint="t('comp.roadmap.cover.hint')"
      :current="coverPreviewUrl ? t('comp.roadmap.cover.label') : undefined"
      :preview="coverPreviewUrl || undefined"
      :busy="coverUploading || coverRemoving"
      removable
      @select="onCoverSelected"
      @remove="openCoverRemove"
    />
    <p v-else class="ds-field__hint">
      {{ t('comp.roadmap.cover.createFirst') }}
    </p>

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
    :title="t('comp.roadmap.deleteTitle')"
    @close="deleteTarget = null"
  >
    <p class="ds-dialog__text">
      {{ t('comp.roadmap.deleteConfirm') }}
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

  <!-- Cover remove confirm -->
  <CModal
    :open="!!coverRemoveTarget"
    :title="t('comp.roadmap.cover.removeTitle')"
    @close="coverRemoveTarget = null"
  >
    <p class="ds-dialog__text">
      {{ t('comp.roadmap.cover.removeConfirm') }}
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
        {{ t('comp.roadmap.cover.remove') }}
      </CButton>
    </div>
  </CModal>
</template>
