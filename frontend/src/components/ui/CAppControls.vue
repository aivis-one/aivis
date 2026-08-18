<script setup lang="ts">
// Language + theme control, for surfaces a signed-out visitor reaches.
//
// WHY IT EXISTS: both mechanisms already worked and neither had any UI before
// sign-in. `useTheme` was wired into InvestorSettingsView only, and the locale
// was set exclusively from `user.language` at login -- so a visitor on /login
// could neither switch language nor pick a theme, in any language they might
// not read.
//
// LANGUAGE, per the owner's spec: the collapsed control shows the two-letter
// code ALONE. The flag appears only inside the open list, beside each code.
// The list is built from SUPPORTED_LOCALES, which stays the single source of
// truth -- adding a language lights it up here with no change to this file.
//
// THEME: a plain light <-> dark toggle. `useTheme` also has an 'auto' state
// that follows the OS, and that stays the DEFAULT until the visitor first
// presses this button -- so dark-by-system-setting is not lost by adding a
// manual switch.

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { useTheme } from '@/composables/useTheme'

const { locale } = useI18n()
const { effective, set: setTheme } = useTheme()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const currentShort = computed(
  () => SUPPORTED_LOCALES.find((l) => l.code === locale.value)?.short ?? 'EN',
)

async function pick(code: string) {
  open.value = false
  await setLocale(code)
}

function toggleTheme() {
  setTheme(effective.value === 'dark' ? 'light' : 'dark')
}

// Close on an outside click or Escape -- a dropdown that only closes by
// re-clicking its own trigger strands itself behind a route change.
function onDocClick(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div ref="root" class="app-controls">
    <div class="app-controls__lang">
      <button
        type="button"
        class="app-controls__btn app-controls__btn--code"
        :aria-expanded="open"
        aria-haspopup="listbox"
        :aria-label="'Language: ' + currentShort"
        @click="open = !open"
      >
        {{ currentShort }}
      </button>

      <ul v-if="open" class="app-controls__menu" role="listbox">
        <li v-for="l in SUPPORTED_LOCALES" :key="l.code">
          <button
            type="button"
            role="option"
            :aria-selected="l.code === locale"
            class="app-controls__item"
            :class="{ 'is-active': l.code === locale }"
            @click="pick(l.code)"
          >
            <span class="app-controls__flag" aria-hidden="true">{{ l.flag }}</span>
            <span class="app-controls__code">{{ l.short }}</span>
          </button>
        </li>
      </ul>
    </div>

    <button
      type="button"
      class="app-controls__btn app-controls__btn--theme"
      :aria-label="effective === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
      @click="toggleTheme"
    >
      <svg v-if="effective === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.app-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.app-controls__lang {
  position: relative;
}

.app-controls__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.app-controls__btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}

.app-controls__btn--theme svg {
  width: 16px;
  height: 16px;
}

.app-controls__menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 200;
  min-width: 84px;
  padding: 4px;
  margin: 0;
  list-style: none;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-2);
}

.app-controls__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.app-controls__item:hover {
  background: var(--bg-subtle);
}

.app-controls__item.is-active {
  background: var(--primary-subtle);
  color: var(--primary);
}

.app-controls__flag {
  font-size: 15px;
  line-height: 1;
}

.app-controls__code {
  letter-spacing: 0.5px;
}
</style>
