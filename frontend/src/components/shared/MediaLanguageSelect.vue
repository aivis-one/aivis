<script setup lang="ts">
// =============================================================================
// MediaLanguageSelect -- which version of a project's pictures is edited (H38)
// =============================================================================
//
// A picture may have a variant per language beside its common file; a reader
// of that language sees the variant, everyone else the common file. This
// select picks what the picture fields below it show and upload: the common
// file (the base language, English) or one language's variant. The options
// are EDIT_LANGUAGES -- SUPPORTED_LOCALES -- never a literal list.
//
//   modelValue  a language code; the base language means the common file
// =============================================================================

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CSelect } from '@/components/ui'
import { BASE_LANGUAGE, EDIT_LANGUAGES } from '@/utils/projectTexts'

defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

const options = computed(() =>
  EDIT_LANGUAGES.map((l) => ({
    value: l.code,
    label:
      l.code === BASE_LANGUAGE
        ? t('common.projectLanguages.commonPicture', { language: l.label })
        : t('common.projectLanguages.variantPicture', { language: l.label }),
  })),
)
</script>

<template>
  <CSelect
    :model-value="modelValue"
    :label="t('common.projectLanguages.pictureLanguage')"
    :options="options"
    @update:model-value="(v: string) => emit('update:modelValue', v)"
  />
</template>
