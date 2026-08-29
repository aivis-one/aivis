<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorFaqView (TASK-39 item 3, FAQ framework)
// =============================================================================
//
// Static FAQ page for investor + representative (agent) -- ONE shared
// file set, ONE shared view, mounted at /investor/faq (route name
// investor-faq) AND /agent/faq (route name agent-faq). Reached from
// the FAQ tile in InvestorMoreView / AgentMoreView. Same "shared
// component lives physically under views/investor/, other shells'
// route records import it directly" convention as InvestorSupportView
// / PortfolioView / InstallmentPlansView / NotificationsInboxView.
//
// OWNER RULING (TASK-39 item 3, verbatim intent):
//   1. Static HTML per locale, following the EXISTING legal-document
//      pattern -- see InvestorDocsView.vue's header comment for the
//      full incident history. Same security model here: fetch the
//      file, wrap the response in a Blob(text/html), URL.
//      createObjectURL -> iframe src, sandbox="" (empty value
//      forbids scripts, forms, same-origin access, navigation and
//      storage), revoke-before-overwrite plus a final revoke on
//      unmount. NOT v-html -- a v-html render gives the mounted node
//      full access to the SPA origin (localStorage, auth token).
//   2. Two audiences, and that is the whole information architecture:
//      investor + agent SHARE this one FAQ; company gets its OWN,
//      SEPARATE FAQ (CompanyFaqView.vue, its own file set under
//      /faq/{lang}/company.html -- a company's questions are not an
//      investor's). Staff/admin gets NO FAQ at all: no staff route,
//      tile, or file exists for it, and none should be added here.
//   3. CONTENT IS NOT WANTED YET. /faq/{lang}/investor.html is a
//      PLACEHOLDER, marked "not written yet" both as a visible
//      in-page notice and an HTML comment. This view renders
//      whatever that static file says, sandboxed, and invents
//      nothing -- no FAQ copy lives in this component.
//
// LOCALE FALLBACK.
//   FAQ content exists for `en` and `ru` only -- `de`/`ar` are parked
//   per the owner's ruling; no files exist for them and none should
//   be added. FAQ_LOCALES below is deliberately its own constant,
//   narrower than i18n's SUPPORTED_LOCALES (which also lists de/ar
//   for the rest of the UI) -- do not swap this for
//   isSupportedLocale(). resolveFaqLocale() maps any UI locale
//   outside {en, ru} to `en`. Unlike the legal-docs flow (where the
//   backend resolves user_language with an `en` fallback before the
//   frontend ever sees a row), there is no backend involved here at
//   all -- this resolution is entirely client-side, which is why it
//   is written out explicitly rather than assumed.
//
// PATH SAFETY.
//   The only path segment derived from user/runtime state is the
//   locale. resolveFaqLocale() narrows it to the literal union
//   'en' | 'ru' BEFORE it reaches the fetch URL, so an unrecognised
//   or malformed locale value can never reach fetch() -- it is
//   mapped to 'en' first, same defensive posture as InvestorDocsView's
//   SAFE_TOKEN guard on doc.type/doc.language, just enforced by the
//   TypeScript union instead of a regex since the value space here is
//   two literals, not open-ended backend strings. The audience
//   segment ("investor") is a hardcoded string literal in this file,
//   never interpolated from a variable, so it carries none of the
//   injection surface doc.type/doc.language have in InvestorDocsView.
//
// NO LIST, NO MODAL. InvestorDocsView renders many rows behind a list
// + detail modal; FAQ is one static page per audience, so this view
// fetches straight into a page-level iframe (loading / error / body),
// no modal at all. Blob URL lifecycle mirrors InvestorDocsView, epoch guard included:
// revoke-before-overwrite on each load() call, final revoke on
// unmount.
// =============================================================================

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { CBackLink, CButton, CEmptyState, CLoader } from '@/components/ui'
import { safeNavigate } from '@/composables/safeNavigate'
import { getShell } from '@/router/helpers'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

// FAQ content exists for these locales only -- see header note. Kept
// separate from i18n's SUPPORTED_LOCALES on purpose: that list also
// carries `de`/`ar`, which are explicitly parked for FAQ content.
const FAQ_LOCALES = ['en', 'ru'] as const
type FaqLocale = (typeof FAQ_LOCALES)[number]

function resolveFaqLocale(value: string): FaqLocale {
  return (FAQ_LOCALES as readonly string[]).includes(value) ? (value as FaqLocale) : 'en'
}

// ---------------------------------------------------------------------------
// Blob lifecycle -- fetch -> Blob(text/html) -> object URL -> sandboxed iframe
// ---------------------------------------------------------------------------

const loading = ref<boolean>(false)
const errored = ref<boolean>(false)
const blobUrl = ref<string | null>(null)

// Monotonic guard, the half of InvestorDocsView's blob lifecycle this
// view originally left out. Two overlapping load()s are reachable by
// double-tapping Retry before the first resolves: without this, the
// loser's object URL is overwritten and never revoked (a real leak),
// and a failing second load would null blobUrl and replace a FAQ the
// user was already reading with an error screen.
let loadEpoch = 0

function revokeBlob(): void {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = null
  }
}

async function load(): Promise<void> {
  const mine = ++loadEpoch
  loading.value = true
  errored.value = false
  revokeBlob()

  let nextUrl: string | null = null
  try {
    const lang = resolveFaqLocale(locale.value)
    const resp = await fetch(`/faq/${lang}/investor.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
    // Wrap the raw HTML in a text/html blob so the iframe renders it
    // as a standalone document. No DOMParser/innerHTML trickery --
    // the iframe is sandboxed so the document chrome is harmless.
    const blob = new Blob([raw], { type: 'text/html' })
    nextUrl = URL.createObjectURL(blob)
  } catch {
    if (mine === loadEpoch) {
      errored.value = true
    }
  } finally {
    if (mine === loadEpoch) {
      loading.value = false
    }
  }

  if (mine !== loadEpoch) {
    // Superseded while in flight: drop OUR blob rather than
    // overwriting (and orphaning) the winner's.
    if (nextUrl) {
      URL.revokeObjectURL(nextUrl)
    }
    return
  }
  blobUrl.value = nextUrl
}

// The language switcher lives in CHeader, which is rendered on this very
// page -- so a user can change locale without navigating, and nothing
// would re-fetch. The chrome would flip language while the iframe kept
// showing the previous locale's document. Refetch on locale change; the
// epoch guard above makes an in-flight load safe to supersede.
watch(locale, () => {
  void load()
})

onMounted(() => {
  void load()
})

onUnmounted(() => {
  // Invalidate any in-flight load so it cannot revive state on a
  // dead component or strand its blob.
  loadEpoch += 1
  revokeBlob()
})

// ---------------------------------------------------------------------------
// Back navigation -- reached from a More-tab tile, drill-down (not a
// top-level tab), same shell-aware fallback InvestorSupportView uses
// since this view is also mounted under two shells.
// ---------------------------------------------------------------------------

const backFallbackRouteName = computed<string>(() => {
  return getShell(route) === 'agent' ? 'agent-more' : 'investor-more'
})

function goBack(): void {
  if (window.history.state?.back) {
    router.back()
    return
  }
  void safeNavigate(router.push({ name: backFallbackRouteName.value }), '[InvestorFaqView] back')
}
</script>

<template>
  <div class="faq">
    <div class="faq__back-row">
      <CBackLink :label="t('common.back')" @click="goBack" />
    </div>

    <header class="faq__header">
      <h1 class="faq__title">
        {{ t('inv.faq.title') }}
      </h1>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="faq__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="faq__center">
      <CEmptyState :title="t('inv.faq.errorTitle')" />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('inv.faq.errorRetry') }}
      </CButton>
    </div>

    <!--
      Loaded body. Rendered in a sandboxed iframe via blob URL,
      mirroring InvestorDocsView / CertificateSheet.vue. `sandbox=""`
      (empty value) forbids scripts, forms, same-origin access,
      navigation, and storage. FAQ content is static text -- none of
      those are needed.
    -->
    <iframe
      v-else-if="blobUrl"
      :src="blobUrl"
      sandbox=""
      class="faq__iframe"
      :title="t('inv.faq.title')"
    />
  </div>
</template>

<style scoped>
.faq {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.faq__back-row {
  padding: var(--space-4) var(--space-4) 0;
}

.faq__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4) var(--space-2);
}
.faq__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.faq__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.faq__iframe {
  height: 65vh;
  height: 65dvh;
  margin: 0 var(--space-4);
  width: calc(100% - var(--space-4) * 2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: #fff;
}
</style>
