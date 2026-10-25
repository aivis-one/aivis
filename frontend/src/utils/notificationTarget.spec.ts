// =============================================================================
// notificationTarget -- a notification leads to the screen of its own event
// =============================================================================

import { describe, it, expect } from 'vitest'
import { notificationTarget } from './notificationTarget'

const base = { kycStatus: 'not_started', shell: 'investor' as string | undefined }

describe('notificationTarget', () => {
  it('a support reply that could not be translated leads to the conversation (H39)', () => {
    const type = 'support.translation_unavailable'
    expect(notificationTarget({ ...base, type })).toEqual({ name: 'investor-support' })
    expect(notificationTarget({ ...base, shell: 'company', type })).toEqual({
      name: 'company-support',
    })
    // The pair: another support.* type is not swept along by the prefix.
    expect(notificationTarget({ ...base, type: 'support.translate_for_user' })).toBeNull()
  })

  it('a confirmed deposit leads back to verification while the account is not verified', () => {
    expect(notificationTarget({ ...base, type: 'deposit.confirmed' })).toBe('/verification')
  })

  it('the same deposit leads to the balance once the account is verified', () => {
    expect(
      notificationTarget({ ...base, kycStatus: 'approved', type: 'deposit.confirmed' }),
    ).toEqual({ name: 'investor-balance' })
  })

  it('a rejected or withdrawn verification leads to the verification screen; an approval to none', () => {
    expect(notificationTarget({ ...base, type: 'kyc.rejected' })).toBe('/verification')
    expect(notificationTarget({ ...base, type: 'kyc.revoked' })).toBe('/verification')
    expect(notificationTarget({ ...base, type: 'kyc.approved' })).toBeNull()
  })

  it('a received gift and a completed purchase lead to the portfolio', () => {
    expect(notificationTarget({ ...base, type: 'purchase.gift_received' })).toEqual({
      name: 'investor-portfolio',
    })
    expect(notificationTarget({ ...base, type: 'purchase.completed' })).toEqual({
      name: 'investor-portfolio',
    })
  })

  it('an instalment notice leads to the plans', () => {
    expect(notificationTarget({ ...base, type: 'installment.tranche_overdue' })).toEqual({
      name: 'investor-installment-plans',
    })
  })

  it('an action_data naming a post or an event wins over the type', () => {
    expect(
      notificationTarget({
        ...base,
        type: 'platform.news',
        actionData: { action: 'post', params: { id: 'p1' } },
      }),
    ).toEqual({ name: 'investor-post', params: { id: 'p1' } })
    expect(
      notificationTarget({
        ...base,
        type: 'platform.news',
        actionData: { action: 'event', params: { id: 'e1' } },
      }),
    ).toEqual({ name: 'investor-event', params: { id: 'e1' } })
  })

  it('a type with no screen, or another role, leads nowhere', () => {
    expect(notificationTarget({ ...base, type: 'auth.password_reset' })).toBeNull()
    expect(notificationTarget({ ...base, shell: 'agent', type: 'purchase.completed' })).toBeNull()
  })

  it('a project account is led to the screen of its own event', () => {
    const company = { ...base, shell: 'company' as string | undefined }
    expect(notificationTarget({ ...company, type: 'withdrawal.completed' })).toEqual({
      name: 'company-balance',
    })
    expect(notificationTarget({ ...company, type: 'purchase.completed' })).toEqual({
      name: 'company-transactions',
    })
    expect(notificationTarget({ ...company, type: 'company.roadmap_item_updated' })).toEqual({
      name: 'company-roadmap',
    })
    expect(notificationTarget({ ...company, type: 'msg.reply' })).toEqual({
      name: 'company-support',
    })
    expect(notificationTarget({ ...company, type: 'deposit.confirmed' })).toBeNull()
  })

  it('an operator signal opens the card of its ticket (H40)', () => {
    const id = '0b0b0b0b-0000-4000-8000-000000000001'
    const actionData = { action: 'open_support_ticket', params: { id } }
    for (const type of [
      'support.message_received',
      'support.ticket_assigned',
      'support.ticket_released',
    ]) {
      expect(notificationTarget({ ...base, shell: 'staff', type, actionData })).toEqual({
        name: 'staff-support-ticket',
        params: { id },
      })
    }
  })

  it('a staff support notice without a ticket leads to the list (H40)', () => {
    // comms' own ping, if an operator turned its category back on.
    expect(notificationTarget({ ...base, shell: 'staff', type: 'msg.support_message' })).toEqual({
      name: 'staff-support',
    })
    // A signal whose action carries no id.
    const actionData = { action: 'open_support_ticket', params: {} }
    expect(
      notificationTarget({ ...base, shell: 'staff', type: 'support.ticket_released', actionData }),
    ).toEqual({ name: 'staff-support' })
    // The pair: another type is not swept along.
    expect(
      notificationTarget({ ...base, shell: 'staff', type: 'support.translate_for_user' }),
    ).toBeNull()
    expect(notificationTarget({ ...base, shell: 'staff', type: 'deposit.confirmed' })).toBeNull()
  })

  it("the integrator's support notices lead to its own support screen (H40)", () => {
    for (const type of ['msg.participant_message', 'support.translation_unavailable']) {
      expect(notificationTarget({ ...base, shell: 'agent', type })).toEqual({
        name: 'agent-support',
      })
    }
    expect(
      notificationTarget({ ...base, shell: 'agent', type: 'support.ticket_assigned' }),
    ).toBeNull()
  })
})
