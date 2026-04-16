<script setup lang="ts">
// Staff avatar mode — operate as another user for support.
// POST /api/v1/staff/avatar/start → { avatar_session_id, session_token }
// POST /api/v1/staff/avatar/end → 204
// GET /api/v1/staff/avatar/active → AvatarSessionResponse | null
//
// Token swap mechanic:
// 1. Save original staff token
// 2. Switch API client to avatar token
// 3. Show overlay banner
// 4. On "Return" → restore staff token + end session

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ghost, Ban, Shield } from 'lucide-vue-next'
import { CButton, CLoader, CInput } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { setAuthToken, getAuthToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { startAvatar, endAvatar, fetchActiveAvatar } from '@/api/admin'
import type { AvatarSessionResponse } from '@/api/types'

const { t } = useI18n()
const { showToast } = useToast()
const authStore = useAuthStore()

const targetUserId = ref('')
const loading = ref(false)
const checkingActive = ref(true)
const activeSession = ref<AvatarSessionResponse | null>(null)

// Preserved staff token for restore after avatar end.
let staffToken: string | null = null

const restrictions = [
  'staff.avatar.noPurchase',
  'staff.avatar.noWithdraw',
  'staff.avatar.noPassword',
  'staff.avatar.noDelete',
  'staff.avatar.noKyc',
] as const

async function checkActive(): Promise<void> {
  checkingActive.value = true
  try {
    activeSession.value = await fetchActiveAvatar()
  } catch {
    // No active session — fine.
    activeSession.value = null
  } finally {
    checkingActive.value = false
  }
}

async function handleStart(): Promise<void> {
  const uid = targetUserId.value.trim()
  if (!uid) return
  loading.value = true
  try {
    // Save current staff token before swap.
    staffToken = getAuthToken()

    const resp = await startAvatar(uid)
    activeSession.value = {
      id: resp.avatar_session_id,
      staff_id: authStore.user?.id ?? '',
      target_user_id: uid,
      status: 'active',
      ip_address: '',
      created_at: new Date().toISOString(),
      ended_at: null,
    }

    // Swap API token to avatar token.
    setAuthToken(resp.session_token)

    showToast(t('staff.avatar.started'), 'success')
    targetUserId.value = ''
  } catch {
    showToast(t('common.error'), 'error')
    // Restore staff token on failure.
    if (staffToken) setAuthToken(staffToken)
  } finally {
    loading.value = false
  }
}

async function handleEnd(): Promise<void> {
  loading.value = true
  try {
    // Restore staff token BEFORE calling end (end uses staff's original token).
    if (staffToken) {
      setAuthToken(staffToken)
    }

    await endAvatar()
    activeSession.value = null
    staffToken = null

    // Refresh staff user data.
    await authStore.fetchMe()

    showToast(t('staff.avatar.ended'), 'success')
  } catch {
    showToast(t('common.error'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(checkActive)
</script>

<template>
  <div class="staff-avatar">
    <!-- Banner -->
    <div class="avatar-banner">
      <div class="avatar-banner__title">
        <Ghost :size="20" /> {{ t('staff.avatar.title') }}
      </div>
      <div class="avatar-banner__sub">{{ t('staff.avatar.subtitle') }}</div>
    </div>

    <!-- Loading check -->
    <div v-if="checkingActive" class="staff-avatar__center">
      <CLoader :size="24" />
    </div>

    <template v-else>
      <!-- No active session — start form -->
      <div v-if="!activeSession" class="avatar-start">
        <CInput
          v-model="targetUserId"
          :label="t('staff.avatar.enterUserId')"
          :placeholder="t('staff.avatar.selectUser')"
        />
        <CButton
          variant="primary" size="sm"
          :loading="loading"
          :disabled="!targetUserId.trim()"
          style="margin-top:12px"
          @click="handleStart"
        >
          <Ghost :size="14" /> {{ t('staff.avatar.start') }}
        </CButton>
      </div>

      <!-- Active session card -->
      <div v-else class="avatar-active">
        <div class="avatar-active__card">
          <div class="avatar-active__label">
            <Ghost :size="14" /> {{ t('staff.avatar.session') }}
          </div>
          <div class="avatar-active__target">
            {{ activeSession.target_user_id.slice(0, 12) }}…
          </div>
          <div class="avatar-active__meta">
            {{ new Date(activeSession.created_at).toLocaleString() }}
          </div>
          <CButton
            variant="secondary" size="sm"
            :loading="loading"
            style="margin-top:12px"
            @click="handleEnd"
          >
            <Shield :size="14" /> {{ t('staff.avatar.return') }}
          </CButton>
        </div>
      </div>

      <!-- Restrictions list -->
      <div class="avatar-restrictions">
        <div class="avatar-restrictions__title">
          <Ban :size="14" /> {{ t('staff.avatar.restrictions') }}
        </div>
        <ul class="avatar-restrictions__list">
          <li v-for="key in restrictions" :key="key" class="avatar-restrictions__item">
            <Ban :size="14" class="avatar-restrictions__icon" />
            {{ t(key) }}
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.staff-avatar { padding: 16px; }

.avatar-banner {
  padding: 20px; background: var(--accent); color: white;
  border-radius: var(--radius-lg); margin-bottom: 20px; text-align: center;
}
.avatar-banner__title {
  font-size: 18px; font-weight: 700; display: flex; align-items: center;
  justify-content: center; gap: 8px;
}
.avatar-banner__sub {
  font-size: 13px; opacity: 0.9; margin-top: 4px;
}

.staff-avatar__center {
  display: flex; align-items: center; justify-content: center; min-height: 120px;
}

.avatar-start { margin-bottom: 24px; }

.avatar-active { margin-bottom: 24px; }
.avatar-active__card {
  padding: 16px; background: var(--accent); color: white;
  border-radius: var(--radius-lg); text-align: center;
}
.avatar-active__label {
  font-size: 14px; font-weight: 700; display: flex; align-items: center;
  justify-content: center; gap: 6px; margin-bottom: 4px;
}
.avatar-active__target {
  font-size: 18px; font-weight: 800; margin-bottom: 4px; font-family: monospace;
}
.avatar-active__meta {
  font-size: 12px; opacity: 0.8; margin-bottom: 4px;
}

.avatar-restrictions {
  padding: 16px; background: var(--bg-subtle); border-radius: var(--radius-md);
}
.avatar-restrictions__title {
  font-size: 13px; font-weight: 700; color: var(--text-secondary);
  display: flex; align-items: center; gap: 6px; margin-bottom: 12px;
}
.avatar-restrictions__list {
  list-style: none; margin: 0; padding: 0;
}
.avatar-restrictions__item {
  display: flex; align-items: center; gap: 8px; padding: 6px 0;
  font-size: 13px; color: var(--text-secondary);
}
.avatar-restrictions__icon { color: var(--danger); flex-shrink: 0; }
</style>
