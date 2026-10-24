<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- InvestorSupportView (Ф-2, shared TASK-39 item 4)
// =============================================================================
//
// One conversation: feed + composer. Reached from the Support tile in
// InvestorMoreView -> /investor/support. The frame's header holds the title,
// the back control and the refresh action (this is a detail screen reached
// from "More", not a tab-bar top level); the conversation is the system's
// chat thread and composer (K51).
//
// TASK-39 item 4: also mounted at /agent/support (the Support row of
// Settings) and /company/support (a row inside
// CompanySettingsView) -- same "shared component lives physically
// under views/investor/, other shells' route records import it
// directly" convention as PortfolioView / NotificationsInboxView /
// InstallmentPlansView. The backend gates every /api/v1/support/*
// route on plain get_current_user[_write] with no role check
// (backend/app/modules/support/router.py), so this was a pure
// frontend-surface gap, not a backend change.
//
// SHELL-SAFETY AUDIT (TASK-39 item 4).
//   Everything else in this file is role-agnostic: the store/api layer
//   carry no role assumption, and the visible copy ("Write to support
//   here...", sender labels, error text) reads fine for any role. The
//   ONE thing that was NOT shell-safe: goBack()'s deep-link fallback
//   hardcoded the buyer's old More screen and the back-link label said
//   "Back to more" -- both true only for investor/agent (which have a
//   More tab) and wrong for company (no More tab; this screen is
//   reached from a Settings row instead). Fixed below by reading
//   route.meta.shell (getShell) to pick the Settings route of the shell /
//   (company-settings for a company); the back control is the frame's.
//
// STATE IS THE STORE'S, EXCEPT ONE LOCAL ID.
//   `knownThreadId` is the only piece of state this component owns:
//   the store has no single "my thread id" field on its own (`thread`
//   is only populated by openThread(); `threads` is the list used
//   only to detect existence). This screen is the one place that
//   decides "which thread am I looking at" and holds it locally, per
//   the api/support.ts docs on threads.support.ts (Ф-1 -- api-slice
//   and store review).
//
// THE FOURTEEN-STATE MACHINE FROM THE GATE, COLLAPSED INTO FOUR
// COMPUTEDS (initLoading / initError / hasThread / showInvite) plus
// the store's own feedLoading/feedError/sending/threadError/sendError.
// Nothing here re-derives what the store already tracks; this file
// only composes it into what the template needs to branch on.
//
// STAKE A (gate): opening + first send is ONE button for the person,
// two store calls underneath. If openThread() succeeds and
// sendMessage() then fails, the screen does NOT fall back to the
// invite state -- `knownThreadId` is set the moment openThread()
// resolves, before sendMessage() is even attempted, so a retry after
// that failure calls sendMessage() alone. This is exactly the
// "thread exists, box has text, error shown" state named on the gate
// (state 10 in the plan) and it is reachable, not theoretical: it is
// what happens whenever comms answers the create call but the send
// call after it times out.
//
// STAKE C (gate): the reverse lives HERE, in `chronologicalMessages`,
// not in the store. The store hands back exactly what comms sent --
// see stores/support.ts's own header on why it never mutates that
// order -- and reversing a fresh array copy on read is the one place
// that decision was always meant to be undone.
//
// STAKE D (gate): a failed markRead is not surfaced at all. It is
// fired after every successful feed load and its result/error is
// left in the store (`support.markError`) for devtools, never read
// here. Read-receipt bookkeeping is not something the person can
// retry or is even aware they did -- showing it as a conversation
// error would teach them to distrust a message that DID go through.
//
// 404-ON-KNOWN-THREAD IS NOT TREATED AS UNREACHABLE (gate note).
//   comms logs support_thread_repointed for a real, if rare, case: a
//   rebuilt comms handing out a fresh thread id for the same user.
//   This screen does not special-case that 404 or silently re-open --
//   re-pointing the local pointer is the BACKEND's job (service.py
//   _remember_thread), and inventing a client-side recovery here
//   would be new, unordered logic on top of stake A's contract. A
//   404 here falls into the same generic error text as any other
//   failure of that action.
//
// Ф-3 CROSS-REFERENCE (gate decision, develop B).
//   views/staff/StaffSupportView.vue duplicates the message-bubble
//   rendering and composer markup below (`.isup__feed`/`.isup__msg*`/
//   `.isup__composer*`) rather than sharing a component with this
//   file. Considered and rejected: extracting would have meant
//   editing this already-shipped, working screen for the sake of a
//   screen that did not exist yet, to save two small presentational
//   blocks that already differ in submit logic (compound open+send
//   here vs a plain reply there) and in how "which side is this
//   message on" is computed (identity here vs thread.client there).
//   A comment pointing both ways is the agreed guard against drift:
//   if you change the bubble markup or the composer's error/disabled
//   states here, check StaffSupportView's copy too.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, RefreshCw } from '@/components/ui/icons'
import { CButton, CEmptyState, CLoader } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { getShell } from '@/router/helpers'
import { formatDateTime } from '@/utils/format'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import type { SupportActionError } from '@/stores/support'
import type { SupportMessageResponse } from '@/api/support'

const { t, locale } = useI18n()
const route = useRoute()
const support = useSupportStore()
const auth = useAuthStore()

// The one thread this screen is showing. null = no request yet.
const knownThreadId = ref<string | null>(null)
const composerText = ref('')

const myUserId = computed<string | null>(() => auth.user?.id ?? null)

const hasThread = computed<boolean>(() => knownThreadId.value !== null)

// Empty state covers BOTH "never opened a request" and "opened one,
// nothing landed in it yet" (state 5 on the gate plan -- reachable
// whenever openThread succeeded and the send after it did not). The
// short-circuit on !hasThread is what keeps this true before a
// thread exists without waiting on feed flags that were never set.
const showInvite = computed<boolean>(
  () =>
    !hasThread.value ||
    (!support.messagesLoading && !support.messagesError && support.messages.length === 0),
)

// Store hands back comms' own order ("newest first"); this screen
// reads "oldest first". A fresh copy every time -- see stake C.
const chronologicalMessages = computed<SupportMessageResponse[]>(() =>
  [...support.messages].reverse(),
)

// Whichever of the two compound-action errors is live right now.
// Mutually exclusive in practice: threadError is only ever set while
// knownThreadId is still null (the open half of stake A), sendError
// only once it is no longer null.
const composerError = computed<SupportActionError | null>(
  () => support.threadError ?? support.sendError,
)

function sentAt(message: SupportMessageResponse): string | null {
  return message.created_at ? formatDateTime(message.created_at, locale.value) : null
}

function isMine(message: SupportMessageResponse): boolean {
  return myUserId.value !== null && message.sender === myUserId.value
}

/**
 * 502/504 (comms unreachable) reads as "try later"; everything else
 * -- a 409 conflict, an unmapped 4xx, a network error -- reads as a
 * plain retry prompt. Applied uniformly to every error surface on
 * this screen (init / feed / send), not only the send action the
 * handoff named, so "comms is down" says the same thing everywhere
 * it shows up.
 */
function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) {
    return t('inv.support.errorUnavailable')
  }
  return t('inv.support.errorGeneric')
}

async function loadFeed(): Promise<void> {
  const id = knownThreadId.value
  if (id === null) return
  await support.fetchMessages(id)
  // Fire-and-forget: a failed mark-read stays in support.markError for
  // devtools only -- see stake D above.
  if (!support.messagesError) {
    void support.markRead(id)
  }
}

async function boot(): Promise<void> {
  await support.fetchThreads()
  if (support.threadsError) return
  const existing = support.threads[0]
  if (existing !== undefined) {
    knownThreadId.value = existing.id
    await loadFeed()
  }
}

async function handleSend(): Promise<void> {
  const text = composerText.value.trim()
  if (text === '' || support.sending) return

  if (knownThreadId.value === null) {
    await support.openThread()
    if (support.threadError) return // stays uncommitted -- box keeps its text
    knownThreadId.value = support.thread?.id ?? null
    if (knownThreadId.value === null) return // defensive; threadError would be set otherwise
  }

  await support.sendMessage(text)
  if (support.sendError) return // box keeps its text -- see stake A

  composerText.value = ''
  await loadFeed()
}

function retryInit(): void {
  void boot()
}

function retryFeed(): void {
  void loadFeed()
}

// Deep-link fallback target, one per shell that hosts this screen.
// investor/agent land back on their Settings tab (where the Support row
// lives); company has no such row -- its entry point is a row inside
// Settings, so that's where a deep-linked company user goes back to.
// The final return serves TWO cases at once: the investor shell (the
// normal, reachable path) and a shell of undefined -- the latter only
// if this screen were ever mounted outside a shell wrapper, which no
// current route does. Both want the investor More tab, so they share
// one branch rather than pretending the second one is unreachable.
const backFallbackRouteName = computed<string>(() => {
  const shell = getShell(route)
  if (shell === 'agent') return 'agent-settings'
  if (shell === 'company') return 'company-settings'
  return 'investor-settings'
})

// Same history-aware pattern as the other drill-down screens: one step back so
// the screen this was reached from restores its scroll for free, the shell's
// Settings only for a deep-linked entry.
useScreenHeader({
  title: () => t('inv.support.title'),
  back: () => (window.history.state?.back ? true : { name: backFallbackRouteName.value }),
  actions: () =>
    hasThread.value
      ? [
          {
            id: 'refresh',
            label: t('inv.support.refresh'),
            icon: RefreshCw,
            onClick: () => {
              if (!support.messagesLoading) retryFeed()
            },
          },
        ]
      : [],
})

onMounted(() => {
  void boot()
})
</script>

<template>
  <div class="isup">
    <!-- INIT: determining whether a request already exists -->
    <CLoader v-if="support.threadsLoading" centered extent="page" />

    <!-- INIT error: never falls back to the invite -- a network -->
    <!-- failure must not look like "you have no history yet". -->
    <CEmptyState
      v-else-if="support.threadsError"
      tone="danger"
      :title="t('inv.support.initErrorTitle')"
      :description="errorMessage(support.threadsError)"
    >
      <template #actions>
        <CButton variant="primary" size="sm" inline @click="retryInit">
          {{ t('inv.support.initErrorRetry') }}
        </CButton>
      </template>
    </CEmptyState>

    <!-- The conversation: the feed and the composer (K51) -->
    <section v-else class="ds-thread isup__thread" :aria-label="t('inv.support.title')">
      <div
        v-if="support.messagesLoading || support.messagesError || showInvite"
        class="isup__state"
      >
        <CLoader v-if="support.messagesLoading" centered />

        <CEmptyState
          v-else-if="support.messagesError"
          tone="danger"
          :title="t('inv.support.feedErrorTitle')"
          :description="errorMessage(support.messagesError)"
        >
          <template #actions>
            <CButton variant="outline" size="sm" inline @click="retryFeed">
              {{ t('inv.support.feedErrorRetry') }}
            </CButton>
          </template>
        </CEmptyState>

        <CEmptyState v-else :title="t('inv.support.invite')" />
      </div>

      <ul v-else class="ds-thread__feed" role="log" aria-live="polite" tabindex="0">
        <li
          v-for="message in chronologicalMessages"
          :key="message.id"
          class="ds-message"
          :data-from="isMine(message) ? 'own' : 'other'"
        >
          <span v-if="isMine(message)" class="ds-sr-only">{{ t('inv.support.sender.me') }}</span>
          <span v-else class="ds-message__author">{{ t('inv.support.sender.operator') }}</span>
          <p class="ds-message__bubble">
            {{ message.body }}
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
            :aria-invalid="composerError ? 'true' : undefined"
            :aria-describedby="composerError ? 'isup-message-error' : undefined"
          />
          <p v-if="composerError" id="isup-message-error" class="ds-field__error">
            <AlertTriangle size="sm" />
            <span>{{ errorMessage(composerError) }}</span>
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
  </div>
</template>

<style scoped>
.isup {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
}

/* The screen gives the thread its height (K51). */
.isup__thread {
  block-size: calc(var(--center-lg) + var(--center-md));
}

/* A state (loading, error, nothing yet) stands where the feed will be. */
.isup__state {
  flex: 1 1 auto;
  display: grid;
  place-items: center;
  min-block-size: 0;
}
</style>
