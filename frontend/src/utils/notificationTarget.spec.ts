// =============================================================================
// notificationTarget -- a notification leads to the screen of its own event
// =============================================================================

import { describe, it, expect } from 'vitest'
import { notificationTarget } from './notificationTarget'

const base = { kycStatus: 'not_started', shell: 'investor' as string | undefined }

describe('notificationTarget', () => {
  it('a confirmed deposit leads back to verification while the account is not verified', () => {
    expect(notificationTarget({ ...base, type: 'deposit.confirmed' })).toBe('/verification')
  })

  it('the same deposit leads to the balance once the account is verified', () => {
    expect(notificationTarget({ ...base, kycStatus: 'approved', type: 'deposit.confirmed' })).toEqual(
      { name: 'investor-balance' },
    )
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
})
