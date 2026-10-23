<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorNewsView ("News and events")
// =============================================================================
//
// The common feed of posts and events: the platform's and every project's.
// Reached from the "News and events" row of the home screen (on a phone it is
// a screen inside the home tab, with a back control) and from its own line of
// the side menu on the web.
//
// ONE LIST, NEWEST FIRST. A post is dated by its publication, an event by its
// start; the two are merged into one list and each row opens its own screen
// (the post, or the event). Posts page in with "Show more"; events are read in
// one go (the upcoming ones and the latest past ones), because they are few.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CalendarDays, FileText } from '@/components/ui/icons'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { listPosts } from '@/api/posts'
import { listPublicEvents, listUpcomingEvents } from '@/api/events'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate } from '@/utils/format'
import type { EventResponse, PostResponse } from '@/api/types'

const { t, locale } = useI18n()
const router = useRouter()

const POSTS_PER_PAGE = 20
const UPCOMING_EVENTS = 50
const PAST_EVENTS = 20

interface FeedRow {
  kind: 'post' | 'event'
  id: string
  title: string
  at: string
  cover: string | null
}

const posts = ref<PostResponse[]>([])
const postsTotal = ref(0)
const postsPage = ref(1)
const events = ref<EventResponse[]>([])
const loading = ref(true)
const errored = ref(false)
const loadingMore = ref(false)

const rows = computed<FeedRow[]>(() => {
  const fromPosts: FeedRow[] = posts.value.map((p) => ({
    kind: 'post',
    id: p.id,
    title: p.title,
    at: p.published_at ?? p.created_at,
    cover: p.cover_url ?? null,
  }))
  const fromEvents: FeedRow[] = events.value.map((e) => ({
    kind: 'event',
    id: e.id,
    title: e.title,
    at: e.starts_at,
    cover: e.cover_url ?? null,
  }))
  return [...fromPosts, ...fromEvents].sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
})

const hasMorePosts = computed(() => posts.value.length < postsTotal.value)

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const [postPage, upcoming, past] = await Promise.all([
      listPosts({ page: 1, per_page: POSTS_PER_PAGE }),
      listUpcomingEvents(UPCOMING_EVENTS),
      listPublicEvents({ upcoming: false, page: 1, per_page: PAST_EVENTS }),
    ])
    posts.value = postPage.items
    postsTotal.value = postPage.total
    postsPage.value = 1
    events.value = [...upcoming, ...past.items]
  } catch {
    errored.value = true
  } finally {
    loading.value = false
  }
}

async function showMore(): Promise<void> {
  if (loadingMore.value || !hasMorePosts.value) return
  loadingMore.value = true
  try {
    const next = postsPage.value + 1
    const resp = await listPosts({ page: next, per_page: POSTS_PER_PAGE })
    posts.value = [...posts.value, ...resp.items]
    postsTotal.value = resp.total
    postsPage.value = next
  } catch {
    // The rows already shown stay; the button is still there to try again.
  } finally {
    loadingMore.value = false
  }
}

function openRow(row: FeedRow): void {
  void safeNavigate(
    router.push(
      row.kind === 'post'
        ? { name: 'investor-post', params: { id: row.id } }
        : { name: 'investor-event', params: { id: row.id } },
    ),
    '[InvestorNewsView] to row',
  )
}

function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push({ name: 'investor-dashboard' }), '[InvestorNewsView] back fallback')
}

onMounted(load)
</script>

<template>
  <div class="news">
    <div class="news__back">
      <CBackLink :label="t('common.back')" @click="goBack" />
    </div>
    <h1 class="news__title">
      {{ t('inv.news.title') }}
    </h1>

    <div v-if="loading" class="news__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="errored" class="news__center">
      <CEmptyState :title="t('inv.news.errorTitle')" />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <div v-else-if="rows.length === 0" class="news__center">
      <CEmptyState :title="t('inv.news.empty')" />
    </div>

    <template v-else>
      <ul class="news__list">
        <li v-for="row in rows" :key="`${row.kind}-${row.id}`">
          <button type="button" class="news__row" @click="openRow(row)">
            <img v-if="row.cover" :src="row.cover" :alt="row.title" class="news__cover" loading="lazy" />
            <span v-else class="news__icon">
              <CalendarDays v-if="row.kind === 'event'" :size="20" />
              <FileText v-else :size="20" />
            </span>
            <span class="news__body">
              <span class="news__kind">{{ t(`inv.news.kind.${row.kind}`) }}</span>
              <span class="news__row-title">{{ row.title }}</span>
              <span class="news__date">{{ formatDate(row.at, locale) }}</span>
            </span>
          </button>
        </li>
      </ul>
      <div v-if="hasMorePosts" class="news__more">
        <CButton variant="outline" size="sm" :loading="loadingMore" @click="showMore">
          {{ t('inv.news.showMore') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.news {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4) var(--space-5);
}

.news__back {
  padding: 0;
}

.news__title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.news__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-height: var(--center-sm);
  padding: var(--space-4) var(--space-2);
}

.news__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.news__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-page);
  color: inherit;
  font-family: inherit;
  text-align: start;
  cursor: pointer;
  transition: border-color 0.15s;
}

.news__row:hover {
  border-color: var(--primary);
}

.news__cover {
  width: var(--size-4xl);
  height: var(--size-4xl);
  object-fit: cover;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.news__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--size-4xl);
  height: var(--size-4xl);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.news__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  flex: 1;
}

.news__kind {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.news__row-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.news__date {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.news__more {
  display: flex;
  justify-content: center;
}
</style>
