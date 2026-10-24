<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyAttachmentsView (TASK-30 self-service)
// =============================================================================
//
// Attachment (document) upload / edit / reorder / soft-delete for the
// CALLER'S OWN company (TASK-30-SPEC.md §4: "attachments / images" is
// listed under the set of things a project may edit about itself).
// Adapted from views/staff/platform/StaffCompanyDocumentsSection.vue
// (grouping-by-category, up/down reorder, soft-delete) but:
//   - wired to api/company-attachments.ts (companyId-free endpoints)
//     instead of api/staff-companies.ts's {companyId}-scoped ones;
//   - owns its own fetch/loading/error state, same reasoning as
//     CompanyRoadmapView.vue (no company-side equivalent of
//     StaffCompanyDetailView to inject from);
//   - drops the FP-23 `canDo('project_manage')` staff-permission gate --
//     every authenticated company user IS the project;
//   - ADDS a real upload control. StaffCompanyDocumentsSection.vue's
//     header comment says the MVP deliberately ships "NO file upload...
//     uploads go through the MinIO Web UI + reconcile" for STAFF. That
//     was a staff-tooling scoping call, not a statement that uploads are
//     unsafe or unwanted -- TASK-30's ruling is that a PROJECT can write
//     its own attachments now, which is a broader grant than what
//     staff's own UI currently exposes. Without an upload control here,
//     the backend half of this feature (attachments_company_router.py)
//     would be unreachable from the product a project actually uses, so
//     this view is the first real upload control shipped anywhere in
//     this codebase for this resource (mirrors the roadmap cover upload
//     control's multipart pattern, which predates this view).
//
// WHERE THIS LIVES.
//   Reached from Settings (CompanySettingsView's "Attachments" row),
//   same placement reasoning as the roadmap link: COMPANY_TABS already
//   has 5 fixed slots and document management is occasional, not daily.
//   Route: /company/attachments (router/index.ts, name
//   'company-attachments').
//
// CATEGORY / MIME / SIZE RULES: see companies/constants.py
// (ATTACHMENT_CATEGORY_REGEX, ALLOWED_ATTACHMENT_MIME_TYPES) and
// attachments_company_router.py's docstring -- identical rules to the
// staff surface, enforced server-side. The 100MB cap is Nginx's job
// (client_max_body_size), not app code's, so there is no client-side
// size check to mirror here (unlike the 10MiB roadmap cover cap, which
// the app enforces itself before Nginx would ever see the request).
// =============================================================================

import { ref, computed, onMounted, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  ChevronUp,
  ChevronDown,
  Pencil,
  Trash2,
  FileText,
  Download,
  Upload,
} from '@/components/ui/icons'
import {
  CButton,
  CBadge,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CSelect,
  CCheckbox,
} from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CActionMenu from '@/components/ui/CActionMenu.vue'
import type { ActionMenuItem } from '@/components/ui/CActionMenu.vue'
import CFileField from '@/components/ui/CFileField.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import { downloadAttachment } from '@/api/attachments'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import {
  fetchOwnAttachments,
  createOwnAttachment,
  updateOwnAttachment,
  replaceOwnAttachmentFile,
  deleteOwnAttachment,
  reorderOwnAttachments,
} from '@/api/company-attachments'
import type { AttachmentUploadMetadata } from '@/api/company-attachments'
import type { AttachmentPatchBody, AttachmentResponse } from '@/api/types'

const { t } = useI18n()
const profileStore = useCompanyProfileStore()
const { showToast } = useToast()
const categoryId = useId()

// The frame's header carries the title, the line under it and the way back to Publications.
useScreenHeader({
  title: () => t('comp.attachments.title'),
  lead: () => t('comp.attachments.subtitle'),
  back: '/company/publications',
})

// File types accepted by the picker, mirroring
// companies/constants.py::ALLOWED_ATTACHMENT_MIME_TYPES by extension.
// The real gate is server-side (extension-based MIME validation); this
// is only a UI hint that filters the OS file picker.
const FILE_ACCEPT = '.pdf,.pptx,.docx,.xlsx,.png,.jpg,.jpeg,.webp,.gif,.svg,.mp4,.webm,.txt,.md'

// A document is kept in the two languages the cabinet's documents ship in. An
// older file that carries another language keeps it until it is edited.
const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'EN' },
  { value: 'ru', label: 'RU' },
]

const languageOptions = computed(() => {
  const current = draftLanguage.value
  return LANGUAGE_OPTIONS.some((o) => o.value === current)
    ? LANGUAGE_OPTIONS
    : [...LANGUAGE_OPTIONS, { value: current, label: current.toUpperCase() }]
})

// Opening one's own file: the published ones are served by the same download
// link a buyer gets. A file that is not published yet has no link to open.
async function openFile(att: AttachmentResponse): Promise<void> {
  const id = profileStore.profile?.id
  if (!id) return
  try {
    await downloadAttachment(id, att.id)
  } catch {
    showToast(t('comp.attachments.downloadError'), 'error')
  }
}

// Mirrors backend ATTACHMENT_CATEGORY_REGEX (companies/constants.py):
// lowercase path-tree, '/'-separated, up to 5 levels.
const CATEGORY_PATTERN = /^[a-z0-9_-]+(\/[a-z0-9_-]+){0,4}$/

// ---------------------------------------------------------------------------
// Data source -- own fetch, own loading/error state
// ---------------------------------------------------------------------------

const rawItems = ref<AttachmentResponse[]>([])
const loading = ref(true)
const errored = ref(false)

async function reload(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    rawItems.value = await fetchOwnAttachments()
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void reload()
  void profileStore.loadIfMissing()
})

// Group by category, preserving the backend's per-category order (it
// returns rows sorted category ASC, order ASC). Map keeps insertion
// order, so categories render in first-seen order -- same pattern as
// StaffCompanyDocumentsSection.vue.
const grouped = computed<{ category: string; rows: AttachmentResponse[] }[]>(() => {
  const map = new Map<string, AttachmentResponse[]>()
  for (const att of rawItems.value) {
    const arr = map.get(att.category)
    if (arr) arr.push(att)
    else map.set(att.category, [att])
  }
  return Array.from(map.entries()).map(([category, rows]) => ({ category, rows }))
})

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ---------------------------------------------------------------------------
// Create / edit modal
// ---------------------------------------------------------------------------

const showForm = ref(false)
const editingId = ref<string | null>(null)
const editingOriginal = ref<AttachmentResponse | null>(null)
const saving = ref(false)

const draftTitle = ref('')
const draftDescription = ref('')
const draftCategory = ref('unsorted')
const draftLanguage = ref('en')
const draftIsPublished = ref(false)
const draftIsPublic = ref(false)

const isEditing = computed<boolean>(() => editingId.value !== null)

// File picked for a NEW attachment (required on create). Replacing the
// file of an EXISTING attachment is a separate control (the second
// CFileField) since the backend treats it as a distinct endpoint that
// leaves metadata untouched.
const selectedFile = ref<File | null>(null)

function resetDraft(): void {
  draftTitle.value = ''
  draftDescription.value = ''
  draftCategory.value = 'unsorted'
  draftLanguage.value = 'en'
  draftIsPublished.value = false
  draftIsPublic.value = false
  selectedFile.value = null
}

function openCreate(): void {
  editingId.value = null
  editingOriginal.value = null
  resetDraft()
  showForm.value = true
}

function openEdit(att: AttachmentResponse): void {
  editingId.value = att.id
  editingOriginal.value = att
  draftTitle.value = att.title
  draftDescription.value = att.description ?? ''
  draftCategory.value = att.category
  draftLanguage.value = att.language
  draftIsPublished.value = att.is_published
  draftIsPublic.value = att.is_public
  selectedFile.value = null
  showForm.value = true
}

function closeForm(): void {
  showForm.value = false
}

const trimmedTitle = computed<string>(() => draftTitle.value.trim())
const trimmedCategory = computed<string>(() => draftCategory.value.trim())
const categoryValid = computed<boolean>(() => CATEGORY_PATTERN.test(trimmedCategory.value))

const canSubmit = computed<boolean>(() => {
  if (!trimmedTitle.value) return false
  if (!categoryValid.value) return false
  if (!isEditing.value && !selectedFile.value) return false
  return true
})

function buildCreateMetadata(): AttachmentUploadMetadata {
  const meta: AttachmentUploadMetadata = {
    title: trimmedTitle.value,
    category: trimmedCategory.value,
    language: draftLanguage.value,
    is_published: draftIsPublished.value,
    is_public: draftIsPublic.value,
  }
  const desc = draftDescription.value.trim()
  if (desc) meta.description = desc
  return meta
}

function buildPatchBody(): AttachmentPatchBody {
  const orig = editingOriginal.value
  const body: AttachmentPatchBody = {}
  if (!orig) return body

  if (trimmedTitle.value !== orig.title) body.title = trimmedTitle.value

  const desc = draftDescription.value.trim()
  const origDesc = orig.description ?? ''
  if (desc !== origDesc) body.description = desc ? desc : null

  if (trimmedCategory.value !== orig.category) body.category = trimmedCategory.value
  if (draftLanguage.value !== orig.language) {
    // LANGUAGE_OPTIONS is drawn from AttachmentPatchBody's own literal
    // union (en/ru/de/ar), so this cast just reasserts what the select
    // control already constrains at the UI layer.
    body.language = draftLanguage.value as AttachmentPatchBody['language']
  }
  if (draftIsPublished.value !== orig.is_published) body.is_published = draftIsPublished.value
  if (draftIsPublic.value !== orig.is_public) body.is_public = draftIsPublic.value

  return body
}

async function handleSave(): Promise<void> {
  if (!canSubmit.value) return

  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      const body = buildPatchBody()
      if (Object.keys(body).length > 0) {
        await updateOwnAttachment(editingId.value, body)
      }
      showToast(t('comp.attachments.updated'), 'success')
    } else if (selectedFile.value) {
      await createOwnAttachment(buildCreateMetadata(), selectedFile.value)
      showToast(t('comp.attachments.created'), 'success')
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
// Replace file (existing attachment only)
// ---------------------------------------------------------------------------

const replacing = ref(false)

async function onReplaceSelected(file: File): Promise<void> {
  if (!editingId.value) return

  replacing.value = true
  try {
    const updated = await replaceOwnAttachmentFile(editingId.value, file)
    editingOriginal.value = updated
    showToast(t('comp.attachments.fileReplaced'), 'success')
    await reload()
  } catch (e2) {
    if (e2 instanceof ApiResponseError && e2.detail) {
      showToast(e2.detail, 'error')
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    replacing.value = false
  }
}

// ---------------------------------------------------------------------------
// Reorder via up/down (scoped within one category)
// ---------------------------------------------------------------------------

const reordering = ref(false)

async function move(
  category: string,
  rows: AttachmentResponse[],
  index: number,
  delta: number,
): Promise<void> {
  const target = index + delta
  if (target < 0 || target >= rows.length) return
  if (reordering.value) return

  const ids = rows.map((r) => r.id)
  const tmp = ids[index]
  ids[index] = ids[target]
  ids[target] = tmp

  reordering.value = true
  try {
    await reorderOwnAttachments({ category, item_ids: ids })
    await reload()
  } catch (e) {
    if (e instanceof ApiResponseError && e.detail.includes('attachments_reorder_set_mismatch')) {
      showToast(t('comp.attachments.reorderStale'), 'error')
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

const deleteTarget = ref<AttachmentResponse | null>(null)
const deleting = ref(false)

function openDelete(att: AttachmentResponse): void {
  deleteTarget.value = att
}

async function handleDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteOwnAttachment(deleteTarget.value.id)
    showToast(t('comp.attachments.deleted'), 'success')
    deleteTarget.value = null
    await reload()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

// ---------------------------------------------------------------------------
// The row's actions, as the system's Action menu (K26)
// ---------------------------------------------------------------------------

function rowActions(att: AttachmentResponse): ActionMenuItem[] {
  const items: ActionMenuItem[] = []
  if (att.is_published) {
    items.push({ value: 'download', label: t('comp.attachments.download'), icon: Download })
  }
  items.push({ value: 'edit', label: t('common.edit'), icon: Pencil })
  items.push({ value: 'delete', label: t('common.delete'), icon: Trash2, danger: true })
  return items
}

function onRowAction(att: AttachmentResponse, value: string): void {
  if (value === 'download') void openFile(att)
  else if (value === 'edit') openEdit(att)
  else if (value === 'delete') openDelete(att)
}
</script>

<template>
  <CListSkeleton v-if="loading" />

  <CEmptyState v-else-if="errored" tone="danger" :title="t('comp.attachments.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="reload">
        {{ t('comp.attachments.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <template v-else>
    <div class="ds-shell__toolbar">
      <div class="ds-shell__primary">
        <CButton variant="primary" size="sm" inline @click="openCreate">
          <Upload size="sm" />
          {{ t('comp.attachments.addCta') }}
        </CButton>
      </div>
    </div>

    <CEmptyState v-if="!rawItems.length" :title="t('comp.attachments.empty')">
      <template #icon>
        <FileText />
      </template>
    </CEmptyState>

    <template v-else>
      <section
        v-for="(group, g) in grouped"
        :key="group.category"
        class="catt__group"
        :aria-labelledby="`catt-group-${g}`"
      >
        <h2 :id="`catt-group-${g}`" class="ds-section-title catt__group-title">
          {{ group.category }}
        </h2>

        <!-- Reorder list (K39), one row actions menu (K26) at each row's end -->
        <ol class="ds-reorder" :aria-labelledby="`catt-group-${g}`">
          <li v-for="(att, idx) in group.rows" :key="att.id" class="ds-reorder__item">
            <div class="ds-reorder__controls">
              <button
                type="button"
                class="ds-reorder__move"
                :aria-label="`${t('common.moveUp')}: ${att.title}`"
                :disabled="idx === 0 || reordering"
                @click="move(group.category, group.rows, idx, -1)"
              >
                <ChevronUp size="sm" />
              </button>
              <button
                type="button"
                class="ds-reorder__move"
                :aria-label="`${t('common.moveDown')}: ${att.title}`"
                :disabled="idx === group.rows.length - 1 || reordering"
                @click="move(group.category, group.rows, idx, 1)"
              >
                <ChevronDown size="sm" />
              </button>
            </div>
            <span class="ds-reorder__pos" aria-hidden="true">{{ idx + 1 }}</span>

            <div class="ds-reorder__body">
              <span class="ds-reorder__title">{{ att.title }}</span>
              <span class="ds-reorder__meta">
                <CBadge
                  :variant="att.is_published ? 'success' : 'neutral'"
                  :text="
                    att.is_published
                      ? t('comp.attachments.published')
                      : t('comp.attachments.unpublished')
                  "
                />
                <CBadge
                  v-if="att.is_public"
                  variant="accent"
                  :text="t('comp.attachments.public')"
                />
                {{ att.language.toUpperCase() }}
              </span>
              <span v-if="att.description" class="ds-reorder__meta">{{ att.description }}</span>
              <span class="ds-reorder__meta">
                {{ att.original_filename }} &bull; {{ formatBytes(att.file_size_bytes) }}
              </span>
            </div>

            <div class="ds-reorder__trail">
              <CActionMenu
                :label="t('common.actions', { title: att.title })"
                icon-key="more"
                icon-only
                align="end"
                :items="rowActions(att)"
                @select="(value) => onRowAction(att, value)"
              />
            </div>
          </li>
        </ol>
      </section>
    </template>
  </template>

  <!-- Create / edit modal -->
  <CModal
    :open="showForm"
    :title="isEditing ? t('comp.attachments.editTitle') : t('comp.attachments.createTitle')"
    @close="closeForm"
  >
    <CInput
      v-model="draftTitle"
      :label="t('comp.attachments.fieldTitle')"
      :placeholder="t('comp.attachments.fieldTitle')"
    />

    <CTextarea
      v-model="draftDescription"
      :label="t('comp.attachments.fieldDescription')"
      :rows="3"
    />

    <div class="ds-field c-field">
      <label class="ds-field__label" :for="categoryId">
        {{ t('comp.attachments.fieldCategory') }}
      </label>
      <input
        :id="categoryId"
        v-model="draftCategory"
        class="ds-input"
        type="text"
        placeholder="legal/incorporation"
        :aria-invalid="trimmedCategory && !categoryValid ? 'true' : undefined"
        :aria-describedby="
          trimmedCategory && !categoryValid
            ? `${categoryId}-hint ${categoryId}-error`
            : `${categoryId}-hint`
        "
      />
      <p :id="`${categoryId}-hint`" class="ds-field__hint">
        {{ t('comp.attachments.categoryHint') }}
      </p>
      <p
        v-if="trimmedCategory && !categoryValid"
        :id="`${categoryId}-error`"
        class="ds-field__error"
      >
        <AlertTriangle size="sm" />
        <span>{{ t('comp.attachments.categoryError') }}</span>
      </p>
    </div>

    <CSelect
      v-model="draftLanguage"
      :label="t('comp.attachments.fieldLanguage')"
      :options="languageOptions"
    />

    <CCheckbox v-model="draftIsPublished" :label="t('comp.attachments.fieldPublished')" />
    <CCheckbox v-model="draftIsPublic" :label="t('comp.attachments.fieldPublic')" />

    <!-- The file: chosen for a new attachment, replaced at once on an existing one (K30) -->
    <CFileField
      v-if="!isEditing"
      :file="selectedFile"
      :label="t('comp.attachments.fieldFile')"
      :button-label="t('comp.attachments.chooseFile')"
      :accept="FILE_ACCEPT"
      :hint="t('comp.attachments.fileHint')"
      removable
      @select="(file) => (selectedFile = file)"
      @remove="selectedFile = null"
    />
    <CFileField
      v-else
      :label="t('comp.attachments.fieldReplaceFile')"
      :button-label="t('comp.attachments.chooseFile')"
      :accept="FILE_ACCEPT"
      :hint="t('comp.attachments.fileHint')"
      :current="editingOriginal?.original_filename"
      :current-meta="editingOriginal ? formatBytes(editingOriginal.file_size_bytes) : undefined"
      :busy="replacing"
      @select="onReplaceSelected"
    />

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
    :title="t('comp.attachments.deleteTitle')"
    @close="deleteTarget = null"
  >
    <p class="ds-dialog__text">
      {{ t('comp.attachments.deleteConfirm') }}
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
</template>

<style scoped>
/* One category: its heading over its list, on the frame's rhythm. */
.catt__group {
  display: grid;
  gap: var(--space-3);
}
/* A category name is the user's own text: it wraps anywhere. */
.catt__group-title {
  overflow-wrap: anywhere;
}
</style>
