<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PublicAttachmentLandingView (iter 2.6 batch 4, R2 §7.2)
// =============================================================================
//
// Deep-link landing for a single public attachment. Reachable via
// /public/companies/:id/attachments/:attId -- the canonical URL we
// expect marketing channels (agents, social posts, email) to share.
//
// SHAPE.
//   Loading      -> spinner centered in the page
//   404          -> "document unavailable" empty state with back-link
//                   to /public/companies/:id (the visitor still has a
//                   useful context they can explore)
//   errored 5xx  -> generic error + retry
//   loaded       -> mime icon hero, title, description, metadata
//   (filename + size), Download CTA, and a back-link to the
//   company overview
//
// WHY FETCH THE LIST + FILTER (not single-attachment endpoint).
//   Backend exposes /public/companies/{id}/attachments returning the
//   full visible list, and /public/companies/{id}/attachments/{att_id}/
//   download for the binary. There is NO single-attachment metadata
//   endpoint -- by design, since the storefront already needs the list
//   for the section component and adding a one-off detail route would
//   duplicate filter/visibility logic. The landing view fetches the
//   full list once and finds the entry by attId.
//
// SECURITY-BY-OBSCURITY (intentional).
//   If the attId is wrong (mistyped) OR if the row is private /
//   unpublished, the backend simply does NOT include it in the public
//   list. The view sees "not in list" and renders the same notFound
//   state -- a 404-equivalent. The visitor cannot tell whether a
//   private document exists, only that nothing public exists at this
//   URL. Matches the backend's "404 not 403" pattern (R2 §3.4 +
//   "anything that fails returns 404 not 403 to avoid confirming
//   the existence of private files").
//
// LIST VS SINGLE FETCH COST.
//   Fetching the full list on every deep-link is ~one extra row of
//   network for typical companies (10-30 attachments, ~few KB JSON).
//   Anyone hitting the deep-link is mid-engagement-funnel; the cost
//   is negligible against the architectural simplification.
//
// PDF PREVIEW (deferred).
//   The view ships with a Download CTA only. Inline PDF rendering is
//   tracked as TD-PDF-PREVIEW-01 -- not blocking iter 2.6 close, will
//   land when there is a real demand signal from analytics.
//
// BACK-LINK CHOICE.
//   Routes to public-company-overview with the same companyId, NOT to
//   public-companies (the list). The visitor arrived via a deep-link
//   for one specific document on one specific company; that company's
//   overview is the natural orientation point. Going back to the
//   catalogue would discard the context the marketing channel
//   established.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Download, File as FileIcon } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { downloadPublicAttachment, listPublicAttachments } from '@/api/attachments'
import { usePublicErrorToast } from '@/composables/usePublicErrorToast'
import { useToast } from '@/composables/useToast'
import { formatBytes } from '@/utils/format'
import { mimeIcon } from '@/utils/mime'
import type { AttachmentResponse } from '@/api/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { showToast } = useToast()
const { notifyRateLimit } = usePublicErrorToast()

const companyId = computed<string>(() => route.params.id as string)
const attachmentId = computed<string>(() => route.params.attId as string)

const attachment = ref<AttachmentResponse | null>(null)
const loading = ref<boolean>(true)
const errored = ref<boolean>(false)
const notFound = ref<boolean>(false)

// Epoch guard. Both companyId and attId can change in-place when the
// router re-uses this component for a different attachment, so the
// fetch path needs the same FP-17 race protection used elsewhere.
let fetchEpoch = 0

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

async function loadAttachment(cId: string, aId: string): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  notFound.value = false
  attachment.value = null

  try {
    const list = await listPublicAttachments(cId)
    if (epoch !== fetchEpoch) return
    const match = list.find((a) => a.id === aId)
    if (!match) {
      // Either the id is wrong, or the row is private / unpublished.
      // Render notFound for both -- the backend deliberately does
      // not distinguish, and neither do we.
      notFound.value = true
      return
    }
    attachment.value = match
  } catch (err) {
    if (epoch !== fetchEpoch) return
    if (err instanceof ApiResponseError && err.status === 404) {
      // The company itself is not active (hidden / archived) -- same
      // visitor-facing surface as a missing attachment.
      notFound.value = true
      return
    }
    // 429 / 5xx / network: render generic error + retry, plus a
    // toast on 429 with the Retry-After hint.
    notifyRateLimit(err)
    errored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

onMounted(() => {
  void loadAttachment(companyId.value, attachmentId.value)
})

// In-place swap when navigating from one deep-link to another (e.g.
// a list of related document links). Same vue-router instance reuse
// pattern that the company overview deals with.
watch(
  () => [route.params.id, route.params.attId] as const,
  ([nextC, nextA]) => {
    if (typeof nextC !== 'string' || typeof nextA !== 'string') return
    void loadAttachment(nextC, nextA)
  },
)

// ---------------------------------------------------------------------------
// Icon component for the loaded-state hero (resolved once data is in).
// Cannot inline `:is="mimeIcon(...)"` directly because the template
// engine evaluates it before the v-if guard would have run.
// ---------------------------------------------------------------------------

const heroIcon = computed(() => {
  if (!attachment.value) return FileIcon
  return mimeIcon(attachment.value.mime_type)
})

const sizeDisplay = computed<string>(() => {
  if (!attachment.value) return ''
  return formatBytes(attachment.value.file_size_bytes)
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function onRetry(): void {
  void loadAttachment(companyId.value, attachmentId.value)
}

function goToCompany(): void {
  void safeNavigate(
    router.push({
      name: 'public-company-overview',
      params: { id: companyId.value },
    }),
    '[PublicAttachmentLandingView] to company',
  )
}

async function onDownload(): Promise<void> {
  const att = attachment.value
  if (!att) return
  try {
    await downloadPublicAttachment(companyId.value, att.id, att.original_filename)
  } catch (err) {
    if (!notifyRateLimit(err)) {
      showToast(t('public.attachmentLanding.downloadError'), 'error')
    }
  }
}
</script>

<template>
  <div class="atl">
    <!-- Loading -->
    <div v-if="loading" class="atl__center">
      <CLoader :size="32" />
    </div>

    <!-- Not found: wrong id, or private / unpublished, or company inactive -->
    <div v-else-if="notFound" class="atl__center">
      <CEmptyState
        :title="t('public.attachmentLanding.notFound.title')"
        :description="t('public.attachmentLanding.notFound.subtitle')"
      />
      <CButton variant="primary" @click="goToCompany">
        <ArrowLeft :size="16" />
        {{ t('public.attachmentLanding.backLink') }}
      </CButton>
    </div>

    <!-- Generic error (429 / 5xx / network) -->
    <div v-else-if="errored" class="atl__center">
      <CEmptyState :title="t('public.attachmentLanding.errorTitle')" />
      <CButton variant="primary" @click="onRetry">
        {{ t('public.attachmentLanding.errorRetry') }}
      </CButton>
    </div>

    <!-- Loaded -->
    <main v-else-if="attachment" class="atl__main">
      <button type="button" class="atl__back" @click="goToCompany">
        <ArrowLeft :size="16" />
        {{ t('public.attachmentLanding.backLink') }}
      </button>

      <section class="atl__hero">
        <div class="atl__icon">
          <component :is="heroIcon" :size="48" />
        </div>
        <h1 class="atl__title">
          {{ attachment.title }}
        </h1>
        <p v-if="attachment.description" class="atl__description">
          {{ attachment.description }}
        </p>
        <p class="atl__meta">{{ attachment.original_filename }} · {{ sizeDisplay }}</p>
      </section>

      <div class="atl__cta">
        <CButton variant="primary" @click="onDownload">
          <Download :size="16" />
          {{ t('public.attachmentLanding.download') }}
        </CButton>
      </div>
    </main>
  </div>
</template>

<style scoped>
.atl {
  display: flex;
  flex-direction: column;
}

.atl__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-lg);
  padding: var(--space-4);
}

.atl__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-4);
}

.atl__back {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-2);
  background: none;
  border: none;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: var(--fs-sm);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition:
    background 0.12s ease,
    color 0.12s ease;
}

.atl__back:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

.atl__hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) var(--space-4);
  background: var(--bg-subtle);
  border-radius: var(--radius-lg);
}

.atl__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  background: var(--bg-page);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
}

.atl__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  text-align: center;
  line-height: 1.3;
  /* Long titles are allowed to wrap; no clamp -- the landing page
     is the dedicated surface for THIS document, full title is fine. */
}

.atl__description {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text-secondary);
  text-align: center;
  white-space: pre-line;
  /* Same: full description on the landing page. */
}

.atl__meta {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-align: center;
}

.atl__cta {
  display: flex;
  justify-content: center;
}

.atl__cta :deep(.c-button) {
  min-width: 200px;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.atl__description {
  max-width: var(--maxw-prose);
}
</style>
