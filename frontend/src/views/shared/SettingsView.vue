<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { useProfileStore } from '@/stores/profile'

const { t, locale } = useI18n()
const profileStore = useProfileStore()
const { addToast } = useToast()

const currentTheme = ref<'light' | 'dark' | 'system'>('system')
const currentLanguage = ref(locale.value)
const notifEmail = ref(true)
const notifPush = ref(true)
const notifSms = ref(false)

onMounted(async () => {
  try {
    await profileStore.fetchSettings()
    if (profileStore.settings) {
      currentTheme.value = profileStore.settings.theme
      currentLanguage.value = profileStore.settings.language
      notifEmail.value = profileStore.settings.notifications_email
      notifPush.value = profileStore.settings.notifications_push
      notifSms.value = profileStore.settings.notifications_sms
    }
  } catch {
    // Settings may not exist yet — use defaults
  }
})

let saveTimeout: ReturnType<typeof setTimeout> | null = null

function debouncedSave(data: Record<string, unknown>) {
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = setTimeout(async () => {
    const success = await profileStore.updateSettings(data)
    if (success) {
      addToast('success', t('settings.saved'))
    }
  }, 500)
}

function setTheme(theme: 'light' | 'dark' | 'system') {
  currentTheme.value = theme
  if (theme === 'system') {
    delete document.documentElement.dataset.theme
  } else {
    document.documentElement.dataset.theme = theme
  }
  localStorage.setItem('cbs-theme', theme)
  debouncedSave({ theme })
}

function setLanguage(lang: string) {
  currentLanguage.value = lang
  locale.value = lang
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
  localStorage.setItem('cbs-lang', lang)
  debouncedSave({ language: lang })
}

function toggleNotification(
  key: 'notifications_email' | 'notifications_push' | 'notifications_sms',
) {
  if (key === 'notifications_email') notifEmail.value = !notifEmail.value
  else if (key === 'notifications_push') notifPush.value = !notifPush.value
  else notifSms.value = !notifSms.value
  debouncedSave({
    [key]:
      key === 'notifications_email'
        ? notifEmail.value
        : key === 'notifications_push'
          ? notifPush.value
          : notifSms.value,
  })
}
</script>

<template>
  <div class="settings-view">
    <h1 class="settings-view__title">{{ t('settings.title') }}</h1>

    <section class="settings-view__section">
      <h2 class="settings-view__heading">{{ t('settings.appearance') }}</h2>
      <div class="settings-view__row">
        <span class="settings-view__label">{{ t('settings.theme') }}</span>
        <div class="settings-view__options">
          <button
            v-for="opt in ['light', 'dark', 'system'] as const"
            :key="opt"
            :class="[
              'settings-view__option',
              { 'settings-view__option--active': currentTheme === opt },
            ]"
            @click="setTheme(opt)"
          >
            {{ t(`settings.theme${opt.charAt(0).toUpperCase() + opt.slice(1)}`) }}
          </button>
        </div>
      </div>
    </section>

    <section class="settings-view__section">
      <h2 class="settings-view__heading">{{ t('settings.language') }}</h2>
      <div class="settings-view__row">
        <select
          :value="currentLanguage"
          class="settings-view__select"
          @change="setLanguage(($event.target as HTMLSelectElement).value)"
        >
          <option value="en">English</option>
          <option value="ru">Русский</option>
          <option value="de">Deutsch</option>
          <option value="ar">العربية</option>
        </select>
      </div>
    </section>

    <section class="settings-view__section">
      <h2 class="settings-view__heading">{{ t('settings.notifications') }}</h2>
      <label class="settings-view__toggle">
        <span>{{ t('settings.notificationsEmail') }}</span>
        <input
          type="checkbox"
          :checked="notifEmail"
          @change="toggleNotification('notifications_email')"
        />
      </label>
      <label class="settings-view__toggle">
        <span>{{ t('settings.notificationsPush') }}</span>
        <input
          type="checkbox"
          :checked="notifPush"
          @change="toggleNotification('notifications_push')"
        />
      </label>
      <label class="settings-view__toggle">
        <span>{{ t('settings.notificationsSms') }}</span>
        <input
          type="checkbox"
          :checked="notifSms"
          @change="toggleNotification('notifications_sms')"
        />
      </label>
    </section>
  </div>
</template>

<style scoped>
.settings-view {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.settings-view__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text);
}

.settings-view__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.settings-view__heading {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text);
}

.settings-view__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.settings-view__label {
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.settings-view__options {
  display: flex;
  gap: var(--space-xs);
}

.settings-view__option {
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-size: var(--text-caption);
  cursor: pointer;
  transition:
    background 0.2s,
    border-color 0.2s;
}

.settings-view__option--active {
  background: var(--primary);
  color: var(--text-on-accent);
  border-color: var(--primary);
}

.settings-view__select {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  font-size: var(--text-md);
  font-family: var(--font);
  width: 100%;
}

.settings-view__toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--border);
  font-size: var(--text-base);
  color: var(--text);
  cursor: pointer;
}

.settings-view__toggle input {
  accent-color: var(--primary);
  width: 18px;
  height: 18px;
}
</style>
