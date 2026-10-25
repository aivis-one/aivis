// =============================================================================
// The support screens' shared rules: a person's name, a status colour, a day
// =============================================================================

import { describe, expect, it } from 'vitest'
import { dayEdges, personName, starsText, statusVariant } from './supportPeople'
import type { SupportPerson, SupportTicketStatus } from '@/api/support'

const person = (over: Partial<SupportPerson> = {}): SupportPerson => ({
  user_id: '12345678-aaaa-4bbb-8ccc-000000000000',
  first_name: null,
  last_name: null,
  email: null,
  ...over,
})

describe('personName', () => {
  it('joins the names, else the e-mail, else the start of the id', () => {
    expect(personName(person({ first_name: 'Ada', last_name: 'Lovelace' }))).toBe('Ada Lovelace')
    expect(personName(person({ first_name: 'Ada' }))).toBe('Ada')
    expect(personName(person({ first_name: '  ', email: 'ada@example.com' }))).toBe(
      'ada@example.com',
    )
    expect(personName(person())).toBe('12345678')
  })

  it('is never empty -- a person the backend could not find is "?"', () => {
    expect(personName(null)).toBe('?')
  })
})

describe('statusVariant', () => {
  it('gives every status a colour of its own', () => {
    const all: SupportTicketStatus[] = ['open', 'resolved', 'rejected', 'duplicate', 'spam']
    const colours = all.map(statusVariant)
    expect(colours.every((c) => typeof c === 'string' && c.length > 0)).toBe(true)
    expect(new Set(colours).size).toBe(all.length)
  })
})

describe('dayEdges', () => {
  it("is the operator's own day: local midnight to the next one", () => {
    const edges = dayEdges('2026-10-25')
    expect(edges).not.toBeNull()
    const from = new Date(edges!.from)
    const to = new Date(edges!.to)
    expect([from.getFullYear(), from.getMonth(), from.getDate(), from.getHours()]).toEqual([
      2026, 9, 25, 0,
    ])
    expect([to.getDate(), to.getHours(), to.getMinutes()]).toEqual([26, 0, 0])
  })

  it('sends instants that carry their zone', () => {
    const edges = dayEdges('2026-10-25')!
    expect(edges.from.endsWith('Z')).toBe(true)
    expect(edges.to.endsWith('Z')).toBe(true)
  })

  it('crosses a month end', () => {
    const to = new Date(dayEdges('2026-10-31')!.to)
    expect([to.getMonth(), to.getDate()]).toEqual([10, 1])
  })

  it('is null for anything but a date', () => {
    for (const value of ['', '2026-10', '25.10.2026', 'garbage']) {
      expect(dayEdges(value)).toBeNull()
    }
  })
})

describe('starsText', () => {
  it('fills as many stars as given, of five', () => {
    expect(starsText(4)).toBe('★★★★☆')
    expect(starsText(1)).toBe('★☆☆☆☆')
    expect(starsText(5)).toBe('★★★★★')
  })

  it('never draws more than five or fewer than none', () => {
    expect(starsText(9)).toBe('★★★★★')
    expect(starsText(-1)).toBe('☆☆☆☆☆')
  })
})
