<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- AgentHubView (Task 2 Block B, Phase F6.1)
// =============================================================================
//
// Replaces the F2.2 stub. The agent's referral workspace:
//   - aggregate funnel stats card (links -> clicks -> registrations ->
//     purchases -> commission), GET /referrals/stats/me
//   - "Create link" CTA, POST /referrals/links -- the new link is
//     prepended by the store (no refetch, no double request)
//   - paginated link list, GET /referrals/links/me -- each card shows
//     the code, is_active state, the full share URL with
//     copy-to-clipboard, and the three per-link counters
//
// FP notes:
//   FP-19 -- no CHeader render here; the shell owns the header. The
//            screen title is the inline hub__header h1 (same mechanism
//            as InvestorDashboardView).
//   FP-25 -- self-hiding: zero links renders a single CEmptyState, no
//            placeholder scaffolding.
//   FP-04 -- double-submit guard on the create button (local
//            `creating` flag flipped before any await).
//   FP-26 -- common.statusActive / common.retry reused; agent-domain
//            texts live under agent.hub.*.
//
// SHARE URL.
//   `${window.location.origin}/r/${code}` -- the /r/:code capture
//   route lives on this very frontend origin, so the share link is
//   correct by construction (no VITE public-URL indirection needed;
//   VITE_API_BASE_URL is the API host, not the share host).
//
// PAGINATION.
//   Explicit "Load more" button over the store's
//   fetchLinksFirstPage/loadMoreLinks/hasMoreLinks trio. An agent's
//   link list is short by nature (tens, not thousands); a scroll
//   sentinel would be ceremony here.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Copy, Link2, Plus } from 'lucide-vue-next'

import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useAgentStore } from '@/stores/agent'
import { useToast } from '@/composables/useToast'
import { formatNumber, formatPrice } from '@/utils/format'
import type { ReferralLinkResponse } from '@/api/types'

const { t, locale } = useI18n()
const { showToast } = useToast()
const agentStore = useAgentStore()

// FP-04: double-submit guard for the create CTA.
const creating = ref(false)

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const statsLoaded = computed(() => !agentStore.statsLoading && agentStore.stats !== null)

const linksEmpty = computed(
  () => !agentStore.linksLoading && !agentStore.linksError && agentStore.links.length === 0,
)

function shareUrl(link: ReferralLinkResponse): string {
  return `${window.location.origin}/r/${link.code}`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value)
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function handleCreate(): Promise<void> {
  if (creating.value) return
  creating.value = true
  try {
    await agentStore.createLink()
    showToast(t('agent.hub.created'), 'success')
  } catch {
    showToast(t('agent.hub.createError'), 'error')
  } finally {
    creating.value = false
  }
}

async function handleCopy(link: ReferralLinkResponse): Promise<void> {
  try {
    await navigator.clipboard.writeText(shareUrl(link))
    showToast(t('agent.hub.link.copied'), 'success')
  } catch {
    // Clipboard API can be unavailable (insecure context, permissions).
    showToast(t('agent.hub.link.copyError'), 'error')
  }
}

function retryStats(): void {
  void agentStore.fetchStats()
}

function retryLinks(): void {
  void agentStore.fetchLinksFirstPage()
}

function loadMore(): void {
  void agentStore.loadMoreLinks()
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  // Two independent probes in parallel; both are never-throw.
  void agentStore.fetchStats()
  void agentStore.fetchLinksFirstPage()
})
</script>

<template>
  <div class="hub">
    <!-- Screen title (FP-19: shell owns CHeader, view owns the h1) -->
    <div class="hub__header">
      <h1 class="hub__title">
        {{ t('agent.hub.title') }}
      </h1>
      <p class="hub__subtitle">
        {{ t('agent.hub.subtitle') }}
      </p>
    </div>

    <!-- Aggregate funnel stats -->
    <section class="hub__stats">
      <div v-if="agentStore.statsLoading" class="hub__center">
        <CLoader :size="24" />
      </div>

      <div v-else-if="agentStore.statsError" class="hub__center">
        <CEmptyState :title="t('agent.hub.stats.errorTitle')">
          <CButton variant="secondary" @click="retryStats">
            {{ t('common.retry') }}
          </CButton>
        </CEmptyState>
      </div>

      <div v-else-if="statsLoaded" class="hub__stats-grid">
        <div class="hub__stat">
          <div class="hub__stat-value">
            {{ formatNumber(agentStore.stats!.total_links, locale) }}
          </div>
          <div class="hub__stat-label">
            {{ t('agent.hub.stats.links') }}
          </div>
        </div>
        <div class="hub__stat">
          <div class="hub__stat-value">
            {{ formatNumber(agentStore.stats!.total_clicks, locale) }}
          </div>
          <div class="hub__stat-label">
            {{ t('agent.hub.stats.clicks') }}
          </div>
        </div>
        <div class="hub__stat">
          <div class="hub__stat-value">
            {{ formatNumber(agentStore.stats!.total_registrations, locale) }}
          </div>
          <div class="hub__stat-label">
            {{ t('agent.hub.stats.registrations') }}
          </div>
        </div>
        <div class="hub__stat">
          <div class="hub__stat-value">
            {{ formatNumber(agentStore.stats!.total_purchases, locale) }}
          </div>
          <div class="hub__stat-label">
            {{ t('agent.hub.stats.purchases') }}
          </div>
        </div>
        <div class="hub__stat hub__stat--wide">
          <div class="hub__stat-value">
            {{ formatPrice(agentStore.stats!.total_commission_cents) }}
          </div>
          <div class="hub__stat-label">
            {{ t('agent.hub.stats.commission') }}
          </div>
        </div>
      </div>
    </section>

    <!-- Create-link CTA (FP-04 guard via `creating`) -->
    <div class="hub__create">
      <CButton :disabled="creating" @click="handleCreate">
        <Plus :size="16" />
        {{ t('agent.hub.createLink') }}
      </CButton>
    </div>

    <!-- Link list -->
    <section class="hub__links">
      <h2 class="hub__links-title">
        {{ t('agent.hub.links.title') }}
      </h2>

      <div v-if="agentStore.linksLoading && agentStore.links.length === 0" class="hub__center">
        <CLoader :size="24" />
      </div>

      <div v-else-if="agentStore.linksError && agentStore.links.length === 0" class="hub__center">
        <CEmptyState :title="t('agent.hub.links.errorTitle')">
          <CButton variant="secondary" @click="retryLinks">
            {{ t('common.retry') }}
          </CButton>
        </CEmptyState>
      </div>

      <!-- FP-25: self-hiding empty state, no placeholder scaffolding -->
      <div v-else-if="linksEmpty" class="hub__center">
        <CEmptyState
          :title="t('agent.hub.links.empty.title')"
          :description="t('agent.hub.links.empty.desc')"
        />
      </div>

      <ul v-else class="hub__list">
        <li v-for="link in agentStore.links" :key="link.id" class="hub__card">
          <div class="hub__card-head">
            <span class="hub__card-code">
              <Link2 :size="16" class="hub__card-code-icon" />
              {{ link.code }}
            </span>
            <span
              class="hub__card-state"
              :class="link.is_active ? 'hub__card-state--active' : 'hub__card-state--inactive'"
            >
              {{ link.is_active ? t('common.statusActive') : t('agent.hub.link.inactive') }}
            </span>
          </div>

          <div class="hub__card-share">
            <span class="hub__card-url">{{ shareUrl(link) }}</span>
            <button
              type="button"
              class="hub__card-copy"
              :aria-label="t('agent.hub.link.copy')"
              @click="handleCopy(link)"
            >
              <Copy :size="16" />
            </button>
          </div>

          <div class="hub__card-counters">
            <div class="hub__counter">
              <span class="hub__counter-value">
                {{ formatNumber(link.click_count, locale) }}
              </span>
              <span class="hub__counter-label">
                {{ t('agent.hub.link.clicks') }}
              </span>
            </div>
            <div class="hub__counter">
              <span class="hub__counter-value">
                {{ formatNumber(link.registration_count, locale) }}
              </span>
              <span class="hub__counter-label">
                {{ t('agent.hub.link.registrations') }}
              </span>
            </div>
            <div class="hub__counter">
              <span class="hub__counter-value">
                {{ formatNumber(link.purchase_count, locale) }}
              </span>
              <span class="hub__counter-label">
                {{ t('agent.hub.link.purchases') }}
              </span>
            </div>
          </div>

          <div class="hub__card-meta">
            {{ t('agent.hub.link.createdAt') }} {{ formatDate(link.created_at) }}
          </div>
        </li>
      </ul>

      <div v-if="agentStore.hasMoreLinks && !linksEmpty" class="hub__more">
        <CButton variant="secondary" :disabled="agentStore.linksLoading" @click="loadMore">
          {{ t('agent.hub.links.loadMore') }}
        </CButton>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hub {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.hub__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.hub__title {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.hub__subtitle {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0;
}

.hub__center {
  display: flex;
  justify-content: center;
  padding: var(--space-5) 0;
}

/* -- Stats card -- */

.hub__stats {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.hub__stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
}

.hub__stat--wide {
  grid-column: 1 / -1;
}

.hub__stat-value {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

.hub__stat-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

/* -- Create CTA -- */

.hub__create {
  display: flex;
}

/* -- Links list -- */

.hub__links-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}

.hub__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.hub__card {
  background: var(--surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.hub__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hub__card-code {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.hub__card-code-icon {
  color: var(--text-tertiary);
}

.hub__card-state {
  font-size: var(--fs-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}

.hub__card-state--active {
  background: var(--success-subtle);
  color: var(--success);
}

.hub__card-state--inactive {
  background: var(--bg-surface);
  color: var(--text-tertiary);
}

.hub__card-share {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
}

.hub__card-url {
  flex: 1;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hub__card-copy {
  background: none;
  border: none;
  padding: var(--space-1);
  color: var(--primary);
  cursor: pointer;
  display: inline-flex;
}

.hub__card-counters {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
}

.hub__counter {
  display: flex;
  flex-direction: column;
}

.hub__counter-value {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.hub__counter-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.hub__card-meta {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.hub__more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-3);
}

/* TILE CEILING — a grid authored `repeat(N, 1fr)` keeps N columns at every
   width, so on a 1016px desktop it stretches its contents to fill: measured,
   a stat tile reached 316px and an action button 497px. Past a point the extra
   room should be whitespace, not wider furniture.

   The COLUMN COUNT IS DELIBERATELY UNCHANGED. Only the ceiling is added, so
   nothing reflows and no set of related figures can wrap into a ragged 2+1.
   An earlier attempt used auto-fit and did exactly that: the cap, not a lack
   of room, was what pushed the third tile onto its own line. Mobile-first, so
   this is a min-width and the phone is untouched. */
@media (min-width: 820px) {
  .hub__stats-grid {
    max-width: calc(2 * var(--tile-max));
  }
  .hub__card-counters {
    max-width: calc(3 * var(--tile-max));
  }
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.hub__subtitle {
  max-width: var(--maxw-prose);
}

/* A5: this control is deliberately 24px to sit right in its row, so the PAINTED
   box stays and the HIT AREA is expanded past it instead. The overlay is
   invisible, centred, and never smaller than the tap floor; clicks land on the
   button because the pseudo-element belongs to it. */
.hub__card-copy {
  position: relative;
}
.hub__card-copy::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: var(--tap-min);
  height: var(--tap-min);
  transform: translate(-50%, -50%);
}
</style>
