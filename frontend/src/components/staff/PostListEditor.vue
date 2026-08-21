<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PostListEditor (iter 2.7 Block B)
// =============================================================================
//
// Shared list + create/edit surface for posts. Used by:
//   - StaffNewsView (no fixedOwner -- lists every post, owner picker
//     shown in the modal so staff can author platform or company posts).
//   - StaffCompanyPostsSection (Block C, fixedOwner={type:'company',
//     id:companyId} -- list scoped to one company, owner picker hidden
//     and forced to that company).
//
// Backend: api/staff-posts.ts (content_manage gated server-side).
//
// FP-23 permission gate: the parent passes `canEdit` (computed from
// useStaffPermissions().canDo('content_manage')). When false the
// create/edit/delete CTAs are hidden (template guard) AND the handlers
// bail with a console.warn (defensive). Read stays available so a
// staffer without content_manage can still see the list.
//
// fixedOwner contract:
//   undefined -> StaffNewsView mode. List unfiltered by owner; the
//                modal shows an owner_type picker (platform / company)
//                plus an owner_id input when company is chosen.
//   { type:'company', id } -> the list is fetched with owner_type=
//                company & owner_id=id; the modal hides the picker and
//                always submits that owner.
// =============================================================================

import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, X, Pencil, Trash2 } from 'lucide-vue-next'
import {
  CBadge,
  CLoader,
  CButton,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CCheckbox,
  CSelect,
} from '@/components/ui'
import { useToast } from '@/composables/useToast'
import {
  fetchStaffPosts,
  createStaffPost,
  updateStaffPost,
  deleteStaffPost,
} from '@/api/staff-posts'
import type {
  PostResponse,
  CreatePostRequest,
  UpdatePostRequest,
} from '@/api/types'

const props = defineProps<{
  /** When set, scope the list + new posts to this company and hide the owner picker. */
  fixedOwner?: { type: 'company'; id: string }
  /** content_manage gate from the parent (FP-23). */
  canEdit: boolean
}>()

const { t } = useI18n()
const { showToast } = useToast()

// -- List state --
const items = ref<PostResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const error = ref(false)

// -- Editor modal state --
const showEditor = ref(false)
// null id = create mode; non-null = edit mode.
const editId = ref<string | null>(null)
const saving = ref(false)

// -- Delete confirm state --
const deleteTarget = ref<PostResponse | null>(null)
const deleting = ref(false)

// Editor form. owner_type / owner_id only meaningful when no fixedOwner.
const form = reactive({
  owner_type: 'platform' as 'platform' | 'company',
  owner_id: '',
  title: '',
  body: '',
  cover_url: '',
  tags: [] as string[],
  is_banner: false,
  is_published: false,
})

// Tag chip-add: the in-progress tag text before Enter / comma commits it.
const tagDraft = ref('')

const totalPages = computed(() => Math.ceil(total.value / perPage))

const ownerTypeOptions = [
  { value: 'platform', label: t('staff.platform.post.ownerPlatform') },
  { value: 'company', label: t('staff.platform.post.ownerCompany') },
]

// CSelect emits string; bridge to the typed union on the form.
const ownerTypeModel = computed<string>({
  get: () => form.owner_type,
  set: (v) => {
    form.owner_type = v === 'company' ? 'company' : 'platform'
  },
})

// Return type intentionally inferred (not annotated as string) so TS
// narrows to the 'primary' | 'accent' literal union that CBadge's
// variant prop accepts -- an explicit `: string` widens it and fails
// the assignment (same pattern as StaffUsersView's kycVariant).
function ownerBadgeVariant(ownerType: string) {
  return ownerType === 'platform' ? 'primary' : 'accent'
}

async function loadPosts(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchStaffPosts({
      owner_type: props.fixedOwner ? 'company' : undefined,
      owner_id: props.fixedOwner ? props.fixedOwner.id : undefined,
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
  form.owner_type = props.fixedOwner ? 'company' : 'platform'
  form.owner_id = props.fixedOwner ? props.fixedOwner.id : ''
  form.title = ''
  form.body = ''
  form.cover_url = ''
  form.tags = []
  form.is_banner = false
  form.is_published = false
  tagDraft.value = ''
}

function openCreate(): void {
  if (!props.canEdit) {
    console.warn('[PostListEditor] openCreate blocked: no content_manage')
    return
  }
  editId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(post: PostResponse): void {
  if (!props.canEdit) {
    console.warn('[PostListEditor] openEdit blocked: no content_manage')
    return
  }
  editId.value = post.id
  form.owner_type = post.owner_type === 'company' ? 'company' : 'platform'
  form.owner_id = post.owner_id ?? ''
  form.title = post.title
  form.body = post.body
  form.cover_url = post.cover_url ?? ''
  form.tags = post.tags ? [...post.tags] : []
  form.is_banner = post.is_banner
  form.is_published = post.is_published
  tagDraft.value = ''
  showEditor.value = true
}

// -- Tag chip-add --

function commitTag(): void {
  const raw = tagDraft.value.trim()
  if (!raw) return
  // Dedup case-sensitively; backend caps each tag at 50 chars (schema),
  // so trim to 50 here for immediate feedback rather than a 422 later.
  const tag = raw.slice(0, 50)
  if (!form.tags.includes(tag)) {
    form.tags.push(tag)
  }
  tagDraft.value = ''
}

function onTagKeydown(e: KeyboardEvent): void {
  // Enter or comma commits the current draft as a chip.
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    commitTag()
  } else if (e.key === 'Backspace' && tagDraft.value === '' && form.tags.length > 0) {
    // Backspace on an empty input removes the last chip (common UX).
    form.tags.pop()
  }
}

function removeTag(tag: string): void {
  const idx = form.tags.indexOf(tag)
  if (idx !== -1) form.tags.splice(idx, 1)
}

// -- Save (create or update) --

const canSubmit = computed<boolean>(() => {
  if (!form.title.trim() || !form.body.trim()) return false
  // company owner requires an owner_id (UUID). When fixedOwner is set
  // the id is injected and the field is hidden, so this only bites the
  // StaffNewsView manual-company path.
  if (form.owner_type === 'company' && !form.owner_id.trim()) return false
  return true
})

async function handleSave(): Promise<void> {
  if (!props.canEdit) {
    console.warn('[PostListEditor] handleSave blocked: no content_manage')
    return
  }
  if (!canSubmit.value) return

  saving.value = true
  try {
    if (editId.value === null) {
      // Create. owner_id is omitted for platform posts (backend wants
      // null there) and sent for company posts.
      const payload: CreatePostRequest = {
        owner_type: form.owner_type,
        owner_id: form.owner_type === 'company' ? form.owner_id.trim() : null,
        title: form.title.trim(),
        body: form.body.trim(),
        cover_url: form.cover_url.trim() || null,
        tags: form.tags.length ? form.tags : null,
        is_banner: form.is_banner,
        is_published: form.is_published,
      }
      await createStaffPost(payload)
      showToast(t('staff.platform.post.created'), 'success')
    } else {
      // Update. owner_type / owner_id are immutable post-create on the
      // backend schema (UpdatePostRequest omits them), so we only send
      // the editable fields.
      const payload: UpdatePostRequest = {
        title: form.title.trim(),
        body: form.body.trim(),
        cover_url: form.cover_url.trim() || null,
        tags: form.tags.length ? form.tags : null,
        is_banner: form.is_banner,
        is_published: form.is_published,
      }
      await updateStaffPost(editId.value, payload)
      showToast(t('staff.platform.post.updated'), 'success')
    }
    showEditor.value = false
    await loadPosts()
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    saving.value = false
  }
}

// -- Delete --

function openDelete(post: PostResponse): void {
  if (!props.canEdit) {
    console.warn('[PostListEditor] openDelete blocked: no content_manage')
    return
  }
  deleteTarget.value = post
}

async function handleDelete(): Promise<void> {
  if (!props.canEdit || !deleteTarget.value) {
    if (!props.canEdit) {
      console.warn('[PostListEditor] handleDelete blocked: no content_manage')
    }
    return
  }
  deleting.value = true
  try {
    await deleteStaffPost(deleteTarget.value.id)
    showToast(t('staff.platform.post.deleted'), 'success')
    deleteTarget.value = null
    // If we just deleted the last row on a page beyond the first, step back.
    // BUG-38-01: stepping the page back triggers the page watcher,
    // which reloads on its own. Only reload inline when the page is
    // unchanged -- otherwise both this call and the watcher fire and
    // race two requests for the same list.
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await loadPosts()
    }
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    deleting.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

watch(page, () => loadPosts())
onMounted(loadPosts)
</script>

<template>
  <div class="ple">
    <!-- Create CTA (FP-23: hidden without content_manage). -->
    <div v-if="canEdit" class="ple__toolbar">
      <CButton variant="primary" size="sm" @click="openCreate">
        <Plus :size="16" />
        {{ t('staff.platform.post.createCta') }}
      </CButton>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="ple__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="ple__center">
      <CButton variant="secondary" size="sm" @click="loadPosts">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.post.empty')" />

    <!-- List -->
    <template v-else>
      <div class="post-list">
        <div v-for="post in items" :key="post.id" class="post-item">
          <div class="post-item__info">
            <div class="post-item__top">
              <CBadge
                :variant="ownerBadgeVariant(post.owner_type)"
                :text="post.owner_type"
              />
              <CBadge
                v-if="post.is_banner"
                variant="warning"
                :text="t('staff.platform.post.bannerBadge')"
              />
              <CBadge
                :variant="post.is_published ? 'success' : 'neutral'"
                :text="post.is_published
                  ? t('staff.platform.post.published')
                  : t('staff.platform.post.draft')"
              />
            </div>
            <div class="post-item__title">{{ post.title }}</div>
            <div class="post-item__date">{{ formatDate(post.created_at) }}</div>
          </div>
          <div v-if="canEdit" class="post-item__actions">
            <button
            :aria-label="t('common.edit')" class="post-item__icon-btn" @click="openEdit(post)">
              <Pencil :size="16" />
            </button>
            <button
            :aria-label="t('common.delete')" class="post-item__icon-btn post-item__icon-btn--danger" @click="openDelete(post)">
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="ple__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">&larr;</CButton>
        <span class="ple__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">&rarr;</CButton>
      </div>
    </template>

    <!-- Editor modal -->
    <CModal :open="showEditor" @close="showEditor = false">
      <h3 class="ple__modal-title">
        {{ editId === null
          ? t('staff.platform.post.createTitle')
          : t('staff.platform.post.editTitle') }}
      </h3>

      <!-- Owner picker: only when not fixed to a company. -->
      <template v-if="!fixedOwner">
        <CSelect
          v-model="ownerTypeModel"
          :label="t('staff.platform.post.ownerType')"
          :options="ownerTypeOptions"
        />
        <CInput
          v-if="form.owner_type === 'company'"
          v-model="form.owner_id"
          :label="t('staff.platform.post.ownerId')"
          :placeholder="t('staff.platform.post.ownerIdPlaceholder')"
        />
      </template>

      <CInput
        v-model="form.title"
        :label="t('staff.platform.post.fieldTitle')"
        :placeholder="t('staff.platform.post.fieldTitle')"
      />
      <CTextarea
        v-model="form.body"
        :label="t('staff.platform.post.fieldBody')"
        :placeholder="t('staff.platform.post.fieldBody')"
        :rows="6"
      />
      <CInput
        v-model="form.cover_url"
        :label="t('staff.platform.post.fieldCover')"
        :placeholder="t('staff.platform.post.fieldCoverPlaceholder')"
      />

      <!-- Tag chip-add -->
      <div class="ple__tags-group">
        <label class="ple__label">{{ t('staff.platform.post.fieldTags') }}</label>
        <div class="ple__chips">
          <span v-for="tag in form.tags" :key="tag" class="ple__chip">
            {{ tag }}
            <button
        :aria-label="t('common.close')" type="button" class="ple__chip-x" @click="removeTag(tag)">
              <X :size="16" />
            </button>
          </span>
        </div>
        <!-- A4: placeholder is a hint, not a name; it vanishes on first keypress. -->
        <CInput
          v-model="tagDraft"
          :aria-label="t('staff.platform.post.tagPlaceholder')"
          :placeholder="t('staff.platform.post.tagPlaceholder')"
          @keydown="onTagKeydown"
        />
      </div>

      <div class="ple__toggles">
        <CCheckbox v-model="form.is_banner" :label="t('staff.platform.post.isBanner')" />
        <CCheckbox v-model="form.is_published" :label="t('staff.platform.post.isPublished')" />
      </div>

      <div class="ple__modal-actions">
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
      <h3 class="ple__modal-title">{{ t('staff.platform.post.deleteTitle') }}</h3>
      <p class="ple__modal-text">{{ t('staff.platform.post.deleteConfirm') }}</p>
      <p v-if="deleteTarget" class="ple__modal-target">{{ deleteTarget.title }}</p>
      <div class="ple__modal-actions">
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
.ple { padding: 0; }

.ple__toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-3);
}

.ple__center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; min-height: var(--center-md); gap: var(--space-4);
}

.post-list { display: flex; flex-direction: column; }
.post-item {
  display: flex; align-items: center; gap: var(--space-3); padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
}
.post-item__info { flex: 1; min-width: 0; }
.post-item__top { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-2); }
.post-item__title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.post-item__date { font-size: var(--fs-xs); color: var(--text-tertiary); margin-top: var(--space-1); }
.post-item__actions { display: flex; gap: var(--space-1); flex-shrink: 0; }
.post-item__icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: var(--size-md); height: var(--size-md); border: none; background: none;
  color: var(--text-secondary); cursor: pointer; border-radius: var(--radius-sm);
  transition: background 0.15s, color 0.15s;
}
.post-item__icon-btn:hover { background: var(--bg-subtle); }
.post-item__icon-btn--danger:hover { color: var(--danger); }

.ple__pagination {
  display: flex; align-items: center; justify-content: center;
  gap: var(--space-3); margin-top: var(--space-4);
}
.ple__page { font-size: var(--fs-xs); color: var(--text-secondary); }

.ple__modal-title { font-size: var(--fs-h4); font-weight: 700; color: var(--text-primary); margin: 0 0 var(--space-4); }
.ple__modal-text { font-size: var(--fs-sm); color: var(--text-secondary); margin: 0 0 var(--space-2); }
.ple__modal-target { font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary); margin: 0 0 var(--space-4); }
.ple__modal-actions { display: flex; gap: var(--space-2); margin-top: var(--space-4); justify-content: flex-end; }

.ple__label {
  display: block; font-size: var(--fs-xs); font-weight: 600;
  color: var(--text-primary); margin-bottom: var(--space-2);
}
.ple__tags-group { margin-bottom: var(--space-4); }
.ple__chips { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-2); }
.ple__chip {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm);
  background: var(--bg-subtle); color: var(--text-primary); font-size: var(--fs-xs); font-weight: 500;
}
.ple__chip-x {
  display: flex; align-items: center; border: none; background: none;
  color: var(--text-tertiary); cursor: pointer; padding: 0;
}
.ple__chip-x:hover { color: var(--danger); }

.ple__toggles { display: flex; flex-direction: column; gap: var(--space-3); margin-bottom: var(--space-2); }
</style>
