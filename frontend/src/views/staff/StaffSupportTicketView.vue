<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSupportTicketView (H40 tickets, H41 ratings)
// =============================================================================
//
// One ticket's card: /staff/users/support/:id, where :id is the ticket's
// comms thread id. Opened from a row of the list (StaffSupportView) and
// from an operator signal (support.message_received / ticket_assigned /
// ticket_released -- utils/notificationTarget.ts), which carries only the
// id. A routed id is safe here: every operator reads every ticket (owner
// ruling, H40), and an id that is not a ticket's is the backend's 404.
//
// WHAT THE CARD OFFERS, by the ticket's state:
//   open, nobody took it      -- take it; hand it over; close it;
//   open, I took it           -- reply; give it back; hand it over; close it;
//   open, a colleague took it -- hand it over; close it (the backend admits
//                                every operator for both); reading only;
//   closed any of four ways   -- back to work. Spam comes back only within
//                                its retention: the backend says when not.
// Taking is what grants the right to reply; a reply on a ticket nobody took
// is refused by comms, and the composer is not drawn.
//
// THE RATING (H41): who last resolved the ticket stands among its facts --
// "resolved by" while it is resolved, "last resolved by" once it is not --
// and the person's rating, when there is one, under them: the stars, the
// comment as written with the person's interface language, the operator it
// is about.
//
// THE PERSON'S CONVERSATION FROM BEFORE TICKETS (their history), when there
// is one, is a second, read-only feed of the same card: "Earlier
// conversation" swaps it in, "Back to the ticket" swaps it out.
//
// TRANSLATION (H39 P-129). The feed comes already decided (backend
// translation.staff_feed). A person's message shows its translation, with
// "Show original"; a reply to a person of another language shows the
// operator's own text, with what the person reads one tap away. Under a
// message stands its translation state; "Retry translation" only where the
// feed says `retryable`. While anything is translating the feed re-reads
// itself every three seconds, for up to two minutes (useTranslationPoll).
//
// Ф-2 CROSS-REFERENCE: views/investor/InvestorSupportView.vue renders the
// same bubbles and composer; a change to their markup here is checked there.
// =============================================================================

import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, RefreshCw } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CLoader, CSelect } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { formatDateTime } from '@/utils/format'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import { useTranslationPoll } from '@/composables/useTranslationPoll'
import { SUPPORT_CLOSING_STATUSES } from '@/api/support'
import type { SupportActionError, TicketAction } from '@/stores/support'
import type { SupportClosingStatus, SupportStaffMessage } from '@/api/support'
import { personName, starsText, statusVariant } from './supportPeople'

const { t, locale } = useI18n()
const route = useRoute()
const support = useSupportStore()
const auth = useAuthStore()

const ticketId = computed<string>(() => String(route.params.id ?? ''))
const myId = computed<string | null>(() => auth.user?.id ?? null)

const ticket = computed(() =>
  support.ticket !== null && support.ticket.id === ticketId.value ? support.ticket : null,
)

const isOpen = computed<boolean>(() => ticket.value?.status === 'open')
const takerId = computed<string | null>(() => ticket.value?.claimed_by?.user_id ?? null)
const isMine = computed<boolean>(() => takerId.value !== null && takerId.value === myId.value)
const isUnclaimed = computed<boolean>(() => takerId.value === null)

// Which feed is on screen: the ticket's, or the person's history.
const viewingHistory = ref(false)
const feedThreadId = computed<string | null>(() => {
  if (ticket.value === null) return null
  return viewingHistory.value ? ticket.value.history_thread_id : ticket.value.id
})

async function load(): Promise<void> {
  viewingHistory.value = false
  for (const key of Object.keys(flipped)) delete flipped[key]
  await support.fetchTicket(ticketId.value)
  if (ticket.value !== null) await loadFeed()
}

async function loadFeed(): Promise<void> {
  const id = feedThreadId.value
  if (id === null) return
  await support.fetchStaffMessages(id)
  restartTranslationPoll()
}

function showHistory(on: boolean): void {
  viewingHistory.value = on
  for (const key of Object.keys(flipped)) delete flipped[key]
  void loadFeed()
}

useScreenHeader({
  back: () => (window.history.state?.back ? true : { name: 'staff-support' }),
  actions: () => [
    { id: 'refresh', label: t('staff.support.refresh'), icon: RefreshCw, onClick: load },
  ],
})

// -- Errors ---------------------------------------------------------------------

function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) return t('staff.support.errorUnavailable')
  return t('staff.support.errorGeneric')
}

// What a refused action means, in the operator's words.
function actionMessage(action: TicketAction, err: SupportActionError): string {
  if (err.status === 409) {
    if (action === 'claim') return t('staff.support.claimConflict')
    if (action === 'reopen') return t('staff.support.reopenRefused')
    return t('staff.support.changedMeanwhile')
  }
  if (err.status === 404 && action === 'reopen') return t('staff.support.ticketGone')
  if (err.status === 422 && action === 'assign') return t('staff.support.assigneeNotOperator')
  return errorMessage(err)
}

const actionErrorText = computed<string | null>(() => {
  const failure = support.actionError
  return failure === null ? null : actionMessage(failure.action, failure.error)
})

// -- Actions --------------------------------------------------------------------

function claim(): void {
  void support.claimTicket(ticketId.value)
}
function release(): void {
  void support.releaseTicket(ticketId.value)
}
function reopen(): void {
  void support.reopenTicket(ticketId.value)
}
function close(status: SupportClosingStatus): void {
  void support.setTicketStatus(ticketId.value, status)
}

const assignee = ref('')
const assigneeOptions = computed(() =>
  support.operators
    .filter((p) => p.user_id !== takerId.value)
    .map((p) => ({ value: p.user_id, label: personName(p) })),
)

async function assign(): Promise<void> {
  if (assignee.value === '') return
  const ok = await support.assignTicket(ticketId.value, assignee.value)
  if (ok) assignee.value = ''
}

// -- The feed ---------------------------------------------------------------------

const feedReady = computed<boolean>(
  () => support.staffMessagesThreadId === feedThreadId.value && feedThreadId.value !== null,
)

// The store holds the backend's order (newest first); read oldest first.
const chronologicalMessages = computed<SupportStaffMessage[]>(() =>
  feedReady.value ? [...support.staffMessages].reverse() : [],
)

function fromPerson(message: SupportStaffMessage): boolean {
  return ticket.value?.opener?.user_id === message.sender
}

function sentAt(message: SupportStaffMessage): string | null {
  return message.created_at ? formatDateTime(message.created_at, locale.value) : null
}

// The states in which a translation is still on its way. `not_requested`
// is among them: the backend has just queued it (the catch-up).
const IN_FLIGHT = new Set(['preparing', 'not_requested'])

// Per message: true = the other text is on screen (the original of a
// person's message, or what the person reads of a reply).
const flipped = reactive<Record<string, boolean>>({})

function otherText(message: SupportStaffMessage): string | null {
  const tr = message.translation
  if (tr === null || tr.state !== 'ready') return null
  if (fromPerson(message)) {
    return message.original !== null && message.original !== message.body ? message.original : null
  }
  return tr.variant_body ?? null
}

function shownText(message: SupportStaffMessage): string {
  const other = otherText(message)
  if (other !== null && flipped[message.id]) return other
  return message.body ?? message.original ?? ''
}

function toggleLabel(message: SupportStaffMessage): string {
  const on = flipped[message.id] === true
  if (fromPerson(message)) {
    return on
      ? t('staff.support.translation.hideOriginal')
      : t('staff.support.translation.showOriginal')
  }
  return on
    ? t('staff.support.translation.hideClientVersion')
    : t('staff.support.translation.showClientVersion')
}

function toggle(message: SupportStaffMessage): void {
  flipped[message.id] = !flipped[message.id]
}

// The line under a message, or null when there is nothing to say. A state
// the backend may add later reads as "cannot be translated" -- never as
// success.
function translationNote(message: SupportStaffMessage): string | null {
  const tr = message.translation
  if (tr === null || tr.state === 'not_needed') return null
  const person = fromPerson(message)
  if (tr.state === 'ready') {
    if (person) {
      return tr.source_locale
        ? t('staff.support.translation.translatedFrom', { lang: tr.source_locale.toUpperCase() })
        : null
    }
    return t('staff.support.translation.clientReads', { lang: tr.locale.toUpperCase() })
  }
  if (IN_FLIGHT.has(tr.state)) {
    return person
      ? t('staff.support.translation.translating')
      : t('staff.support.translation.translatingForClient')
  }
  if (tr.retryable) {
    return person
      ? t('staff.support.translation.failed')
      : t('staff.support.translation.failedForClient')
  }
  return person
    ? t('staff.support.translation.declined')
    : t('staff.support.translation.declinedForClient')
}

function retryTranslation(message: SupportStaffMessage): void {
  const id = feedThreadId.value
  if (id === null) return
  void support.retryTranslation(id, message.id).then(() => restartTranslationPoll())
}

const { restart: restartTranslationPoll } = useTranslationPoll({
  translating: () =>
    feedReady.value &&
    support.staffMessages.some((m) => m.translation !== null && IN_FLIGHT.has(m.translation.state)),
  refresh: async () => {
    const id = feedThreadId.value
    if (id !== null) await support.fetchStaffMessages(id, { silent: true })
  },
})

// -- Reply ----------------------------------------------------------------------

const canReply = computed<boolean>(() => isMine.value && isOpen.value && !viewingHistory.value)
const composerText = ref('')

async function handleSend(): Promise<void> {
  const text = composerText.value.trim()
  if (text === '' || support.replying) return
  const ok = await support.replyToThread(ticketId.value, text)
  if (!ok) return
  composerText.value = ''
  await loadFeed()
}

const replyErrorText = computed<string | null>(() => {
  const err = support.replyError
  if (err === null) return null
  return err.status === 409 ? t('staff.support.readOnlyHint') : errorMessage(err)
})

// Started last: an immediate watcher runs at once, and load() reaches
// everything declared above.
watch(ticketId, () => void load(), { immediate: true })
watch(
  isOpen,
  (open) => {
    if (open) void support.fetchOperators()
  },
  { immediate: true },
)
</script>

<template>
  <div class="stck">
    <CLoader v-if="support.ticketLoading && ticket === null" centered extent="page" />

    <CEmptyState
      v-else-if="support.ticketError && ticket === null"
      tone="danger"
      :title="
        support.ticketError.status === 404
          ? t('staff.support.ticketGone')
          : t('staff.support.feedErrorTitle')
      "
      :description="
        support.ticketError.status === 404 ? undefined : errorMessage(support.ticketError)
      "
    >
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else-if="ticket !== null">
      <div class="stck__head">
        <h2 class="ds-section-title stck__person">{{ personName(ticket.opener) }}</h2>
        <CBadge
          :variant="statusVariant(ticket.status)"
          :text="t(`staff.support.status.${ticket.status}`)"
        />
      </div>
      <dl class="stck__facts">
        <dt>{{ t('staff.support.topic') }}</dt>
        <dd>{{ t(`inv.support.topics.${ticket.topic}`) }}</dd>
        <dt>{{ t('staff.support.appealed') }}</dt>
        <dd>{{ ticket.created_at ? formatDateTime(ticket.created_at, locale) : '' }}</dd>
        <dt>{{ t('staff.support.taker') }}</dt>
        <dd>
          {{
            ticket.claimed_by === null
              ? t('staff.support.unclaimed')
              : personName(ticket.claimed_by)
          }}
        </dd>
        <template v-if="ticket.opener?.email">
          <dt>{{ t('staff.support.email') }}</dt>
          <dd>{{ ticket.opener.email }}</dd>
        </template>
        <!-- H41: who resolved it. Once the ticket is no longer resolved (back
             at work, or closed another way since) it is the LAST resolver. -->
        <template v-if="ticket.resolved_by">
          <dt>
            {{
              ticket.status === 'resolved'
                ? t('staff.support.resolver')
                : t('staff.support.lastResolver')
            }}
          </dt>
          <dd>{{ personName(ticket.resolved_by) }}</dd>
        </template>
        <dt>{{ t('staff.support.ticketIdLabel') }}</dt>
        <dd class="stck__mono">{{ ticket.id }}</dd>
      </dl>

      <!-- H41: the person's rating -- the stars, the comment as written
           (never translated) with the person's interface language, the
           likely language of the text, and the operator it is about. -->
      <section
        v-if="ticket.rating"
        class="stck__rating"
        :aria-label="t('staff.support.rating.title')"
      >
        <p class="stck__rating-stars">
          <span :aria-label="t('staff.support.rating.stars', { n: ticket.rating.stars })">
            {{ starsText(ticket.rating.stars) }}
          </span>
          <span v-if="ticket.rating.rated_at" class="ds-note">
            {{ formatDateTime(ticket.rating.rated_at, locale) }}
          </span>
        </p>
        <blockquote
          v-if="ticket.rating.comment"
          class="stck__rating-comment"
          :lang="ticket.rating.comment_locale ?? undefined"
        >
          {{ ticket.rating.comment }}
        </blockquote>
        <p v-if="ticket.rating.comment && ticket.rating.comment_locale" class="ds-note">
          {{
            t('staff.support.rating.commentLocale', {
              lang: ticket.rating.comment_locale.toUpperCase(),
            })
          }}
        </p>
        <p v-if="ticket.rating.rated_resolver" class="ds-note">
          {{ t('staff.support.rating.about', { name: personName(ticket.rating.rated_resolver) }) }}
        </p>
      </section>

      <!-- Actions on the ticket -->
      <div class="stck__actions">
        <template v-if="isOpen">
          <CButton
            v-if="isUnclaimed"
            variant="primary"
            size="sm"
            inline
            :loading="support.acting === 'claim'"
            :disabled="support.acting !== null"
            @click="claim"
          >
            {{ t('staff.support.claim') }}
          </CButton>
          <CButton
            v-if="isMine"
            variant="outline"
            size="sm"
            inline
            :loading="support.acting === 'release'"
            :disabled="support.acting !== null"
            @click="release"
          >
            {{ t('staff.support.release') }}
          </CButton>
        </template>
        <CButton
          v-else
          variant="primary"
          size="sm"
          inline
          :loading="support.acting === 'reopen'"
          :disabled="support.acting !== null"
          @click="reopen"
        >
          {{ t('staff.support.reopen') }}
        </CButton>
      </div>

      <div
        v-if="isOpen"
        class="stck__actions"
        role="group"
        :aria-label="t('staff.support.closeAs')"
      >
        <span class="ds-note">{{ t('staff.support.closeAs') }}</span>
        <CButton
          v-for="status in SUPPORT_CLOSING_STATUSES"
          :key="status"
          :variant="status === 'spam' ? 'danger' : 'outline'"
          size="sm"
          inline
          :loading="support.acting === 'status'"
          :disabled="support.acting !== null"
          @click="close(status)"
        >
          {{ t(`staff.support.close.${status}`) }}
        </CButton>
      </div>

      <form v-if="isOpen" class="stck__assign" @submit.prevent="assign">
        <CSelect
          v-model="assignee"
          :label="t('staff.support.assignTo')"
          :placeholder="t('staff.support.assignPlaceholder')"
          :options="assigneeOptions"
          :error="support.operatorsError ? errorMessage(support.operatorsError) : undefined"
        />
        <CButton
          variant="outline"
          size="sm"
          inline
          :loading="support.acting === 'assign'"
          :disabled="assignee === '' || support.acting !== null"
        >
          {{ t('staff.support.assign') }}
        </CButton>
      </form>

      <CAlert v-if="actionErrorText" tone="danger">{{ actionErrorText }}</CAlert>

      <CAlert v-if="isOpen && isUnclaimed" tone="info">{{
        t('staff.support.readOnlyHint')
      }}</CAlert>
      <CAlert v-else-if="isOpen && !isMine" tone="info">
        {{ t('staff.support.foreignHint') }}
      </CAlert>

      <!-- The person's history: a second, read-only feed -->
      <div v-if="ticket.history_thread_id !== null" class="stck__actions">
        <CButton variant="link" size="sm" inline @click="showHistory(!viewingHistory)">
          {{ viewingHistory ? t('staff.support.backToTicket') : t('staff.support.history') }}
        </CButton>
      </div>
      <CAlert v-if="viewingHistory" tone="info">{{ t('staff.support.historyHint') }}</CAlert>

      <!-- The feed and the composer (K51) -->
      <section class="ds-thread stck__thread" :aria-label="personName(ticket.opener)">
        <CLoader v-if="support.staffMessagesLoading" centered />

        <CEmptyState
          v-else-if="support.staffMessagesError"
          tone="danger"
          :title="t('staff.support.feedErrorTitle')"
          :description="errorMessage(support.staffMessagesError)"
        >
          <template #actions>
            <CButton variant="outline" size="sm" inline @click="loadFeed">
              {{ t('common.retry') }}
            </CButton>
          </template>
        </CEmptyState>

        <CEmptyState
          v-else-if="chronologicalMessages.length === 0"
          :title="t('staff.support.noMessages')"
        />

        <ul v-else class="ds-thread__feed" role="log" aria-live="polite" tabindex="0">
          <li
            v-for="message in chronologicalMessages"
            :key="message.id"
            class="ds-message"
            :data-from="fromPerson(message) ? 'other' : 'own'"
          >
            <span class="ds-message__author">
              {{
                fromPerson(message)
                  ? t('staff.support.sender.client')
                  : t('staff.support.sender.operator')
              }}
            </span>
            <p class="ds-message__bubble">{{ shownText(message) }}</p>
            <p v-if="translationNote(message)" class="stck__tr-note">
              {{ translationNote(message) }}
            </p>
            <span
              v-if="otherText(message) !== null || message.translation?.retryable"
              class="stck__tr-actions"
            >
              <CButton
                v-if="otherText(message) !== null"
                variant="link"
                size="sm"
                inline
                @click="toggle(message)"
              >
                {{ toggleLabel(message) }}
              </CButton>
              <CButton
                v-if="message.translation?.retryable"
                variant="outline"
                size="sm"
                inline
                :loading="support.retryingTranslation[message.id]"
                :disabled="support.retryingTranslation[message.id]"
                @click="retryTranslation(message)"
              >
                {{ t('staff.support.translation.retry') }}
              </CButton>
            </span>
            <p v-if="support.retryTranslationErrors[message.id]" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>{{ t('staff.support.translation.retryError') }}</span>
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

        <form v-if="canReply" class="ds-composer" @submit.prevent="handleSend">
          <div class="ds-field ds-composer__input">
            <label class="ds-sr-only" for="stck-message">{{
              t('staff.support.placeholder')
            }}</label>
            <textarea
              id="stck-message"
              v-model="composerText"
              class="ds-input"
              rows="2"
              maxlength="4000"
              :placeholder="t('staff.support.placeholder')"
              :disabled="support.replying"
              :aria-invalid="replyErrorText ? 'true' : undefined"
              :aria-describedby="replyErrorText ? 'stck-message-error' : undefined"
            />
            <p v-if="replyErrorText" id="stck-message-error" class="ds-field__error">
              <AlertTriangle size="sm" />
              <span>{{ replyErrorText }}</span>
            </p>
          </div>
          <CButton
            variant="primary"
            inline
            :loading="support.replying"
            :disabled="composerText.trim() === '' || support.replying"
          >
            {{ t('staff.support.send') }}
          </CButton>
        </form>
      </section>
    </template>
  </div>
</template>

<style scoped>
.stck {
  display: grid;
  gap: var(--space-4);
  align-content: start;
  min-inline-size: 0;
}
.stck__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.stck__person {
  overflow-wrap: anywhere;
}
.stck__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-3);
  margin: 0;
  font-size: var(--fs-sm);
}
.stck__facts dt {
  color: var(--text-secondary);
}
.stck__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.stck__mono {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}
.stck__rating {
  display: grid;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}
.stck__rating-stars {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--fs-lg);
  color: var(--accent, currentColor);
}
.stck__rating-comment {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.stck__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.stck__assign {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--space-2);
}

/* The translation state under a message, and its two actions (H39). */
.stck__tr-note {
  margin: 0;
  font-size: var(--fs-xs);
  font-style: italic;
  color: var(--text-secondary);
}
.stck__tr-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* The screen gives the thread its height (K51). */
.stck__thread {
  block-size: calc(var(--center-lg) + var(--center-md));
}
</style>
