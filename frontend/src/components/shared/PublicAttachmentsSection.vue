<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicAttachmentsSection (iter 2.6 batch 4, R2 §3.4 + §7.2)
// =============================================================================
//
// Anonymous-storefront counterpart to AttachmentsSection. Embedded in
// PublicCompanyOverviewView the same way the auth-flow section is
// embedded in CompanyOverviewView.
//
// WHY A SEPARATE COMPONENT (not a parameterised AttachmentsSection).
//   Four moving parts diverge between auth and public flows:
//     - API: listAttachments vs listPublicAttachments
//     - Download: downloadAttachment vs downloadPublicAttachment
//     - State: useAttachmentsStore (auth-side, session-bound) vs
//       local state (public-side, no session boundary worth
//       maintaining for an anonymous visitor)
//     - Toast: useToast for arbitrary errors vs usePublicErrorToast
//       on 429 + generic toast on download failure
//   A `:isPublic` prop would scatter if-branches across every
//   call-site. The cleaner split is two files that share helpers
//   (tOrRaw, mime icons, L1 grouping, formatBytes) but each owns
//   its own wiring end-to-end.
//
// SELF-HIDING CONTRACT (R2 §7.2, mirrors AttachmentsSection).
//   - loading             -> render (spinner inside the section)
//   - errored             -> render (error + retry inside the section)
//   - success + empty     -> DON'T render at all (return <!---->)
//   - success + items     -> render (header + grouped list)
//   The parent does NOT wrap this in v-if; the component decides.
//
// L1 GROUPING + LANGUAGE FILTER.
//   Identical mechanics to the auth-flow section -- same
//   tOrRaw('inv.path.<l1>', titleCase(l1)) (the inv.path.* catalogue
//   is shared, the labels are category names not auth concepts), same
//   English-as-universal-fallback filter, same "All languages"
//   override, same select-only-with-2+-languages guard.
//
// ERROR HANDLING.
//   List fetch (onMounted + retry):
//     - 429 -> notifyRateLimit toast (handled by usePublicErrorToast)
//     - anything else -> errored ref flips, section shows error + retry
//   Download click:
//     - 429 -> notifyRateLimit toast (the user's burst hit the
//       PUBLIC_DOWNLOAD_RATE_LIMIT bucket, separate from list)
//     - anything else -> generic "couldn't download" toast (the
//       download was user-initiated, silent failure would confuse)
//   The two toast composables coexist: usePublicErrorToast covers
//   only 429 (because Retry-After info is only ever on a 429), and
//   useToast handles the generic-error path.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader, CSelect } from '@/components/ui'
import { downloadPublicAttachment, listPublicAttachments } from '@/api/attachments'
import { usePublicErrorToast } from '@/composables/usePublicErrorToast'
import { useToast } from '@/composables/useToast'
import { formatBytes } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import { mimeIcon } from '@/utils/mime'
import type { AttachmentResponse } from '@/api/types'

const props = defineProps<{
  companyId: string
}>()

const { t, locale } = useI18n()
const { showToast } = useToast()
const { notifyRateLimit } = usePublicErrorToast()

// ---------------------------------------------------------------------------
// Local state (no per-public-section store -- see file header)
// ---------------------------------------------------------------------------

const items = ref<AttachmentResponse[]>([])
const loading = ref<boolean>(true)
const errored = ref<boolean>(false)

// Monotonic counter for the FP-17 epoch guard. Bumped before each
// fetch; a resolve whose epoch no longer matches the current value
// is dropped on the floor. Covers the in-place :id swap race below.
let fetchEpoch = 0

// ---------------------------------------------------------------------------
// Language filter state (mirrors AttachmentsSection)
// ---------------------------------------------------------------------------

// null sentinel = "All languages"; any string = pinned filter.
const filterLanguage = ref<string | null>(locale.value)

watch(
  () => locale.value,
  (next) => {
    // Locale switches mid-session update the filter only when the
    // user hasn't explicitly toggled to "All languages". Same rule
    // as the auth-flow section.
    if (filterLanguage.value !== null) {
      filterLanguage.value = next
    }
  },
)

// ---------------------------------------------------------------------------
// Fetch lifecycle
// ---------------------------------------------------------------------------

async function fetchList(id: string): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  // Clear stale items synchronously so an in-place id swap doesn't
  // paint company A's documents under company B's hero during the
  // network window.
  items.value = []
  try {
    const resp = await listPublicAttachments(id)
    if (epoch !== fetchEpoch) return
    items.value = resp
  } catch (err) {
    if (epoch !== fetchEpoch) return
    // 429 is shown as a toast; the section still flips to errored
    // so the visitor sees the retry path (waiting silently with no
    // UI signal would be worse than a redundant retry button).
    notifyRateLimit(err)
    errored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

onMounted(() => {
  void fetchList(props.companyId)
})

// In-place id swap when the parent view navigates from one company
// to another without unmounting (Vue Router reuses the component
// instance across :id changes). Same race coverage as the auth-flow
// AttachmentsSection.
watch(
  () => props.companyId,
  (next) => {
    if (next) {
      void fetchList(next)
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
  return Array.from(set).sort()
})

const hasMultipleLanguages = computed<boolean>(() => availableLanguages.value.length >= 2)

const filteredItems = computed<AttachmentResponse[]>(() => {
  const filter = filterLanguage.value
  if (filter === null) {
    return items.value
  }
  // English-as-universal-fallback (same as auth-flow section):
  // when filter is not 'en', the visitor still sees English rows
  // alongside their locale.
  return items.value.filter((att) => att.language === filter || att.language === 'en')
})

// Group filtered items by L1 path segment, then sort each bucket by
// `order` ASC and the bucket list alphabetically by L1 key.
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
  for (const list of buckets.values()) {
    list.sort((a, b) => a.order - b.order)
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([l1, items]) => ({ l1, items }))
})

// ---------------------------------------------------------------------------
// Self-hide decision (R2 §7.2, mirrors AttachmentsSection §7.1)
// ---------------------------------------------------------------------------

const shouldRender = computed<boolean>(() => {
  // Render while the fetch is in flight so the visitor sees a spinner
  // rather than a layout pop-in once data arrives.
  if (loading.value) return true
  // Render the error state so the visitor can retry.
  if (errored.value) return true
  // Hide the section entirely when the fetch succeeded with zero rows
  // -- R2 §7.2 "hide when empty" contract.
  return items.value.length > 0
})

// ---------------------------------------------------------------------------
// CSelect options for the filter dropdown
// ---------------------------------------------------------------------------

const selectOptions = computed<{ value: string; label: string }[]>(() => {
  const allOption = {
    value: '',
    label: t('public.companyOverview.documents.languageFilterAll'),
  }
  const langOptions = availableLanguages.value.map((lang) => ({
    value: lang,
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
  // Reuse inv.path.<l1> -- the catalogue describes category names
  // (Legal, Marketing, Patents, Reports), which are domain-neutral
  // concepts shared with the public flow. titleCase fallback covers
  // unknown L1 segments (e.g. a future 'pitch-decks') without an
  // i18n bump.
  return tOrRaw(t, `inv.path.${l1}`, titleCase(l1))
}

function titleCase(s: string): string {
  return s
    .split(/[-_]+/)
    .filter((part) => part.length > 0)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function onRetry(): Promise<void> {
  await fetchList(props.companyId)
}

async function onDownload(att: AttachmentResponse): Promise<void> {
  try {
    await downloadPublicAttachment(props.companyId, att.id, att.original_filename)
  } catch (err) {
    // 429 has its own toast with Retry-After hint; for everything
    // else (404 -- the row was un-published between list and click,
    // 5xx, network) we show a generic toast so the user knows the
    // tap actually failed.
    if (!notifyRateLimit(err)) {
      showToast(t('public.companyOverview.documents.downloadError'), 'error')
    }
  }
}
</script>

<template>
  <!--
    The section renders unless we know there are zero items after a
    successful fetch. Loading + errored states stay visible so the
    visitor has feedback.
  -->
  <section v-if="shouldRender" class="ats">
    <header class="ats__head">
      <h2 class="ats__title">
        {{ t('public.companyOverview.sectionDocuments') }}
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

    <div v-if="loading" class="ats__center">
      <CLoader :size="24" />
    </div>

    <div v-else-if="errored" class="ats__center">
      <CEmptyState :title="t('public.companyOverview.documents.errorTitle')" />
      <CButton variant="outline" size="sm" @click="onRetry">
        {{ t('public.companyOverview.documents.errorRetry') }}
      </CButton>
    </div>

    <div v-else class="ats__groups">
      <section v-for="group in groupedItems" :key="group.l1" class="ats__group">
        <h3 class="ats__group-title">
          {{ pathLabel(group.l1) }}
        </h3>
        <ul class="ats__list">
          <li v-for="att in group.items" :key="att.id">
            <button type="button" class="ats__item" @click="onDownload(att)">
              <span class="ats__item-icon">
                <component :is="mimeIcon(att.mime_type)" :size="20" />
              </span>
              <div class="ats__item-body">
                <p class="ats__item-title">
                  {{ att.title }}
                </p>
                <p v-if="att.description" class="ats__item-desc">
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
            </button>
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
  flex-shrink: 0;
  min-width: 140px;
}

.ats__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: var(--center-sm);
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
  appearance: none;
  background: none;
  border: none;
  margin: 0;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: start;
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition:
    background 0.12s ease,
    transform 0.12s ease;
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
  width: var(--size-xl);
  height: var(--size-xl);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.ats__item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.ats__item-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ats__item-desc {
  margin: 0;
  font-size: var(--fs-xs);
  line-height: 1.4;
  color: var(--text-secondary);
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
  width: var(--size-md);
  height: var(--size-md);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
}

.ats__item:hover .ats__item-download {
  color: var(--primary);
}
</style>
