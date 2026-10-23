<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSettingsView (the staff member's Settings tab)
// =============================================================================
//
// The fifth staff tab: the member's own profile, security and notifications,
// and nothing about the platform (that is the Platform tab).
//
//   1. Profile card -- name, e-mail, the role line ("Staff" or
//      "Administrator", the latter when every permission is on).
//   2. Language -- English or Russian, saved on the account.
//   3. Account -- two-factor authentication, active sessions, notification
//      preferences (the shared sections), the notifications inbox, the staff
//      member's legal documents (the AML policy among them), sign-out.
//   4. About -- the version of this build: its tag, written into the bundle at
//      build time (src/appVersion.ts).
// =============================================================================

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell, FileText, LogOut } from '@/components/ui/icons'
import { CAvatar, CBadge, CSelect } from '@/components/ui'
import TwoFactorSection from '@/components/shared/TwoFactorSection.vue'
import ActiveSessionsSection from '@/components/shared/ActiveSessionsSection.vue'
import NotificationPreferencesSection from '@/components/shared/NotificationPreferencesSection.vue'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { safeNavigate } from '@/composables/safeNavigate'
import { updateMe } from '@/api/users'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { showToast } = useToast()
const { isAdmin } = useStaffPermissions()

const userName = computed(() => {
  const p = authStore.user?.profile
  if (p && typeof p === 'object') {
    const fn = (p as Record<string, unknown>).first_name
    const ln = (p as Record<string, unknown>).last_name
    if (fn || ln) return `${fn ?? ''} ${ln ?? ''}`.trim()
  }
  return t('staff.settings.noName')
})
const userEmail = computed(() => authStore.user?.email ?? '')
const roleLine = computed(() =>
  isAdmin.value ? t('staff.settings.roleAdmin') : t('staff.settings.roleStaff'),
)

// -- Language ---------------------------------------------------------------

const languageOptions = SUPPORTED_LOCALES.map((l) => ({ value: l.code, label: l.label }))
const currentLanguage = computed<string>(() => authStore.user?.language ?? 'en')
const savingLanguage = ref(false)

async function changeLanguage(code: string): Promise<void> {
  if (!code || code === currentLanguage.value || savingLanguage.value) return
  savingLanguage.value = true
  try {
    await updateMe({ language: code })
    await authStore.fetchMe()
    await setLocale(code)
    showToast(t('staff.settings.languageSaved'), 'success')
  } catch {
    showToast(t('staff.settings.languageError'), 'error')
  } finally {
    savingLanguage.value = false
  }
}

// -- Navigation and sign-out --------------------------------------------------

function goNotifications(): void {
  void safeNavigate(router.push('/staff/notifications'), '[StaffSettingsView] to notifications')
}

function goDocuments(): void {
  void safeNavigate(router.push('/staff/docs'), '[StaffSettingsView] to documents')
}

const loggingOut = ref(false)
async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await authStore.logout()
  } finally {
    loggingOut.value = false
  }
  void safeNavigate(router.push('/login'), '[StaffSettingsView] to login')
}

const version = __APP_VERSION__
</script>

<template>
  <div class="staff-settings">
    <!-- Profile card -->
    <div class="staff-settings__profile">
      <CAvatar :name="userName" :size="72" />
      <div class="staff-settings__name">
        {{ userName }}
      </div>
      <div class="staff-settings__email">
        {{ userEmail }}
      </div>
      <div class="staff-settings__badges">
        <CBadge variant="primary" :text="roleLine" />
      </div>
    </div>

    <!-- Language -->
    <div class="staff-settings__section">
      <div class="staff-settings__section-label">
        {{ t('staff.settings.language') }}
      </div>
      <CSelect
        :model-value="currentLanguage"
        :options="languageOptions"
        :label="t('staff.settings.language')"
        :disabled="savingLanguage"
        @update:model-value="changeLanguage"
      />
    </div>

    <!-- Account -->
    <div class="staff-settings__section">
      <div class="staff-settings__section-label">
        {{ t('staff.settings.account') }}
      </div>
      <TwoFactorSection tPrefix="staff.settings.actions" />
      <ActiveSessionsSection tPrefix="staff.settings.actions" />
      <NotificationPreferencesSection tPrefix="staff.settings.actions" />

      <button type="button" class="staff-settings__nav-item" @click="goNotifications">
        <span class="staff-settings__nav-left">
          <Bell :size="16" /> {{ t('staff.notifications.title') }}
        </span>
        <span class="staff-settings__nav-right">&rarr;</span>
      </button>

      <button type="button" class="staff-settings__nav-item" @click="goDocuments">
        <span class="staff-settings__nav-left">
          <FileText :size="16" /> {{ t('staff.settings.documents') }}
        </span>
        <span class="staff-settings__nav-right">&rarr;</span>
      </button>

      <button
        type="button"
        class="staff-settings__nav-item staff-settings__nav-item--danger"
        :disabled="loggingOut"
        @click="handleLogout"
      >
        <span class="staff-settings__nav-left">
          <LogOut :size="16" /> {{ t('staff.settings.logout') }}
        </span>
        <span class="staff-settings__nav-right">&rarr;</span>
      </button>
    </div>

    <!-- About -->
    <div class="staff-settings__section">
      <div class="staff-settings__section-label">
        {{ t('staff.settings.about') }}
      </div>
      <div class="staff-settings__info-row">
        <span>{{ t('staff.settings.version') }}</span>
        <span class="staff-settings__info-val">{{ version }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staff-settings {
  padding: var(--space-4);
}

.staff-settings__profile {
  text-align: center;
  padding: var(--space-4-lg) 0;
  margin-block-end: var(--space-4);
}
.staff-settings__name {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin-block-start: var(--space-3);
}
.staff-settings__email {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-block-start: var(--space-1);
}
.staff-settings__badges {
  display: inline-flex;
  gap: var(--space-2);
  margin-block-start: var(--space-2);
}

.staff-settings__section {
  border-block-start: thin solid var(--border-default);
  padding-block-start: var(--space-4);
  margin-block-start: var(--space-4);
}
.staff-settings__section-label {
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin-block-end: var(--space-3);
}

.staff-settings__nav-item {
  appearance: none;
  background: none;
  border: none;
  margin: 0;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: start;
  inline-size: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) 0;
  border-block-end: thin solid var(--border-default);
  cursor: pointer;
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.staff-settings__nav-item:hover {
  opacity: 0.8;
}
.staff-settings__nav-item--danger {
  color: var(--danger);
  border-block-end: none;
}
.staff-settings__nav-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.staff-settings__nav-right {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.staff-settings__info-row {
  display: flex;
  justify-content: space-between;
  padding: var(--space-4) 0;
  border-block-end: thin solid var(--border-default);
  font-size: var(--fs-sm);
  color: var(--text-primary);
}
.staff-settings__info-val {
  font-size: var(--fs-sm);
  color: var(--text-tertiary);
}
</style>
