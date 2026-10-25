<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffSupportView (Ф-3, H40 tickets, H41 ratings)
// =============================================================================
//
// The list of support tickets: /staff/users/support, a section of the
// Users hub. A row opens the ticket's card, its own route
// (staff-support-ticket, StaffSupportTicketView) -- the same card an
// operator signal opens.
//
// EVERY OPERATOR SEES EVERY TICKET (owner ruling, H40): an operator is any
// active staff member, and the list is the product's own table. Who took a
// ticket is a column, not a filter of visibility.
//
// THREE TABS: "All" -- every ticket but spam, with a status filter;
// "Spam" -- spam alone; "Statistics" (H41) -- not a list, StaffSupportStats.
// The other filters apply to both lists: the categories and the ratings
// (any of those chosen; none chosen is all of them) and one day of the
// appeal.
// The day is the OPERATOR's day: its edges are this browser's local
// midnights, sent as instants with their zone (the backend refuses an
// edge without one -- only the screen knows the operator's zone).
//
// Newest appeal first; the next page is the backend's cursor, "Show more"
// at the foot of the list.
//
// H41: a row also says who last resolved the ticket and the person's
// rating (stars, the comment's first line); "no rating" is one of the
// rating filter's chips.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CSelect } from '@/components/ui'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import { useScreenHeader } from '@/components/layout/screenHeader'
import { formatDateTime } from '@/utils/format'
import { useSupportStore } from '@/stores/support'
import { SUPPORT_CATEGORIES, SUPPORT_RATING_FILTERS } from '@/api/support'
import type { SupportActionError } from '@/stores/support'
import type {
  ListTicketsParams,
  SupportCategory,
  SupportPerson,
  SupportRatingFilter,
  SupportTicketRow,
  SupportTicketStatus,
} from '@/api/support'
import StaffSupportStats from './StaffSupportStats.vue'
import { dayEdges, personName, starsText, statusVariant } from './supportPeople'

const { t, locale } = useI18n()
const support = useSupportStore()

// H41: the third tab is the statistics (StaffSupportStats), not a list.
type Tab = 'all' | 'spam' | 'stats'

const tab = ref<Tab>('all')
const categories = ref<SupportCategory[]>([])
const ratings = ref<SupportRatingFilter[]>([])
const status = ref<'' | Exclude<SupportTicketStatus, 'spam'>>('')
const day = ref('') // yyyy-mm-dd from the date input, or ''

const statusOptions = computed(() =>
  (['open', 'resolved', 'rejected', 'duplicate'] as const).map((code) => ({
    value: code,
    label: t(`staff.support.status.${code}`),
  })),
)

const filter = computed<ListTicketsParams>(() => {
  const edges = dayEdges(day.value)
  return {
    category: categories.value.length > 0 ? categories.value : undefined,
    rating: ratings.value.length > 0 ? ratings.value : undefined,
    status: tab.value === 'spam' ? 'spam' : status.value || undefined,
    created_from: edges?.from,
    created_to: edges?.to,
  }
})

function load(): void {
  if (tab.value === 'stats') return // the statistics load themselves
  void support.fetchTickets(filter.value)
}

watch(filter, load, { deep: true })

function toggleCategory(code: SupportCategory): void {
  const i = categories.value.indexOf(code)
  categories.value =
    i === -1 ? [...categories.value, code] : categories.value.filter((c) => c !== code)
}

function toggleRating(code: SupportRatingFilter): void {
  ratings.value = ratings.value.includes(code)
    ? ratings.value.filter((r) => r !== code)
    : [...ratings.value, code]
}

function ratingChip(code: SupportRatingFilter): string {
  return code === 'none' ? t('staff.support.rating.none') : starsText(Number(code))
}

function selectTab(next: Tab): void {
  tab.value = next
}

function errorMessage(err: SupportActionError | null): string {
  if (!err) return ''
  if (err.status === 502 || err.status === 504) return t('staff.support.errorUnavailable')
  return t('staff.support.errorGeneric')
}

function appealedAt(row: SupportTicketRow): string {
  return row.created_at ? formatDateTime(row.created_at, locale.value) : ''
}

function takerLine(person: SupportPerson | null): string {
  return person === null
    ? t('staff.support.unclaimed')
    : t('staff.support.takenBy', { name: personName(person) })
}

useScreenHeader({
  actions: () =>
    tab.value === 'stats'
      ? []
      : [{ id: 'refresh', label: t('staff.support.refresh'), icon: RefreshCw, onClick: load }],
})

onMounted(load)
</script>

<template>
  <div class="ssup">
    <div class="ssup__tabs" role="tablist" :aria-label="t('staff.support.title')">
      <CButton
        role="tab"
        :aria-selected="tab === 'all'"
        :variant="tab === 'all' ? 'primary' : 'outline'"
        size="sm"
        inline
        @click="selectTab('all')"
      >
        {{ t('staff.support.tabAll') }}
      </CButton>
      <CButton
        role="tab"
        :aria-selected="tab === 'spam'"
        :variant="tab === 'spam' ? 'primary' : 'outline'"
        size="sm"
        inline
        @click="selectTab('spam')"
      >
        {{ t('staff.support.tabSpam') }}
      </CButton>
      <CButton
        role="tab"
        :aria-selected="tab === 'stats'"
        :variant="tab === 'stats' ? 'primary' : 'outline'"
        size="sm"
        inline
        @click="selectTab('stats')"
      >
        {{ t('staff.support.tabStats') }}
      </CButton>
    </div>

    <StaffSupportStats v-if="tab === 'stats'" />

    <template v-else>
      <fieldset class="ssup__filters">
        <legend class="ds-sr-only">{{ t('staff.support.filters') }}</legend>
        <div class="ssup__chips" role="group" :aria-label="t('staff.support.category')">
          <CButton
            v-for="code in SUPPORT_CATEGORIES"
            :key="code"
            :aria-pressed="categories.includes(code)"
            :variant="categories.includes(code) ? 'primary' : 'outline'"
            size="sm"
            inline
            @click="toggleCategory(code)"
          >
            {{ t(`staff.support.categories.${code}`) }}
          </CButton>
        </div>
        <div class="ssup__chips" role="group" :aria-label="t('staff.support.rating.filter')">
          <CButton
            v-for="code in SUPPORT_RATING_FILTERS"
            :key="code"
            :aria-pressed="ratings.includes(code)"
            :variant="ratings.includes(code) ? 'primary' : 'outline'"
            size="sm"
            inline
            @click="toggleRating(code)"
          >
            {{ ratingChip(code) }}
          </CButton>
        </div>
        <div class="ssup__fields">
          <CSelect
            v-if="tab === 'all'"
            v-model="status"
            :label="t('staff.support.statusFilter')"
            :placeholder="t('staff.support.statusAny')"
            :options="statusOptions"
          />
          <CInput v-model="day" type="date" :label="t('staff.support.day')" />
        </div>
      </fieldset>

      <CListSkeleton v-if="support.ticketsLoading && !support.ticketsLoaded" />

      <CEmptyState
        v-else-if="support.ticketsError"
        tone="danger"
        :description="errorMessage(support.ticketsError)"
      >
        <template #actions>
          <CButton variant="primary" size="sm" inline @click="load">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <CEmptyState v-else-if="support.tickets.length === 0" :title="t('staff.support.empty')" />

      <template v-else>
        <ul class="ds-rows">
          <li v-for="row in support.tickets" :key="row.id" class="ds-row">
            <span class="ds-row__body">
              <RouterLink
                class="ds-row__link"
                :to="{ name: 'staff-support-ticket', params: { id: row.id } }"
              >
                <span class="ds-row__title">{{ personName(row.opener) }}</span>
              </RouterLink>
              <span class="ds-row__meta">
                {{ t(`inv.support.topics.${row.topic}`) }} &bull; {{ appealedAt(row) }}
              </span>
              <span class="ds-row__meta">{{ takerLine(row.claimed_by) }}</span>
              <span v-if="row.resolved_by" class="ds-row__meta">
                {{ t('staff.support.resolvedBy', { name: personName(row.resolved_by) }) }}
              </span>
              <span v-if="row.rating" class="ds-row__meta ssup__rating">
                <span :aria-label="t('staff.support.rating.stars', { n: row.rating.stars })">
                  {{ starsText(row.rating.stars) }}
                </span>
                <template v-if="row.rating.comment"> &bull; {{ row.rating.comment }} </template>
              </span>
            </span>
            <span class="ds-row__trail">
              <CBadge
                :variant="statusVariant(row.status)"
                :text="t(`staff.support.status.${row.status}`)"
              />
            </span>
          </li>
        </ul>
        <p v-if="support.moreTicketsError" class="ds-field__error">
          {{ errorMessage(support.moreTicketsError) }}
        </p>
        <CButton
          v-if="support.ticketsNextCursor !== null"
          variant="outline"
          size="sm"
          inline
          :loading="support.moreTicketsLoading"
          :disabled="support.moreTicketsLoading"
          @click="support.fetchMoreTickets"
        >
          {{ t('staff.support.more') }}
        </CButton>
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
.ssup__tabs,
.ssup__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.ssup__filters {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  border: 0;
  min-inline-size: 0;
}
/* The rating of a row (H41): the stars, and the comment cut to one line. */
.ssup__rating {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-inline-size: 100%;
}
.ssup__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--space-3);
}
</style>
