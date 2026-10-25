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
//
// LANGUAGES (H38 P-132): title and body are edited in every language of the
// interface (LocalizedTextFields), English the base and required; the form
// starts from the post's base and translations, not from the displayed
// (reader's) texts. The preview shows the English base.
// =============================================================================

import { ref, computed, onMounted, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, Pencil, Trash2, Newspaper, Plus, X, Check } from '@/components/ui/icons'
import { CButton, CBadge, CEmptyState, CModal, CInput, CCheckbox } from '@/components/ui'
import LocalizedTextFields from '@/components/shared/LocalizedTextFields.vue'
import type { LocalizedField } from '@/components/shared/LocalizedTextFields.vue'
import {
  baseText,
  emptyDraft,
  makeDraft,
  sameTranslations,
  translationsFromDraft,
} from '@/utils/projectTexts'
import type { TextDraft } from '@/utils/projectTexts'
import { useScreenHeader } from '@/components/layout/screenHeader'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import { fetchOwnPosts, createOwnPost, updateOwnPost, deleteOwnPost } from '@/api/company-posts'
import type { PostResponse, CreateCompanyPostRequest, UpdateCompanyPostRequest } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const { t, locale } = useI18n()
const { showToast } = useToast()
const tagsId = useId()

// The frame's header carries the title, the line under it and the way back to Publications.
useScreenHeader({
  title: () => t('comp.posts.title'),
  lead: () => t('comp.posts.subtitle'),
  back: '/company/publications',
})

// ---------------------------------------------------------------------------
// Data source -- own fetch, own loading/error state (no parent context,
// same reasoning as CompanyRoadmapView.vue / CompanyAttachmentsView.vue)
// ---------------------------------------------------------------------------

const items = ref<PostResponse[]>([])
const total = ref(0)
// A page is an address (the Pager, K17): `?page=n`.
const page = useUrlPage()
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

function goToPage(n: number): void {
  page.value = n
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

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => reload())

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

const TEXT_FIELDS = ['title', 'body'] as const
const draftTexts = ref<TextDraft>(emptyDraft(TEXT_FIELDS))
const textFields = computed<LocalizedField[]>(() => [
  { key: 'title', label: t('comp.posts.fieldTitle'), maxlength: 500 },
  { key: 'body', label: t('comp.posts.fieldBody'), multiline: true, rows: 10, maxlength: 50000 },
])
// The English base, for the checks and the preview.
const draftTitle = computed<string>(() => baseText(draftTexts.value, 'title'))
const draftBody = computed<string>(() => baseText(draftTexts.value, 'body'))
const draftCoverUrl = ref('')
const draftTags = ref<string[]>([])

// The preview: the post as a buyer will read it, built from the draft before
// anything is published. Nothing is sent to the server.
const showPreview = ref(false)
const previewDate = computed<string>(() => new Date().toLocaleDateString(locale.value))
const draftIsPublished = ref(false)

// Tag chip-add: the in-progress tag text before Enter / comma commits it.
// Interaction copied verbatim from PostListEditor.vue.
const tagDraft = ref('')

const isEditing = computed<boolean>(() => editingId.value !== null)

function resetDraft(): void {
  draftTexts.value = emptyDraft(TEXT_FIELDS)
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
  draftTexts.value = makeDraft(TEXT_FIELDS, post.base, post.translations)
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
    translations: translationsFromDraft(draftTexts.value, TEXT_FIELDS, {}),
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

  // Against the English base, not the displayed (reader's) texts.
  if (trimmedTitle.value !== (orig.base?.title ?? '')) {
    body.title = trimmedTitle.value
  }
  if (trimmedBody.value !== (orig.base?.body ?? '')) {
    body.body = trimmedBody.value
  }
  const translations = translationsFromDraft(draftTexts.value, TEXT_FIELDS, orig.translations)
  if (!sameTranslations(translations, orig.translations)) {
    body.translations = translations
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
</script>

<template>
  <!-- Filters: is_published chips, the search, and the one primary action -->
  <div class="ds-shell__toolbar">
    <div class="ds-shell__filters">
      <div class="ds-chip-row" role="group" :aria-label="t('comp.posts.title')">
        <button
          class="ds-chip"
          :aria-pressed="!statusFilter"
          type="button"
          @click="setStatusFilter('')"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('comp.posts.filterAll') }}</span>
        </button>
        <button
          v-for="s in ['published', 'draft'] as const"
          :key="s"
          class="ds-chip"
          :aria-pressed="statusFilter === s"
          type="button"
          @click="setStatusFilter(s)"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t(`comp.posts.${s}`) }}</span>
        </button>
      </div>
      <!-- A4: a placeholder is not an accessible name -- it is a hint, and it
           disappears the moment the user types. The visible design is a bare
           search box, so the name goes on the control rather than into a label. -->
      <div class="ds-field">
        <input
          v-model="search"
          class="ds-input"
          type="search"
          :aria-label="t('comp.posts.searchPlaceholder')"
          :placeholder="t('comp.posts.searchPlaceholder')"
        />
      </div>
    </div>
    <div class="ds-shell__primary">
      <CButton variant="primary" size="sm" inline @click="openCreate">
        <Plus size="sm" />
        {{ t('comp.posts.addCta') }}
      </CButton>
    </div>
  </div>

  <!-- Loading -->
  <CListSkeleton v-if="loading" />

  <!-- Error -->
  <CEmptyState v-else-if="errored" tone="danger" :title="t('comp.posts.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="reload">
        {{ t('comp.posts.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded -->
  <template v-else>
    <CEmptyState v-if="!items.length" :title="t('comp.posts.empty')">
      <template #icon>
        <Newspaper />
      </template>
    </CEmptyState>

    <ul v-else class="ds-rows">
      <li v-for="post in items" :key="post.id" class="ds-row">
        <span class="ds-row__lead"><Newspaper size="sm" /></span>
        <span class="ds-row__body">
          <span class="ds-row__title">{{ post.title }}</span>
          <span class="ds-row__meta">
            {{ t('comp.posts.createdAt') }}: {{ formatDateTime(post.created_at) }}
            <template v-if="post.updated_at">
              &bull; {{ t('comp.posts.updatedAt') }}: {{ formatDateTime(post.updated_at) }}
            </template>
          </span>
        </span>
        <span class="ds-row__trail">
          <CBadge
            :variant="post.is_published ? 'success' : 'neutral'"
            :text="t(`comp.posts.${post.is_published ? 'published' : 'draft'}`)"
          />
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="`${t('common.edit')}: ${post.title}`"
            @click="openEdit(post)"
          >
            <Pencil size="sm" />
          </button>
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="`${t('common.delete')}: ${post.title}`"
            @click="openDelete(post)"
          >
            <Trash2 size="sm" />
          </button>
        </span>
      </li>
    </ul>

    <!-- Pagination (K17: a page is an address, ?page=n) -->
    <CPager :page="page" :total-pages="totalPages" @update:page="goToPage" />
  </template>

  <!-- Create / edit modal -->
  <CModal
    :open="showForm"
    :title="isEditing ? t('comp.posts.editTitle') : t('comp.posts.createTitle')"
    @close="closeForm"
  >
    <LocalizedTextFields v-model="draftTexts" :fields="textFields" />

    <CInput
      v-model="draftCoverUrl"
      :label="t('comp.posts.fieldCoverUrl')"
      :placeholder="t('comp.posts.fieldCoverUrlPlaceholder')"
      maxlength="2000"
      :error="!coverUrlValid ? t('comp.posts.coverUrlError') : ''"
    />

    <!-- Tag chip-add -- interaction copied verbatim from PostListEditor.vue -->
    <div class="ds-field c-field">
      <label class="ds-field__label" :for="tagsId">{{ t('comp.posts.fieldTags') }}</label>
      <div v-if="draftTags.length > 0" class="ds-chip-row">
        <span v-for="tag in draftTags" :key="tag" class="ds-chip ds-chip--removable">
          <span>{{ tag }}</span>
          <button
            type="button"
            class="ds-chip__remove"
            :aria-label="`${t('common.clear')} ${tag}`"
            @click="removeTag(tag)"
          >
            <X size="sm" />
          </button>
        </span>
      </div>
      <input
        :id="tagsId"
        v-model="tagDraft"
        class="ds-input"
        type="text"
        :placeholder="t('comp.posts.tagPlaceholder')"
        @keydown="onTagKeydown"
      />
    </div>

    <CCheckbox v-model="draftIsPublished" :label="t('comp.posts.published')" />

    <div class="ds-dialog__actions">
      <CButton variant="outline" size="sm" inline @click="closeForm">
        {{ t('common.cancel') }}
      </CButton>
      <CButton variant="outline" size="sm" inline @click="showPreview = true">
        <Eye size="sm" />
        {{ t('comp.posts.preview') }}
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

  <!-- Preview: the post as a buyer will see it, as the system's media card -->
  <CModal :open="showPreview" :title="t('comp.posts.preview')" @close="showPreview = false">
    <p class="ds-dialog__text">
      {{ t('comp.posts.previewNote') }}
    </p>
    <article class="ds-card ds-card--media">
      <div v-if="draftCoverUrl.trim() && coverUrlValid" class="ds-card__media" data-size="sm">
        <img :src="draftCoverUrl.trim()" :alt="draftTitle" />
      </div>
      <div class="ds-card__content">
        <h3 class="ds-card__title">{{ draftTitle }}</h3>
        <time class="ds-card__label">{{ previewDate }}</time>
        <p class="ds-card__body cpost__preview-body">{{ draftBody }}</p>
        <div v-if="draftTags.length > 0" class="ds-chip-row">
          <span v-for="tag in draftTags" :key="tag" class="ds-chip">
            <span>{{ tag }}</span>
          </span>
        </div>
      </div>
    </article>
    <div class="ds-dialog__actions">
      <CButton variant="outline" size="sm" inline @click="showPreview = false">
        {{ t('common.close') }}
      </CButton>
    </div>
  </CModal>

  <!-- Delete confirm -->
  <CModal :open="!!deleteTarget" :title="t('comp.posts.deleteTitle')" @close="deleteTarget = null">
    <p class="ds-dialog__text">
      {{ t('comp.posts.deleteConfirm') }}
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
/* The post's text keeps its line breaks, as the buyer's page does. */
.cpost__preview-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
