<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyDocumentsSection (iter 2.7 Block C / C2)
// =============================================================================
//
// Project document (attachment) management: list grouped by category,
// UPLOAD of a new document, EDIT of a document's title, category, language and
// visibility, REPLACE of its file, per-category reorder via up/down buttons,
// and soft-delete. The upload / edit / replace form is AttachmentFormModal;
// the file goes to the server in one multipart request, never through the
// storage console. The storage_key is shown as a copyable hint for staff who
// need to find the object in storage.
//
// REORDER MODEL (up/down, not drag-drop). The backend reorder endpoint
// takes the COMPLETE ordered id list for one (company, category) and
// enforces an exact set match. Each up/down click swaps two adjacent
// rows WITHIN their category, then submits the full category id list in
// the new order. Buttons beat drag-drop on a narrow touch screen and
// need no extra dependency.
//
// SET-MISMATCH HANDLING. If another staffer changed the category
// between our load and our reorder, the backend rejects with the
// `attachments_reorder_set_mismatch:` prefix. We detect that prefix,
// tell the user the list is stale, and reload -- rather than surfacing
// a raw 400. Optimistic UI is rolled back by the reload.
//
// FP-23. Upload, edit, replace, reorder and delete mutate, so all are gated on
// canDo('project_manage') -- narrowed from company_manage (TASK-30 §7)
// -- (template guard on the buttons + defensive check in the handlers).
// A staffer without project_manage can still read the list (the parent
// route only enforces requireStaff).
//
// GROUPING. Attachments are grouped by `category`; reorder is scoped to
// a single category. Within a group, rows are shown in `order`. The
// backend returns them sorted (category ASC, order ASC); we group in
// render order so the per-category sequence is already correct.
// =============================================================================

import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronUp, ChevronDown, Trash2, FileText, Pencil, Upload } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CModal } from '@/components/ui'
import AttachmentFormModal from '@/components/staff/AttachmentFormModal.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import { formatBytes } from '@/utils/format'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { ApiResponseError } from '@/api/client'
import {
  fetchStaffCompanyAttachments,
  reorderStaffCompanyAttachments,
  deleteStaffCompanyAttachment,
} from '@/api/staff-companies'
import type { StaffAttachmentResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const route = useRoute()
const { canDo } = useStaffPermissions()

// FP-23: reorder + delete require project_manage.
const canManage = canDo('project_manage')

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const items = ref<StaffAttachmentResponse[]>([])
const loading = ref(true)
const error = ref(false)

// Reorder in flight -- disables the up/down buttons to avoid racing
// two reorder requests for the same category.
const reordering = ref(false)

// Delete confirm.
const deleteTarget = ref<StaffAttachmentResponse | null>(null)
const deleting = ref(false)

// Upload / edit form. `formTarget` null = a new document.
const showForm = ref(false)
const formTarget = ref<StaffAttachmentResponse | null>(null)

function openUpload(): void {
  if (!canManage.value) return
  formTarget.value = null
  showForm.value = true
}

function openEdit(att: StaffAttachmentResponse): void {
  if (!canManage.value) return
  formTarget.value = att
  showForm.value = true
}

// Group attachments by category, preserving the backend's per-category
// order (it returns rows sorted by category ASC, order ASC). Map keeps
// insertion order, so categories render in first-seen order.
const grouped = computed<{ category: string; rows: StaffAttachmentResponse[] }[]>(() => {
  const map = new Map<string, StaffAttachmentResponse[]>()
  for (const att of items.value) {
    const arr = map.get(att.category)
    if (arr) arr.push(att)
    else map.set(att.category, [att])
  }
  return Array.from(map.entries()).map(([category, rows]) => ({ category, rows }))
})

async function loadAttachments(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    items.value = await fetchStaffCompanyAttachments(id)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

// -- Reorder via up/down --

// Move the row at `index` within its category by `delta` (-1 = up,
// +1 = down), then submit the full category id list in the new order.
async function move(
  category: string,
  rows: StaffAttachmentResponse[],
  index: number,
  delta: number,
): Promise<void> {
  if (!canManage.value) {
    console.warn('[StaffCompanyDocumentsSection] move blocked: no company_manage')
    return
  }
  const target = index + delta
  if (target < 0 || target >= rows.length) return
  if (reordering.value) return

  // Build the reordered id list for this category.
  const ids = rows.map((r) => r.id)
  const tmp = ids[index]
  ids[index] = ids[target]
  ids[target] = tmp

  reordering.value = true
  try {
    await reorderStaffCompanyAttachments(companyId.value, {
      category,
      item_ids: ids,
    })
    // Reload to reflect the committed order (and pick up any concurrent
    // change). Cheap -- the list is small and unpaginated.
    await loadAttachments()
  } catch (e) {
    // Set-mismatch = someone else changed this category. Tell the user
    // and reload so they see the current state.
    if (e instanceof ApiResponseError && e.detail.includes('attachments_reorder_set_mismatch')) {
      showToast(t('staff.platform.documents.reorderStale'), 'error')
      await loadAttachments()
    } else {
      showToast(t('common.error'), 'error')
    }
  } finally {
    reordering.value = false
  }
}

// -- Soft-delete --

function openDelete(att: StaffAttachmentResponse): void {
  if (!canManage.value) {
    console.warn('[StaffCompanyDocumentsSection] openDelete blocked: no company_manage')
    return
  }
  deleteTarget.value = att
}

async function handleDelete(): Promise<void> {
  if (!canManage.value || !deleteTarget.value) {
    if (!canManage.value) {
      console.warn('[StaffCompanyDocumentsSection] handleDelete blocked: no company_manage')
    }
    return
  }
  deleting.value = true
  try {
    await deleteStaffCompanyAttachment(companyId.value, deleteTarget.value.id)
    showToast(t('staff.platform.documents.deleted'), 'success')
    deleteTarget.value = null
    await loadAttachments()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

watch(companyId, () => loadAttachments())
onMounted(loadAttachments)
</script>

<template>
  <div class="scd">
    <!-- Loading -->
    <CListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadAttachments">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else>
      <div v-if="canManage" class="scd__toolbar">
        <CButton variant="primary" size="sm" inline @click="openUpload">
          <Upload size="sm" />
          {{ t('staff.platform.documents.addCta') }}
        </CButton>
      </div>

      <!-- Empty -->
      <CEmptyState v-if="!items.length" :title="t('staff.platform.documents.empty')">
        <template #icon>
          <FileText />
        </template>
      </CEmptyState>

      <template v-else>
        <section v-for="(group, g) in grouped" :key="group.category" class="scd__group">
          <h2 :id="`scd-group-${g}`" class="scd__group-title">
            {{ group.category }}
          </h2>

          <!-- The category's documents in order (K39: the move buttons are named by the row) -->
          <ol class="ds-reorder doc-list" :aria-labelledby="`scd-group-${g}`">
            <li v-for="(att, idx) in group.rows" :key="att.id" class="ds-reorder__item doc-item">
              <!-- Reorder buttons (FP-23: only with project_manage) -->
              <div v-if="canManage" class="ds-reorder__controls">
                <button
                  type="button"
                  class="ds-reorder__move"
                  :aria-label="`${t('common.moveUp')}: ${att.title}`"
                  :disabled="idx === 0 || reordering"
                  @click="move(group.category, group.rows, idx, -1)"
                >
                  <ChevronUp />
                </button>
                <button
                  type="button"
                  class="ds-reorder__move"
                  :aria-label="`${t('common.moveDown')}: ${att.title}`"
                  :disabled="idx === group.rows.length - 1 || reordering"
                  @click="move(group.category, group.rows, idx, 1)"
                >
                  <ChevronDown />
                </button>
              </div>
              <span class="ds-reorder__pos" aria-hidden="true">{{ idx + 1 }}</span>

              <div class="ds-reorder__body">
                <span class="ds-reorder__title">{{ att.title }}</span>
                <span class="ds-reorder__meta">
                  {{ att.original_filename }} &bull; {{ formatBytes(att.file_size_bytes) }} &bull;
                  {{ att.language.toUpperCase() }}
                </span>
                <span class="ds-reorder__meta doc-item__badges">
                  <CBadge
                    :variant="att.is_published ? 'success' : 'neutral'"
                    :text="
                      att.is_published
                        ? t('staff.platform.documents.published')
                        : t('staff.platform.documents.unpublished')
                    "
                  />
                  <CBadge
                    v-if="att.is_public"
                    variant="accent"
                    :text="t('staff.platform.documents.public')"
                  />
                </span>
                <code class="doc-item__storage">{{ att.storage_key }}</code>
              </div>

              <!-- Edit and delete (FP-23) -->
              <span v-if="canManage" class="ds-row__trail">
                <button
                  type="button"
                  class="ds-button ds-button--ghost ds-button--icon"
                  data-size="sm"
                  :aria-label="t('common.edit')"
                  @click="openEdit(att)"
                >
                  <Pencil />
                </button>
                <button
                  type="button"
                  class="ds-button ds-button--danger ds-button--icon"
                  data-size="sm"
                  :aria-label="t('common.delete')"
                  @click="openDelete(att)"
                >
                  <Trash2 />
                </button>
              </span>
            </li>
          </ol>
        </section>
      </template>
    </template>

    <!-- Upload / edit / replace -->
    <AttachmentFormModal
      :open="showForm"
      :company-id="companyId"
      :editing="formTarget"
      @close="showForm = false"
      @saved="loadAttachments"
    />

    <!-- Delete confirm -->
    <CModal
      :open="!!deleteTarget"
      :title="t('staff.platform.documents.deleteTitle')"
      @close="deleteTarget = null"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.documents.deleteConfirm') }}
      </p>
      <p v-if="deleteTarget" class="scd__target">
        {{ deleteTarget.title }}
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
  </div>
</template>

<style scoped>
.scd {
  display: grid;
  gap: var(--space-4);
  align-content: start;
}

.scd__toolbar {
  display: flex;
  justify-content: flex-end;
}

.scd__group {
  display: grid;
  gap: var(--space-2);
}
.scd__group-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-all;
}

/* The badges sit in a line under the file's facts. */
.doc-item__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* The storage key is read and copied character by character: a mono block (D11). */
.doc-item__storage {
  display: block;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--bg-inset);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  word-break: break-all;
}

.scd__target {
  margin: 0;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}
</style>
