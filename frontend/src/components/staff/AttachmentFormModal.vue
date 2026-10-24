<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AttachmentFormModal (a project's document: upload, edit, replace)
// =============================================================================
//
// The form a staff member fills to put a document on a project (title,
// description, category, language, who may see it, the file) or to change one
// that is there (the same fields, and a button that swaps the file and keeps
// the rest). The project's own account has the same form on its side; this one
// speaks the staff endpoints, which take the project's id.
//
// POST  /api/v1/staff/companies/{id}/attachments            (multipart)
// PATCH /api/v1/staff/companies/{id}/attachments/{att}      (metadata)
// PATCH /api/v1/staff/companies/{id}/attachments/{att}/replace   (multipart)
//
// All three need project_manage; the parent draws the buttons that open this
// only for a member who has it. The file's type is judged by the server from
// its name, and the 100 MB cap is the web server's; the picker's `accept` is a
// hint, not the gate.
// =============================================================================

import { computed, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Upload, X } from '@/components/ui/icons'
import { formatBytes } from '@/utils/format'
import { CButton, CCheckbox, CInput, CModal, CSelect, CTextarea } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import {
  createStaffAttachment,
  replaceStaffAttachmentFile,
  updateStaffAttachment,
} from '@/api/staff-companies'
import type { AttachmentUploadMetadata } from '@/api/company-attachments'
import { useToast } from '@/composables/useToast'
import type { AttachmentPatchBody, StaffAttachmentResponse } from '@/api/types'

const props = defineProps<{
  open: boolean
  companyId: string
  /** The document being edited; null = a new one. */
  editing: StaffAttachmentResponse | null
}>()

const emit = defineEmits<{
  close: []
  /** A document was created, changed or had its file replaced; the list is read again. */
  saved: []
}>()

const { t } = useI18n()
const { showToast } = useToast()

// File types the picker offers, by extension (the server's list is the gate).
const FILE_ACCEPT = '.pdf,.pptx,.docx,.xlsx,.png,.jpg,.jpeg,.webp,.gif,.svg,.mp4,.webm,.txt,.md'

// Lowercase path tree, '/'-separated, up to 5 levels (the server's rule).
const CATEGORY_PATTERN = /^[a-z0-9_-]+(\/[a-z0-9_-]+){0,4}$/

// A document is kept in the two languages the cabinet ships in; an older file
// that carries another language keeps it until it is edited.
const BASE_LANGUAGES = [
  { value: 'en', label: 'EN' },
  { value: 'ru', label: 'RU' },
]

const draftTitle = ref('')
const draftDescription = ref('')
const draftCategory = ref('unsorted')
const draftLanguage = ref('en')
const draftIsPublished = ref(false)
const draftIsPublic = ref(false)
const selectedFile = ref<File | null>(null)

const saving = ref(false)
const replacing = ref(false)

const isEditing = computed<boolean>(() => props.editing !== null)

const languageOptions = computed(() =>
  BASE_LANGUAGES.some((o) => o.value === draftLanguage.value)
    ? BASE_LANGUAGES
    : [...BASE_LANGUAGES, { value: draftLanguage.value, label: draftLanguage.value.toUpperCase() }],
)

// The form starts from the document being edited, or blank, every time it opens.
watch(
  () => props.open,
  (open) => {
    if (!open) return
    const att = props.editing
    draftTitle.value = att?.title ?? ''
    draftDescription.value = att?.description ?? ''
    draftCategory.value = att?.category ?? 'unsorted'
    draftLanguage.value = att?.language ?? 'en'
    draftIsPublished.value = att?.is_published ?? false
    draftIsPublic.value = att?.is_public ?? false
    selectedFile.value = null
  },
)

const trimmedTitle = computed(() => draftTitle.value.trim())
const trimmedCategory = computed(() => draftCategory.value.trim())
const categoryValid = computed(() => CATEGORY_PATTERN.test(trimmedCategory.value))

const canSubmit = computed<boolean>(() => {
  if (!trimmedTitle.value) return false
  if (!categoryValid.value) return false
  if (!isEditing.value && !selectedFile.value) return false
  return true
})

function serverReason(err: unknown): string {
  return err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
}

function buildCreateMetadata(): AttachmentUploadMetadata {
  const meta: AttachmentUploadMetadata = {
    title: trimmedTitle.value,
    category: trimmedCategory.value,
    language: draftLanguage.value,
    is_published: draftIsPublished.value,
    is_public: draftIsPublic.value,
  }
  const description = draftDescription.value.trim()
  if (description) meta.description = description
  return meta
}

// Only what changed travels: an omitted field is kept, an explicit null clears
// the description.
function buildPatchBody(original: StaffAttachmentResponse): AttachmentPatchBody {
  const body: AttachmentPatchBody = {}
  if (trimmedTitle.value !== original.title) body.title = trimmedTitle.value
  const description = draftDescription.value.trim()
  if (description !== (original.description ?? '')) body.description = description || null
  if (trimmedCategory.value !== original.category) body.category = trimmedCategory.value
  if (draftLanguage.value !== original.language) {
    body.language = draftLanguage.value as AttachmentPatchBody['language']
  }
  if (draftIsPublished.value !== original.is_published) body.is_published = draftIsPublished.value
  if (draftIsPublic.value !== original.is_public) body.is_public = draftIsPublic.value
  return body
}

async function handleSave(): Promise<void> {
  if (!canSubmit.value) return
  saving.value = true
  try {
    const original = props.editing
    if (original) {
      const body = buildPatchBody(original)
      if (Object.keys(body).length > 0) {
        await updateStaffAttachment(props.companyId, original.id, body)
      }
      showToast(t('staff.platform.documents.form.updated'), 'success')
    } else if (selectedFile.value) {
      await createStaffAttachment(props.companyId, buildCreateMetadata(), selectedFile.value)
      showToast(t('staff.platform.documents.form.created'), 'success')
    }
    emit('saved')
    emit('close')
  } catch (err) {
    showToast(serverReason(err), 'error')
  } finally {
    saving.value = false
  }
}

// -- The file ------------------------------------------------------------------

const fileInputEl = ref<HTMLInputElement | null>(null)
const replaceFileEl = ref<HTMLInputElement | null>(null)
const fileLabelId = useId()

function clearSelectedFile(): void {
  selectedFile.value = null
  if (fileInputEl.value) fileInputEl.value.value = ''
}

function onFileSelected(e: Event): void {
  const input = e.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function onReplaceSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const original = props.editing
  if (!file || !original) return
  replacing.value = true
  try {
    await replaceStaffAttachmentFile(props.companyId, original.id, file)
    showToast(t('staff.platform.documents.form.fileReplaced'), 'success')
    emit('saved')
  } catch (err) {
    showToast(serverReason(err), 'error')
  } finally {
    replacing.value = false
  }
}
</script>

<template>
  <CModal
    :open="open"
    :title="
      isEditing
        ? t('staff.platform.documents.form.editTitle')
        : t('staff.platform.documents.form.createTitle')
    "
    @close="emit('close')"
  >
    <CInput v-model="draftTitle" :label="t('staff.platform.documents.form.fieldTitle')" />

    <CTextarea
      v-model="draftDescription"
      :label="t('staff.platform.documents.form.fieldDescription')"
      :rows="3"
    />

    <div class="ds-field">
      <CInput
        v-model="draftCategory"
        :label="t('staff.platform.documents.form.fieldCategory')"
        placeholder="legal/incorporation"
        :error="
          trimmedCategory && !categoryValid ? t('staff.platform.documents.form.categoryError') : ''
        "
      />
      <p class="ds-field__hint">
        {{ t('staff.platform.documents.form.categoryHint') }}
      </p>
    </div>

    <CSelect
      v-model="draftLanguage"
      :label="t('staff.platform.documents.form.fieldLanguage')"
      :options="languageOptions"
    />

    <CCheckbox
      v-model="draftIsPublished"
      :label="t('staff.platform.documents.form.fieldPublished')"
    />
    <CCheckbox v-model="draftIsPublic" :label="t('staff.platform.documents.form.fieldPublic')" />

    <!-- The file to put on the project (K30: the picker is the label that draws the
         button, the chosen file is listed with a remove control). -->
    <div v-if="!isEditing" class="ds-field ds-file">
      <span :id="fileLabelId" class="ds-field__label">
        {{ t('staff.platform.documents.form.fieldFile') }}
      </span>
      <label class="ds-button ds-button--secondary ds-file__pick">
        <Upload size="sm" />
        <span>{{ t('staff.platform.documents.form.chooseFile') }}</span>
        <input
          ref="fileInputEl"
          class="ds-file__input"
          type="file"
          :accept="FILE_ACCEPT"
          :aria-labelledby="fileLabelId"
          @change="onFileSelected"
        />
      </label>
      <ul class="ds-file__list" aria-live="polite">
        <li v-if="selectedFile" class="ds-file__item" data-state="selected">
          <span class="ds-file__thumb"><FileText size="sm" /></span>
          <span class="ds-file__body">
            <span class="ds-file__name">{{ selectedFile.name }}</span>
            <span class="ds-file__meta ds-file__status">{{ formatBytes(selectedFile.size) }}</span>
          </span>
          <span class="ds-file__aside">
            <button
              type="button"
              class="ds-file__remove"
              :aria-label="`${t('common.clear')}: ${selectedFile.name}`"
              @click="clearSelectedFile"
            >
              <X size="sm" />
            </button>
          </span>
        </li>
      </ul>
    </div>

    <!-- The file of a document that is there: swap it, the rest is kept (K30). -->
    <div v-else class="ds-field ds-file" :aria-busy="replacing || undefined">
      <span :id="fileLabelId" class="ds-field__label">
        {{ t('staff.platform.documents.form.fieldReplaceFile') }}
      </span>
      <label class="ds-button ds-button--secondary ds-file__pick">
        <Upload size="sm" />
        <span>{{ editing?.original_filename }}</span>
        <input
          ref="replaceFileEl"
          class="ds-file__input"
          type="file"
          :accept="FILE_ACCEPT"
          :aria-labelledby="fileLabelId"
          :disabled="replacing"
          @change="onReplaceSelected"
        />
      </label>
    </div>

    <div class="ds-dialog__actions">
      <CButton variant="outline" size="sm" inline @click="emit('close')">
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
</template>
