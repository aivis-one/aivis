<script setup lang="ts">
// =============================================================================
// ActionMenu -- the design system's Action menu (K26), the menu button pattern
// =============================================================================
//
// A Button (`aria-haspopup="menu"`, `aria-expanded`, `aria-controls`) that opens a
// list of menu items. The menu never acts itself: a pick is the `select` event
// carrying the item's `value`. Keys as the system names them: Enter, Space and
// Down open and focus the first item, Up opens on the last; Up and Down move and
// wrap, Home and End go to the ends, a typed letter moves to the next item that
// starts with it, Escape closes and returns the focus to the button, Tab closes,
// a click outside closes. An item with `disabled` stays in the list and is skipped.
// =============================================================================

import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import type { Component } from 'vue'
import { ChevronDown } from '@/components/ui/icons'

export interface ActionMenuItem {
  value: string
  label: string
  icon?: Component
  danger?: boolean
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    /** The trigger's word (its accessible name when `iconOnly`). */
    label: string
    items: ActionMenuItem[]
    /** An icon before the word. */
    icon?: Component
    iconOnly?: boolean
    /** `end` opens toward the end edge: use it when the button sits at the end of a row. */
    align?: 'end'
    disabled?: boolean
  }>(),
  { align: undefined },
)

const emit = defineEmits<{ select: [value: string] }>()

const root = ref<HTMLElement | null>(null)
const button = ref<HTMLButtonElement | null>(null)
const list = ref<HTMLElement | null>(null)
const open = ref(false)
const buttonId = useId()
const listId = useId()

function enabledItems(): HTMLButtonElement[] {
  if (!list.value) return []
  return Array.from(
    list.value.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([aria-disabled="true"])'),
  )
}

async function openMenu(which: 'first' | 'last'): Promise<void> {
  if (props.disabled) return
  open.value = true
  await nextTick()
  const items = enabledItems()
  const target = which === 'last' ? items[items.length - 1] : items[0]
  target?.focus()
}

function closeMenu(refocus: boolean): void {
  if (!open.value) return
  open.value = false
  if (refocus) button.value?.focus()
}

function toggle(): void {
  if (open.value) closeMenu(false)
  else void openMenu('first')
}

function onButtonKey(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    void openMenu('first')
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    void openMenu('last')
  }
}

function choose(item: ActionMenuItem): void {
  if (item.disabled) return
  emit('select', item.value)
  closeMenu(true)
}

function onItemKey(e: KeyboardEvent): void {
  const items = enabledItems()
  const index = items.indexOf(e.target as HTMLButtonElement)
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    items[(index + 1) % items.length]?.focus()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    items[(index - 1 + items.length) % items.length]?.focus()
  } else if (e.key === 'Home') {
    e.preventDefault()
    items[0]?.focus()
  } else if (e.key === 'End') {
    e.preventDefault()
    items[items.length - 1]?.focus()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    closeMenu(true)
  } else if (e.key === 'Tab') {
    closeMenu(false)
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const letter = e.key.toLowerCase()
    const ordered = [...items.slice(index + 1), ...items.slice(0, index + 1)]
    ordered.find((i) => (i.textContent ?? '').trim().toLowerCase().startsWith(letter))?.focus()
  }
}

function onDocClick(e: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(e.target as Node)) closeMenu(false)
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="ds-menu" :data-align="align">
    <button
      :id="buttonId"
      ref="button"
      type="button"
      class="ds-button ds-button--secondary ds-menu__button"
      :class="{ 'ds-button--icon': iconOnly }"
      data-size="sm"
      aria-haspopup="menu"
      :aria-expanded="open"
      :aria-controls="listId"
      :aria-label="iconOnly ? label : undefined"
      :disabled="disabled"
      @click="toggle"
      @keydown="onButtonKey"
    >
      <component :is="icon" v-if="icon" size="sm" />
      <template v-if="!iconOnly">{{ label }}</template>
      <ChevronDown size="sm" />
    </button>
    <ul
      :id="listId"
      ref="list"
      class="ds-menu__list"
      role="menu"
      :aria-labelledby="buttonId"
      :hidden="!open"
    >
      <li v-for="item in items" :key="item.value" role="none">
        <button
          type="button"
          role="menuitem"
          class="ds-menu__item"
          :class="{ 'ds-menu__item--danger': item.danger }"
          :aria-disabled="item.disabled ? 'true' : undefined"
          tabindex="-1"
          @click="choose(item)"
          @keydown="onItemKey"
        >
          <component :is="item.icon" v-if="item.icon" size="sm" />
          {{ item.label }}
        </button>
      </li>
    </ul>
  </div>
</template>
