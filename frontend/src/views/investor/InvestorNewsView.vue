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
//
// The list is the system's Row list (K23): each row is one link on its title.
// The frame's header holds the title and the back control.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarDays, FileText } from '@/components/ui/icons'
import { CButton, CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { listPosts } from '@/api/posts'
import { listPublicEvents, listUpcomingEvents } from '@/api/events'
import { formatDate } from '@/utils/format'
import type { EventResponse, PostResponse } from '@/api/types'

const { t, locale } = useI18n()

// Back: one step back when there is a page to return to, else the shell's home.
useScreenHeader({
  title: () => t('inv.news.title'),
  back: () => (window.history.state?.back ? true : { name: 'investor-dashboard' }),
})

const POSTS_PER_PAGE = 20
const UPCOMING_EVENTS = 50
const PAST_EVENTS = 20

interface FeedRow {
  kind: 'post' | 'event'
  id: string
  title: string
  at: string
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
  }))
  const fromEvents: FeedRow[] = events.value.map((e) => ({
    kind: 'event',
    id: e.id,
    title: e.title,
    at: e.starts_at,
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

function rowRoute(row: FeedRow) {
  return row.kind === 'post'
    ? { name: 'investor-post', params: { id: row.id } }
    : { name: 'investor-event', params: { id: row.id } }
}

onMounted(load)
</script>

<template>
  <div class="news">
    <!-- Loading: the placeholder rows of the list that will arrive (K19) -->
    <section v-if="loading" aria-busy="true">
      <span class="ds-sr-only" role="status">{{ t('common.loading') }}</span>
      <div class="ds-rows" aria-hidden="true">
        <div v-for="n in 4" :key="n" class="ds-skeleton-row">
          <span class="ds-skeleton ds-skeleton--avatar" />
          <span class="ds-skeleton-stack">
            <span class="ds-skeleton ds-skeleton--title" />
            <span class="ds-skeleton ds-skeleton--text" />
          </span>
        </div>
      </div>
    </section>

    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.news.errorTitle')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState v-else-if="rows.length === 0" :title="t('inv.news.empty')" />

    <template v-else>
      <ul class="ds-rows">
        <li v-for="row in rows" :key="`${row.kind}-${row.id}`" class="ds-row">
          <span class="ds-row__lead">
            <CalendarDays v-if="row.kind === 'event'" size="sm" />
            <FileText v-else size="sm" />
          </span>
          <span class="ds-row__body">
            <RouterLink class="ds-row__link" :to="rowRoute(row)">
              <span class="ds-row__title">{{ row.title }}</span>
            </RouterLink>
            <span class="ds-row__meta">{{ formatDate(row.at, locale) }}</span>
          </span>
          <span class="ds-row__trail">
            <span class="ds-badge">{{ t(`inv.news.kind.${row.kind}`) }}</span>
          </span>
        </li>
      </ul>
      <div v-if="hasMorePosts" class="news__more">
        <CButton variant="outline" size="sm" inline :loading="loadingMore" @click="showMore">
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
}

.news__more {
  display: flex;
  justify-content: center;
}
</style>
