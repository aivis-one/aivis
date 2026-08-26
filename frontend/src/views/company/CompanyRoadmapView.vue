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

const { t } = useI18n()
const { showToast } = useToast()
const router = useRouter()

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
const draftTitle = ref('')
const draftDescription = ref('')
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
  draftTitle.value = ''
  draftDescription.value = ''
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
  coverPreviewUrl.value = ''
  resetDraft('milestone')
  showForm.value = true
}

function openEdit(item: RoadmapItemResponse): void {
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

const trimmedTitle = computed<string>(() => draftTitle.value.trim())
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
  const desc = draftDescription.value.trim()
  if (desc) body.description = desc
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

const coverInputEl = ref<HTMLInputElement | null>(null)
const coverPreviewUrl = ref('')
const coverUploading = ref(false)
const coverRemoving = ref(false)
const coverRemoveTarget = ref<string | null>(null)

function triggerCoverPicker(): void {
  coverInputEl.value?.click()
}

async function onCoverSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
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
    const updated = await uploadOwnRoadmapCover(editingId.value, file)
    coverPreviewUrl.value = updated.cover_url ?? ''
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
    await deleteOwnRoadmapCover(coverRemoveTarget.value)
    coverPreviewUrl.value = ''
    coverRemoveTarget.value = null
    showToast(t('comp.roadmap.cover.removed'), 'success')
    await reload()
  } catch (e) {
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

function goBack(): void {
  void router.push('/company/settings')
}
</script>

<template>
  <div class="croad">
    <!-- Inline page header, back link to Settings (where the entry point lives) -->
    <div class="croad__header">
      <button type="button" class="croad__back" @click="goBack">
        <ArrowLeft :size="16" />
        {{ t('comp.settings.title') }}
      </button>
      <h1 class="croad__page-title">
        {{ t('comp.roadmap.title') }}
      </h1>
      <p class="croad__page-subtitle">
        {{ t('comp.roadmap.subtitle') }}
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="croad__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="croad__center">
      <CEmptyState :title="t('comp.roadmap.errorTitle')" />
      <CButton variant="outline" size="sm" @click="reload">
        {{ t('comp.roadmap.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <div class="croad__toolbar">
        <CButton variant="primary" size="sm" @click="openCreate">
          {{ t('comp.roadmap.addCta') }}
        </CButton>
      </div>

      <CEmptyState v-if="!items.length" :title="t('comp.roadmap.empty')">
        <template #icon>
          <MapIcon :size="40" />
        </template>
      </CEmptyState>

      <div v-else class="rm-list">
        <div v-for="(item, idx) in items" :key="item.id" class="rm-item">
          <div class="rm-item__reorder">
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

          <div v-if="item.cover_url" class="rm-item__cover">
            <img :src="item.cover_url" :alt="item.title" class="rm-item__cover-img" />
          </div>

          <div class="rm-item__body">
            <div class="rm-item__badges">
              <CBadge :variant="kindVariant(item.kind)" :text="kindLabel(item.kind)" />
              <CBadge
                v-if="item.kind === 'milestone'"
                :variant="statusVariant(item.status)"
                :text="statusLabel(item.status)"
              />
            </div>

            <div class="rm-item__title">
              {{ item.title }}
            </div>

            <div v-if="item.target_date || item.valid_until" class="rm-item__dates">
              <span v-if="item.target_date">
                {{ t('comp.roadmap.fieldTargetDate') }}: {{ formatDate(item.target_date) }}
              </span>
              <span v-if="item.valid_until">
                {{ t('comp.roadmap.fieldValidUntil') }}: {{ formatDate(item.valid_until) }}
              </span>
            </div>

            <p v-if="item.description" class="rm-item__desc">
              {{ item.description }}
            </p>

            <a
              v-if="item.external_url"
              :href="item.external_url"
              target="_blank"
              rel="noopener noreferrer"
              class="rm-item__link"
              >{{ item.external_url }}</a
            >

            <div v-if="item.post" class="rm-item__rel">
              {{ item.post.title }}
            </div>
          </div>

          <div class="rm-item__actions">
            <button :aria-label="t('common.edit')" class="rm-item__action" @click="openEdit(item)">
              <Pencil :size="16" />
            </button>
            <button
              :aria-label="t('common.delete')"
              class="rm-item__action"
              @click="openDelete(item)"
            >
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Create / edit modal -->
    <CModal :open="showForm" @close="closeForm">
      <h3 class="croad__modal-title">
        {{ isEditing ? t('comp.roadmap.editTitle') : t('comp.roadmap.createTitle') }}
      </h3>

      <div class="croad__kind">
        <span class="croad__kind-label">{{ t('comp.roadmap.kindLabel') }}</span>
        <template v-if="isEditing">
          <CBadge :variant="kindVariant(draftKind)" :text="kindLabel(draftKind)" />
          <p class="croad__kind-hint">
            {{ t('comp.roadmap.kindLockedHint') }}
          </p>
        </template>
        <div v-else class="croad__kind-tabs">
          <button
            v-for="k in KIND_VALUES"
            :key="k"
            class="croad__kind-tab"
            :class="{ 'croad__kind-tab--active': draftKind === k }"
            @click="selectKind(k)"
          >
            {{ kindLabel(k) }}
          </button>
        </div>
      </div>

      <CInput
        v-model="draftTitle"
        :label="t('comp.roadmap.fieldTitle')"
        :placeholder="t('comp.roadmap.fieldTitle')"
      />

      <CTextarea v-model="draftDescription" :label="t('comp.roadmap.fieldDescription')" :rows="4" />

      <p v-if="draftKind === 'event'" class="croad__hint">
        {{ t('comp.roadmap.eventDatesHint') }}
      </p>

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
        :error="
          draftTargetDate && draftValidUntil && !eventDatesValid
            ? t('comp.roadmap.validUntilAfterTargetError')
            : ''
        "
      />

      <template v-if="showStatus">
        <template v-if="statusLocked">
          <div class="croad__field">
            <label class="croad__field-label">{{ t('comp.roadmap.fieldStatus') }}</label>
            <CBadge :variant="statusVariant(draftStatus)" :text="statusLabel(draftStatus)" />
          </div>
          <p class="croad__hint">
            {{ t('comp.roadmap.completedLockedHint') }}
          </p>
        </template>
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

      <div class="croad__cover">
        <label class="croad__field-label">{{ t('comp.roadmap.cover.label') }}</label>

        <template v-if="isEditing">
          <div v-if="coverPreviewUrl" class="croad__cover-preview">
            <img :src="coverPreviewUrl" alt="" class="croad__cover-img" />
          </div>

          <div class="croad__cover-actions">
            <CButton
              variant="outline"
              size="sm"
              :loading="coverUploading"
              @click="triggerCoverPicker"
            >
              <ImageUp :size="16" />
              {{
                coverPreviewUrl ? t('comp.roadmap.cover.replace') : t('comp.roadmap.cover.upload')
              }}
            </CButton>
            <CButton
              v-if="coverPreviewUrl"
              variant="outline"
              size="sm"
              :loading="coverRemoving"
              @click="openCoverRemove"
            >
              <X :size="16" />
              {{ t('comp.roadmap.cover.remove') }}
            </CButton>
          </div>

          <input
            ref="coverInputEl"
            :aria-label="t('comp.roadmap.cover.remove')"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="croad__cover-input"
            @change="onCoverSelected"
          />
        </template>

        <p v-else class="croad__hint">
          {{ t('comp.roadmap.cover.createFirst') }}
        </p>
      </div>

      <div class="croad__modal-actions">
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
      <h3 class="croad__modal-title">
        {{ t('comp.roadmap.deleteTitle') }}
      </h3>
      <p class="croad__modal-hint">
        {{ t('comp.roadmap.deleteConfirm') }}
      </p>
      <div class="croad__modal-actions">
        <CButton variant="outline" size="sm" @click="deleteTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="deleting" @click="handleDelete">
          {{ t('common.delete') }}
        </CButton>
      </div>
    </CModal>

    <!-- Cover remove confirm -->
    <CModal :open="!!coverRemoveTarget" @close="coverRemoveTarget = null">
      <h3 class="croad__modal-title">
        {{ t('comp.roadmap.cover.removeTitle') }}
      </h3>
      <p class="croad__modal-hint">
        {{ t('comp.roadmap.cover.removeConfirm') }}
      </p>
      <div class="croad__modal-actions">
        <CButton variant="outline" size="sm" @click="coverRemoveTarget = null">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="danger" size="sm" :loading="coverRemoving" @click="handleCoverRemove">
          {{ t('comp.roadmap.cover.remove') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.croad {
  padding-bottom: var(--space-5);
}

.croad__header {
  padding: var(--space-4) var(--space-4) 0;
}
.croad__back {
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
.croad__back:hover {
  color: var(--text-primary);
}
.croad__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.croad__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}

.croad__center {
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

.croad__toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0 var(--space-4);
  margin-bottom: var(--space-4);
}

/* -- List (shared naming with the staff section for visual parity) -- */
.rm-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 var(--space-4);
}

.rm-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
}

.rm-item__reorder {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 0 0 auto;
}
.rm-item__move {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-sm);
  height: var(--size-xs);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-page);
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    border-color 0.2s,
    color 0.2s;
}
.rm-item__move:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}
.rm-item__move:disabled {
  opacity: 0.4;
  cursor: default;
}

.rm-item__cover {
  flex: 0 0 auto;
}
.rm-item__cover-img {
  width: var(--size-4xl);
  height: var(--size-4xl);
  object-fit: cover;
  border-radius: var(--radius-sm);
  display: block;
}

.rm-item__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.rm-item__badges {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.rm-item__title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.rm-item__dates {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.rm-item__desc {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.4;
  max-width: var(--maxw-prose);
}
.rm-item__link {
  font-size: var(--fs-sm);
  color: var(--primary);
  word-break: break-all;
  text-decoration: none;
}
.rm-item__link:hover {
  text-decoration: underline;
}
.rm-item__rel {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.rm-item__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 0 0 auto;
}
.rm-item__action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--size-md);
  height: var(--size-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition:
    color 0.2s,
    background 0.2s;
}
.rm-item__action:hover {
  color: var(--text-primary);
  background: var(--bg-page);
}

/* -- Modal -- */
.croad__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.croad__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.croad__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  justify-content: flex-end;
}

.croad__hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
  line-height: 1.4;
  max-width: var(--maxw-prose);
}

.croad__kind {
  margin-bottom: var(--space-4);
}
.croad__kind-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}
.croad__kind-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: var(--space-2) 0 0;
  line-height: 1.4;
}
.croad__kind-tabs {
  display: flex;
  gap: var(--space-2);
}
.croad__kind-tab {
  flex: 1;
  padding: var(--space-3) var(--space-2);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-page);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.croad__kind-tab--active {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--bg-subtle);
}

.croad__field {
  margin-bottom: var(--space-4);
}
.croad__field-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.croad__cover {
  margin-bottom: var(--space-4);
}
.croad__cover-preview {
  margin-bottom: var(--space-2);
}
.croad__cover-img {
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: var(--radius-md);
  display: block;
}
.croad__cover-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.croad__cover-input {
  display: none;
}
</style>
