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
import { Bell, ChevronRight, FileText, LogOut } from '@/components/ui/icons'
import { CAvatar, CBadge, CButton, CSelect } from '@/components/ui'
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

// -- Sign-out -----------------------------------------------------------------
// The two destinations are links (K34 tiles) and need no handler here.

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
    <!-- Profile -->
    <section class="staff-settings__profile" aria-labelledby="staff-settings-name">
      <CAvatar :name="userName" :size="56" />
      <h2 id="staff-settings-name" class="ds-section-title">
        {{ userName }}
      </h2>
      <p class="ds-note">
        {{ userEmail }}
      </p>
      <CBadge variant="primary" :text="roleLine" />
    </section>

    <!-- Language -->
    <CSelect
      :model-value="currentLanguage"
      :options="languageOptions"
      :label="t('staff.settings.language')"
      :disabled="savingLanguage"
      @update:model-value="changeLanguage"
    />

    <!-- Account -->
    <section class="staff-settings__section">
      <h2 class="ds-section-title">
        {{ t('staff.settings.account') }}
      </h2>
      <TwoFactorSection tPrefix="staff.settings.actions" />
      <ActiveSessionsSection tPrefix="staff.settings.actions" />
      <NotificationPreferencesSection tPrefix="staff.settings.actions" />

      <!-- The destinations (K34 nav tiles) -->
      <div class="ds-navtiles">
        <RouterLink class="ds-navtile" to="/staff/notifications">
          <span class="ds-navtile__icon"><Bell /></span>
          <span class="ds-navtile__text">
            <span class="ds-navtile__title">{{ t('staff.notifications.title') }}</span>
          </span>
          <ChevronRight class="ds-navtile__go" />
        </RouterLink>
        <RouterLink class="ds-navtile" to="/staff/docs">
          <span class="ds-navtile__icon"><FileText /></span>
          <span class="ds-navtile__text">
            <span class="ds-navtile__title">{{ t('staff.settings.documents') }}</span>
          </span>
          <ChevronRight class="ds-navtile__go" />
        </RouterLink>
      </div>

      <div>
        <CButton variant="outline" inline :disabled="loggingOut" @click="handleLogout">
          <LogOut size="sm" /> {{ t('staff.settings.logout') }}
        </CButton>
      </div>
    </section>

    <!-- About (K49) -->
    <section class="staff-settings__section">
      <h2 class="ds-section-title">
        {{ t('staff.settings.about') }}
      </h2>
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('staff.settings.version') }}</dt>
          <dd>{{ version }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>

<style scoped>
.staff-settings {
  display: grid;
  gap: var(--space-5);
}

.staff-settings__profile {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
  text-align: center;
}

.staff-settings__section {
  display: grid;
  gap: var(--space-3);
}
</style>
