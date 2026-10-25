<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorSupportView (Ф-2, shared TASK-39 item 4, H40)
// =============================================================================
//
// The person's ONE conversation with support: the feed, the composer, and
// the form of a new appeal. Mounted at /investor/support, /agent/support
// and /company/support -- the same "shared component lives physically
// under views/investor/, other shells' route records import it directly"
// convention as PortfolioView / NotificationsInboxView. The backend gates
// every /api/v1/support/* route on the session alone, with no role check.
//
// ONE CONVERSATION, HOWEVER MANY TICKETS (H40). The feed is every support
// thread of the person glued into one, newest first (the backend's
// client_support_messages); this screen reads it oldest first and never
// sees a thread id. Two ways to write:
//   - the FORM ("New request" in the header, and in place of an empty
//     feed): a topic and the text -- a new ticket, every time;
//   - the COMPOSER under the feed: a message in the conversation -- the
//     backend puts it into the latest open ticket, else the latest one,
//     else opens a ticket "other".
// Every reply of support is signed "Support", never with a name.
//
// TRANSLATION (H39 P-129). The feed is decided for the person
// (render_for_client): a message has its text -- their own, or the reply
// in their language -- or NO text and a state, `translating` or
// `unavailable`. A null body is shown as that state and never filled from
// anywhere. While anything is translating the feed re-reads itself every
// three seconds, for up to two minutes (useTranslationPoll).
//
// READ. After every successful load the conversation is marked read; a
// failure of that is not shown -- read bookkeeping is nothing the person
// can retry, and showing it would teach them to distrust a message that
// did go through.
//
// Ф-3 CROSS-REFERENCE: views/staff/StaffSupportTicketView.vue renders the
// same bubbles and composer (`.ds-message*`, `.ds-composer*`); a change to
// their markup or error states here is checked there too.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, Plus, RefreshCw } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader, CSelect, CTextarea } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getShell } from '@/router/helpers'
import { formatDateTime } from '@/utils/format'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import { useTranslationPoll } from '@/composables/useTranslationPoll'
import { SUPPORT_TOPICS } from '@/api/support'
import type { SupportActionError } from '@/stores/support'
import type { SupportClientMessage, SupportTopic } from '@/api/support'

const { t, locale } = useI18n()
const route = useRoute()
const support = useSupportStore()
const auth = useAuthStore()

const myUserId = computed<string | null>(() => auth.user?.id ?? null)

// -- The feed -----------------------------------------------------------------

const isEmpty = computed<boolean>(
  () => support.messagesLoaded && !support.messagesError && support.messages.length === 0,
)

// The store holds the backend's order (newest first); this screen reads
// oldest first. A fresh copy every time.
const chronologicalMessages = computed<SupportClientMessage[]>(() =>
  [...support.messages].reverse(),
)

function isMine(message: SupportClientMessage): boolean {
  return myUserId.value !== null && message.sender === myUserId.value
}

function sentAt(message: SupportClientMessage): string | null {
  return message.created_at ? formatDateTime(message.created_at, locale.value) : null
}

// A message with no text says why: a translation on its way, or none to
// come. Anything but `translating` reads as unavailable -- the backend's
// own rule for a state it does not know (fail-closed).
function pendingText(message: SupportClientMessage): string {
  return message.translation === 'translating'
    ? t('inv.support.translating')
    : t('inv.support.translationUnavailable')
}

const { restart: restartTranslationPoll } = useTranslationPoll({
  translating: () => support.messages.some((m) => m.translation === 'translating'),
  refresh: async () => {
    await support.fetchMessages({ silent: true })
  },
})

/**
 * 502/504 (comms unreachable) reads as "try later"; anything else as a
 * plain retry prompt -- the same wording on every surface of this screen.
 */
function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) return t('inv.support.errorUnavailable')
  return t('inv.support.errorGeneric')
}

async function loadFeed(): Promise<void> {
  await support.fetchMessages()
  if (!support.messagesError) {
    void support.markRead()
    restartTranslationPoll()
  }
}

// -- The form: a new appeal ---------------------------------------------------

const formOpen = ref(false)
const formTopic = ref<SupportTopic | ''>('')
const formText = ref('')
const formTried = ref(false)

// The form stands in place of an empty conversation, and on demand above
// a conversation that has messages.
const showForm = computed<boolean>(() => formOpen.value || isEmpty.value)

const topicOptions = computed(() =>
  SUPPORT_TOPICS.map((code) => ({ value: code, label: t(`inv.support.topics.${code}`) })),
)

const topicError = computed<string | undefined>(() =>
  formTried.value && formTopic.value === '' ? t('inv.support.form.topicRequired') : undefined,
)

async function handleCreateTicket(): Promise<void> {
  formTried.value = true
  const text = formText.value.trim()
  if (formTopic.value === '' || text === '' || support.creatingTicket) return
  const ok = await support.createTicket(formTopic.value, text)
  if (!ok) return // the form keeps what was typed
  formText.value = ''
  formTopic.value = ''
  formTried.value = false
  formOpen.value = false
  await loadFeed()
}

function toggleForm(): void {
  formOpen.value = !formOpen.value
}

// -- The composer: a message in the conversation ------------------------------

const composerText = ref('')

async function handleSend(): Promise<void> {
  const text = composerText.value.trim()
  if (text === '' || support.sending) return
  const ok = await support.sendMessage(text)
  if (!ok) return // the box keeps its text
  composerText.value = ''
  await loadFeed()
}

// -- The frame ------------------------------------------------------------------

// Deep-link fallback target, one per shell that hosts this screen: the
// Settings of the shell (where the Support row lives).
const backFallbackRouteName = computed<string>(() => {
  const shell = getShell(route)
  if (shell === 'agent') return 'agent-settings'
  if (shell === 'company') return 'company-settings'
  return 'investor-settings'
})

useScreenHeader({
  title: () => t('inv.support.title'),
  back: () => (window.history.state?.back ? true : { name: backFallbackRouteName.value }),
  actions: () => [
    ...(isEmpty.value
      ? []
      : [
          {
            id: 'new-request',
            label: t('inv.support.form.open'),
            icon: Plus,
            onClick: toggleForm,
          },
        ]),
    {
      id: 'refresh',
      label: t('inv.support.refresh'),
      icon: RefreshCw,
      onClick: () => {
        if (!support.messagesLoading) void loadFeed()
      },
    },
  ],
})

onMounted(() => {
  void loadFeed()
})
</script>

<template>
  <div class="isup">
    <CLoader v-if="support.messagesLoading && !support.messagesLoaded" centered extent="page" />

    <!-- A failed first load never falls back to the form: a network -->
    <!-- failure must not look like "you have no conversation yet". -->
    <CEmptyState
      v-else-if="support.messagesError && !support.messagesLoaded"
      tone="danger"
      :title="t('inv.support.feedErrorTitle')"
      :description="errorMessage(support.messagesError)"
    >
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="loadFeed">
          {{ t('inv.support.feedErrorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else>
      <!-- The form of a new appeal -->
      <form v-if="showForm" class="isup__form" novalidate @submit.prevent="handleCreateTicket">
        <h2 class="ds-section-title">{{ t('inv.support.form.title') }}</h2>
        <p v-if="isEmpty" class="ds-note">{{ t('inv.support.invite') }}</p>
        <CSelect
          v-model="formTopic"
          :label="t('inv.support.form.topic')"
          :placeholder="t('inv.support.form.topicPlaceholder')"
          :options="topicOptions"
          :error="topicError"
        />
        <CTextarea
          v-model="formText"
          :label="t('inv.support.form.text')"
          :placeholder="t('inv.support.placeholder')"
          :rows="4"
        />
        <p v-if="support.createTicketError" class="ds-field__error">
          <AlertTriangle size="sm" />
          <span>{{ errorMessage(support.createTicketError) }}</span>
        </p>
        <div class="isup__form-actions">
          <CButton
            variant="primary"
            inline
            :loading="support.creatingTicket"
            :disabled="formText.trim() === '' || support.creatingTicket"
          >
            {{ t('inv.support.form.submit') }}
          </CButton>
          <CButton v-if="!isEmpty" type="button" variant="outline" inline @click="toggleForm">
            {{ t('common.cancel') }}
          </CButton>
        </div>
      </form>

      <!-- The conversation: the feed and the composer (K51) -->
      <section v-if="!isEmpty" class="ds-thread isup__thread" :aria-label="t('inv.support.title')">
        <ul class="ds-thread__feed" role="log" aria-live="polite" tabindex="0">
          <li v-if="support.messagesNextCursor !== null" class="isup__older">
            <CButton
              variant="link"
              size="sm"
              inline
              :loading="support.olderLoading"
              :disabled="support.olderLoading"
              @click="support.fetchOlderMessages"
            >
              {{ t('inv.support.older') }}
            </CButton>
            <p v-if="support.olderError" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>{{ errorMessage(support.olderError) }}</span>
            </p>
          </li>
          <li
            v-for="message in chronologicalMessages"
            :key="message.id"
            class="ds-message"
            :data-from="isMine(message) ? 'own' : 'other'"
          >
            <span v-if="isMine(message)" class="ds-sr-only">{{ t('inv.support.sender.me') }}</span>
            <span v-else class="ds-message__author">{{ t('inv.support.sender.operator') }}</span>
            <p v-if="message.body !== null" class="ds-message__bubble">
              {{ message.body }}
            </p>
            <p v-else class="ds-message__bubble isup__pending" :data-state="message.translation">
              {{ pendingText(message) }}
            </p>
            <time
              v-if="sentAt(message)"
              class="ds-message__time"
              :datetime="message.created_at ?? undefined"
            >
              {{ sentAt(message) }}
            </time>
          </li>
        </ul>

        <form class="ds-composer" @submit.prevent="handleSend">
          <div class="ds-field ds-composer__input">
            <label class="ds-sr-only" for="isup-message">{{ t('inv.support.placeholder') }}</label>
            <textarea
              id="isup-message"
              v-model="composerText"
              class="ds-input"
              rows="2"
              maxlength="4000"
              :placeholder="t('inv.support.placeholder')"
              :disabled="support.sending"
              :aria-invalid="support.sendError ? 'true' : undefined"
              :aria-describedby="support.sendError ? 'isup-message-error' : undefined"
            />
            <p v-if="support.sendError" id="isup-message-error" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>{{ errorMessage(support.sendError) }}</span>
            </p>
          </div>
          <CButton
            variant="primary"
            inline
            :loading="support.sending"
            :disabled="composerText.trim() === '' || support.sending"
          >
            {{ t('inv.support.send') }}
          </CButton>
        </form>
      </section>
    </template>
  </div>
</template>

<style scoped>
.isup {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-block-size: 0;
}

.isup__form {
  display: grid;
  gap: var(--space-3);
}
.isup__form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* The screen gives the thread its height (K51). */
.isup__thread {
  block-size: calc(var(--center-lg) + var(--center-md));
}

/* "Earlier messages" stands at the top of the feed. */
.isup__older {
  display: grid;
  justify-items: center;
  gap: var(--space-1);
}

/* A reply with no text yet, or none to come (H39): the state in place of it. */
.isup__pending {
  font-style: italic;
  color: var(--text-secondary);
}
</style>
