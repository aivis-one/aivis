<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyFaqView (TASK-39 item 3, FAQ framework)
// =============================================================================
//
// Static FAQ page for the company (project) audience -- its OWN,
// SEPARATE file set from the shared investor/agent FAQ (see
// InvestorFaqView.vue's header comment for the full ruling). Reached
// from a row inside CompanySettingsView -> /company/faq (route name
// company-faq). Same "no dead 6th tab-bar slot" placement reasoning
// as the Roadmap/Posts/Attachments/Support/Audit rows already there:
// CompanyShell has no More tab (COMPANY_TABS has 5 fixed slots), so
// every non-tab entry lives as a Settings row instead. Same
// back target as CompanyRoadmapView / CompanyPostsView /
// CompanyAttachmentsView (a single fixed target, /company/settings --
// company has no shell-switching to account for, unlike
// InvestorFaqView which is shared across two shells).
//
// OWNER RULING (TASK-39 item 3, verbatim intent) -- see
// InvestorFaqView.vue for the full ruling text. Summary as it applies
// here:
//   1. THE FORM (decided by the owner, 2026-10-23): the FAQ is a section of
//      the system's Accordion (K27, the FAQ form: one open at a time, a
//      search above the list), and the screen READS the existing FAQ file,
//      so the judged text keeps one place. The file is parsed with
//      DOMParser (no script runs) and drawn from text pieces and safe
//      links by Vue, never as markup: NOT v-html.
//   2. This view is the company's OWN FAQ, deliberately not merged
//      with the investor/agent one -- a company's questions are not
//      an investor's. Staff/admin gets no FAQ; nothing here or
//      anywhere adds one.
//   3. The text lives in /faq/{lang}/company.html, which this view
//      renders as it is. This view invents no FAQ copy.
//
// LOCALE FALLBACK + PATH SAFETY -- identical reasoning to
// InvestorFaqView.vue: FAQ_LOCALES is its own {en, ru} constant,
// narrower than i18n's SUPPORTED_LOCALES ({en, ru, de, ar}), and
// resolveFaqLocale() narrows the runtime locale value to that literal
// union BEFORE it reaches the fetch URL -- an unrecognised locale
// (including the parked de/ar) resolves to `en` and never reaches
// fetch() unresolved. The audience segment ("company") is a hardcoded
// literal in this file, not interpolated from a variable.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@/components/ui/icons'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'

const { t, locale } = useI18n()

// FAQ content exists for these locales only -- see header note.
const FAQ_LOCALES = ['en', 'ru'] as const
type FaqLocale = (typeof FAQ_LOCALES)[number]

function resolveFaqLocale(value: string): FaqLocale {
  return (FAQ_LOCALES as readonly string[]).includes(value) ? (value as FaqLocale) : 'en'
}

// ---------------------------------------------------------------------------
// The questions, read from the file's headings
// ---------------------------------------------------------------------------

/** A piece of an answer's paragraph: plain text, or a link. */
interface Piece {
  text: string
  href?: string
}
interface FaqItem {
  question: string
  paragraphs: Piece[][]
  /** The question and the answer as one lowercase string, for the search. */
  haystack: string
}

const SAFE_HREF = /^(https?:|mailto:)/i

function pieces(p: Element): Piece[] {
  const out: Piece[] = []
  p.childNodes.forEach((node) => {
    const text = node.textContent ?? ''
    if (!text) return
    const href = node instanceof Element && node.tagName === 'A' ? node.getAttribute('href') : null
    if (href && SAFE_HREF.test(href)) out.push({ text, href })
    else out.push({ text })
  })
  return out
}

// Each h2 is a question; the elements after it, up to the next h2, are its answer.
function readFaq(raw: string): FaqItem[] {
  const doc = new DOMParser().parseFromString(raw, 'text/html')
  const items: FaqItem[] = []
  let current: FaqItem | null = null
  for (const el of Array.from(doc.body.children)) {
    if (el.tagName === 'H2') {
      current = { question: (el.textContent ?? '').trim(), paragraphs: [], haystack: '' }
      items.push(current)
    } else if (current && el.tagName === 'P') {
      current.paragraphs.push(pieces(el))
    }
  }
  items.forEach((item) => {
    const answer = item.paragraphs.map((p) => p.map((piece) => piece.text).join('')).join(' ')
    item.haystack = `${item.question} ${answer}`.toLowerCase()
  })
  return items
}

// ---------------------------------------------------------------------------
// Load -- fetch -> parse -> the list
// ---------------------------------------------------------------------------

const loading = ref<boolean>(false)
const errored = ref<boolean>(false)
const items = ref<FaqItem[]>([])

// Monotonic guard: two overlapping load()s are reachable by double-tapping
// Retry or by switching the language while one is in flight. Only the latest
// one may write the list, and a failing later load never replaces a FAQ the
// user is already reading with an error screen.
let loadEpoch = 0

async function load(): Promise<void> {
  const mine = ++loadEpoch
  loading.value = true
  errored.value = false

  let next: FaqItem[] | null = null
  try {
    const lang = resolveFaqLocale(locale.value)
    const resp = await fetch(`${import.meta.env.BASE_URL}faq/${lang}/company.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    next = readFaq(await resp.text())
  } catch {
    if (mine === loadEpoch) {
      errored.value = true
    }
  } finally {
    if (mine === loadEpoch) {
      loading.value = false
    }
  }

  if (mine !== loadEpoch || next === null) return
  items.value = next
}

// The language switcher lives in the header, which is rendered on this very
// page -- so a user can change locale without navigating, and nothing
// would re-fetch. Refetch on locale change; the epoch guard above makes an
// in-flight load safe to supersede.
watch(locale, () => {
  void load()
})

onMounted(() => {
  void load()
})

onUnmounted(() => {
  // Invalidate any in-flight load so it cannot revive state on a dead component.
  loadEpoch += 1
})

// ---------------------------------------------------------------------------
// The search: the items whose question or answer contains the typed words
// ---------------------------------------------------------------------------

const query = ref<string>('')
const needle = computed(() => query.value.trim().toLowerCase())

function matches(item: FaqItem): boolean {
  return !needle.value || item.haystack.includes(needle.value)
}
const shown = computed(() => items.value.filter(matches).length)

// The frame's header carries the title and the way back to Settings.
useScreenHeader({
  title: () => t('comp.faq.title'),
  back: '/company/settings',
})
</script>

<template>
  <!-- Loading -->
  <div v-if="loading" class="ds-empty" aria-busy="true">
    <CLoader />
  </div>

  <!-- Error -->
  <CEmptyState v-else-if="errored" tone="danger" :title="t('comp.faq.errorTitle')">
    <template #actions>
      <CButton variant="outline" size="sm" inline @click="load">
        {{ t('comp.faq.errorRetry') }}
      </CButton>
    </template>
  </CEmptyState>

  <!-- Loaded: the search and the accordion (K27, the FAQ form) -->
  <template v-else-if="items.length > 0">
    <div class="ds-field ds-accordion__search">
      <label class="ds-field__label" for="cfaq-search">{{ t('common.search') }}</label>
      <input
        id="cfaq-search"
        v-model="query"
        class="ds-input"
        type="search"
        aria-controls="cfaq-list"
      />
    </div>
    <div id="cfaq-list" class="ds-accordion ds-accordion--faq">
      <details
        v-for="(item, index) in items"
        :key="index"
        class="ds-accordion__item"
        name="cfaq"
        :hidden="!matches(item)"
      >
        <summary class="ds-accordion__summary">
          <span>{{ item.question }}</span>
          <ChevronDown class="ds-accordion__chev" />
        </summary>
        <div class="ds-accordion__panel">
          <p v-for="(paragraph, p) in item.paragraphs" :key="p">
            <template v-for="(piece, k) in paragraph" :key="k">
              <a v-if="piece.href" :href="piece.href" target="_blank" rel="noopener">{{
                piece.text
              }}</a>
              <template v-else>{{ piece.text }}</template>
            </template>
          </p>
        </div>
      </details>
    </div>
    <p class="ds-accordion__none" :hidden="shown !== 0" role="status">
      {{ t('common.noResults') }}
    </p>
  </template>
</template>
