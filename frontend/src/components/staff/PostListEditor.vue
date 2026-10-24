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
// bail with a console.warn (defensive). The list itself needs content_manage on the server, so the section is not drawn without it.
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
import { Plus, X, Pencil, Trash2 } from '@/components/ui/icons'
import {
  CBadge,
  CButton,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CCheckbox,
  CSelect,
} from '@/components/ui'
import StaffListSkeleton from './StaffListSkeleton.vue'
import StaffPager from './StaffPager.vue'
import { useUrlPage } from './useUrlPage'
import { useToast } from '@/composables/useToast'
import {
  fetchStaffPosts,
  createStaffPost,
  updateStaffPost,
  deleteStaffPost,
} from '@/api/staff-posts'
import type { PostResponse, CreatePostRequest, UpdatePostRequest } from '@/api/types'

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
const page = useUrlPage()
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
      <CButton variant="primary" size="sm" inline @click="openCreate">
        <Plus size="sm" />
        {{ t('staff.platform.post.createCta') }}
      </CButton>
    </div>

    <!-- Loading -->
    <StaffListSkeleton v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadPosts">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.platform.post.empty')" />

    <!-- List (K23 rows) -->
    <template v-else>
      <ul class="ds-rows post-list">
        <li v-for="post in items" :key="post.id" class="ds-row post-item">
          <span class="ds-row__body">
            <span class="ds-row__title">{{ post.title }}</span>
            <span class="ds-row__meta">{{ formatDate(post.created_at) }}</span>
          </span>
          <span class="ds-row__trail post-item__trail">
            <CBadge :variant="ownerBadgeVariant(post.owner_type)" :text="post.owner_type" />
            <CBadge
              v-if="post.is_banner"
              variant="warning"
              :text="t('staff.platform.post.bannerBadge')"
            />
            <CBadge
              :variant="post.is_published ? 'success' : 'neutral'"
              :text="
                post.is_published
                  ? t('staff.platform.post.published')
                  : t('staff.platform.post.draft')
              "
            />
            <template v-if="canEdit">
              <button
                type="button"
                class="ds-button ds-button--ghost ds-button--icon"
                data-size="sm"
                :aria-label="t('common.edit')"
                @click="openEdit(post)"
              >
                <Pencil />
              </button>
              <button
                type="button"
                class="ds-button ds-button--danger ds-button--icon"
                data-size="sm"
                :aria-label="t('common.delete')"
                @click="openDelete(post)"
              >
                <Trash2 />
              </button>
            </template>
          </span>
        </li>
      </ul>

      <!-- Pagination (K17) -->
      <StaffPager :page="page" :total-pages="totalPages" @update:page="(n: number) => (page = n)" />
    </template>

    <!-- Editor modal -->
    <CModal
      :open="showEditor"
      :title="
        editId === null ? t('staff.platform.post.createTitle') : t('staff.platform.post.editTitle')
      "
      @close="showEditor = false"
    >
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

      <!-- Tags: removable chips (K13) and the field that adds one -->
      <fieldset class="ds-fieldset">
        <legend class="ds-fieldset__legend">{{ t('staff.platform.post.fieldTags') }}</legend>
        <div v-if="form.tags.length" class="ds-chip-row">
          <span v-for="tag in form.tags" :key="tag" class="ds-chip ds-chip--removable">
            <span>{{ tag }}</span>
            <button
              type="button"
              class="ds-chip__remove"
              :aria-label="t('common.close')"
              @click="removeTag(tag)"
            >
              <X size="sm" />
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
      </fieldset>

      <CCheckbox v-model="form.is_banner" :label="t('staff.platform.post.isBanner')" />
      <CCheckbox v-model="form.is_published" :label="t('staff.platform.post.isPublished')" />

      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showEditor = false">
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
      :title="t('staff.platform.post.deleteTitle')"
      @close="deleteTarget = null"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.post.deleteConfirm') }}
      </p>
      <p v-if="deleteTarget" class="ple__target">
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
.ple {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.ple__toolbar {
  display: flex;
  justify-content: flex-end;
}

.ple__target {
  margin: 0;
  font-weight: 600;
  color: var(--text-primary);
}

/* On a narrow row the trail drops under the text instead of squeezing it: the row wraps, and the
   text keeps a floor of its own width (the system's trail does not shrink). */
.post-item {
  flex-wrap: wrap;
}
.post-item .ds-row__body {
  flex: 1 1 var(--center-sm);
}
.post-item__trail {
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-inline-start: auto;
}
</style>
