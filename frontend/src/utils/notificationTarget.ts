// =============================================================================
// AIVIS.ONE Frontend -- Where a notification leads
// =============================================================================
//
// The inbox row opens the screen of its own event. The server
// carries no navigation target for these notifications, so the screen is
// chosen here from the notification's TYPE (the dotted names the comms profile
// declares: `kyc.approved`, `deposit.confirmed`, ...). When a notification does
// carry an `action_data` naming a post or an event, that wins.
//
// A type with no screen of its own (a letter-only type, a type of another
// role) leads nowhere: the row is only marked read.
//
// H40: the staff shell's operator signals open the ticket's card, by the
// thread id in their action_data; the integrator's support notices open
// its support screen, as the buyer's and the project's do.
// =============================================================================

import type { RouteLocationRaw } from 'vue-router'

export interface NotificationTargetInput {
  /** The notification's type, e.g. `deposit.confirmed`. */
  type: string
  /** `action_data` of the row, when comms sends one. */
  actionData?: { action: string; params?: Record<string, unknown> } | null
  /** The reader's identity-verification status. */
  kycStatus: string | null
  /** The shell the reader is in. The buyer's and the project's shells have these screens. */
  shell: string | undefined
}

// A notice about the support conversation: comms' own message pings
// (msg.*) and the product's "a reply could not be translated"
// (support.translation_unavailable, H39) -- both lead to the conversation,
// where the reply is and where it can be answered.
function isSupportNotice(type: string): boolean {
  return type.startsWith('msg.') || type === 'support.translation_unavailable'
}

function paramId(params: Record<string, unknown> | undefined): string | null {
  const id = params?.id
  return typeof id === 'string' && id.length > 0 ? id : null
}

// The project account's notices: a withdrawal leads to the balance, a sale to
// the operations, a post or a roadmap change to the publications, a message to
// support. A notice with no screen of its own leads nowhere.
function companyTarget(
  type: string,
  actionData: NotificationTargetInput['actionData'],
): RouteLocationRaw | null {
  if (actionData?.action === 'post') return { name: 'company-posts' }
  if (type.startsWith('withdrawal.')) return { name: 'company-balance' }
  if (type.startsWith('purchase.') || type.startsWith('installment.')) {
    return { name: 'company-transactions' }
  }
  if (type.startsWith('post.')) return { name: 'company-posts' }
  if (type.startsWith('company.roadmap_')) return { name: 'company-roadmap' }
  if (type.startsWith('company.attachment')) return { name: 'company-attachments' }
  if (type.startsWith('company.')) return { name: 'company-audit' }
  if (isSupportNotice(type)) return { name: 'company-support' }
  return null
}

// The action of every operator signal (backend support/service.py
// OPEN_TICKET_ACTION): open the ticket's card, whose id is the one param.
const OPEN_SUPPORT_TICKET = 'open_support_ticket'

// The operator signals (comms-profile/types.yaml, H40 item 8).
const OPERATOR_SIGNALS = new Set([
  'support.message_received',
  'support.ticket_assigned',
  'support.ticket_released',
])

// The staff member's notices. The operator signals of H40 (support.*) open
// the card of their ticket. comms' own ping (msg.support_message) carries
// no ticket -- comms mutes it for operators (backend support/mute.py), and
// an operator who turned it back on lands on the list.
function staffTarget(
  type: string,
  actionData: NotificationTargetInput['actionData'],
): RouteLocationRaw | null {
  if (actionData?.action === OPEN_SUPPORT_TICKET) {
    const id = paramId(actionData.params)
    if (id) return { name: 'staff-support-ticket', params: { id } }
  }
  if (type.startsWith('msg.') || OPERATOR_SIGNALS.has(type)) return { name: 'staff-support' }
  return null
}

export function notificationTarget(input: NotificationTargetInput): RouteLocationRaw | null {
  const { type, actionData, kycStatus, shell } = input

  // Identity verification belongs to every role's entry; its screen is shared.
  if (type.startsWith('kyc.')) {
    return type === 'kyc.approved' ? null : '/verification'
  }

  if (shell === 'company') return companyTarget(type, actionData)
  if (shell === 'staff') return staffTarget(type, actionData)

  // The integrator's shell: its own conversation with support.
  if (shell === 'agent') return isSupportNotice(type) ? { name: 'agent-support' } : null

  if (shell !== 'investor') return null

  if (actionData) {
    const id = paramId(actionData.params)
    if (actionData.action === 'post' && id) return { name: 'investor-post', params: { id } }
    if (actionData.action === 'event' && id) return { name: 'investor-event', params: { id } }
  }

  // A confirmed deposit that is waiting on verification leads back to it: the
  // fee is now on the account.
  if (type === 'deposit.confirmed') {
    return kycStatus === 'approved' ? { name: 'investor-balance' } : '/verification'
  }
  if (type === 'payment.reversed') return { name: 'investor-balance' }

  if (type === 'purchase.completed' || type === 'purchase.gift_received') {
    return { name: 'investor-portfolio' }
  }
  if (type.startsWith('installment.')) return { name: 'investor-installment-plans' }

  if (type.startsWith('agent_application.')) return { name: 'investor-settings' }
  if (isSupportNotice(type)) return { name: 'investor-support' }

  return null
}
