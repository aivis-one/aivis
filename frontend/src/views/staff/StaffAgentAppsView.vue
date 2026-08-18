<script setup lang="ts">
// Staff agent applications — pending queue with approve/reject.
// GET /api/v1/staff/agent-applications → AgentApplicationResponse[]
// POST /api/v1/staff/agent-applications/{id}/approve → 204
// POST /api/v1/staff/agent-applications/{id}/reject → 204

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Check, X } from 'lucide-vue-next'
import { CAvatar, CLoader, CButton, CEmptyState, CModal, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { fetchAgentApplications, approveAgentApplication, rejectAgentApplication } from '@/api/admin'
import type { AgentApplicationResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()

const items = ref<AgentApplicationResponse[]>([])
const loading = ref(true)
const error = ref(false)

// Double-submit guard.
const processingIds = ref<Set<string>>(new Set())

// Reject modal.
const showRejectModal = ref(false)
const rejectTarget = ref<AgentApplicationResponse | null>(null)
const rejectReason = ref('')
const rejectLoading = ref(false)

async function loadQueue(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    items.value = await fetchAgentApplications()
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function handleApprove(item: AgentApplicationResponse): Promise<void> {
  if (processingIds.value.has(item.id)) return
  processingIds.value.add(item.id)
  try {
    await approveAgentApplication(item.id)
    showToast(t('staff.agentApps2.approved'), 'success')
    items.value = items.value.filter(i => i.id !== item.id)
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(item.id)
  }
}

function openReject(item: AgentApplicationResponse): void {
  rejectTarget.value = item
  rejectReason.value = ''
  showRejectModal.value = true
}

async function handleReject(): Promise<void> {
  if (!rejectTarget.value || !rejectReason.value.trim()) return
  const id = rejectTarget.value.id
  if (processingIds.value.has(id)) return
  processingIds.value.add(id)
  rejectLoading.value = true
  try {
    await rejectAgentApplication(id, { reason: rejectReason.value })
    showToast(t('staff.agentApps2.rejected'), 'success')
    items.value = items.value.filter(i => i.id !== id)
    showRejectModal.value = false
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    processingIds.value.delete(id)
    rejectLoading.value = false
  }
}

onMounted(loadQueue)
</script>

<template>
  <div class="staff-apps">
    <!-- Hint -->
    <div class="staff-apps__hint">
      <FileText :size="16" />
      {{ t('staff.agentApps2.hint') }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="staff-apps__center">
      <CLoader :size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="staff-apps__center">
      <CButton variant="secondary" size="sm" @click="loadQueue">{{ t('common.retry') }}</CButton>
    </div>

    <!-- Empty -->
    <CEmptyState v-else-if="!items.length" :title="t('staff.agentApps2.noQueue')">
      <template #icon><FileText :size="40" /></template>
    </CEmptyState>

    <!-- Queue -->
    <div v-else class="apps-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="app-item"
      >
        <CAvatar :name="item.user_id.slice(0, 8)" :size="40" />
        <div class="app-item__info">
          <div class="app-item__name">{{ item.user_id.slice(0, 8) }}…</div>
          <div class="app-item__detail">
            {{ item.status }} &bull;
            {{ new Date(item.created_at).toLocaleDateString() }}
          </div>
        </div>
        <div class="app-item__actions">
          <button
            class="app-btn app-btn--approve"
            :disabled="processingIds.has(item.id)"
            @click.stop="handleApprove(item)"
          >
            <Check :size="16" />
          </button>
          <button
            class="app-btn app-btn--reject"
            :disabled="processingIds.has(item.id)"
            @click.stop="openReject(item)"
          >
            <X :size="16" />
          </button>
        </div>
      </div>
    </div>

    <!-- Reject modal -->
    <CModal :open="showRejectModal" @close="showRejectModal = false">
      <h3 class="reject__title">{{ t('staff.agentApps2.reject') }}</h3>
      <CInput
        v-model="rejectReason"
        :label="t('staff.agentApps2.rejectReason')"
        :placeholder="t('staff.agentApps2.rejectReason')"
      />
      <div class="reject__actions">
        <CButton variant="outline" size="sm" @click="showRejectModal = false">{{ t('common.cancel') }}</CButton>
        <CButton
          variant="danger" size="sm"
          :loading="rejectLoading"
          :disabled="!rejectReason.trim()"
          @click="handleReject"
        >{{ t('staff.agentApps2.reject') }}</CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-apps { padding: 16px; }

.staff-apps__hint {
  display: flex; align-items: center; gap: 8px;
  padding: 12px; background: var(--bg-surface, var(--bg-subtle)); border-radius: var(--radius-md);
  margin-bottom: 16px; font-size: 12px; color: var(--text-secondary);
}

.staff-apps__center {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px; gap: 16px;
}

.apps-list { display: flex; flex-direction: column; }
.app-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 0;
  border-bottom: 1px solid var(--border-default);
}
.app-item__info { flex: 1; min-width: 0; }
.app-item__name { font-size: 14px; font-weight: 600; color: var(--text-primary); font-family: monospace; }
.app-item__detail { font-size: 12px; color: var(--text-tertiary); text-transform: capitalize; }
.app-item__actions { display: flex; gap: 4px; flex-shrink: 0; }

.app-btn {
  width: 32px; height: 32px; border-radius: var(--radius-sm); border: none;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  transition: opacity 0.2s;
}
.app-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.app-btn--approve { background: var(--success); color: var(--on-success); }
.app-btn--approve:hover:not(:disabled) { opacity: 0.9; }
.app-btn--reject { background: var(--danger); color: var(--on-danger); }
.app-btn--reject:hover:not(:disabled) { opacity: 0.9; }

.reject__title { font-size: 18px; font-weight: 700; color: var(--text-primary); margin: 0 0 16px; }
.reject__actions { display: flex; gap: 8px; margin-top: 16px; }
</style>
