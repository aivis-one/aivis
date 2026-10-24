<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PostDetailView
// =============================================================================
//
// One post, full. Reached from a feed row on the home screen, from a roadmap
// entry that is linked to a post, and from a notification about a post. The
// same screen serves the investor shell (/investor/posts/:id) and the open
// storefront (/public/posts/:id); the endpoint is readable without signing in.
//
// The frame's header holds the title and the back control: it returns to where
// the person came from, and a deep link (no history) goes to the shell's home.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getPost } from '@/api/posts'
import { formatDate } from '@/utils/format'
import type { PostResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()

const post = ref<PostResponse | null>(null)
const loading = ref(true)
const errored = ref(false)

const postId = computed(() => route.params.id as string)
const isPublic = computed(() => route.meta.public === true)

// Back: one step back when there is a page to return to, else the shell's home.
useScreenHeader({
  title: () => post.value?.title,
  back: () =>
    window.history.state?.back
      ? true
      : { name: isPublic.value ? 'public-companies' : 'investor-dashboard' },
})

async function load(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    post.value = await getPost(postId.value)
  } catch {
    post.value = null
    errored.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="post">
    <CLoader v-if="loading" />

    <CEmptyState
      v-else-if="errored || !post"
      tone="danger"
      :title="t('inv.post.errorTitle')"
      :description="t('inv.post.errorDesc')"
    >
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <article v-else class="ds-card ds-card--media post__article">
      <div v-if="post.cover_url" class="ds-card__media" data-size="lg">
        <img :src="post.cover_url" :alt="post.title" />
      </div>
      <div class="ds-card__content">
        <time class="post__date" :datetime="post.published_at ?? post.created_at">
          {{ formatDate(post.published_at ?? post.created_at, locale) }}
        </time>
        <p class="ds-card__body post__body">
          {{ post.body }}
        </p>
      </div>
    </article>
  </div>
</template>

<style scoped>
.post {
  display: flex;
  flex-direction: column;
}

.post__article {
  inline-size: 100%;
}

.post__date {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.post__body {
  margin: 0;
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* On a wide screen the text keeps a reading measure instead of the full row. */
@media (min-width: 880px) {
  .post__article {
    max-inline-size: var(--maxw-prose);
  }
}
</style>
