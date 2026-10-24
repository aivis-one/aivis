<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- EventDetailView
// =============================================================================
//
// One event, in full: cover, title, when, where, the description and the
// outside link when the event has one. Reached from a card on the home screen,
// from the events list and from a notification about an event.
//
// THE SERVER HAS NO READ-BY-ID FOR AN EVENT. The screen finds the event in
// the upcoming list first and, failing that, in the past list; the lists are
// small and public. An id that is in neither shows the "not found" state.
//
// The frame's header holds the title and the back control: it returns to where
// the person came from, and a deep link (no history) goes to the shell's home.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CalendarDays, ExternalLink, MapPin } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getPublicEvent } from '@/api/events'
import { ApiResponseError } from '@/api/client'
import { formatDateTime } from '@/utils/format'
import type { EventResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()

const event = ref<EventResponse | null>(null)
const loading = ref(true)
const errored = ref(false)

const eventId = computed(() => route.params.id as string)

// Back: one step back when there is a page to return to, else the shell's home.
useScreenHeader({
  title: () => event.value?.title,
  back: () => (window.history.state?.back ? true : { name: 'investor-dashboard' }),
})

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    event.value = await getPublicEvent(eventId.value)
  } catch (err) {
    event.value = null
    // 404 = no such published event: the "not found" state, not an error.
    errored.value = !(err instanceof ApiResponseError && err.status === 404)
  } finally {
    loading.value = false
  }
}

const whenLabel = computed<string>(() => {
  const e = event.value
  if (!e) return ''
  const start = formatDateTime(e.starts_at, locale.value)
  return e.ends_at ? `${start} — ${formatDateTime(e.ends_at, locale.value)}` : start
})

onMounted(load)
</script>

<template>
  <div class="evd">
    <CLoader v-if="loading" centered extent="page" />

    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.events.errorTitle')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState v-else-if="!event" :title="t('inv.events.notFound')" />

    <article v-else class="ds-card ds-card--media evd__article">
      <div v-if="event.cover_url" class="ds-card__media" data-size="lg">
        <img :src="event.cover_url" :alt="event.title" />
      </div>
      <div class="ds-card__content">
        <p class="ds-note evd__meta">
          <CalendarDays size="sm" />
          <span>{{ whenLabel }}</span>
        </p>
        <p v-if="event.location" class="ds-note evd__meta">
          <MapPin size="sm" />
          <span>{{ event.location }}</span>
        </p>
        <p v-if="event.description" class="ds-card__body evd__body">
          {{ event.description }}
        </p>
        <div v-if="event.url" class="evd__actions">
          <a
            :href="event.url"
            target="_blank"
            rel="noopener"
            class="ds-button ds-button--secondary"
          >
            <ExternalLink size="sm" />
            <span>{{ t('inv.events.eventCard.openUrl') }}</span>
          </a>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.evd {
  display: flex;
  flex-direction: column;
}

.evd__article {
  inline-size: 100%;
}

.evd__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.evd__body {
  margin: 0;
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.evd__actions {
  display: flex;
}

/* On a wide screen the text keeps a reading measure instead of the full row. */
@media (min-width: 880px) {
  .evd__article {
    max-inline-size: var(--maxw-prose);
  }
}
</style>
