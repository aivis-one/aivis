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
//   - loading             -> render (skeleton rows inside the section)
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
import { useRouter } from 'vue-router'

import { CButton, CEmptyState, CSelect } from '@/components/ui'
import DocumentRow from '@/components/shared/DocumentRow.vue'
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
const router = useRouter()
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

function onDownloadFailed(err: unknown): void {
  // 429 has its own toast with Retry-After hint; for everything
  // else (404 -- the row was un-published between list and click,
  // 5xx, network) we show a generic toast so the user knows the
  // tap actually failed.
  if (!notifyRateLimit(err)) {
    showToast(t('public.companyOverview.documents.downloadError'), 'error')
  }
}

// The row's own address is the document's landing page; a click downloads the
// file at once (K44), a middle click or a copied link opens the landing page.
function attachmentHref(att: AttachmentResponse): string {
  return router.resolve({
    name: 'public-attachment-landing',
    params: { id: props.companyId, attId: att.id },
  }).href
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
      <h2 class="ds-section-title">
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

    <div v-if="loading" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="ds-rows" aria-hidden="true">
        <div v-for="n in 3" :key="n" class="ds-skeleton-row">
          <span class="ds-skeleton ds-skeleton--avatar" /><span class="ds-skeleton-stack"
            ><span class="ds-skeleton ds-skeleton--title" /><span
              class="ds-skeleton ds-skeleton--text"
          /></span>
        </div>
      </div>
    </div>

    <CEmptyState
      v-else-if="errored"
      tone="danger"
      :title="t('public.companyOverview.documents.errorTitle')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="onRetry">
          {{ t('public.companyOverview.documents.errorRetry') }}
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
            :href="attachmentHref(att)"
            :download="() => downloadPublicAttachment(companyId, att.id)"
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
