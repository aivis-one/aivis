<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- RoadmapTimeline (iter 2.5 batch 5, R1 §6.1)
// =============================================================================
//
// Vertical timeline rendered on the Investor CompanyOverviewView
// (batch 6). Left rail with axis line + per-item dot; right rail with
// per-item cards. Mobile-first single-column layout; no responsive
// switch to two columns -- the spec calls for vertical only.
//
// SORT ORDER.
//   Items are rendered in the order received -- the backend public
//   endpoint sorts by `order ASC` (R1 §5 backend contract). The
//   component does NOT re-sort: a future drag-to-reorder editor on
//   the staff side will produce the canonical order and the public
//   read path mirrors it. Re-sorting here would mask backend bugs.
//
// CARD CONTENT MATRIX (R1 §6.1).
//   cover_url           -- if set, banner at top of card (16:9)
//   title               -- always
//   target_date         -- rendered for kind=milestone | event; OMITTED
//                          for kind=announcement (announcements are
//                          dateless by spec)
//   kind chip           -- always (milestone / event / announcement)
//   status chip         -- when status is present and non-empty
//   description         -- ONLY when post_id is null. A linked post
//                          supersedes the inline description; rendering
//                          both would duplicate content.
//   post snippet        -- when item.post is non-null: mini card with
//                          cover_url / title / excerpt + "Read more"
//                          link. Read-more emits `post-click`.
//   "View product" btn  -- when linked_product_id is set
//   "Open" btn          -- when external_url is set
//
// END MARKER.
//   The last visual element is a terminal dot + label
//   "Beginning of company history" (i18n key inv.roadmap.endMarker).
//   The spec originally proposed including the company's founded_at
//   year in the marker label, but the final iter 2.4 backend does
//   NOT emit `founded_at` on PublicCompanyStatsResponse. The marker
//   therefore renders without a year. Adding the year later is a
//   single-line change in the locale catalogue + a year prop here.
//
// EMPTY STATE.
//   By spec, the parent view (CompanyOverviewView) skips rendering
//   the entire Roadmap section -- including this component -- when
//   `roadmap.items` is empty. This component therefore assumes
//   `items.length > 0`. Defensive coding inside the template
//   (v-if="items.length") would mask a contract violation, so it is
//   deliberately absent.
//
// EMITS, NOT NAVIGATION.
//   The component is shell-agnostic. Navigation (which depends on
//   /investor/* vs /agent/* shell) belongs to the parent view, which
//   reads route meta via isAgentShell. The three emits:
//     - product-click (productId)  -> caller pushes ProductDetailView
//     - external-click (url)       -> caller opens via window.open
//     - post-click (postId)        -> reserved for the post-view route
//                                     that iter 2.6 may bring; until
//                                     then the parent can no-op or
//                                     route to a placeholder
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@/components/ui/icons'
import { CBadge, CButton } from '@/components/ui'

import { tOrRaw } from '@/utils/i18n'
import type { RoadmapItemResponse } from '@/api/types'

defineProps<{
  items: RoadmapItemResponse[]
}>()

const emit = defineEmits<{
  'product-click': [productId: string]
  'external-click': [url: string]
  'post-click': [postId: string]
}>()

const { t, locale } = useI18n()

// ---------------------------------------------------------------------------
// Per-item display helpers
// ---------------------------------------------------------------------------

function kindLabel(kind: string): string {
  // FP-15 tOrRaw: unknown kinds fall through to the raw token instead
  // of blanking the chip. A future kind that lands before the i18n
  // catalogue catches up still produces a sensible (capitalised at
  // backend) label.
  return tOrRaw(t, `inv.roadmap.kind.${kind}`, kind)
}

function statusLabel(status: string): string {
  return tOrRaw(t, `inv.roadmap.status.${status}`, status)
}

// status badge look (K08) -- known statuses map to a semantic look; unknown falls
// through to the neutral badge.
type BadgeVariant = 'success' | 'accent' | 'danger' | 'neutral'
function statusVariant(status: string): BadgeVariant {
  if (status === 'done') return 'success'
  if (status === 'in_progress') return 'accent'
  if (status === 'cancelled') return 'danger'
  return 'neutral'
}

// The timeline's state of an entry (K54): done, current or upcoming.
function stateOf(item: RoadmapItemResponse): 'done' | 'current' | 'upcoming' {
  if (item.status === 'done') return 'done'
  if (item.status === 'in_progress') return 'current'
  return 'upcoming'
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(locale.value, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

// Show date for milestone / event; hide for announcement.
function shouldShowDate(item: RoadmapItemResponse): boolean {
  if (!item.target_date) return false
  return item.kind === 'milestone' || item.kind === 'event'
}

// An entry is short by default: the title (with its badges and date). A tap opens
// what it holds (the description, a cover, the links), a second tap closes it (a
// native `details`). An entry linked to a post opens the post screen instead, and
// an entry with neither has nothing to open.
function hasPost(item: RoadmapItemResponse): boolean {
  return item.post_id !== null && item.post_id !== undefined
}

// The description is the entry's detail only when there is NO linked post: the
// post supersedes it (a content curation rule from the spec, not a layout
// shortcut).
function hasDetail(item: RoadmapItemResponse): boolean {
  return !!item.description && !hasPost(item)
}

// An entry opens when it holds a description, a cover or a link, and no post.
function isOpenable(item: RoadmapItemResponse): boolean {
  if (hasPost(item)) return false
  return hasDetail(item) || !!item.cover_url || !!item.linked_product_id || !!item.external_url
}

function onEntryClick(item: RoadmapItemResponse): void {
  if (hasPost(item)) emit('post-click', item.post_id as string)
}

// End-marker key -- single locale string, no params (spec deferred
// the founded_at integration).
const endMarkerLabel = computed<string>(() => t('inv.roadmap.endMarker'))
</script>

<template>
  <!-- The roadmap is the system's Timeline (K54): a marker, a connector and an entry as a
       card. An entry that has something to open (a description, a cover or actions, and no
       linked post) is a `details` card: the head shows the date, the title and the badges,
       and a tap opens the body. An entry linked to a post is a plain card whose title opens
       the post screen. -->
  <ol class="ds-timeline">
    <li v-for="item in items" :key="item.id" class="ds-timeline__item" :data-state="stateOf(item)">
      <span class="ds-timeline__marker" aria-hidden="true" />

      <!-- An entry with something to open -->
      <details v-if="isOpenable(item)" class="ds-timeline__card">
        <summary class="ds-timeline__head">
          <time
            v-if="shouldShowDate(item)"
            class="ds-timeline__date"
            :datetime="item.target_date ?? undefined"
          >
            {{ formatDate(item.target_date!) }}
          </time>
          <span class="ds-timeline__title">{{ item.title }}</span>
          <CBadge variant="neutral" :text="kindLabel(item.kind)" />
          <CBadge
            v-if="item.status"
            :variant="statusVariant(item.status)"
            :text="statusLabel(item.status)"
          />
          <ChevronDown class="ds-timeline__chev" size="sm" />
        </summary>
        <div class="ds-timeline__body">
          <div v-if="item.cover_url" class="ds-card ds-card--media">
            <div class="ds-card__media" data-size="sm">
              <img :src="item.cover_url" alt="" loading="lazy" />
            </div>
          </div>
          <p v-if="hasDetail(item)">{{ item.description }}</p>
          <div v-if="item.linked_product_id || item.external_url" class="rti__actions">
            <CButton
              v-if="item.linked_product_id"
              variant="primary"
              size="sm"
              inline
              @click="$emit('product-click', item.linked_product_id)"
            >
              {{ t('inv.roadmap.openProduct') }}
            </CButton>
            <CButton
              v-if="item.external_url"
              variant="outline"
              size="sm"
              inline
              @click="$emit('external-click', item.external_url)"
            >
              {{ t('inv.roadmap.openExternal') }}
            </CButton>
          </div>
        </div>
      </details>

      <!-- An entry with nothing to open, or one linked to a post -->
      <div v-else class="ds-timeline__card">
        <div class="ds-timeline__head">
          <time
            v-if="shouldShowDate(item)"
            class="ds-timeline__date"
            :datetime="item.target_date ?? undefined"
          >
            {{ formatDate(item.target_date!) }}
          </time>
          <span class="ds-timeline__title">
            <button
              v-if="hasPost(item)"
              type="button"
              class="rti__title-button"
              @click="onEntryClick(item)"
            >
              {{ item.title }}
            </button>
            <template v-else>{{ item.title }}</template>
          </span>
          <CBadge variant="neutral" :text="kindLabel(item.kind)" />
          <CBadge
            v-if="item.status"
            :variant="statusVariant(item.status)"
            :text="statusLabel(item.status)"
          />
        </div>
        <div v-if="item.post" class="ds-timeline__body">
          <!-- The linked post's snippet: a card that opens the post screen -->
          <div
            class="ds-card ds-card--flat ds-card--interactive"
            :class="{ 'ds-card--media': item.post.cover_url }"
          >
            <div v-if="item.post.cover_url" class="ds-card__media" data-size="sm">
              <img :src="item.post.cover_url" alt="" loading="lazy" />
            </div>
            <div :class="item.post.cover_url ? 'ds-card__content' : undefined">
              <h4 class="ds-card__title">
                <button
                  type="button"
                  class="ds-card__link"
                  @click="$emit('post-click', item.post.id)"
                >
                  {{ item.post.title }}
                </button>
              </h4>
              <p v-if="item.post.excerpt" class="ds-card__body">
                {{ item.post.excerpt }}
              </p>
              <p class="ds-card__body">{{ t('inv.roadmap.readMore') }}</p>
            </div>
          </div>
        </div>
        <div
          v-if="!hasPost(item) && (item.linked_product_id || item.external_url)"
          class="ds-timeline__body"
        >
          <div class="rti__actions">
            <CButton
              v-if="item.linked_product_id"
              variant="primary"
              size="sm"
              inline
              @click="$emit('product-click', item.linked_product_id)"
            >
              {{ t('inv.roadmap.openProduct') }}
            </CButton>
            <CButton
              v-if="item.external_url"
              variant="outline"
              size="sm"
              inline
              @click="$emit('external-click', item.external_url)"
            >
              {{ t('inv.roadmap.openExternal') }}
            </CButton>
          </div>
        </div>
      </div>
    </li>

    <!-- The end of the history: the last entry of the line, with no date. -->
    <li class="ds-timeline__item" data-state="done">
      <span class="ds-timeline__marker" aria-hidden="true" />
      <div class="ds-timeline__card">
        <div class="ds-timeline__head">
          <span class="ds-timeline__title">{{ endMarkerLabel }}</span>
        </div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
/* The entry's two links to other screens sit side by side. */
.rti__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* A title that opens a screen is a button in the title's own type (the system's
   timeline has no title-as-button form; NEED). */
.rti__title-button {
  padding: 0;
  text-align: start;
}
</style>
