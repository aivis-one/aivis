<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PurchaseTerms
// =============================================================================
//
// What the buyer meets before paying, on the purchase screen and on the
// instalment confirmation:
//
//   1. the pre-purchase disclosure sheet, SHORT on the screen -- one line for
//      each of its sections, taken from the sheet itself -- with the full text
//      one tap away (the cabinet's own document window; the static file stays
//      the link that can be saved);
//   2. ONE tick, "I accept the agreement", with the buyer agreement behind a
//      link to its full text.
//
// The tick is the parent's (v-model). The parent records the acceptance of the
// buyer agreement (documents/by-type + sign) when the button is pressed, and
// keeps the button shut while the tick is empty.
//
// The short form is read from the same static file the full window shows
// (public/legal/<lang>/pre_purchase_disclosure.html): the first sentence of
// each numbered section's opening paragraph. Nothing is rendered as HTML.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t, locale } = useI18n()

const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))

function docUrl(type: string): string {
  return `${import.meta.env.BASE_URL}legal/${docLang.value}/${type}.html`
}

// ---------------------------------------------------------------------------
// The short form of the disclosure sheet
// ---------------------------------------------------------------------------

interface DigestRow {
  heading: string
  line: string
}

const SENTENCE_LIMIT = 170

const digest = ref<DigestRow[]>([])
const digestFailed = ref(false)

// A later language switch must not be overwritten by an earlier, slower fetch.
let epoch = 0

function firstSentence(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  const cut = flat.search(/[.!?](\s|$)/)
  const sentence = cut >= 0 ? flat.slice(0, cut + 1) : flat
  return sentence.length > SENTENCE_LIMIT ? `${sentence.slice(0, SENTENCE_LIMIT - 1)}…` : sentence
}

async function loadDigest(): Promise<void> {
  const mine = ++epoch
  digestFailed.value = false
  try {
    const resp = await fetch(docUrl('pre_purchase_disclosure'))
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const dom = new DOMParser().parseFromString(await resp.text(), 'text/html')
    const rows: DigestRow[] = []
    dom.querySelectorAll('h2').forEach((h) => {
      let node = h.nextElementSibling
      while (node && node.tagName !== 'P') node = node.nextElementSibling
      if (!node) return
      // The paragraph opens with its own number ("1.1.").
      const body = (node.textContent ?? '').replace(/^\s*\d+(\.\d+)*\.\s*/, '')
      rows.push({
        heading: (h.textContent ?? '').replace(/^\s*\d+\.\s*/, '').trim(),
        line: firstSentence(body),
      })
    })
    if (mine === epoch) digest.value = rows
  } catch {
    if (mine === epoch) {
      digest.value = []
      digestFailed.value = true
    }
  }
}

onMounted(loadDigest)
watch(docLang, loadDigest)

// ---------------------------------------------------------------------------
// The two document windows
// ---------------------------------------------------------------------------

const openDoc = ref<'pre_purchase_disclosure' | 'buyer_agreement' | null>(null)

const openTitle = computed(() =>
  openDoc.value === 'buyer_agreement'
    ? t('inv.terms.agreementTitle')
    : t('inv.terms.disclosureTitle'),
)
</script>

<template>
  <section class="pt">
    <h2 class="pt__title">
      {{ t('inv.terms.title') }}
    </h2>

    <ul v-if="digest.length > 0" class="pt__list">
      <li v-for="row in digest" :key="row.heading" class="pt__row">
        <span class="pt__heading">{{ row.heading }}.</span>
        {{ row.line }}
      </li>
    </ul>
    <p v-else-if="digestFailed" class="pt__hint">
      {{ t('inv.terms.digestFailed') }}
    </p>

    <p class="pt__hint">
      <a
        :href="docUrl('pre_purchase_disclosure')"
        target="_blank"
        rel="noopener"
        @click.prevent="openDoc = 'pre_purchase_disclosure'"
        >{{ t('inv.terms.readFull') }}</a
      >
    </p>

    <label class="pt__accept">
      <input
        type="checkbox"
        :checked="modelValue"
        @change="emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
      />
      <span>
        {{ t('inv.terms.acceptPrefix') }}
        <a
          :href="docUrl('buyer_agreement')"
          target="_blank"
          rel="noopener"
          @click.prevent="openDoc = 'buyer_agreement'"
          >{{ t('inv.terms.agreementLink') }}</a
        >
      </span>
    </label>

    <LegalDocModal
      :open="openDoc !== null"
      :title="openTitle"
      :lang="docLang"
      :type="openDoc ?? 'pre_purchase_disclosure'"
      @close="openDoc = null"
    />
  </section>
</template>

<style scoped>
.pt {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border: thin solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-page);
}

.pt__title {
  margin: 0;
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.pt__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.pt__row {
  font-size: var(--fs-xs);
  line-height: 1.5;
  color: var(--text-secondary);
}

.pt__heading {
  font-weight: 600;
  color: var(--text-primary);
}

.pt__hint {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.pt a {
  color: var(--primary);
  text-decoration: underline;
}

.pt__accept {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.pt__accept input[type='checkbox'] {
  flex: none;
  inline-size: 1rem;
  block-size: 1rem;
  margin: calc((1.5 * var(--fs-sm) - 1rem) / 2) 0 0;
}
</style>
