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
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CalendarDays, ExternalLink, MapPin } from 'lucide-vue-next'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { listPublicEvents, listUpcomingEvents } from '@/api/events'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDateTime } from '@/utils/format'
import type { EventResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const event = ref<EventResponse | null>(null)
const loading = ref(true)
const errored = ref(false)

const eventId = computed(() => route.params.id as string)

const UPCOMING_LIMIT = 50
const PAST_PAGE_SIZE = 100

async function find(id: string): Promise<EventResponse | null> {
  const upcoming = await listUpcomingEvents(UPCOMING_LIMIT)
  const inUpcoming = upcoming.find((e) => e.id === id)
  if (inUpcoming) return inUpcoming
  const past = await listPublicEvents({ upcoming: false, page: 1, per_page: PAST_PAGE_SIZE })
  return past.items.find((e) => e.id === id) ?? null
}

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    event.value = await find(eventId.value)
  } catch {
    event.value = null
    errored.value = true
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

function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push({ name: 'investor-dashboard' }), '[EventDetailView] back fallback')
}

onMounted(load)
</script>

<template>
  <div class="evd">
    <div class="evd__back">
      <CBackLink :label="t('common.back')" @click="goBack" />
    </div>

    <div v-if="loading" class="evd__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="errored" class="evd__center">
      <CEmptyState :title="t('inv.events.errorTitle')" />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <div v-else-if="!event" class="evd__center">
      <CEmptyState :title="t('inv.events.notFound')" />
    </div>

    <article v-else class="evd__article">
      <img v-if="event.cover_url" :src="event.cover_url" :alt="event.title" class="evd__cover" />
      <h1 class="evd__title">
        {{ event.title }}
      </h1>
      <p class="evd__meta">
        <CalendarDays :size="16" />
        <span>{{ whenLabel }}</span>
      </p>
      <p v-if="event.location" class="evd__meta">
        <MapPin :size="16" />
        <span>{{ event.location }}</span>
      </p>
      <p v-if="event.description" class="evd__body">
        {{ event.description }}
      </p>
      <a v-if="event.url" :href="event.url" target="_blank" rel="noopener" class="evd__link">
        <ExternalLink :size="16" />
        {{ t('inv.events.eventCard.openUrl') }}
      </a>
    </article>
  </div>
</template>

<style scoped>
.evd {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.evd__back {
  padding: var(--space-3) var(--space-4) 0;
}

.evd__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: calc(100vh - 160px);
  min-height: calc(100dvh - 160px);
  padding: var(--space-5);
}

.evd__article {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}

.evd__cover {
  width: 100%;
  max-height: 240px;
  object-fit: cover;
  border-radius: var(--radius-md);
}

.evd__title {
  margin: 0;
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.evd__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.evd__body {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.evd__link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--primary);
  text-decoration: none;
}

.evd__link:hover {
  text-decoration: underline;
}
</style>
