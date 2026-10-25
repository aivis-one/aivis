// =============================================================================
// AIVIS.ONE Frontend -- the support screens' small shared rules (H40)
// =============================================================================
//
// Shared by the ticket list (StaffSupportView) and the ticket's card
// (StaffSupportTicketView), so the two never name a person, colour a status
// or cut a day differently.
// =============================================================================

import type { SupportPerson, SupportTicketStatus } from '@/api/support'

/**
 * A person as the staff area writes one: first and last name joined
 * (StaffUsersView's rule), else the e-mail, else the start of the id --
 * something an operator can act on, never a dash. "?" for a person the
 * backend could not find (deleted meanwhile).
 */
export function personName(person: SupportPerson | null): string {
  if (person === null) return '?'
  const parts = [person.first_name, person.last_name].filter(
    (p): p is string => typeof p === 'string' && p.trim() !== '',
  )
  if (parts.length > 0) return parts.join(' ')
  return person.email ?? person.user_id.slice(0, 8)
}

/** The badge colour of a ticket status. */
export function statusVariant(
  status: SupportTicketStatus,
): 'primary' | 'success' | 'neutral' | 'warning' | 'danger' {
  switch (status) {
    case 'open':
      return 'primary'
    case 'resolved':
      return 'success'
    case 'duplicate':
      return 'neutral'
    case 'rejected':
      return 'warning'
    case 'spam':
      return 'danger'
  }
}

/**
 * The edges of one LOCAL day as instants: [its midnight, the next one), for
 * the list's day filter. Built from the date's parts, never by parsing the
 * string -- `new Date('2026-10-25')` is UTC midnight, not the operator's.
 * The backend reads each edge with its zone (toISOString's `Z`). null for
 * anything but `yyyy-mm-dd`.
 */
export function dayEdges(value: string): { from: string; to: string } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const y = Number(match[1])
  const m = Number(match[2]) - 1
  const d = Number(match[3])
  return {
    from: new Date(y, m, d).toISOString(),
    to: new Date(y, m, d + 1).toISOString(),
  }
}

/** Stars as text, filled then empty: 4 -> "★★★★☆" (H41). */
export function starsText(stars: number): string {
  const n = Math.max(0, Math.min(5, Math.round(stars)))
  return '★'.repeat(n) + '☆'.repeat(5 - n)
}
