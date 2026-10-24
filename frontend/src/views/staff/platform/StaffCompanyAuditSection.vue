<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyAuditSection (TASK-30 batch 1 W3)
// =============================================================================
//
// Read-only, paginated audit feed for ONE company (project): every
// write the project made to itself, recorded server-side via
// record_audit(target_type="company"). Mirrors
// StaffCompanyPriceSection's pattern -- immutable history list, same
// loading/error/empty states, same pagination controls -- rather than
// the roadmap section's editable-modal pattern: this screen has NO
// mutation affordances of any kind (backend ruling, see
// backend/app/modules/audit/router.py module docstring). Never add
// approve/reject/acknowledge here.
//
// Source: GET /api/v1/staff/audit/companies?company_id=... (iter W3).
// Always scoped to the current route's company id -- this section
// never shows the cross-company feed (there is no UI for that yet).
//
// performed_by / on_behalf_of: when both are set, a STAFF member wrote
// this entry on the project's behalf via avatar mode (performed_by =
// the staff member, on_behalf_of = the identity they acted as). Shown
// as a small "via avatar" badge (FP-25 self-hide when performed_by is
// null -- the ordinary-write case).
//
// `data` is a free-form, event-specific JSONB blob (no fixed schema
// client-side, same posture as StaffCompanyProfileSection's
// distribution_config) -- rendered pretty-printed in a <pre> block
// rather than a designed layout.
// =============================================================================

import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CEmptyState, CBadge } from '@/components/ui'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import { fetchCompanyAuditFeed } from '@/api/staff-audit'
import type { CompanyAuditEntryResponse } from '@/api/types'

const { t } = useI18n()
const route = useRoute()

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const entries = ref<CompanyAuditEntryResponse[]>([])
const total = ref(0)
const page = useUrlPage()
const perPage = 20
const loading = ref(true)
const error = ref(false)

const totalPages = computed(() => Math.ceil(total.value / perPage))

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

// Pretty-print the event-specific data blob for read-only inspection --
// same posture as StaffCompanyProfileSection's distribution_config: a
// free-form JSONB on the backend, shown verbatim rather than assuming a
// fixed shape.
function formatData(data: Record<string, unknown>): string {
  return JSON.stringify(data, null, 2)
}

async function loadFeed(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    const resp = await fetchCompanyAuditFeed({
      company_id: id,
      page: page.value,
      per_page: perPage,
    })
    entries.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

watch(page, () => loadFeed())
watch(companyId, () => {
  page.value = 1
  void loadFeed()
})
onMounted(loadFeed)
</script>

<template>
  <div class="scau">
    <h2 class="scau__title">
      {{ t('staff.platform.audit.title') }}
    </h2>

    <CListSkeleton v-if="loading" />

    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadFeed">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState v-else-if="!entries.length" :title="t('staff.platform.audit.empty')" />

    <template v-else>
      <!-- The feed (K23 rows): the event, its time, and the event's data as read-only text -->
      <ul class="ds-rows audit-feed">
        <li v-for="entry in entries" :key="entry.id" class="ds-row audit-feed__row">
          <span class="ds-row__body">
            <span class="ds-row__title">{{ entry.event }}</span>
            <span class="ds-row__meta">{{ formatDateTime(entry.created_at) }}</span>
            <pre class="audit-feed__data">{{ formatData(entry.data) }}</pre>
          </span>
          <!-- FP-25 self-hide: only staff-on-behalf writes carry performed_by. -->
          <span v-if="entry.performed_by" class="ds-row__trail">
            <CBadge variant="neutral" :text="t('staff.platform.audit.viaAvatar')" />
          </span>
        </li>
      </ul>

      <!-- Pagination (K17) -->
      <CPager :page="page" :total-pages="totalPages" @update:page="(n: number) => (page = n)" />
    </template>
  </div>
</template>

<style scoped>
.scau {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.scau__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}

/* The event's data is a free-form blob shown verbatim: a mono block (D11). */
.audit-feed__data {
  margin: 0;
  padding: var(--space-2);
  background: var(--bg-inset);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}
</style>
