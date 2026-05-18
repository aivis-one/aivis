<script setup lang="ts">
// 404 — page not found.
// Uses common.back key (exists) for button text.
// error.pageNotFound will show key string until i18n is added.

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'

const { t } = useI18n()
const router = useRouter()

function goHome(): void {
  void safeNavigate(router.push('/'), '[NotFoundView] to home')
}
</script>

<template>
  <div class="not-found">
    <h1 class="not-found__code">404</h1>
    <p class="not-found__text">{{ t('error.pageNotFound') }}</p>
    <button class="not-found__btn" @click="goHome">
      {{ t('common.back') }}
    </button>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg);
  padding: 24px;
  text-align: center;
}

.not-found__code {
  font-size: 72px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1;
}

.not-found__text {
  font-size: 16px;
  color: var(--text-secondary);
  margin: 16px 0 32px;
}

.not-found__btn {
  padding: 12px 32px;
  border-radius: var(--radius-md, 8px);
  background: var(--accent);
  color: white;
  font-weight: 600;
  font-size: 15px;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
</style>
