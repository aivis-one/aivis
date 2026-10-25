// =============================================================================
// useSharesPerOption -- the parts per lot of the projects a screen shows
// =============================================================================
//
// A project is asked once however many entries name it; an unreadable project
// answers null (the screen then shows no count rather than the lot count).
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'

const getCompany = vi.fn()
vi.mock('@/api/companies', () => ({ getCompany: (id: string) => getCompany(id) }))

import { resetSharesPerOptionCache, useSharesPerOption } from './useSharesPerOption'

beforeEach(() => {
  getCompany.mockReset()
  resetSharesPerOptionCache()
})

describe('useSharesPerOption', () => {
  it('knows nothing until the project answers, then its parts per lot', async () => {
    getCompany.mockResolvedValue({ shares_per_option: 25 })
    const { ensure, partsPerLot } = useSharesPerOption()
    expect(partsPerLot('c1')).toBeNull()
    await ensure(['c1'])
    expect(partsPerLot('c1')).toBe(25)
  })

  it('asks each project once, however many entries name it', async () => {
    getCompany.mockImplementation(async (id: string) => ({
      shares_per_option: id === 'c1' ? 25 : 1,
    }))
    const first = useSharesPerOption()
    const second = useSharesPerOption()
    await first.ensure(['c1', 'c1', 'c2'])
    await second.ensure(['c1'])
    expect(getCompany).toHaveBeenCalledTimes(2)
    expect(second.partsPerLot('c1')).toBe(25)
    expect(first.partsPerLot('c2')).toBe(1)
  })

  it('answers null for a project that cannot be read, and for no project', async () => {
    getCompany.mockRejectedValue(new Error('404'))
    const { ensure, partsPerLot } = useSharesPerOption()
    await ensure(['gone'])
    expect(partsPerLot('gone')).toBeNull()
    expect(partsPerLot(null)).toBeNull()
    expect(partsPerLot(undefined)).toBeNull()
  })
})
