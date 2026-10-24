<script setup lang="ts">
// The pager of a staff list, on the design system's Pager (K17): the first page,
// the last, the current one and its neighbours, with a gap between. Each page is a
// link naming `?page=n` (the address `useUrlPage` reads); a plain click moves the
// list in place and emits `update:page`, so the list keeps its filters and its
// scroll. The ends that cannot move are `aria-disabled` and carry no address.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight } from '@/components/ui/icons'
import { PAGE_KEY, searchForPage } from './useUrlPage'

const props = defineProps<{ page: number; totalPages: number }>()
const emit = defineEmits<{ 'update:page': [page: number] }>()

const { t, te } = useI18n()

// The wording of the pager's names: the keys the pager needs are common.pager.*;
// until they are in the language files the previous and next names are the common
// Back and Next, and the landmark and the numbers carry no extra name.
const navLabel = computed(() => (te('common.pager.label') ? t('common.pager.label') : undefined))
const prevLabel = computed(() =>
  te('common.pager.prev') ? t('common.pager.prev') : t('common.back'),
)
const nextLabel = computed(() =>
  te('common.pager.next') ? t('common.pager.next') : t('common.next'),
)
function pageLabel(n: number): string | undefined {
  return te('common.pager.page') ? t('common.pager.page', { n }) : undefined
}

type Item = { kind: 'page'; n: number } | { kind: 'gap'; key: string }

const items = computed<Item[]>(() => {
  const last = props.totalPages
  const shown = new Set<number>([1, last, props.page - 1, props.page, props.page + 1])
  const numbers = [...shown].filter((n) => n >= 1 && n <= last).sort((a, b) => a - b)
  const out: Item[] = []
  numbers.forEach((n, i) => {
    const before = numbers[i - 1]
    if (before !== undefined && n - before > 1) out.push({ kind: 'gap', key: `gap-${n}` })
    out.push({ kind: 'page', n })
  })
  return out
})

function hrefFor(n: number): string {
  const search = typeof window === 'undefined' ? '' : window.location.search
  // The first page is the bare address; the others name their page.
  return searchForPage(search, n, PAGE_KEY) || '?'
}

function go(n: number): void {
  if (n < 1 || n > props.totalPages || n === props.page) return
  emit('update:page', n)
}
</script>

<template>
  <nav v-if="totalPages > 1" class="ds-pager" :aria-label="navLabel">
    <ul class="ds-pager__list">
      <li>
        <a
          class="ds-pager__item"
          :href="page > 1 ? hrefFor(page - 1) : undefined"
          :aria-disabled="page <= 1 ? 'true' : undefined"
          :aria-label="prevLabel"
          @click.prevent="go(page - 1)"
        >
          <ChevronLeft />
        </a>
      </li>
      <template v-for="item in items" :key="item.kind === 'page' ? item.n : item.key">
        <li v-if="item.kind === 'page'">
          <a
            class="ds-pager__item"
            :href="hrefFor(item.n)"
            :aria-current="item.n === page ? 'page' : undefined"
            :aria-label="pageLabel(item.n)"
            @click.prevent="go(item.n)"
          >
            {{ item.n }}
          </a>
        </li>
        <li v-else><span class="ds-pager__gap" aria-hidden="true">&hellip;</span></li>
      </template>
      <li>
        <a
          class="ds-pager__item"
          :href="page < totalPages ? hrefFor(page + 1) : undefined"
          :aria-disabled="page >= totalPages ? 'true' : undefined"
          :aria-label="nextLabel"
          @click.prevent="go(page + 1)"
        >
          <ChevronRight />
        </a>
      </li>
    </ul>
  </nav>
</template>
