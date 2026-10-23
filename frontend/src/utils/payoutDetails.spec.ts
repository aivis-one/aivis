// =============================================================================
// utils/payoutDetails -- WHERE A WITHDRAWAL GOES, AS TWO LINES AND NOT AS JSON
// =============================================================================
//
// Axes: EMPTINESS (no snapshot, an empty one, blank fields), SHORTAGE (only the
// network, only the wallet), SURPLUS (a field the screen has no name for must
// still be shown, not hidden).
// =============================================================================

import { describe, expect, it } from 'vitest'

import { payoutLines } from './payoutDetails'

describe('payoutLines', () => {
  it('shows the network, then the wallet', () => {
    expect(payoutLines({ wallet: 'TXyz', network: 'TRC20' })).toEqual([
      { key: 'network', value: 'TRC20' },
      { key: 'wallet', value: 'TXyz' },
    ])
  })

  it('shows nothing for no snapshot or an empty one', () => {
    expect(payoutLines(null)).toEqual([])
    expect(payoutLines(undefined)).toEqual([])
    expect(payoutLines({})).toEqual([])
  })

  it('leaves out a blank field but keeps the other', () => {
    expect(payoutLines({ network: '  ', wallet: 'TXyz' })).toEqual([
      { key: 'wallet', value: 'TXyz' },
    ])
  })

  it('keeps any other field the person saved, after the two', () => {
    expect(payoutLines({ memo: '42', wallet: 'TXyz', network: 'TRC20' })).toEqual([
      { key: 'network', value: 'TRC20' },
      { key: 'wallet', value: 'TXyz' },
      { key: 'memo', value: '42' },
    ])
  })

  it('shows a nested value as its text rather than dropping it', () => {
    const lines = payoutLines({ wallet: 'TXyz', extra: { a: 1 } })
    expect(lines.find((l) => l.key === 'extra')?.value).toBe('{"a":1}')
  })
})
