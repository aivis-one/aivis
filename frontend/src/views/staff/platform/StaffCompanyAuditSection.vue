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
import { CLoader, CButton, CEmptyState, CBadge } from '@/components/ui'
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
const page = ref(1)
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
    <h3 class="scau__title">
      {{ t('staff.platform.audit.title') }}
    </h3>

    <div v-if="loading" class="scau__center">
      <CLoader :size="28" />
    </div>

    <div v-else-if="error" class="scau__center">
      <CButton variant="secondary" size="sm" @click="loadFeed">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <CEmptyState v-else-if="!entries.length" :title="t('staff.platform.audit.empty')" />

    <template v-else>
      <ul class="audit-feed">
        <li v-for="entry in entries" :key="entry.id" class="audit-feed__row">
          <div class="audit-feed__head">
            <span class="audit-feed__event">{{ entry.event }}</span>
            <!-- FP-25 self-hide: only staff-on-behalf writes carry performed_by. -->
            <CBadge
              v-if="entry.performed_by"
              variant="neutral"
              :text="t('staff.platform.audit.viaAvatar')"
            />
            <span class="audit-feed__date">{{ formatDateTime(entry.created_at) }}</span>
          </div>
          <pre class="audit-feed__data">{{ formatData(entry.data) }}</pre>
        </li>
      </ul>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="scau__pagination">
        <CButton variant="outline" size="sm" :disabled="page <= 1" @click="page--">
          &larr;
        </CButton>
        <span class="scau__page">{{ page }} / {{ totalPages }}</span>
        <CButton variant="outline" size="sm" :disabled="page >= totalPages" @click="page++">
          &rarr;
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.scau {
  padding: var(--space-4);
}

.scau__title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}

.scau__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-sm);
  gap: var(--space-4);
}

.audit-feed {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}
.audit-feed__row {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}
.audit-feed__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}
.audit-feed__event {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}
.audit-feed__date {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin-left: auto;
}
.audit-feed__data {
  margin: 0;
  padding: var(--space-2);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.scau__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
.scau__page {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
</style>
