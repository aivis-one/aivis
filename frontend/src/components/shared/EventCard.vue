<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EventCard (iter 2.7b C, R1 §6.3)
// =============================================================================
//
// Shared card for calendar events. Two variants from one component so
// the dashboard widget and the full /investor/events screen render the
// same event consistently (no duplicated event markup):
//
//   variant="compact"  -- dashboard "Upcoming events" widget. A row of the
//                         Row list (K23): calendar icon + title + date, time
//                         and location. The whole row is one click target
//                         (the title's button stretches over it); the parent
//                         navigates to the events screen.
//   variant="full"     -- /investor/events list. A media card (K07): the
//                         cover with the date on it, the title, time and
//                         location, a description preview, plus an explicit
//                         "open link" affordance when the event has a url.
//
// NAVIGATION-AGNOSTIC, AND ONLY `compact` IS A CLICK TARGET.
//   compact emits @click with the event and the parent decides what a
//   tap does (the dashboard widget pushes to the events screen).
//   full does NOT emit and is NOT clickable as a whole. Its one
//   affordance is the explicit external link, a plain
//   <a target="_blank"> inside the card.
//   ⚠ full USED TO PAINT cursor:pointer, a :hover lift and an :active
//   depress, and to emit @click -- which NO call site listened to
//   (its only full-variant call site is InvestorEventsView). Every card on
//   /investor/events looked pressable and did nothing, and with no
//   tabindex and no role a keyboard user could not even discover it was
//   inert. The affordance was removed rather than wired up, because
//   /investor/events IS the events screen and there is no decided
//   destination for a tap. If one is ever decided, the painted states
//   come back WITH the listener, never before it.
//
// FP-25 SELF-HIDE.
//   cover, description, location, and url are all optional on
//   EventResponse -- each renders only when present. A full card with
//   no cover falls back to the media card's icon tile (same pattern as
//   CompanyCard's fallback) so the grid stays visually even.
//
// LOCALE-AWARE DATES.
//   Day / month / time come from Intl (toLocaleDateString /
//   toLocaleTimeString with locale.value) -- no hardcoded month names
//   or i18n month keys. Same pattern as the dashboard date helpers.
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarDays, ChevronRight, ExternalLink } from '@/components/ui/icons'
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

// The cover is a picture that covers the media part of the card (K07); without one
// the fallback tile with the calendar icon.
const coverSrc = computed(() => props.event.cover_url ?? null)

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

// "1 Sep, 15:00, Dubai": the date, the time and the place, one line.
const meta = computed<string>(() =>
  [`${day.value} ${month.value}`, time.value, props.event.location].filter(Boolean).join(', '),
)

function fmtDate(opts: Intl.DateTimeFormatOptions): string {
  try {
    return new Date(props.event.starts_at).toLocaleDateString(locale.value, opts)
  } catch {
    return ''
  }
}
</script>

<template>
  <!-- Compact: dashboard widget row (K23). The whole row emits @click: the title is
       a button whose area stretches over the row. -->
  <ul v-if="variant === 'compact'" class="ds-rows">
    <li class="ds-row">
      <span class="ds-row__lead"><CalendarDays size="sm" /></span>
      <span class="ds-row__body">
        <button
          type="button"
          class="ds-row__link event-card--compact"
          @click="$emit('click', event)"
        >
          <span class="ds-row__title">{{ event.title }}</span>
        </button>
        <span class="ds-row__meta">{{ meta }}</span>
      </span>
      <span class="ds-row__trail"><ChevronRight size="sm" /></span>
    </li>
  </ul>

  <!-- Full: list card (K07 media). Cover + description + optional external link.
       Not a click target -- see the note at the top of this file. -->
  <div v-else class="ds-card ds-card--media event-card--full">
    <div class="ds-card__media" :class="{ 'ds-card__media--fallback': !coverSrc }">
      <img v-if="coverSrc" :src="coverSrc" alt="" loading="lazy" />
      <CalendarDays v-else />
      <span class="ds-card__tag">{{ day }} {{ month }}</span>
    </div>

    <div class="ds-card__content">
      <h3 class="ds-card__title">
        {{ event.title }}
      </h3>

      <p class="ds-card__body">{{ meta }}</p>

      <p v-if="event.description" class="ds-card__body event-card__desc">
        {{ event.description }}
      </p>

      <div v-if="event.url">
        <a
          :href="event.url"
          target="_blank"
          rel="noopener noreferrer"
          class="ds-button ds-button--ghost event-card__link"
          data-size="sm"
        >
          <ExternalLink size="sm" />
          {{ t('inv.events.eventCard.openUrl') }}
        </a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The card, its cover, the date chip, the row and the link are the system's. What
   is left is the description's two-line preview, capped at the reading measure
   (--maxw-prose is a ceiling: on a phone it does nothing). */
.event-card__desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-inline-size: var(--maxw-prose);
}
</style>
