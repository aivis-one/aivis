<script setup lang="ts">
// Language + theme control, for surfaces a signed-out visitor reaches, on the
// design system's K40 contract: the buttons are the system's Button, and every
// accessible name comes from the translation tables.
//
// LANGUAGE: the collapsed control shows the two-letter code alone; inside the
// open list each option shows its flag and the language's own name. The list is
// built from SUPPORTED_LOCALES, which stays the single source of truth -- adding
// a language lights it up here with no change to this file.
//
// THEME: a plain light <-> dark toggle. `useTheme` also has an 'auto' state that
// follows the OS, and that stays the DEFAULT until the visitor first presses
// this button -- so dark-by-system-setting is not lost by adding a manual switch.
// The button's name is the action, not the state.

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'
import { SUPPORTED_LOCALES } from '@/i18n/locales.config'
import { useTheme } from '@/composables/useTheme'
import { Moon, Sun } from '@/components/ui/icons'

const { locale, t } = useI18n()
const { effective, set: setTheme } = useTheme()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const current = computed(() => SUPPORTED_LOCALES.find((l) => l.code === locale.value))
const currentShort = computed(() => current.value?.short ?? 'EN')
const currentName = computed(() => current.value?.label ?? 'English')

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
        class="ds-button ds-button--secondary"
        :aria-expanded="open"
        aria-haspopup="listbox"
        :aria-label="t('common.language.current', { name: currentName })"
        @click="open = !open"
      >
        {{ currentShort }}
      </button>

      <ul v-if="open" class="app-controls__menu" role="listbox" :aria-label="t('common.language.label')">
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
            <span>{{ l.label }}</span>
          </button>
        </li>
      </ul>
    </div>

    <button
      type="button"
      class="ds-button ds-button--secondary ds-button--icon"
      :aria-label="effective === 'dark' ? t('common.theme.toLight') : t('common.theme.toDark')"
      @click="toggleTheme"
    >
      <Sun v-if="effective === 'dark'" size="sm" />
      <Moon v-else size="sm" />
    </button>
  </div>
</template>

<style scoped>
.app-controls {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.app-controls__lang {
  position: relative;
}

/* The open list. The system's Action menu (K26) is a menu; this is a listbox,
   so it keeps its form and takes the system's surface, border, radius, shadow. */
.app-controls__menu {
  position: absolute;
  inset-block-start: calc(100% + var(--space-1));
  inset-inline-end: 0;
  z-index: 200;
  min-inline-size: var(--size-4xl);
  padding: var(--space-1);
  margin: 0;
  list-style: none;
  background: var(--bg-surface);
  border: thin solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-2);
}

.app-controls__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  inline-size: 100%;
  padding-block: var(--space-3);
  padding-inline: var(--space-3);
  min-block-size: var(--touch-min);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font-body);
  font-size: var(--fs-sm);
  font-weight: 600;
  white-space: nowrap;
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
  font-size: var(--fs-sm);
  line-height: 1;
}
</style>
