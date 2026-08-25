<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyDocumentsSection (iter 2.7 Block C / C2)
// =============================================================================
//
// Company document (attachment) management: list grouped by category,
// per-category reorder via up/down buttons, and soft-delete. NO file
// upload in MVP -- uploads go through the MinIO Web UI + reconcile
// (R2 §6.2). The storage_key is surfaced as a copyable hint for staff
// who need to find the object in MinIO.
//
// REORDER MODEL (up/down, not drag-drop). The backend reorder endpoint
// takes the COMPLETE ordered id list for one (company, category) and
// enforces an exact set match. Each up/down click swaps two adjacent
// rows WITHIN their category, then submits the full category id list in
// the new order. Buttons beat drag-drop on a 380px touch screen and
// need no extra dependency.
//
// SET-MISMATCH HANDLING. If another staffer changed the category
// between our load and our reorder, the backend rejects with the
// `attachments_reorder_set_mismatch:` prefix. We detect that prefix,
// tell the user the list is stale, and reload -- rather than surfacing
// a raw 400. Optimistic UI is rolled back by the reload.
//
// FP-23. Reorder + delete mutate, so both are gated on
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
import { ChevronUp, ChevronDown, Trash2, FileText } from 'lucide-vue-next'
import { CLoader, CBadge, CButton, CEmptyState, CModal } from '@/components/ui'
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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

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
    <div v-if="loading" class="scd__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="scd__center">
      <CButton variant="secondary" size="sm" @click="loadAttachments">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.documents.empty')">
      <template #icon>
        <FileText :size="40" />
      </template>
    </CEmptyState>

    <!-- Grouped list -->
    <template v-else>
      <p class="scd__hint">
        {{ t('staff.platform.documents.uploadHint') }}
      </p>

      <div v-for="group in grouped" :key="group.category" class="scd__group">
        <h3 class="scd__group-title">
          {{ group.category }}
        </h3>

        <div class="doc-list">
          <div v-for="(att, idx) in group.rows" :key="att.id" class="doc-item">
            <!-- Reorder buttons (FP-23: only with company_manage) -->
            <div v-if="canManage" class="doc-item__reorder">
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
                      ? t('staff.platform.documents.published')
                      : t('staff.platform.documents.unpublished')
                  "
                />
                <CBadge
                  v-if="att.is_public"
                  variant="accent"
                  :text="t('staff.platform.documents.public')"
                />
                <span class="doc-item__lang">{{ att.language.toUpperCase() }}</span>
              </div>
              <div class="doc-item__title">
                {{ att.title }}
              </div>
              <div class="doc-item__meta">
                {{ att.original_filename }} &bull; {{ formatBytes(att.file_size_bytes) }}
              </div>
              <code class="doc-item__storage">{{ att.storage_key }}</code>
            </div>

            <!-- Delete (FP-23) -->
            <button
              v-if="canManage"
              :aria-label="t('common.delete')"
              class="doc-item__delete"
              @click="openDelete(att)"
            >
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Delete confirm -->
    <CModal :open="!!deleteTarget" @close="deleteTarget = null">
      <h3 class="scd__modal-title">
        {{ t('staff.platform.documents.deleteTitle') }}
      </h3>
      <p class="scd__modal-text">
        {{ t('staff.platform.documents.deleteConfirm') }}
      </p>
      <p v-if="deleteTarget" class="scd__modal-target">
        {{ deleteTarget.title }}
      </p>
      <div class="scd__modal-actions">
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
.scd {
  padding: var(--space-4);
}

.scd__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-sm);
  gap: var(--space-4);
}

.scd__hint {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.scd__group {
  margin-bottom: var(--space-5);
}
.scd__group-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 var(--space-2);
  word-break: break-all;
}

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
.doc-item__meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}
.doc-item__storage {
  display: block;
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  margin-top: var(--space-2);
  word-break: break-all;
}

.doc-item__delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-md);
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.doc-item__delete:hover {
  background: var(--bg-subtle);
  color: var(--danger);
}

.scd__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.scd__modal-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-2);
}
.scd__modal-target {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
  word-break: break-all;
}
.scd__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  justify-content: flex-end;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.scd__hint {
  max-width: var(--maxw-prose);
}
</style>
