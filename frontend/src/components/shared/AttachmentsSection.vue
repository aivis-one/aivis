<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AttachmentsSection (iter 2.5 batch 6, R2 §7.1)
// =============================================================================
//
// Investor-side "Company documents" section, embedded in
// CompanyOverviewView. Backed by useAttachmentsStore (batch 4) which
// drives a single GET /api/v1/companies/{id}/attachments per company.
//
// SELF-HIDING CONTRACT.
//   Per R2 §7.1 the section "hides when empty". The parent view does
//   NOT wrap this component in v-if -- the component decides itself
//   whether to render. The decision tree:
//     - loading           -> render (spinner inside the section)
//     - errored           -> render (error + retry inside the section)
//     - success + empty   -> DON'T render at all (return <!---->)
//     - success + items   -> render (header + grouped list)
//   The successful-empty case is the only "fully hidden" branch.
//   Loading/errored show the section so the user gets feedback that
//   something was being fetched.
//
// L1 GROUPING (R2 §7.1).
//   Backend stores `category` as a path-tree string ("legal/licenses/
//   business", "marketing/onepagers", etc.). The grouping key is the
//   first segment (category.split('/')[0]). Known L1 segments resolve
//   to localised labels via inv.path.<l1>; unknown L1 segments fall
//   through to a title-case derivation of the raw token. This matches
//   the FP-15 "server-driven enum + tOrRaw" pattern: an inbox upload
//   with a new top-level path renders readably without an i18n catalogue
//   bump.
//
// LANGUAGE FILTER (R2 §7.1 + backend mini-fix iter 2.4-post).
//   Default filter = current vue-i18n locale. Filtered set =
//   items with language === filter OR language === 'en'. The 'en'
//   fallback comes from the product team's English-as-universal-default
//   rule (R2 v0.7 §3.6, attachments.language NOT NULL post-0034) --
//   non-English locales always see English documents alongside their
//   own, because the platform standardised on English-as-fallback
//   rather than null-language-agnostic semantics.
//
//   Override: "All languages" sets filter = null, showing every row
//   regardless of language. The dropdown is only rendered when the
//   raw items set contains 2+ distinct language codes -- a single-
//   language company doesn't need a picker at all.
//
// MIME ICON MAPPING.
//   Minimal coarse-grained mapping by mime prefix / known type. Anything
//   unmapped falls through to a generic File icon. Adding more icons
//   later is a one-line tweak; no contract to break.
//
// DOWNLOAD UX.
//   downloadAttachment (api/attachments.ts, batch 2) is imperative --
//   no spinner state exposed to the template, the function fires fetch
//   + blob + anchor click + revoke and either resolves or throws. The
//   caller (this component) catches and surfaces a toast on failure.
//   No per-row loading flag -- single-tap-and-wait is the expected UX
//   for a fast presigned download.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import {
  Download,
  File as FileIcon,
  FileArchive,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Video,
} from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CSelect } from '@/components/ui'
import { downloadAttachment } from '@/api/attachments'
import { useAttachmentsStore } from '@/stores/attachments'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import type { AttachmentResponse } from '@/api/types'

const props = defineProps<{
  companyId: string
}>()

const { t, locale } = useI18n()
const { showToast } = useToast()
const store = useAttachmentsStore()
const { items, loading, errored } = storeToRefs(store)

// ---------------------------------------------------------------------------
// Language filter state
// ---------------------------------------------------------------------------

// null sentinel = "All languages" override; any string = pinned filter.
// Initial value is the current vue-i18n locale -- the user sees their
// own language documents (plus English fallback) by default. The watch
// below keeps this in sync if the locale switches mid-session (rare
// but supported in the auth flow).
const filterLanguage = ref<string | null>(locale.value)

watch(
  () => locale.value,
  (next) => {
    // Only update if the user hasn't already overridden to "All".
    // Switching the UI locale shouldn't undo their explicit "show
    // everything" toggle.
    if (filterLanguage.value !== null) {
      filterLanguage.value = next
    }
  },
)

// ---------------------------------------------------------------------------
// Derived collections
// ---------------------------------------------------------------------------

const availableLanguages = computed<string[]>(() => {
  const set = new Set<string>()
  for (const att of items.value) {
    set.add(att.language)
  }
  // Sort alphabetically so the dropdown order is stable across renders.
  // 'en' first only when explicitly present -- consistency over special-case.
  return Array.from(set).sort()
})

const hasMultipleLanguages = computed<boolean>(
  () => availableLanguages.value.length >= 2,
)

const filteredItems = computed<AttachmentResponse[]>(() => {
  const filter = filterLanguage.value
  if (filter === null) {
    return items.value
  }
  // English-as-universal-fallback: when the filter is anything other
  // than 'en', the user still sees English rows alongside their locale.
  // When the filter IS 'en', the predicate is trivially true on the
  // 'en' rows and false on the others -- no special case needed.
  return items.value.filter(
    (att) => att.language === filter || att.language === 'en',
  )
})

// Group filtered items by L1 path segment. Map preserves insertion
// order; we sort the bucket list at the end so the visual order is
// deterministic regardless of how items arrived from the backend.
const groupedItems = computed<{ l1: string; items: AttachmentResponse[] }[]>(() => {
  const buckets = new Map<string, AttachmentResponse[]>()
  for (const att of filteredItems.value) {
    const l1 = (att.category.split('/')[0] ?? '').toLowerCase()
    const list = buckets.get(l1)
    if (list) {
      list.push(att)
    } else {
      buckets.set(l1, [att])
    }
  }
  // Sort items inside each bucket by `order` ASC -- the same canonical
  // ordering the backend uses for the unfiltered list. Backend already
  // returns rows sorted by (category, order), but filtering preserves
  // that order; the explicit sort here is defensive against a future
  // backend change.
  for (const list of buckets.values()) {
    list.sort((a, b) => a.order - b.order)
  }
  // Sort L1 keys alphabetically for stable display. Known L1 segments
  // (legal/marketing/patents/reports) all land in a reasonable order
  // alphabetically; the spec does not prescribe a specific sort.
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([l1, items]) => ({ l1, items }))
})

// ---------------------------------------------------------------------------
// Self-hide decision (R2 §7.1)
// ---------------------------------------------------------------------------

const shouldRender = computed<boolean>(() => {
  // Render the section while the fetch is in flight so the user sees a
  // spinner rather than a layout pop-in once data arrives.
  if (loading.value) return true
  // Render the error state so the user can retry.
  if (errored.value) return true
  // Hide the section entirely when the fetch succeeded with zero rows.
  // This is the R2 §7.1 "hide when empty" contract.
  return items.value.length > 0
})

// ---------------------------------------------------------------------------
// CSelect options for the filter dropdown
// ---------------------------------------------------------------------------

// "All languages" + one option per language present in the items set.
// Value '' represents the null sentinel because CSelect typically
// expects string values -- we translate at the v-model boundary below.
const selectOptions = computed<{ value: string; label: string }[]>(() => {
  const allOption = {
    value: '',
    label: t('inv.companyOverview.documents.languageFilterAll'),
  }
  const langOptions = availableLanguages.value.map((lang) => ({
    value: lang,
    // Locale label via Intl.DisplayNames -- localised to the user's
    // current locale, so a ru-user sees "Английский / Русский" while
    // an en-user sees "English / Russian". Fallback to the raw code
    // if Intl can't name it (e.g. exotic language code from a future
    // backend addition).
    label: localeDisplayName(lang),
  }))
  return [allOption, ...langOptions]
})

function localeDisplayName(code: string): string {
  try {
    const dn = new Intl.DisplayNames([locale.value], { type: 'language' })
    return dn.of(code) ?? code
  } catch {
    return code
  }
}

// v-model boundary: CSelect emits string, we store null for "All".
const selectModel = computed<string>({
  get: () => filterLanguage.value ?? '',
  set: (v) => {
    filterLanguage.value = v === '' ? null : v
  },
})

// ---------------------------------------------------------------------------
// L1 path label resolution
// ---------------------------------------------------------------------------

function pathLabel(l1: string): string {
  // FP-15 tOrRaw -- known L1 segments resolve to inv.path.<l1>; unknown
  // segments fall through to a title-case derivation so a backend that
  // adds 'pitch-decks' renders as "Pitch Decks" without an i18n bump.
  return tOrRaw(t, `inv.path.${l1}`, titleCase(l1))
}

function titleCase(s: string): string {
  // Handles 'pitch-decks' -> 'Pitch Decks', 'q4_reports' -> 'Q4 Reports'.
  return s
    .split(/[-_]+/)
    .filter((part) => part.length > 0)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

// ---------------------------------------------------------------------------
// Mime icon mapping
// ---------------------------------------------------------------------------

function mimeIcon(mime: string) {
  if (mime.startsWith('image/')) return ImageIcon
  if (mime.startsWith('video/')) return Video
  if (mime === 'application/pdf') return FileText
  if (
    mime.includes('spreadsheet')
    || mime === 'text/csv'
    || mime === 'application/vnd.ms-excel'
  ) {
    return FileSpreadsheet
  }
  if (mime.includes('zip') || mime.includes('archive')) return FileArchive
  return FileIcon
}

// ---------------------------------------------------------------------------
// Lifecycle + actions
// ---------------------------------------------------------------------------

onMounted(() => {
  void store.setCompanyId(props.companyId)
})

// In-place swap when the parent view navigates from one company to
// another without unmounting CompanyOverviewView (Vue Router reuses
// the component instance across :id changes).
watch(
  () => props.companyId,
  (next) => {
    if (next && next !== store.currentCompanyId) {
      void store.setCompanyId(next)
    }
  },
)

onUnmounted(() => {
  store.clearCurrent()
})

async function onRetry(): Promise<void> {
  // setCompanyId is non-idempotent on the same id -- it re-fetches,
  // which is exactly the Retry semantic.
  await store.setCompanyId(props.companyId)
}

async function onDownload(att: AttachmentResponse): Promise<void> {
  try {
    await downloadAttachment(props.companyId, att.id, att.original_filename)
  } catch {
    // 401 / 403 / 404 / network all surface the same toast -- the user
    // can't distinguish these and a retry path is opaque from this UI.
    // A more nuanced taxonomy would belong in a downloads center, not
    // here.
    showToast(t('inv.companyOverview.documents.downloadError'), 'error')
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}
</script>

<template>
  <!--
    The section renders unless we know there are zero items after a
    successful fetch. Loading + errored states stay visible so the user
    has feedback.
  -->
  <section v-if="shouldRender" class="ats">
    <header class="ats__head">
      <h2 class="ats__title">
        {{ t('inv.companyOverview.sectionDocuments') }}
      </h2>
      <CSelect
        v-if="hasMultipleLanguages"
        v-model="selectModel"
        :options="selectOptions"
        class="ats__filter"
      />
    </header>

    <div v-if="loading" class="ats__center">
      <CLoader :size="24" />
    </div>

    <div v-else-if="errored" class="ats__center">
      <CEmptyState
        :title="t('inv.companyOverview.documents.errorTitle')"
      />
      <CButton variant="outline" size="sm" @click="onRetry">
        {{ t('inv.companyOverview.documents.errorRetry') }}
      </CButton>
    </div>

    <div v-else class="ats__groups">
      <section
        v-for="group in groupedItems"
        :key="group.l1"
        class="ats__group"
      >
        <h3 class="ats__group-title">{{ pathLabel(group.l1) }}</h3>
        <ul class="ats__list">
          <li
            v-for="att in group.items"
            :key="att.id"
            class="ats__item"
            @click="onDownload(att)"
          >
            <span class="ats__item-icon">
              <component :is="mimeIcon(att.mime_type)" :size="20" />
            </span>
            <div class="ats__item-body">
              <p class="ats__item-title">{{ att.title }}</p>
              <p
                v-if="att.description"
                class="ats__item-desc"
              >
                {{ att.description }}
              </p>
              <p class="ats__item-meta">
                {{ att.original_filename }}
                ·
                {{ formatBytes(att.file_size_bytes) }}
              </p>
            </div>
            <span class="ats__item-download" aria-hidden="true">
              <Download :size="16" />
            </span>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ats {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ats__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.ats__title {
  margin: 0;
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.ats__filter {
  /* The select claims minimum width; the title absorbs the rest. */
  flex-shrink: 0;
  min-width: 140px;
}

.ats__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 120px;
}

.ats__groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.ats__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ats__group-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.ats__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ats__item {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.12s ease, transform 0.12s ease;
}

.ats__item:hover {
  background: var(--bg-subtle);
  transform: translateY(-1px);
}

.ats__item:active {
  transform: translateY(0);
}

.ats__item-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.ats__item-body {
  flex: 1;
  min-width: 0; /* allow text truncation within flex */
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ats__item-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  /* Truncate long titles instead of pushing the download icon off. */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ats__item-desc {
  margin: 0;
  font-size: var(--fs-xs);
  line-height: 1.4;
  color: var(--text-secondary);
  /* 2-line clamp -- description is optional and may be long. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ats__item-meta {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ats__item-download {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
}

.ats__item:hover .ats__item-download {
  color: var(--primary);
}
</style>
