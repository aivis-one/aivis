<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSupportView (Ф-3)
// =============================================================================
//
// One route (/staff/support): the queue by default, a conversation
// panel in place of it once a card is tapped. No child route for a
// single thread -- see STAKE A below for why that is deliberate, not
// a shortcut.
//
// Reached from a nav-item in StaffMoreView, same tier as
// StaffAgentAppsView / StaffAvatarView (both outside STAFF_TABS).
// Neither of those has a CBackLink or an inline <h1> -- 14 of 15
// screens in this cabinet skip both; the one exception
// (StaffCompanyDetailView) is a real routed detail entity with tabs.
// This screen follows the dominant convention: no page title of its own,
// a short one-line hint instead (an info Alert, as StaffAgentAppsView has).
// Its refresh is a title-side action, so it stands in the frame's header.
//
// STAKE A (gate): one route, not a routed thread id.
//   The new GET .../messages endpoint is gated ONLY by "does this
//   thread exist" (_require_known_thread) -- NOT by whether the
//   caller's own queue would ever have shown it. list_operator_threads
//   filters visibility server-side; the read endpoint does not. If a
//   thread id were reachable as a route param, a plain operator could
//   type a colleague's claimed thread's id into the URL bar and read
//   a conversation their own queue never surfaced. Keeping the
//   selection as component-local state driven only by rows already
//   present in `support.queue` (itself already visibility-filtered)
//   closes that door without adding a check the backend doesn't
//   already need for its own reasons. This is a narrower answer than
//   the handoff's "без нового вида в нижней навигации" alone requires
//   -- named here because it wasn't asked for, it was found.
//
// STAKE B (gate): a COPY of Ф-2's bubbles/composer, not a shared
//   component. See the cross-reference comment in
//   views/investor/InvestorSupportView.vue's own header. Cost of
//   extracting was named and rejected: it would have meant editing an
//   already-shipped screen for one that did not exist yet, to save
//   two small blocks that differ in submit logic and in how "which
//   side" is computed anyway.
//
// STAKE C (gate): side is computed from `message.sender ===
//   selectedThread.client`, never from identity. comms' own message
//   body carries only `sender` (a bare uuid, no role) -- verified by
//   re-reading comms' _message_out serializer -- so a message from a
//   PREVIOUS operator on a transferred thread lands on the same
//   (right) side as one from the current viewer, unlabelled by name.
//   Accepted price for a proof-of-concept tool; T-75 (names instead
//   of uuids) is the registered fix for showing WHICH operator wrote
//   it, not for which SIDE it is on -- that question is answered
//   correctly already, by the same rule comms itself uses in
//   notify_new_message.
//
// STATUS ACTIONS ARE NOT GATED ON "MINE" (found while re-reading
//   service.py for this same question). comms lets ANY active
//   operator change ANY section thread's status, claimed by them or
//   not -- service.py documents this as accepted, not a gap. This
//   view narrows it anyway: status controls render on ALREADY-CLAIMED
//   rows (mine or a colleague's, the latter visible to a supervisor
//   only), never on a still-unclaimed pool row. That narrowing is
//   this screen's own choice, not a backend limit -- closing a
//   request nobody has even looked at yet has no described use case
//   here, so it isn't built, but it is not being called impossible
//   either.
//
// "CLAIMED, QUEUE NOT YET REFRESHED" (gate requirement).
//   claimThread() mutates the SAME row object in `support.queue` in
//   place (store's _replaceQueueRow) -- it does not remove/reinsert
//   it and does not trigger a fetchQueue(). The three group lists
//   below (poolRows/mineRows/foreignRows) are plain `computed`
//   filters over that one array, so the instant the claim resolves,
//   the row reclassifies from "unclaimed" to "mine" in the same
//   render -- no network round-trip needed to see it move. The one
//   thing that does NOT update until a real fetchQueue(): `unread`
//   (claim's response never carries it -- store preserves whatever
//   the row had) and the row's position in the server's own
//   recency order. Neither reads as loss: an unclaimed row never
//   carried `unread` to begin with, so the absence continues exactly
//   as it was: absent means "not applicable", never a lied-about
//   zero.
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, RefreshCw } from '@/components/ui/icons'
import { CBackLink, CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import StaffAlert from '@/components/staff/StaffAlert.vue'
import StaffListSkeleton from '@/components/staff/StaffListSkeleton.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { formatDateTime } from '@/utils/format'
import { useSupportStore } from '@/stores/support'
import { useAuthStore } from '@/stores/auth'
import type { SupportActionError } from '@/stores/support'
import type { SupportMessageResponse, SupportOperatorThreadRow } from '@/api/support'

const { t, locale } = useI18n()
const support = useSupportStore()
const auth = useAuthStore()

const myOperatorId = computed<string | null>(() => auth.user?.id ?? null)

// The queue's refresh is the screen's one title-side action, so the frame's header
// carries it (an icon button, named by its label); the open conversation has none.
useScreenHeader({
  actions: () =>
    openThreadId.value === null
      ? [
          {
            id: 'refresh',
            label: t('staff.support.refresh'),
            icon: RefreshCw,
            onClick: retryQueue,
          },
        ]
      : [],
})

// -- Queue --------------------------------------------------------------

const poolRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee === null),
)
const mineRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee === myOperatorId.value),
)
// Non-empty only for a supervisor: a plain operator's own queue never
// contains a colleague's claimed thread at all (comms' own visibility
// filter), so this group is naturally empty for everyone else.
const foreignRows = computed<SupportOperatorThreadRow[]>(() =>
  support.queue.filter((row) => row.assignee !== null && row.assignee !== myOperatorId.value),
)

function retryQueue(): void {
  void support.fetchQueue()
}

async function handleClaim(threadId: string): Promise<void> {
  await support.claimThread(threadId)
}

// -- Selection: which conversation panel is open, if any ----------------

const openThreadId = ref<string | null>(null)

// Derived LIVE from the queue array, not a separate fetched copy --
// see stake A header: the moment claimThread() updates a row, this
// picks up the change for free, in the same render.
const selectedThread = computed<SupportOperatorThreadRow | null>(
  () => support.queue.find((row) => row.id === openThreadId.value) ?? null,
)

const isMine = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee === myOperatorId.value,
)
const isPool = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee === null,
)
const isForeign = computed<boolean>(
  () =>
    selectedThread.value !== null &&
    selectedThread.value.assignee !== null &&
    selectedThread.value.assignee !== myOperatorId.value,
)

function openThread(threadId: string): void {
  openThreadId.value = threadId
  void support.fetchStaffMessages(threadId)
}

function closeThread(): void {
  openThreadId.value = null
}

function sentAt(message: SupportMessageResponse): string | null {
  return message.created_at ? formatDateTime(message.created_at, locale.value) : null
}

function retryFeed(): void {
  if (openThreadId.value !== null) {
    void support.fetchStaffMessages(openThreadId.value)
  }
}

// Store hands back comms' own order ("newest first"); read "oldest
// first" here -- same rule as Ф-2, re-applied rather than shared
// (stake B).
const chronologicalMessages = computed<SupportMessageResponse[]>(() =>
  [...support.staffMessages].reverse(),
)

// -- Who is asking (T-75) -----------------------------------------------
//
// TWO IDENTIFIERS ON THIS SCREEN, and they are not interchangeable. The
// THREAD id is what the operator quotes to a colleague or looks up in
// comms, and it keeps its place. The CLIENT id identifies the person and
// was never on screen at all -- it appears now, but only underneath the
// name, and only when there is no name to show.
//
// The join rule is StaffUsersView.fullName's, deliberately: same section
// of the product, same way of rendering a person. It differs in the
// fallback only, because "—" tells an operator nothing they can act on
// whereas an email or a uuid identifies the person they are answering.
function clientName(row: SupportOperatorThreadRow): string {
  const parts = [row.client_profile?.first_name, row.client_profile?.last_name].filter(Boolean)
  if (parts.length > 0) return parts.join(' ')
  return row.client_profile?.email ?? row.client
}

// True when the line above is already the client's identifier, so the
// secondary line would repeat it.
function clientNameIsIdentifier(row: SupportOperatorThreadRow): boolean {
  return clientName(row) === row.client
}

// STAKE C: side by comparison with the thread's fixed client id, never
// by identity -- see header.
function isRight(message: SupportMessageResponse): boolean {
  return selectedThread.value !== null && message.sender !== selectedThread.value.client
}

function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) {
    return t('staff.support.errorUnavailable')
  }
  return t('staff.support.errorGeneric')
}

// -- Reply ----------------------------------------------------------------

const composerText = ref('')

async function handleSend(): Promise<void> {
  const id = openThreadId.value
  const text = composerText.value.trim()
  if (id === null || text === '' || support.replying[id]) return

  await support.replyToThread(id, text)
  if (support.replyErrors[id]) return

  composerText.value = ''
  void support.fetchStaffMessages(id)
}

// -- Status -----------------------------------------------------------

// Only rendered on an ALREADY-CLAIMED thread (mine or a colleague's) --
// see header on why a still-unclaimed pool row gets none.
const canChangeStatus = computed<boolean>(
  () => selectedThread.value !== null && selectedThread.value.assignee !== null,
)

async function handleResolve(): Promise<void> {
  const id = openThreadId.value
  if (id === null) return
  await support.setThreadStatus(id, 'resolved')
}

async function handleClose(): Promise<void> {
  const id = openThreadId.value
  if (id === null) return
  await support.setThreadStatus(id, 'closed')
}

onMounted(() => {
  void support.fetchQueue()
})
</script>

<template>
  <div class="ssup">
    <!-- ============================== QUEUE ============================== -->
    <template v-if="openThreadId === null">
      <StaffAlert tone="info">
        {{ t('staff.support.hint') }}
      </StaffAlert>

      <StaffListSkeleton v-if="support.queueLoading && !support.queueLoaded" />

      <CEmptyState
        v-else-if="support.queueError"
        tone="danger"
        :description="errorMessage(support.queueError)"
      >
        <template #actions>
          <CButton variant="primary" size="sm" inline @click="retryQueue">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <CEmptyState v-else-if="support.queue.length === 0" :title="t('staff.support.empty')" />

      <div v-else class="ssup__groups">
        <section v-if="poolRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupPool') }}
          </h2>
          <!-- Pool rows never carry an unread count, and that is a
               property of comms rather than a gap on this screen: the
               count is attached only to threads the operator takes part
               in, and nobody takes part in an unclaimed one. Said on
               screen because its absence is otherwise read as a bug. -->
          <p class="ssup__group-note">{{ t('staff.support.poolNoUnread') }}</p>
          <ul class="ds-rows">
            <li v-for="row in poolRows" :key="row.id" class="ds-row ssup__row">
              <span class="ds-row__body">
                <button type="button" class="ds-row__link ssup__open" @click="openThread(row.id)">
                  <span class="ds-row__title">{{ clientName(row) }}</span>
                </button>
                <span class="ds-row__meta">
                  {{ row.id.slice(0, 8) }}
                  <template v-if="row.last_message_at">
                    &bull; {{ new Date(row.last_message_at).toLocaleString() }}
                  </template>
                </span>
                <StaffAlert v-if="support.claimErrors[row.id]" tone="danger">
                  {{
                    support.claimErrors[row.id]?.status === 409
                      ? t('staff.support.claimConflict')
                      : errorMessage(support.claimErrors[row.id])
                  }}
                </StaffAlert>
              </span>
              <span class="ds-row__trail">
                <CButton
                  variant="primary"
                  size="sm"
                  inline
                  :loading="support.claiming[row.id]"
                  :disabled="support.claiming[row.id]"
                  @click="handleClaim(row.id)"
                >
                  {{ t('staff.support.claim') }}
                </CButton>
              </span>
            </li>
          </ul>
        </section>

        <section v-if="mineRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupMine') }}
          </h2>
          <ul class="ds-rows">
            <li v-for="row in mineRows" :key="row.id" class="ds-row ssup__row">
              <span class="ds-row__body">
                <button type="button" class="ds-row__link ssup__open" @click="openThread(row.id)">
                  <span class="ds-row__title">{{ clientName(row) }}</span>
                </button>
                <span class="ds-row__meta">{{ row.id.slice(0, 8) }}</span>
              </span>
              <span class="ds-row__trail">
                <CBadge
                  v-if="typeof row.unread === 'number' && row.unread > 0"
                  variant="primary"
                  :text="String(row.unread)"
                />
              </span>
            </li>
          </ul>
        </section>

        <section v-if="foreignRows.length > 0" class="ssup__group">
          <h2 class="ssup__group-title">
            {{ t('staff.support.groupForeign') }}
          </h2>
          <ul class="ds-rows">
            <li v-for="row in foreignRows" :key="row.id" class="ds-row ssup__row">
              <span class="ds-row__body">
                <button type="button" class="ds-row__link ssup__open" @click="openThread(row.id)">
                  <span class="ds-row__title">{{ clientName(row) }}</span>
                </button>
                <span class="ds-row__meta">{{ row.id.slice(0, 8) }}</span>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </template>

    <!-- =========================== CONVERSATION =========================== -->
    <template v-else>
      <!-- The conversation is a state of this screen, not a route (stake A), so its
           way back is the screen's own: the back button (K01 ghost with the arrow). -->
      <div>
        <CBackLink :label="t('staff.support.backToQueue')" @click="closeThread" />
      </div>

      <CEmptyState v-if="selectedThread === null" :title="t('staff.support.empty')" />
      <!-- The row left the queue mid-view (a colleague's claim
           changed visibility, or a refresh dropped it). Reading is
           still allowed by the backend, but this screen has nothing
           left in `support.queue` to gate actions against, so it
           sends the person back rather than guess. -->

      <template v-else>
        <div class="ssup__panel-head">
          <h2 class="ssup__panel-client">{{ clientName(selectedThread) }}</h2>
          <p class="ssup__panel-ids">
            <span v-if="!clientNameIsIdentifier(selectedThread)">
              {{ selectedThread.client }}
            </span>
            <span>
              {{ t('staff.support.threadId', { id: selectedThread.id.slice(0, 8) }) }}
            </span>
          </p>
        </div>

        <div v-if="isMine || isForeign" class="ssup__actions">
          <CButton
            v-if="canChangeStatus"
            variant="outline"
            size="sm"
            inline
            :loading="support.changingStatus[selectedThread.id]"
            :disabled="support.changingStatus[selectedThread.id]"
            @click="handleResolve"
          >
            {{ t('staff.support.statusResolve') }}
          </CButton>
          <CButton
            v-if="canChangeStatus"
            variant="outline"
            size="sm"
            inline
            :loading="support.changingStatus[selectedThread.id]"
            :disabled="support.changingStatus[selectedThread.id]"
            @click="handleClose"
          >
            {{ t('staff.support.statusClose') }}
          </CButton>
        </div>
        <StaffAlert v-if="support.statusErrors[selectedThread.id]" tone="danger">
          {{ errorMessage(support.statusErrors[selectedThread.id]) }}
        </StaffAlert>

        <div v-if="isPool" class="ssup__actions">
          <p class="ssup__note">{{ t('staff.support.readOnlyHint') }}</p>
          <CButton
            variant="primary"
            size="sm"
            inline
            :loading="support.claiming[selectedThread.id]"
            :disabled="support.claiming[selectedThread.id]"
            @click="handleClaim(selectedThread.id)"
          >
            {{ t('staff.support.claim') }}
          </CButton>
        </div>
        <StaffAlert v-if="isPool && support.claimErrors[selectedThread.id]" tone="danger">
          {{
            support.claimErrors[selectedThread.id]?.status === 409
              ? t('staff.support.claimConflict')
              : errorMessage(support.claimErrors[selectedThread.id])
          }}
        </StaffAlert>

        <StaffAlert v-if="isForeign" tone="info">
          {{ t('staff.support.foreignHint') }}
        </StaffAlert>

        <!-- The feed and the composer (K51) -->
        <section class="ds-thread ssup__thread" :aria-label="clientName(selectedThread)">
          <div v-if="support.staffMessagesLoading" class="ssup__state">
            <CLoader :size="24" />
          </div>

          <CEmptyState
            v-else-if="support.staffMessagesError"
            tone="danger"
            :title="t('staff.support.feedErrorTitle')"
            :description="errorMessage(support.staffMessagesError)"
          >
            <template #actions>
              <CButton variant="outline" size="sm" inline @click="retryFeed">
                {{ t('common.retry') }}
              </CButton>
            </template>
          </CEmptyState>

          <CEmptyState
            v-else-if="chronologicalMessages.length === 0"
            :title="t('staff.support.empty')"
          />

          <ul v-else class="ds-thread__feed" role="log" aria-live="polite" tabindex="0">
            <li
              v-for="message in chronologicalMessages"
              :key="message.id"
              class="ds-message"
              :data-from="isRight(message) ? 'own' : 'other'"
            >
              <span class="ds-message__author">
                {{
                  isRight(message)
                    ? t('staff.support.sender.operator')
                    : t('staff.support.sender.client')
                }}
              </span>
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

          <form v-if="isMine" class="ds-composer" @submit.prevent="handleSend">
            <div class="ds-field ds-composer__input">
              <label class="ds-sr-only" for="ssup-message">{{ t('staff.support.placeholder') }}</label>
              <textarea
                id="ssup-message"
                v-model="composerText"
                class="ds-input"
                rows="2"
                maxlength="4000"
                :placeholder="t('staff.support.placeholder')"
                :disabled="support.replying[selectedThread.id]"
                :aria-invalid="support.replyErrors[selectedThread.id] ? 'true' : undefined"
                :aria-describedby="
                  support.replyErrors[selectedThread.id] ? 'ssup-message-error' : undefined
                "
              />
              <p
                v-if="support.replyErrors[selectedThread.id]"
                id="ssup-message-error"
                class="ds-field__error"
              >
                <AlertTriangle size="sm" />
                <span>
                  {{
                    support.replyErrors[selectedThread.id]?.status === 409
                      ? t('staff.support.readOnlyHint')
                      : errorMessage(support.replyErrors[selectedThread.id])
                  }}
                </span>
              </p>
            </div>
            <CButton
              variant="primary"
              inline
              :loading="support.replying[selectedThread.id]"
              :disabled="composerText.trim() === '' || support.replying[selectedThread.id]"
            >
              {{ t('staff.support.send') }}
            </CButton>
          </form>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.ssup {
  display: grid;
  gap: var(--space-4);
  align-content: start;
  min-inline-size: 0;
}

.ssup__groups {
  display: grid;
  gap: var(--space-5);
}
.ssup__group {
  display: grid;
  gap: var(--space-2);
}
.ssup__group-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
}
.ssup__group-note,
.ssup__note {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

/* The row opens its conversation in place: a button holds the row's one link-part
   (its title), and a button aligns its text to the start by hand. */
.ssup__open {
  text-align: start;
}

.ssup__panel-head {
  display: grid;
  gap: var(--space-1);
  min-inline-size: 0;
}
.ssup__panel-client {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
.ssup__panel-ids {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}

.ssup__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

/* The screen gives the thread its height (K51). */
.ssup__thread {
  block-size: calc(var(--center-lg) + var(--center-md));
}
.ssup__state {
  flex: 1 1 auto;
  display: grid;
  place-items: center;
  min-block-size: 0;
}
</style>
