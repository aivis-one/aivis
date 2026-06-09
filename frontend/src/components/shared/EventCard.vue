<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- EventCard (iter 2.7b C, R1 §6.3)
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
          <MapPin :size="12" />
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
          <MapPin :size="12" />
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
        <ExternalLink :size="14" />
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
  color: var(--accent, var(--text));
}
.event-card__day { font-size: 18px; font-weight: 700; line-height: 1; }
.event-card__mon {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.event-card__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.event-card__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.event-card__title--full { font-size: 16px; }
.event-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}
.event-card__loc {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}
.event-card__desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.event-card__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent, var(--primary));
  text-decoration: none;
  width: fit-content;
}

/* Compact variant: single clickable row. */
.event-card--compact {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  text-align: left;
  cursor: pointer;
}
.event-card--compact .event-card__badge {
  width: 48px;
  height: 48px;
}
.event-card__chev { color: var(--text-secondary); flex-shrink: 0; }

/* Full variant: cover on top, body below. */
.event-card--full {
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.event-card--full:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
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
    var(--bg-elevated) 100%
  );
}
.event-card__cover-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 44px;
  height: 44px;
  background: var(--bg);
  box-shadow: var(--shadow-sm);
}
.event-card--full .event-card__body { padding: var(--space-md, 12px); }
</style>
