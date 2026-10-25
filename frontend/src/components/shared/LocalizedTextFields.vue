<script setup lang="ts">
// =============================================================================
// LocalizedTextFields -- a project's texts in every language (H38 P-132)
// =============================================================================
//
// One group per editing language (EDIT_LANGUAGES, from SUPPORTED_LOCALES),
// English first: English is the base and the fallback, so its fields are
// required where the screen requires them; every other language is
// optional, and a blank field means "no translation" -- the reader of that
// language sees the English text.
//
//   modelValue  the draft, language -> field -> text (utils/projectTexts)
//   fields      the fields, in order: key, label, multiline, rows, maxlength
//
// It edits the draft only; the screen builds the request from it
// (baseText, translationsFromDraft).
// =============================================================================

import { useI18n } from 'vue-i18n'
import { CInput, CTextarea } from '@/components/ui'
import { BASE_LANGUAGE, EDIT_LANGUAGES } from '@/utils/projectTexts'
import type { TextDraft } from '@/utils/projectTexts'

export interface LocalizedField {
  key: string
  label: string
  multiline?: boolean
  rows?: number
  maxlength?: number
}

const props = defineProps<{
  modelValue: TextDraft
  fields: readonly LocalizedField[]
}>()

const emit = defineEmits<{ 'update:modelValue': [value: TextDraft] }>()

const { t } = useI18n()

function valueOf(language: string, field: string): string {
  return props.modelValue[language]?.[field] ?? ''
}

function update(language: string, field: string, value: string): void {
  emit('update:modelValue', {
    ...props.modelValue,
    [language]: { ...(props.modelValue[language] ?? {}), [field]: value },
  })
}
</script>

<template>
  <fieldset v-for="lang in EDIT_LANGUAGES" :key="lang.code" class="ds-fieldset ltf">
    <legend class="ds-fieldset__legend">
      {{
        lang.code === BASE_LANGUAGE
          ? t('common.projectLanguages.base', { language: lang.label })
          : t('common.projectLanguages.optional', { language: lang.label })
      }}
    </legend>
    <template v-for="field in fields" :key="field.key">
      <CTextarea
        v-if="field.multiline"
        :model-value="valueOf(lang.code, field.key)"
        :label="field.label"
        :rows="field.rows ?? 4"
        :maxlength="field.maxlength"
        :lang="lang.code"
        @update:model-value="(v: string) => update(lang.code, field.key, v)"
      />
      <CInput
        v-else
        :model-value="valueOf(lang.code, field.key)"
        :label="field.label"
        :maxlength="field.maxlength"
        :lang="lang.code"
        @update:model-value="(v: string) => update(lang.code, field.key, v)"
      />
    </template>
  </fieldset>
  <p class="ds-field__hint">{{ t('common.projectLanguages.hint') }}</p>
</template>

<style scoped>
.ltf + .ltf {
  margin-block-start: var(--space-3);
}
</style>
