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

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  ChevronUp,
  ChevronDown,
  Pencil,
  Trash2,
  FileText,
  Upload,
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
  CCheckbox,
} from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
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
const { showToast } = useToast()
const router = useRouter()

// File types accepted by the picker, mirroring
// companies/constants.py::ALLOWED_ATTACHMENT_MIME_TYPES by extension.
// The real gate is server-side (extension-based MIME validation); this
// is only a UI hint that filters the OS file picker.
const FILE_ACCEPT = '.pdf,.pptx,.docx,.xlsx,.png,.jpg,.jpeg,.webp,.gif,.svg,.mp4,.webm,.txt,.md'

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'EN' },
  { value: 'ru', label: 'RU' },
  { value: 'de', label: 'DE' },
  { value: 'ar', label: 'AR' },
]

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
// file of an EXISTING attachment is a separate control (replaceFileEl
// below) since the backend treats it as a distinct endpoint that leaves
// metadata untouched.
const fileInputEl = ref<HTMLInputElement | null>(null)
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

function onFileSelected(e: Event): void {
  const input = e.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
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

const replaceFileEl = ref<HTMLInputElement | null>(null)
const replacing = ref(false)

function triggerReplacePicker(): void {
  replaceFileEl.value?.click()
}

async function onReplaceSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !editingId.value) return

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

function goBack(): void {
  void router.push('/company/settings')
}
</script>

<template>
  <div class="catt">
    <div class="catt__header">
      <button type="button" class="catt__back" @click="goBack">
        <ArrowLeft :size="16" />
        {{ t('comp.settings.title') }}
      </button>
      <h1 class="catt__page-title">
        {{ t('comp.attachments.title') }}
      </h1>
      <p class="catt__page-subtitle">
        {{ t('comp.attachments.subtitle') }}
      </p>
    </div>

    <div v-if="loading" class="catt__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="errored" class="catt__center">
      <CEmptyState :title="t('comp.attachments.errorTitle')" />
      <CButton variant="outline" size="sm" @click="reload">
        {{ t('comp.attachments.errorRetry') }}
      </CButton>
    </div>

    <template v-else>
      <div class="catt__toolbar">
        <CButton variant="primary" size="sm" @click="openCreate">
          <Upload :size="16" />
          {{ t('comp.attachments.addCta') }}
        </CButton>
      </div>

      <CEmptyState v-if="!rawItems.length" :title="t('comp.attachments.empty')">
        <template #icon>
          <FileText :size="40" />
        </template>
      </CEmptyState>

      <div v-else class="catt__groups">
        <div v-for="group in grouped" :key="group.category" class="catt__group">
          <h3 class="catt__group-title">
            {{ group.category }}
          </h3>

          <div class="doc-list">
            <div v-for="(att, idx) in group.rows" :key="att.id" class="doc-item">
              <div class="doc-item__reorder">
                <button
                  :aria-label="t('common.moveUp')"
                  class="doc-item__move"
                  :disabled="idx === 0 || reordering"
                  @click="move(group.category, group.rows, idx, -1)"
                >
                  <ChevronUp :size="16" />
                </button>
                <button
                  :aria-label="t('common.moveDown')"
                  class="doc-item__move"
                  :disabled="idx === group.rows.length - 1 || reordering"
                  @click="move(group.category, group.rows, idx, 1)"
                >
                  <ChevronDown :size="16" />
                </button>
              </div>

              <div class="doc-item__info">
                <div class="doc-item__top">
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
                  <span class="doc-item__lang">{{ att.language.toUpperCase() }}</span>
                </div>
                <div class="doc-item__title">
                  {{ att.title }}
                </div>
                <p v-if="att.description" class="doc-item__desc">
                  {{ att.description }}
                </p>
                <div class="doc-item__meta">
                  {{ att.original_filename }} &bull; {{ formatBytes(att.file_size_bytes) }}
                </div>
              </div>

              <div class="doc-item__actions">
                <button
                  :aria-label="t('common.edit')"
                  class="doc-item__action"
                  @click="openEdit(att)"
                >
                  <Pencil :size="16" />
                </button>
                <button
                  :aria-label="t('common.delete')"
                  class="doc-item__action"
                  @click="openDelete(att)"
                >
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Create / edit modal -->
    <CModal :open="showForm" @close="closeForm">
      <h3 class="catt__modal-title">
        {{ isEditing ? t('comp.attachments.editTitle') : t('comp.attachments.createTitle') }}
      </h3>

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

      <CInput
        v-model="draftCategory"
        :label="t('comp.attachments.fieldCategory')"
        placeholder="legal/incorporation"
        :error="trimmedCategory && !categoryValid ? t('comp.attachments.categoryError') : ''"
      />
      <p class="catt__hint">
        {{ t('comp.attachments.categoryHint') }}
      </p>

      <CSelect
        v-model="draftLanguage"
        :label="t('comp.attachments.fieldLanguage')"
        :options="LANGUAGE_OPTIONS"
      />

      <CCheckbox v-model="draftIsPublished" :label="t('comp.attachments.fieldPublished')" />
      <CCheckbox v-model="draftIsPublic" :label="t('comp.attachments.fieldPublic')" />

      <div v-if="!isEditing" class="catt__field">
        <label class="catt__field-label">{{ t('comp.attachments.fieldFile') }}</label>
        <CButton variant="outline" size="sm" @click="fileInputEl?.click()">
          <Upload :size="16" />
          {{ selectedFile ? selectedFile.name : t('comp.attachments.chooseFile') }}
        </CButton>
        <input
          ref="fileInputEl"
          type="file"
          :accept="FILE_ACCEPT"
          class="catt__file-input"
          @change="onFileSelected"
        />
      </div>

      <div v-else class="catt__field">
        <label class="catt__field-label">{{ t('comp.attachments.fieldReplaceFile') }}</label>
        <CButton variant="outline" size="sm" :loading="replacing" @click="triggerReplacePicker">
          <Upload :size="16" />
          {{ editingOriginal?.original_filename }}
        </CButton>
        <input
          ref="replaceFileEl"
          type="file"
          :accept="FILE_ACCEPT"
          class="catt__file-input"
          @change="onReplaceSelected"
        />
      </div>

      <div class="catt__modal-actions">
        <CButton variant="outline" size="sm" @click="closeForm">
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
      <h3 class="catt__modal-title">
        {{ t('comp.attachments.deleteTitle') }}
      </h3>
      <p class="catt__modal-hint">
        {{ t('comp.attachments.deleteConfirm') }}
      </p>
      <div class="catt__modal-actions">
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
.catt {
  padding-bottom: var(--space-5);
}

.catt__header {
  padding: var(--space-4) var(--space-4) 0;
}
.catt__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  padding: 0;
  margin-bottom: var(--space-3);
  cursor: pointer;
}
.catt__back:hover {
  color: var(--text-primary);
}
.catt__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.catt__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}

.catt__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: calc(100vh - 280px);
  min-height: calc(100dvh - 280px);
  padding: var(--space-5);
  text-align: center;
}

.catt__toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0 var(--space-4);
  margin-bottom: var(--space-4);
}

.catt__groups {
  padding: 0 var(--space-4);
}
.catt__group {
  margin-bottom: var(--space-5);
}
.catt__group-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 var(--space-2);
  word-break: break-all;
}

/* -- List (shared naming with the staff section for visual parity) -- */
.doc-list {
  display: flex;
  flex-direction: column;
}
.doc-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}
.doc-item__reorder {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex-shrink: 0;
}
.doc-item__move {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-sm);
  height: var(--size-xs);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
}
.doc-item__move:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.doc-item__move:not(:disabled):hover {
  background: var(--bg-subtle);
}

.doc-item__info {
  flex: 1;
  min-width: 0;
}
.doc-item__top {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--space-1);
}
.doc-item__lang {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  font-weight: 600;
}
.doc-item__title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.doc-item__desc {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: var(--space-1) 0 0;
  line-height: 1.4;
  max-width: var(--maxw-prose);
}
.doc-item__meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.doc-item__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex-shrink: 0;
}
.doc-item__action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-sm);
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition:
    color 0.2s,
    background 0.2s;
}
.doc-item__action:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

/* -- Modal -- */
.catt__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.catt__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.catt__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  justify-content: flex-end;
}

.catt__hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: calc(-1 * var(--space-2)) 0 var(--space-4);
  line-height: 1.4;
  max-width: var(--maxw-prose);
}

.catt__field {
  margin-bottom: var(--space-4);
}
.catt__field-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}
.catt__file-input {
  display: none;
}
</style>
