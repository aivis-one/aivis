<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EventCard (iter 2.7b C, R1 §6.3)
// =============================================================================
//
// Shared card for calendar events. Two variants from one component so
// the dashboard widget and the full /investor/events screen render the
// same event consistently (no duplicated event markup):
//
//   variant="compact"  -- dashboard "Upcoming events" widget. A tight
//                         row: date badge + title + time + location.
//                         The whole card is one click target; the
//                         parent navigates to the events screen.
//   variant="full"     -- /investor/events list. Adds the cover image
//                         and a description preview, plus an explicit
//                         "open link" affordance when the event has a
//                         url.
//
// NAVIGATION-AGNOSTIC (mirrors CompanyCard / ProductCard).
//   The card emits @click with the event; the parent decides what a
//   tap does (the widget pushes to the events screen, the full list
//   may do nothing or open the external url). The external link is the
//   one exception: it is a plain <a target="_blank"> inside the card,
//   stopPropagation'd so opening the link does not also fire @click.
//
// FP-25 SELF-HIDE.
//   cover, description, location, and url are all optional on
//   EventResponse -- each renders only when present. A full card with
//   no cover falls back to a calendar-icon tile (same pattern as
//   CompanyCard's fallback) so the grid stays visually even.
//
// LOCALE-AWARE DATES.
//   Day / month / time come from Intl (toLocaleDateString /
//   toLocaleTimeString with locale.value) -- no hardcoded month names
//   or i18n month keys. Same pattern as the dashboard date helpers.
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarDays, MapPin, ChevronRight, ExternalLink } from 'lucide-vue-next'
import { resolveCoverImage } from '@/utils/format'
import type { EventResponse } from '@/api/types'

const props = withDefaults(
  defineProps<{
    event: EventResponse
    variant?: 'compact' | 'full'
  }>(),
  { variant: 'full' },
)

defineEmits<{ click: [event: EventResponse] }>()

const { t, locale } = useI18n()

const coverImage = computed(() =>
  resolveCoverImage({ cover_url: props.event.cover_url }),
)

const day = computed<string>(() => fmtDate({ day: 'numeric' }))
const month = computed<string>(() => fmtDate({ month: 'short' }))
const time = computed<string>(() => {
  try {
    return new Date(props.event.starts_at).toLocaleTimeString(locale.value, {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
})

function fmtDate(opts: Intl.DateTimeFormatOptions): string {
  try {
    return new Date(props.event.starts_at).toLocaleDateString(
      locale.value,
      opts,
    )
  } catch {
    return ''
  }
}
</script>

<template>
  <!-- Compact: dashboard widget row. Whole card emits @click. -->
  <button
    v-if="variant === 'compact'"
    type="button"
    class="event-card event-card--compact"
    @click="$emit('click', event)"
  >
    <div class="event-card__badge">
      <span class="event-card__day">{{ day }}</span>
      <span class="event-card__mon">{{ month }}</span>
    </div>
    <div class="event-card__body">
      <div class="event-card__title">{{ event.title }}</div>
      <div class="event-card__meta">
        <span class="event-card__time">{{ time }}</span>
        <span v-if="event.location" class="event-card__loc">
          <MapPin :size="16" />
          {{ event.location }}
        </span>
      </div>
    </div>
    <ChevronRight :size="16" class="event-card__chev" />
  </button>

  <!-- Full: list card. Cover + description + optional external link. -->
  <div
    v-else
    class="event-card event-card--full"
    @click="$emit('click', event)"
  >
    <div
      class="event-card__cover"
      :class="{ 'event-card__cover--fallback': !coverImage }"
      :style="{ backgroundImage: coverImage ?? undefined }"
    >
      <CalendarDays v-if="!coverImage" :size="32" />
      <div class="event-card__cover-badge">
        <span class="event-card__day">{{ day }}</span>
        <span class="event-card__mon">{{ month }}</span>
      </div>
    </div>

    <div class="event-card__body">
      <div class="event-card__title event-card__title--full">
        {{ event.title }}
      </div>

      <div class="event-card__meta">
        <span class="event-card__time">{{ time }}</span>
        <span v-if="event.location" class="event-card__loc">
          <MapPin :size="16" />
          {{ event.location }}
        </span>
      </div>

      <p v-if="event.description" class="event-card__desc">
        {{ event.description }}
      </p>

      <a
        v-if="event.url"
        :href="event.url"
        target="_blank"
        rel="noopener noreferrer"
        class="event-card__link"
        @click.stop
      >
        <ExternalLink :size="16" />
        {{ t('inv.events.eventCard.openUrl') }}
      </a>
    </div>
  </div>
</template>

<style scoped>
.event-card__badge,
.event-card__cover-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--accent);
}
.event-card__day { font-size: var(--fs-h4); font-weight: 700; line-height: 1; }
.event-card__mon {
  font-size: var(--fs-3xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.event-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}
.event-card__title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.event-card__title--full { font-size: var(--fs-body); }
.event-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.event-card__loc {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-width: 0;
}
.event-card__desc {
  margin: var(--space-1) 0 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.event-card__link {
  /* A5: 81.8 x 21 measured -- a 21px-tall touch target. The painted link must
     stay inline with the card text, so the HIT AREA is expanded past it.
     ⚠ NEITHER SWEEP CAUGHT THIS. Reaching /investor/events by router.push does
     not render the event cards, so the sweep measured a page with no cards on
     it; a direct page load shows eight of these failing. A route visited by
     client-side navigation is not always the page a user loads. */
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  width: fit-content;
}

.event-card__link::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: max(100%, var(--tap-min));
  height: max(100%, var(--tap-min));
}

/* Compact variant: single clickable row. */
.event-card--compact {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  text-align: left;
  cursor: pointer;
}
.event-card--compact .event-card__badge {
  width: var(--size-3xl);
  height: var(--size-3xl);
}
.event-card__chev { color: var(--text-secondary); flex-shrink: 0; }

/* Full variant: cover on top, body below. */
.event-card--full {
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.event-card--full:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
.event-card--full:active { transform: translateY(0); }
.event-card__cover {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  background-size: cover;
  background-position: center;
  background-color: var(--bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}
.event-card__cover--fallback {
  background-image: linear-gradient(
    135deg,
    var(--bg-subtle) 0%,
    var(--bg-surface) 100%
  );
}
.event-card__cover-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  width: var(--size-2xl);
  height: var(--size-2xl);
  background: var(--bg-page);
  box-shadow: var(--shadow-1);
}
.event-card--full .event-card__body { padding: var(--space-4); }

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.event-card__desc { max-width: var(--maxw-prose); }
</style>
