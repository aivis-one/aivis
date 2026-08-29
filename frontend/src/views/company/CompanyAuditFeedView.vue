<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CompanyAuditFeedView (TASK-39 item 7)
// =============================================================================
//
// Read-only, newest-first feed of the caller's OWN company (project)
// write history -- who touched the project and roughly what area
// changed, without exposing WHO on staff did it or WHAT value it
// changed to. Reached from a row inside CompanySettingsView (no
// company_id in the URL, no company picker anywhere -- the backend
// forces the caller's own company_id server-side via
// get_current_company_profile, see api/company-audit.ts's header),
// same "no dead 6th tab-bar slot" placement reasoning as the
// Roadmap/Posts/Attachments/Notifications/Support rows already there
// (CompanyShell has no More tab, COMPANY_TABS has 5 fixed slots).
//
// NOT the staff feed. StaffCompanyAuditSection.vue (staff shell) shows
// EVERY field of CompanyAuditEntryResponse, including actor_id /
// performed_by / on_behalf_of and the raw `data` blob, because staff
// is allowed to know which admin did what. This screen consumes
// CompanySelfAuditEntryResponse instead -- a deliberately narrower
// shape with only id / event / created_at / actor_type /
// changed_fields. There is no `data` here to render even if we wanted
// to: the backend never sends it. See backend/app/modules/audit/
// schemas.py for the full reasoning (in particular why a
// company.price_updated row always renders with an empty
// changed_fields list -- price visibility is a parked product
// question this screen must not decide either way).
//
// EVENT / FIELD LABELS: `event` ("company.self_updated") and each
// entry of `changed_fields` ("description", "logo_url", ...) are raw
// backend tokens, not something to show verbatim to a non-technical
// company user. eventLabel()/fieldLabel() below map known tokens to
// i18n labels via tOrRaw (frontend/src/utils/i18n.ts) with a
// humanised-snake_case fallback for anything not yet in the
// catalogue -- same pattern TransactionDetailSheet.keyLabel already
// uses for the same "server-driven token, translate or humanise"
// problem.
//
// LOADING / ERROR / EMPTY TAXONOMY: copied verbatim from
// InstallmentPlansView.vue (itself matching PortfolioView /
// NotificationsInboxView) -- first-load spinner while items.length
// === 0 and no error yet; error state (CEmptyState + retry) when the
// first load failed; empty state (CEmptyState, no CTA -- there is
// nothing else to navigate to from an empty history) when the load
// succeeded with zero rows; populated state renders the list plus an
// infinite-scroll sentinel / load-more-error row underneath.
//
// PAGINATION: page/per_page (matches the backend's plain offset
// pagination, GET /api/v1/company/audit?page=&per_page=) via
// composables/usePagination's useInfiniteScroll, same stale-fetch
// epoch guard as InstallmentPlansView.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ArrowLeft, History } from 'lucide-vue-next'
import { CEmptyState, CLoader, CButton } from '@/components/ui'
import { useInfiniteScroll } from '@/composables/usePagination'
import { fetchOwnAuditFeed } from '@/api/company-audit'
import { formatDateTime } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { CompanySelfAuditEntryResponse } from '@/api/types'

const PER_PAGE = 20

const { t, locale } = useI18n()
const router = useRouter()

// Back to Settings -- this screen has no tab-bar slot of its own
// (CompanyShell's tab bar is five fixed tabs), so Settings, where its
// entry row lives, is the only place "back" can honestly mean. Same
// shape as CompanyPostsView / CompanyRoadmapView / CompanyFaqView; this
// view shipped without one, leaving a company user who opened the audit
// feed with no in-app way back.
function goBack(): void {
  void router.push('/company/settings')
}

const items = ref<CompanySelfAuditEntryResponse[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loaded = ref(false)
const errored = ref(false)
const loadMoreErrored = ref(false)

const sentinelRef = ref<HTMLElement | null>(null)

// Stale-epoch guard -- same pattern as InstallmentPlansView /
// BalanceView payment history: a fresh fetchFirstPage invalidates any
// in-flight loadMore left over from a previous visit to this screen.
let fetchEpoch = 0

const hasMore = computed(() => items.value.length < total.value)
// See InstallmentPlansView's identical comment: `loaded` alone stays
// true after a FAILED first load, so isEmpty must also check
// !loading/!errored to avoid flashing the empty state mid-retry.
const isEmpty = computed(
  () => loaded.value && !loading.value && !errored.value && items.value.length === 0,
)

// ---------------------------------------------------------------------------
// Event / actor / field label mapping
// ---------------------------------------------------------------------------

function humanise(token: string): string {
  // 'company.self_updated' -> 'Self Updated' (drop the constant
  // "company." prefix -- every event on this feed is target_type=
  // "company", so it adds nothing) / 'logo_url' -> 'Logo Url'.
  const withoutPrefix = token.startsWith('company.') ? token.slice('company.'.length) : token
  return withoutPrefix.replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function eventLabel(event: string): string {
  return tOrRaw(t, `comp.auditFeed.event.${event}`, humanise(event))
}

function fieldLabel(field: string): string {
  return tOrRaw(t, `comp.auditFeed.field.${field}`, humanise(field))
}

function actorLabel(actorType: string): string {
  return tOrRaw(t, `comp.auditFeed.actor.${actorType}`, humanise(actorType))
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function fetchFirstPage(): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  try {
    const resp = await fetchOwnAuditFeed({ page: 1, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = resp.items
    total.value = resp.total
    page.value = 1
    loaded.value = true
  } catch {
    if (epoch !== fetchEpoch) return
    errored.value = true
    loaded.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

async function loadMore(): Promise<void> {
  if (loading.value || !hasMore.value) return
  const epoch = ++fetchEpoch
  loading.value = true
  loadMoreErrored.value = false
  try {
    const nextPage = page.value + 1
    const resp = await fetchOwnAuditFeed({ page: nextPage, per_page: PER_PAGE })
    if (epoch !== fetchEpoch) return
    items.value = [...items.value, ...resp.items]
    total.value = resp.total
    page.value = nextPage
  } catch {
    if (epoch !== fetchEpoch) return
    // Non-destructive: keep already-loaded pages visible, surface a
    // retry row instead (same brake as InstallmentPlansView).
    loadMoreErrored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

function retryLoadMore(): void {
  loadMoreErrored.value = false
  void loadMore()
}

useInfiniteScroll(sentinelRef, hasMore, loadMore, loadMoreErrored)

onMounted(() => {
  void fetchFirstPage()
})
</script>

<template>
  <div class="caf">
    <div class="caf__header">
      <button type="button" class="caf__back" @click="goBack">
        <ArrowLeft :size="16" />
        {{ t('comp.settings.title') }}
      </button>
      <h1 class="caf__title">
        {{ t('comp.auditFeed.list.title') }}
      </h1>
      <p class="caf__subtitle">
        {{ t('comp.auditFeed.list.subtitle') }}
      </p>
    </div>

    <!-- Initial load spinner -->
    <div v-if="loading && items.length === 0" class="caf__center">
      <CLoader :size="28" />
    </div>

    <!-- Error (first load failed) -->
    <div v-else-if="errored && items.length === 0" class="caf__center">
      <CEmptyState :title="t('comp.auditFeed.list.errorTitle')" />
      <CButton variant="outline" size="sm" @click="fetchFirstPage">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <!-- Empty -->
    <div v-else-if="isEmpty" class="caf__center">
      <CEmptyState
        :title="t('comp.auditFeed.list.empty.title')"
        :description="t('comp.auditFeed.list.empty.description')"
      >
        <template #icon>
          <History :size="32" />
        </template>
      </CEmptyState>
    </div>

    <!-- Populated -->
    <template v-else>
      <ul class="caf__list">
        <li v-for="entry in items" :key="entry.id" class="caf__row">
          <div class="caf__row-head">
            <span class="caf__event">{{ eventLabel(entry.event) }}</span>
            <span class="caf__date">{{ formatDateTime(entry.created_at, locale) }}</span>
          </div>
          <div class="caf__row-meta">
            <span class="caf__actor">{{ actorLabel(entry.actor_type) }}</span>
            <span v-if="entry.changed_fields.length > 0" class="caf__fields">
              {{ t('comp.auditFeed.list.item.changedPrefix') }}
              {{ entry.changed_fields.map(fieldLabel).join(', ') }}
            </span>
          </div>
        </li>
      </ul>

      <!-- Infinite scroll sentinel -->
      <div ref="sentinelRef" class="caf__sentinel">
        <CLoader v-if="loading" :size="20" />
      </div>

      <div v-if="loadMoreErrored && !loading" class="caf__loadmore-error">
        <span>{{ t('comp.auditFeed.list.loadMoreError') }}</span>
        <CButton variant="outline" size="sm" @click="retryLoadMore">
          {{ t('common.retry') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.caf {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.caf__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  border: 0;
  background: none;
  padding: 0;
  margin-bottom: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
}

.caf__back:hover {
  color: var(--text-primary);
}

.caf__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.caf__title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.caf__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
  max-width: var(--maxw-prose);
}

.caf__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  min-height: var(--center-md);
  padding: var(--space-5);
}

.caf__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.caf__row {
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  border-radius: var(--radius);
  padding: var(--space-3) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.caf__row-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}
.caf__event {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.caf__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.caf__row-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1) var(--space-2);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.caf__actor {
  font-weight: 600;
  color: var(--text-secondary);
}
.caf__fields {
  color: var(--text-tertiary);
}

.caf__sentinel {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0 0;
  min-height: var(--size-md);
}

.caf__loadmore-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  margin-top: var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  text-align: center;
}
</style>
