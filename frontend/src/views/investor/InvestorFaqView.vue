<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorFaqView (TASK-39 item 3, FAQ framework)
// =============================================================================
//
// FAQ page for investor + representative (agent) -- ONE shared view
// (investor.html or agent.html by route), mounted at /investor/faq (route name
// investor-faq) AND /agent/faq (route name agent-faq). Reached from
// the FAQ row of Settings. Same "shared
// component lives physically under views/investor/, other shells'
// route records import it directly" convention as InvestorSupportView
// / PortfolioView / InstallmentPlansView / NotificationsInboxView.
//
// THE FORM (decided by the owner, 2026-10-23): the FAQ is a section of the
// cabinet itself -- each question is an item of the system's Accordion (K27,
// the FAQ form: one open at a time, a search above the list), and the screen
// READS the existing FAQ files, so the judged texts keep one place and are not
// copied. A file marks each question by an h2 heading; the nodes after it up to
// the next h2 are its answer. There is no iframe.
//
// OWNER RULING (TASK-39 item 3, verbatim intent):
//   1. The text lives in static files per locale; no FAQ copy lives in this
//      component. This view renders whatever the file says and invents nothing.
//   2. Three audiences, each with its own FAQ file: investor and
//      agent share this one view but not one text (investor.html and agent.html, item 3); company gets its OWN,
//      SEPARATE FAQ (CompanyFaqView.vue, its own file set under
//      /faq/{lang}/company.html -- a company's questions are not an
//      investor's). Staff/admin gets NO FAQ at all: no staff route,
//      tile, or file exists for it, and none should be added here.
//   3. The text lives in static files: /faq/{lang}/investor.html for
//      the investor route and /faq/{lang}/agent.html for the agent
//      route (route name agent-faq).
//
// SAFETY. The file is parsed with DOMParser into a detached document (nothing
// in it runs) and only its text is kept: a question is a string, an answer is a
// list of paragraphs of text and http(s) / mailto links. The screen renders
// them with Vue's own bindings -- never v-html -- so the page's markup cannot
// reach the SPA origin (localStorage, auth token).
//
// LOCALE FALLBACK.
//   FAQ content exists for `en` and `ru` only -- `de`/`ar` are parked
//   per the owner's ruling; no files exist for them and none should
//   be added. FAQ_LOCALES below is deliberately its own constant,
//   narrower than i18n's SUPPORTED_LOCALES (which also lists de/ar
//   for the rest of the UI) -- do not swap this for
//   isSupportedLocale(). resolveFaqLocale() maps any UI locale
//   outside {en, ru} to `en`.
//
// PATH SAFETY.
//   The only path segment derived from user/runtime state is the
//   locale. resolveFaqLocale() narrows it to the literal union
//   'en' | 'ru' BEFORE it reaches the fetch URL, so an unrecognised
//   or malformed locale value can never reach fetch() -- it is
//   mapped to 'en' first. The audience segment comes from faqFile, a
//   computed typed as the literal union 'agent' | 'investor' and chosen by
//   comparing route.name, never copied from the route.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { ChevronDown } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getShell } from '@/router/helpers'

const { t, locale } = useI18n()
const route = useRoute()

// FAQ content exists for these locales only -- see header note. Kept
// separate from i18n's SUPPORTED_LOCALES on purpose: that list also
// carries `de`/`ar`, which are explicitly parked for FAQ content.
const FAQ_LOCALES = ['en', 'ru'] as const
type FaqLocale = (typeof FAQ_LOCALES)[number]

// The agent shell (route name agent-faq) has its own FAQ file; every
// other mount shows the investor one. A fixed two-value literal, never
// interpolated from the route.
const faqFile = computed<'agent' | 'investor'>(() =>
  route.name === 'agent-faq' ? 'agent' : 'investor',
)

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
    const resp = await fetch(`${import.meta.env.BASE_URL}faq/${lang}/${faqFile.value}.html`)
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

// ---------------------------------------------------------------------------
// Back navigation -- reached from a More-tab tile, drill-down (not a
// top-level tab), same shell-aware fallback InvestorSupportView uses
// since this view is also mounted under two shells.
// ---------------------------------------------------------------------------

const backFallbackRouteName = computed<string>(() => {
  return getShell(route) === 'agent' ? 'agent-settings' : 'investor-settings'
})

useScreenHeader({
  title: () => t('inv.faq.title'),
  back: () =>
    window.history.state?.back ? true : { name: backFallbackRouteName.value },
})
</script>

<template>
  <div class="faq">
    <!-- Loading -->
    <CLoader v-if="loading" />

    <!-- Error -->
    <CEmptyState v-else-if="errored" tone="danger" :title="t('inv.faq.errorTitle')">
      <template #actions>
        <CButton variant="outline" size="sm" inline @click="load">
          {{ t('inv.faq.errorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- Loaded: the search and the accordion (K27, the FAQ form) -->
    <template v-else-if="items.length > 0">
      <div class="ds-field ds-accordion__search">
        <label class="ds-field__label" for="faq-search">{{ t('common.search') }}</label>
        <input
          id="faq-search"
          v-model="query"
          class="ds-input"
          type="search"
          aria-controls="faq-list"
        />
      </div>
      <div id="faq-list" class="ds-accordion ds-accordion--faq">
        <details
          v-for="(item, index) in items"
          :key="index"
          class="ds-accordion__item"
          name="faq"
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
  </div>
</template>

<style scoped>
.faq {
  display: flex;
  flex-direction: column;
}
</style>
