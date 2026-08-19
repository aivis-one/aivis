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

import { tOrRaw } from '@/utils/i18n'
import type { RoadmapItemResponse } from '@/api/types'

defineProps<{
  items: RoadmapItemResponse[]
}>()

defineEmits<{
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

// status chip color -- map known statuses to semantic tokens; unknown
// falls through to a neutral chip. Mirrors the legalBasis pattern in
// CompanyPositionView.
function statusClass(status: string): string {
  if (status === 'done') return 'rti__chip--success'
  if (status === 'in_progress') return 'rti__chip--accent'
  if (status === 'cancelled') return 'rti__chip--danger'
  return 'rti__chip--neutral'
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

function itemCoverStyle(coverUrl: string | null): string | undefined {
  // Inline cover for roadmap-item is simpler than resolveCoverImage:
  // RoadmapItemResponse has no company_logo fallback field, just
  // cover_url. Keep encodeURI hygiene though.
  if (!coverUrl) return undefined
  return `url("${encodeURI(coverUrl)}")`
}

// Show date for milestone / event; hide for announcement.
function shouldShowDate(item: RoadmapItemResponse): boolean {
  if (!item.target_date) return false
  return item.kind === 'milestone' || item.kind === 'event'
}

// Description renders only when there's NO linked post. The post
// snippet supersedes inline description -- this is a content
// curation rule from the spec, not a layout shortcut.
function shouldShowDescription(item: RoadmapItemResponse): boolean {
  if (!item.description) return false
  return item.post_id === null || item.post_id === undefined
}

// End-marker key -- single locale string, no params (spec deferred
// the founded_at integration).
const endMarkerLabel = computed<string>(() =>
  t('inv.roadmap.endMarker'),
)
</script>

<template>
  <div class="roadmap">
    <ol class="roadmap__list">
      <li
        v-for="item in items"
        :key="item.id"
        class="roadmap__item"
      >
        <!-- Axis: line segment + dot. The line continues through the
             end-marker via the .roadmap__terminal block below. -->
        <div class="roadmap__axis">
          <span class="roadmap__line" />
          <span class="roadmap__dot" />
        </div>

        <article class="roadmap__card">
          <!-- Cover (optional). -->
          <div
            v-if="item.cover_url"
            class="roadmap__cover"
            :style="{ backgroundImage: itemCoverStyle(item.cover_url) }"
          />

          <header class="roadmap__head">
            <div class="roadmap__chips">
              <span class="rti__chip rti__chip--neutral">
                {{ kindLabel(item.kind) }}
              </span>
              <span
                v-if="item.status"
                class="rti__chip"
                :class="statusClass(item.status)"
              >
                {{ statusLabel(item.status) }}
              </span>
            </div>
            <time
              v-if="shouldShowDate(item)"
              class="roadmap__date"
              :datetime="item.target_date ?? undefined"
            >
              {{ formatDate(item.target_date!) }}
            </time>
          </header>

          <h3 class="roadmap__title">{{ item.title }}</h3>

          <!-- Description (inline) -- suppressed when post_id is set. -->
          <p
            v-if="shouldShowDescription(item)"
            class="roadmap__description"
          >
            {{ item.description }}
          </p>

          <!-- Embedded post snippet -- when present, supersedes the
               inline description. -->
          <button
            v-if="item.post"
            type="button"
            class="roadmap__post"
            @click="$emit('post-click', item.post.id)"
          >
            <div
              v-if="item.post.cover_url"
              class="roadmap__post-cover"
              :style="{
                backgroundImage: itemCoverStyle(item.post.cover_url),
              }"
            />
            <div class="roadmap__post-body">
              <h4 class="roadmap__post-title">{{ item.post.title }}</h4>
              <p
                v-if="item.post.excerpt"
                class="roadmap__post-excerpt"
              >
                {{ item.post.excerpt }}
              </p>
              <span class="roadmap__post-link">
                {{ t('inv.roadmap.readMore') }}
              </span>
            </div>
          </button>

          <!-- Actions: linked product + external URL. Two slots, may
               both be present, in which case they sit side by side. -->
          <div
            v-if="item.linked_product_id || item.external_url"
            class="roadmap__actions"
          >
            <button
              v-if="item.linked_product_id"
              type="button"
              class="roadmap__action roadmap__action--primary"
              @click="$emit('product-click', item.linked_product_id)"
            >
              {{ t('inv.roadmap.openProduct') }}
            </button>
            <button
              v-if="item.external_url"
              type="button"
              class="roadmap__action roadmap__action--outline"
              @click="$emit('external-click', item.external_url)"
            >
              {{ t('inv.roadmap.openExternal') }}
            </button>
          </div>
        </article>
      </li>
    </ol>

    <!-- Terminal: axis dot without a following line + end-marker
         label. Lives outside the <ol> so its DOM semantics don't
         pretend to be another timeline entry. -->
    <div class="roadmap__terminal">
      <div class="roadmap__axis roadmap__axis--terminal">
        <span class="roadmap__line roadmap__line--terminal" />
        <span class="roadmap__dot roadmap__dot--terminal" />
      </div>
      <div class="roadmap__terminal-label">{{ endMarkerLabel }}</div>
    </div>
  </div>
</template>

<style scoped>
.roadmap {
  display: flex;
  flex-direction: column;
}

.roadmap__list {
  /* List semantics for assistive tech, but no bullets / numbers --
     the visual axis communicates ordering. */
  list-style: none;
  margin: 0;
  padding: 0;
}

.roadmap__item {
  display: grid;
  /* Fixed-width axis column + flexible content. 32px fits the dot
     (12px) centered with room for breathing space. */
  grid-template-columns: 32px 1fr;
  gap: var(--space-4);
  padding-bottom: var(--space-6);
}

.roadmap__axis {
  position: relative;
  display: flex;
  justify-content: center;
}

.roadmap__line {
  position: absolute;
  top: 0;
  /* Bleed the axis line into the gap below so consecutive items share
     a continuous visual axis. calc() because plain `-var()` is invalid
     in CSS syntax. */
  bottom: calc(-1 * var(--space-6));
  width: 2px;
  background: var(--border-default);
}

.roadmap__dot {
  position: relative;
  width: 12px;
  height: 12px;
  margin-top: var(--space-2); /* align with the card's first line of text */
  border-radius: var(--radius-pill);
  background: var(--primary);
  box-shadow: 0 0 0 4px var(--bg-page);
  z-index: 1;
}

.roadmap__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.roadmap__cover {
  width: 100%;
  aspect-ratio: 16 / 9;
  background-size: cover;
  background-position: center;
  background-color: var(--bg-subtle);
}

.roadmap__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-4) 0;
}

.roadmap__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.rti__chip {
  display: inline-block;
  padding: var(--space-1) var(--space-2);
  font-size: var(--fs-xs);
  font-weight: 500;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.rti__chip--neutral {
  color: var(--text-secondary);
  background: var(--bg-subtle);
}

.rti__chip--success {
  color: var(--success);
  background: var(--success-subtle);
}

.rti__chip--accent {
  color: var(--accent);
  background: var(--accent-subtle);
}

.rti__chip--danger {
  color: var(--danger);
  background: var(--danger-subtle);
}

.roadmap__date {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.roadmap__title {
  margin: 0;
  padding: 0 var(--space-4);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
}

.roadmap__description {
  margin: 0;
  padding: 0 var(--space-4);
  font-size: var(--fs-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

.roadmap__post {
  display: flex;
  gap: var(--space-2);
  margin: 0 var(--space-4);
  padding: var(--space-2);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-align: left;
  /* Reset native button styling -- the affordance is the link below. */
  font: inherit;
  color: inherit;
  transition: background 0.12s ease;
}

.roadmap__post:hover {
  background: var(--bg-surface);
}

.roadmap__post-cover {
  flex-shrink: 0;
  width: 72px;
  aspect-ratio: 1 / 1;
  background-size: cover;
  background-position: center;
  background-color: var(--bg-surface);
  border-radius: var(--radius-sm);
}

.roadmap__post-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0; /* allow text truncation to work inside flex */
}

.roadmap__post-title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.roadmap__post-excerpt {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.roadmap__post-link {
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--primary);
}

.roadmap__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: 0 var(--space-4) var(--space-4);
}

.roadmap__action {
  flex: 1;
  min-width: 0;
  padding: var(--space-2) var(--space-4);
  font-size: var(--fs-sm);
  font-weight: 500;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.12s ease;
  font: inherit;
}

.roadmap__action--primary {
  color: var(--bg-page);
  background: var(--primary);
  border: 1px solid var(--primary);
}

.roadmap__action--primary:hover {
  background: var(--primary-active);
}

.roadmap__action--outline {
  color: var(--primary);
  background: transparent;
  border: 1px solid var(--primary);
}

.roadmap__action--outline:hover {
  background: var(--primary-subtle);
}

/* ---------- Terminal block (end-marker) ---------- */

.roadmap__terminal {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: var(--space-4);
  align-items: center;
}

.roadmap__axis--terminal {
  height: var(--size-sm); /* compact -- no card to anchor against */
}

.roadmap__line--terminal {
  /* The terminal line stops at the dot (no bleed into a non-existent
     next item). Pull bottom up to match the dot center. */
  top: 0;
  bottom: 50%;
}

.roadmap__dot--terminal {
  margin-top: var(--space-2);
  background: var(--border-default); /* terminal dot is muted vs progress dots */
}

.roadmap__terminal-label {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.roadmap__description { max-width: var(--maxw-prose); }
</style>
