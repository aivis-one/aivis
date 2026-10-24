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
// MIME ICON MAPPING (utils/mime).
//   Minimal coarse-grained mapping by mime prefix / known type. Anything
//   unmapped falls through to a generic File icon. Adding more icons
//   later is a one-line tweak; no contract to break.
//
// DOWNLOAD UX.
//   downloadAttachment (api/attachments.ts) is imperative -- no spinner
//   state exposed to the template: it asks the API for the presigned link
//   and sends the browser to it (H32 P-121), and either resolves or
//   throws. The caller (this component) catches and surfaces a toast on
//   failure.
//   No per-row loading flag -- single-tap-and-wait is the expected UX
//   for a fast presigned download.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'

import { CButton, CEmptyState, CLoader, CSelect } from '@/components/ui'
import DocumentRow from '@/components/shared/DocumentRow.vue'
import { downloadAttachment } from '@/api/attachments'
import { useAttachmentsStore } from '@/stores/attachments'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { mimeIcon } from '@/utils/mime'
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

const hasMultipleLanguages = computed<boolean>(() => availableLanguages.value.length >= 2)

const filteredItems = computed<AttachmentResponse[]>(() => {
  const filter = filterLanguage.value
  if (filter === null) {
    return items.value
  }
  // English-as-universal-fallback: when the filter is anything other
  // than 'en', the user still sees English rows alongside their locale.
  // When the filter IS 'en', the predicate is trivially true on the
  // 'en' rows and false on the others -- no special case needed.
  return items.value.filter((att) => att.language === filter || att.language === 'en')
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

function onDownloadFailed(): void {
  // 401 / 403 / 404 / network all surface the same toast -- the user
  // can't distinguish these and a retry path is opaque from this UI.
  // A more nuanced taxonomy would belong in a downloads center, not
  // here.
  showToast(t('inv.companyOverview.documents.downloadError'), 'error')
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
      <!-- A4: the section heading beside it is a heading, not a label. -->
      <CSelect
        v-if="hasMultipleLanguages"
        v-model="selectModel"
        :aria-label="t('auth.profile.language')"
        :options="selectOptions"
        class="ats__filter"
      />
    </header>

    <div v-if="loading" class="ds-empty">
      <CLoader :size="24" />
    </div>

    <CEmptyState
      v-else-if="errored"
      tone="danger"
      :title="t('inv.companyOverview.documents.errorTitle')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="onRetry">
          {{ t('inv.companyOverview.documents.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <div v-else class="ats__groups">
      <section v-for="group in groupedItems" :key="group.l1" class="ats__group">
        <h3 class="ats__group-title">
          {{ pathLabel(group.l1) }}
        </h3>
        <ul class="ds-rows">
          <DocumentRow
            v-for="att in group.items"
            :key="att.id"
            :title="att.title"
            :description="att.description"
            :meta="`${att.original_filename} · ${formatBytes(att.file_size_bytes)}`"
            :icon="mimeIcon(att.mime_type)"
            :href="`/api/v1/companies/${companyId}/attachments/${att.id}/download`"
            :download="() => downloadAttachment(companyId, att.id)"
            @failed="onDownloadFailed"
          />
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ats {
  display: grid;
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
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  line-height: var(--lh-snug);
  color: var(--text-primary);
}

/* The select claims its own width; the title absorbs the rest. */
.ats__filter {
  flex-shrink: 0;
}

.ats__groups {
  display: grid;
  gap: var(--space-6);
}

.ats__group {
  display: grid;
  gap: var(--space-2);
}

.ats__group-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}
</style>
