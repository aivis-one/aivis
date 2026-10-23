// =============================================================================
// AIVIS.ONE Frontend -- Where a notification leads
// =============================================================================
//
// The inbox row of an investor opens the screen of its own event. The server
// carries no navigation target for these notifications, so the screen is
// chosen here from the notification's TYPE (the dotted names the comms profile
// declares: `kyc.approved`, `deposit.confirmed`, ...). When a notification does
// carry an `action_data` naming a post or an event, that wins.
//
// A type with no screen of its own (a letter-only type, a type of another
// role) leads nowhere: the row is only marked read.
// =============================================================================

import type { RouteLocationRaw } from 'vue-router'

export interface NotificationTargetInput {
  /** The notification's type, e.g. `deposit.confirmed`. */
  type: string
  /** `action_data` of the row, when comms sends one. */
  actionData?: { action: string; params?: Record<string, unknown> } | null
  /** The reader's identity-verification status. */
  kycStatus: string | null
  /** The shell the reader is in. Only the investor shell has these screens. */
  shell: string | undefined
}

function paramId(params: Record<string, unknown> | undefined): string | null {
  const id = params?.id
  return typeof id === 'string' && id.length > 0 ? id : null
}

export function notificationTarget(input: NotificationTargetInput): RouteLocationRaw | null {
  const { type, actionData, kycStatus, shell } = input

  // Identity verification belongs to every role's entry; its screen is shared.
  if (type.startsWith('kyc.')) {
    return type === 'kyc.approved' ? null : '/verification'
  }

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
  if (type.startsWith('msg.')) return { name: 'investor-support' }

  return null
}
