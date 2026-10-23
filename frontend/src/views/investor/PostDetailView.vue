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
// The screen has its own back control: it returns to where the person came
// from, and a deep link (no history) goes to the shell's home.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { getPost } from '@/api/posts'
import { safeNavigate } from '@/composables/safeNavigate'
import { formatDate } from '@/utils/format'
import type { PostResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const post = ref<PostResponse | null>(null)
const loading = ref(true)
const errored = ref(false)

const postId = computed(() => route.params.id as string)
const isPublic = computed(() => route.meta.public === true)

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

function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(
    router.push({ name: isPublic.value ? 'public-companies' : 'investor-dashboard' }),
    '[PostDetailView] back fallback',
  )
}

onMounted(load)
</script>

<template>
  <div class="post">
    <div class="post__back">
      <CBackLink :label="t('common.back')" @click="goBack" />
    </div>

    <div v-if="loading" class="post__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="errored || !post" class="post__center">
      <CEmptyState
        :title="t('inv.post.errorTitle')"
        :description="t('inv.post.errorDesc')"
      />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <article v-else class="post__article">
      <img v-if="post.cover_url" :src="post.cover_url" :alt="post.title" class="post__cover" />
      <h1 class="post__title">
        {{ post.title }}
      </h1>
      <time class="post__date" :datetime="post.published_at ?? post.created_at">
        {{ formatDate(post.published_at ?? post.created_at, locale) }}
      </time>
      <p class="post__body">
        {{ post.body }}
      </p>
    </article>
  </div>
</template>

<style scoped>
.post {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.post__back {
  padding: var(--space-3) var(--space-4) 0;
}

.post__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: calc(100vh - 160px);
  min-height: calc(100dvh - 160px);
  padding: var(--space-5);
}

.post__article {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}

.post__cover {
  width: 100%;
  max-height: 240px;
  object-fit: cover;
  border-radius: var(--radius-md);
}

.post__title {
  margin: 0;
  font-size: var(--fs-h3);
  font-weight: 700;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.post__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.post__body {
  margin: 0;
  font-size: var(--fs-sm);
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* On a wide screen the text keeps a reading measure instead of the full row. */
@media (min-width: 880px) {
  .post__article {
    max-width: var(--maxw-prose);
  }
}
</style>
