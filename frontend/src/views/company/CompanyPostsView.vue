<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyPostsView (TASK-30 self-service, W4)
// =============================================================================
//
// News-post CRUD for the CALLER'S OWN company (TASK-30-SPEC.md §4:
// "news posts" is listed under the set of things a project may edit
// about itself). Backend: posts/company_router.py
// (/api/v1/company/posts). Adapted from the two sibling TASK-30
// self-service screens that established this convention:
//   - CompanyRoadmapView.vue -- own fetch/loading/error state (no
//     parent detail view to inject from, same reasoning applies here:
//     there is no company-side equivalent of StaffCompanyDetailView),
//     the diff-based buildUpdateBody() pattern for PATCH bodies, the
//     create/edit + delete-confirm CModal pairing, and the
//     ApiResponseError -> toast(e.detail) fallback-to-common.error
//     handling used throughout handleSave/handleDelete below.
//   - CompanyAttachmentsView.vue -- same "drops the FP-23 canDo
//     gate" reasoning: every authenticated company user IS the
//     project (backend enforcement is get_current_company_profile,
//     role=company), so there is no separate "manage" permission to
//     check on this side of the fence, unlike PostListEditor.vue's
//     staff surface (content_manage-gated).
//
// List + filter + pagination shape is instead lifted from
// StaffCompaniesListView.vue (status filter chips + debounced search +
// page controls) rather than PostListEditor.vue's plain unfiltered
// list -- PostListEditor has no is_published filter or search box at
// all, and the spec for this screen calls for both.
//
// FIELDS. Same four editable fields as CreateCompanyPostRequest /
// UpdateCompanyPostRequest (posts/schemas.py): title, body, cover_url,
// tags, is_published. Tag chip-add (type, Enter/comma commits) is
// PostListEditor.vue's exact interaction, copied rather than
// reinvented. `is_banner` does NOT exist on this surface at all -- it
// is a staff-only editorial privilege (the site-wide homepage banner)
// and is never rendered here; every company-authored post is created
// with is_banner=False server-side (see company_router.py's module
// docstring).
//
// WHERE THIS LIVES.
//   Reached from Settings (CompanySettingsView's new "Posts" row),
//   same placement reasoning as roadmap/attachments -- COMPANY_TABS
//   already has 5 fixed slots and post management is occasional, not
//   daily. Route: /company/posts (router/index.ts, name
//   'company-posts').
//
// MODERATION: none, by design -- see company_router.py's module
// docstring ("not needed even as a task"). A post the project marks
// is_published=true publishes the moment the request lands.
// =============================================================================

import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ArrowLeft, Pencil, Trash2, Newspaper, Plus, X } from 'lucide-vue-next'
import {
  CLoader,
  CButton,
  CBadge,
  CEmptyState,
  CModal,
  CInput,
  CTextarea,
  CCheckbox,
} from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import { fetchOwnPosts, createOwnPost, updateOwnPost, deleteOwnPost } from '@/api/company-posts'
import type { PostResponse, CreateCompanyPostRequest, UpdateCompanyPostRequest } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const router = useRouter()

// ---------------------------------------------------------------------------
// Data source -- own fetch, own loading/error state (no parent context,
// same reasoning as CompanyRoadmapView.vue / CompanyAttachmentsView.vue)
// ---------------------------------------------------------------------------

const items = ref<PostResponse[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const loading = ref(true)
const errored = ref(false)

const statusFilter = ref<'' | 'published' | 'draft'>('')
const search = ref('')

// Debounce handle for the search box (mirrors StaffCompaniesListView.vue).
let searchTimer: ReturnType<typeof setTimeout> | null = null

const totalPages = computed(() => Math.ceil(total.value / perPage))

async function reload(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const resp = await fetchOwnPosts({
      is_published:
        statusFilter.value === 'published'
          ? true
          : statusFilter.value === 'draft'
            ? false
            : undefined,
      search: search.value.trim() || undefined,
      page: page.value,
      per_page: perPage,
    })
    items.value = resp.items
    total.value = resp.total
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}

function setStatusFilter(s: '' | 'published' | 'draft'): void {
  statusFilter.value = s
  page.value = 1
  void reload()
}

function goToPrevPage(): void {
  page.value--
  void reload()
}

function goToNextPage(): void {
  page.value++
  void reload()
}

// Search debounce: reset to page 1 and reload 300ms after the last
// keystroke -- identical shape to StaffCompaniesListView.vue's watcher.
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    void reload()
  }, 300)
})

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

onMounted(() => {
  void reload()
})

// ---------------------------------------------------------------------------
// Create / edit modal
// ---------------------------------------------------------------------------

const showForm = ref(false)
const editingId = ref<string | null>(null)
const editingOriginal = ref<PostResponse | null>(null)
const saving = ref(false)

const draftTitle = ref('')
const draftBody = ref('')
const draftCoverUrl = ref('')
const draftTags = ref<string[]>([])
const draftIsPublished = ref(false)

// Tag chip-add: the in-progress tag text before Enter / comma commits it.
// Interaction copied verbatim from PostListEditor.vue.
const tagDraft = ref('')

const isEditing = computed<boolean>(() => editingId.value !== null)

function resetDraft(): void {
  draftTitle.value = ''
  draftBody.value = ''
  draftCoverUrl.value = ''
  draftTags.value = []
  draftIsPublished.value = false
  tagDraft.value = ''
}

function openCreate(): void {
  editingId.value = null
  editingOriginal.value = null
  resetDraft()
  showForm.value = true
}

function openEdit(post: PostResponse): void {
  editingId.value = post.id
  editingOriginal.value = post
  draftTitle.value = post.title
  draftBody.value = post.body
  draftCoverUrl.value = post.cover_url ?? ''
  draftTags.value = post.tags ? [...post.tags] : []
  draftIsPublished.value = post.is_published
  tagDraft.value = ''
  showForm.value = true
}

function closeForm(): void {
  showForm.value = false
}

// -- Tag chip-add --

function commitTag(): void {
  const raw = tagDraft.value.trim()
  if (!raw) return
  // Dedup case-sensitively; backend caps each tag at 50 chars (schema),
  // so trim to 50 here for immediate feedback rather than a 422 later.
  const tag = raw.slice(0, 50)
  if (!draftTags.value.includes(tag)) {
    draftTags.value.push(tag)
  }
  tagDraft.value = ''
}

function onTagKeydown(e: KeyboardEvent): void {
  // Enter or comma commits the current draft as a chip.
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    commitTag()
  } else if (e.key === 'Backspace' && tagDraft.value === '' && draftTags.value.length > 0) {
    // Backspace on an empty input removes the last chip (common UX).
    draftTags.value.pop()
  }
}

function removeTag(tag: string): void {
  const idx = draftTags.value.indexOf(tag)
  if (idx !== -1) draftTags.value.splice(idx, 1)
}

const trimmedTitle = computed<string>(() => draftTitle.value.trim())
const trimmedBody = computed<string>(() => draftBody.value.trim())
const trimmedCoverUrl = computed<string>(() => draftCoverUrl.value.trim())

// Same http(s):// validation pattern as CompanyRoadmapView.vue's
// externalUrlValid / StaffCompanyRoadmapSection.vue's original.
const coverUrlValid = computed<boolean>(() => {
  const v = trimmedCoverUrl.value
  if (!v) return true
  return v.startsWith('http://') || v.startsWith('https://')
})

const canSubmit = computed<boolean>(() => {
  if (!trimmedTitle.value || !trimmedBody.value) return false
  if (!coverUrlValid.value) return false
  return true
})

function buildCreateBody(): CreateCompanyPostRequest {
  const body: CreateCompanyPostRequest = {
    title: trimmedTitle.value,
    body: trimmedBody.value,
    is_published: draftIsPublished.value,
  }
  if (trimmedCoverUrl.value) body.cover_url = trimmedCoverUrl.value
  if (draftTags.value.length) body.tags = draftTags.value
  return body
}

// Diff-based PATCH body -- only fields that actually changed, same
// pattern as CompanyRoadmapView.vue's buildUpdateBody / CompanyAttachmentsView.vue's
// buildPatchBody: an omitted field is kept server-side, an explicit
// null clears it.
function buildUpdateBody(): UpdateCompanyPostRequest {
  const orig = editingOriginal.value
  const body: UpdateCompanyPostRequest = {}
  if (!orig) return body

  if (trimmedTitle.value !== orig.title) {
    body.title = trimmedTitle.value
  }
  if (trimmedBody.value !== orig.body) {
    body.body = trimmedBody.value
  }

  const origCoverUrl = orig.cover_url ?? ''
  if (trimmedCoverUrl.value !== origCoverUrl) {
    body.cover_url = trimmedCoverUrl.value ? trimmedCoverUrl.value : null
  }

  const origTags = orig.tags ?? []
  const tagsChanged =
    draftTags.value.length !== origTags.length ||
    draftTags.value.some((tag, i) => tag !== origTags[i])
  if (tagsChanged) {
    body.tags = draftTags.value.length ? draftTags.value : null
  }

  if (draftIsPublished.value !== orig.is_published) {
    body.is_published = draftIsPublished.value
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
      await updateOwnPost(editingId.value, body)
      showToast(t('comp.posts.updated'), 'success')
    } else {
      await createOwnPost(buildCreateBody())
      showToast(t('comp.posts.created'), 'success')
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
// Soft-delete -- mirrors StaffCompanyRoadmapSection.vue's / CompanyRoadmapView.vue's
// delete-confirm pattern exactly.
// ---------------------------------------------------------------------------

const deleteTarget = ref<PostResponse | null>(null)
const deleting = ref(false)

function openDelete(post: PostResponse): void {
  deleteTarget.value = post
}

async function handleDelete(): Promise<void> {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteOwnPost(deleteTarget.value.id)
    showToast(t('comp.posts.deleted'), 'success')
    deleteTarget.value = null
    // If we just deleted the last row on a page beyond the first, step
    // back rather than reloading an empty page (same guard as
    // PostListEditor.vue's handleDelete, BUG-38-01).
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
      await reload()
    } else {
      await reload()
    }
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
  <div class="cpost">
    <!-- Inline page header, back link to Settings (where the entry point lives) -->
    <div class="cpost__header">
      <button type="button" class="cpost__back" @click="goBack">
        <ArrowLeft :size="16" />
        {{ t('comp.settings.title') }}
      </button>
      <h1 class="cpost__page-title">
        {{ t('comp.posts.title') }}
      </h1>
      <p class="cpost__page-subtitle">
        {{ t('comp.posts.subtitle') }}
      </p>
    </div>

    <!-- Filters: is_published chips -->
    <div class="cpost__filters">
      <button class="filter-chip" :class="{ active: !statusFilter }" @click="setStatusFilter('')">
        {{ t('comp.posts.filterAll') }}
      </button>
      <button
        v-for="s in ['published', 'draft'] as const"
        :key="s"
        class="filter-chip"
        :class="{ active: statusFilter === s }"
        @click="setStatusFilter(s)"
      >
        {{ t(`comp.posts.${s}`) }}
      </button>
    </div>

    <!-- Search -->
    <!-- A4: a placeholder is not an accessible name -- it is a hint, and it
         disappears the moment the user types. The visible design is a bare
         search box, so the name goes on the control rather than into a label. -->
    <div class="cpost__search">
      <CInput
        v-model="search"
        :aria-label="t('comp.posts.searchPlaceholder')"
        :placeholder="t('comp.posts.searchPlaceholder')"
      />
    </div>

    <div class="cpost__toolbar">
      <CButton variant="primary" size="sm" @click="openCreate">
        <Plus :size="16" />
        {{ t('comp.posts.addCta') }}
      </CButton>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="cpost__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="cpost__center">
      <CEmptyState :title="t('comp.posts.errorTitle')" />
      <CButton variant="outline" size="sm" @click="reload">
        {{ t('comp.posts.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <template v-else>
      <CEmptyState v-if="!items.length" :title="t('comp.posts.empty')">
        <template #icon>
          <Newspaper :size="40" />
        </template>
      </CEmptyState>

      <div v-else class="post-list">
        <div v-for="post in items" :key="post.id" class="post-item">
          <div class="post-item__info">
            <div class="post-item__top">
              <CBadge
                :variant="post.is_published ? 'success' : 'neutral'"
                :text="t(`comp.posts.${post.is_published ? 'published' : 'draft'}`)"
              />
            </div>
            <div class="post-item__title">
              {{ post.title }}
            </div>
            <div class="post-item__meta">
              <span>{{ t('comp.posts.createdAt') }}: {{ formatDateTime(post.created_at) }}</span>
              <span v-if="post.updated_at">
                &bull; {{ t('comp.posts.updatedAt') }}: {{ formatDateTime(post.updated_at) }}
              </span>
            </div>
          </div>
          <div class="post-item__actions">
            <button
              :aria-label="t('common.edit')"
              class="post-item__action"
              @click="openEdit(post)"
            >
              <Pencil :size="16" />
            </button>
            <button
              :aria-label="t('common.delete')"
              class="post-item__action"
              @click="openDelete(post)"
            >
              <Trash2 :size="16" />
            </button>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="cpost__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="goToPrevPage">
          &larr;
        </CButton>
        <span class="cpost__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="goToNextPage">
          &rarr;
        </CButton>
      </div>
    </template>

    <!-- Create / edit modal -->
    <CModal :open="showForm" @close="closeForm">
      <h3 class="cpost__modal-title">
        {{ isEditing ? t('comp.posts.editTitle') : t('comp.posts.createTitle') }}
      </h3>

      <CInput
        v-model="draftTitle"
        :label="t('comp.posts.fieldTitle')"
        :placeholder="t('comp.posts.fieldTitle')"
        maxlength="500"
      />

      <CTextarea
        v-model="draftBody"
        :label="t('comp.posts.fieldBody')"
        :placeholder="t('comp.posts.fieldBody')"
        :rows="10"
        maxlength="50000"
      />

      <CInput
        v-model="draftCoverUrl"
        :label="t('comp.posts.fieldCoverUrl')"
        :placeholder="t('comp.posts.fieldCoverUrlPlaceholder')"
        maxlength="2000"
        :error="!coverUrlValid ? t('comp.posts.coverUrlError') : ''"
      />

      <!-- Tag chip-add -- interaction copied verbatim from PostListEditor.vue -->
      <div class="cpost__tags-group">
        <label class="cpost__field-label">{{ t('comp.posts.fieldTags') }}</label>
        <div class="cpost__chips">
          <span v-for="tag in draftTags" :key="tag" class="cpost__chip">
            {{ tag }}
            <button
              :aria-label="t('common.close')"
              type="button"
              class="cpost__chip-x"
              @click="removeTag(tag)"
            >
              <X :size="16" />
            </button>
          </span>
        </div>
        <CInput
          v-model="tagDraft"
          :aria-label="t('comp.posts.tagPlaceholder')"
          :placeholder="t('comp.posts.tagPlaceholder')"
          @keydown="onTagKeydown"
        />
      </div>

      <CCheckbox v-model="draftIsPublished" :label="t('comp.posts.published')" />

      <div class="cpost__modal-actions">
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
      <h3 class="cpost__modal-title">
        {{ t('comp.posts.deleteTitle') }}
      </h3>
      <p class="cpost__modal-hint">
        {{ t('comp.posts.deleteConfirm') }}
      </p>
      <div class="cpost__modal-actions">
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
.cpost {
  padding-bottom: var(--space-5);
}

.cpost__header {
  padding: var(--space-4) var(--space-4) 0;
}
.cpost__back {
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
.cpost__back:hover {
  color: var(--text-primary);
}
.cpost__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}
.cpost__page-subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}

.cpost__filters {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding: 0 var(--space-4) var(--space-1);
}
.filter-chip {
  position: relative;
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-transform: capitalize;
  font-family: inherit;
}
.filter-chip::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}
.filter-chip.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.cpost__search {
  padding: var(--space-3) var(--space-4) 0;
}

.cpost__toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0 var(--space-4);
  margin-bottom: var(--space-4);
}

.cpost__center {
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

/* -- List -- */
.post-list {
  display: flex;
  flex-direction: column;
  padding: 0 var(--space-4);
}
.post-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--border-default);
}
.post-item__info {
  flex: 1;
  min-width: 0;
}
.post-item__top {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}
.post-item__title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}
.post-item__meta {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

.post-item__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 0 0 auto;
}
.post-item__action {
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
.post-item__action:hover {
  color: var(--text-primary);
  background: var(--bg-page);
}

.cpost__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.cpost__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

/* -- Modal -- */
.cpost__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.cpost__modal-hint {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--space-4);
}
.cpost__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  justify-content: flex-end;
}

.cpost__field-label {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.cpost__tags-group {
  margin-bottom: var(--space-4);
}
.cpost__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.cpost__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-size: var(--fs-xs);
  font-weight: 500;
}
.cpost__chip-x {
  display: flex;
  align-items: center;
  border: none;
  background: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 0;
}
.cpost__chip-x:hover {
  color: var(--danger);
}
</style>
