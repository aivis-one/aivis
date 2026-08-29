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
// back-button shape as CompanyRoadmapView / CompanyPostsView /
// CompanyAttachmentsView (a single fixed target, /company/settings --
// company has no shell-switching to account for, unlike
// InvestorFaqView which is shared across two shells).
//
// OWNER RULING (TASK-39 item 3, verbatim intent) -- see
// InvestorFaqView.vue for the full ruling text. Summary as it applies
// here:
//   1. Same sandboxed-iframe security model as the legal-document
//      pattern (InvestorDocsView.vue): fetch, wrap in a
//      Blob(text/html), URL.createObjectURL -> iframe src,
//      sandbox="" (empty value forbids scripts, forms, same-origin
//      access, navigation, storage). NOT v-html.
//   2. This view is the company's OWN FAQ, deliberately not merged
//      with the investor/agent one -- a company's questions are not
//      an investor's. Staff/admin gets no FAQ; nothing here or
//      anywhere adds one.
//   3. CONTENT IS NOT WANTED YET. /faq/{lang}/company.html is a
//      PLACEHOLDER marked "not written yet" both in-page and as an
//      HTML comment. This view invents no FAQ copy.
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

import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader } from '@/components/ui'

const { t, locale } = useI18n()
const router = useRouter()

// FAQ content exists for these locales only -- see header note.
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
    const resp = await fetch(`/faq/${lang}/company.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
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

function goBack(): void {
  void router.push('/company/settings')
}
</script>

<template>
  <div class="cfaq">
    <!-- Inline page header, back link to Settings (where the entry point lives) -->
    <div class="cfaq__header">
      <button type="button" class="cfaq__back" @click="goBack">
        <ArrowLeft :size="16" />
        {{ t('comp.settings.title') }}
      </button>
      <h1 class="cfaq__page-title">
        {{ t('comp.faq.title') }}
      </h1>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="cfaq__center">
      <CLoader :size="28" />
    </div>

    <!-- Error -->
    <div v-else-if="errored" class="cfaq__center">
      <CEmptyState :title="t('comp.faq.errorTitle')" />
      <CButton variant="outline" size="sm" @click="load">
        {{ t('comp.faq.errorRetry') }}
      </CButton>
    </div>

    <!--
      Loaded body. Sandboxed iframe via blob URL -- same model as
      InvestorFaqView / InvestorDocsView / CertificateSheet.vue.
      `sandbox=""` forbids scripts, forms, same-origin access,
      navigation, and storage.
    -->
    <iframe
      v-else-if="blobUrl"
      :src="blobUrl"
      sandbox=""
      class="cfaq__iframe"
      :title="t('comp.faq.title')"
    />
  </div>
</template>

<style scoped>
.cfaq {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--space-5);
}

.cfaq__header {
  padding: var(--space-4) var(--space-4) 0;
}
.cfaq__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  padding: 0;
  margin-bottom: var(--space-3);
  cursor: pointer;
}
.cfaq__back:hover {
  color: var(--text-primary);
}
.cfaq__page-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}

.cfaq__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.cfaq__iframe {
  height: 65vh;
  height: 65dvh;
  margin: 0 var(--space-4);
  width: calc(100% - var(--space-4) * 2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: #fff;
}
</style>
