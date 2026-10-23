// =============================================================================
// api/admin -- THE INTEGRATOR QUEUE IS PAGED, AND THE REQUEST SAYS WHICH PAGE
// =============================================================================
//
// The server's queue answers `{ items, total, page, per_page }` with the
// applicant's name, e-mail and identity-check status on every item. The
// wrapper used to type the answer as a plain list; these pin the paged shape
// and the query it sends.
// =============================================================================

import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'
import { deactivateStaff, fetchAgentApplications, fetchUsers } from './admin'

afterEach(() => {
  vi.restoreAllMocks()
})

const PAGE = {
  items: [
    {
      id: 'a1',
      user_id: 'u1',
      status: 'pending',
      created_at: '2026-10-20T10:00:00Z',
      applicant_name: 'Ada Lovelace',
      applicant_email: 'ada@example.com',
      applicant_kyc_status: 'approved',
    },
  ],
  total: 41,
  page: 2,
  per_page: 20,
}

describe('fetchAgentApplications', () => {
  it('asks for the page and the page size it is given', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue(PAGE)
    await fetchAgentApplications({ page: 2, per_page: 20 })
    const url = String(get.mock.calls[0]?.[0])
    expect(url.startsWith('/api/v1/staff/agent-applications?')).toBe(true)
    expect(url).toContain('page=2')
    expect(url).toContain('per_page=20')
  })

  it('sends no query at all when it is given none', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue(PAGE)
    await fetchAgentApplications()
    expect(get.mock.calls[0]?.[0]).toBe('/api/v1/staff/agent-applications')
  })

  it('hands back the paged shape with the applicant on every item', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(PAGE)
    const resp = await fetchAgentApplications({ page: 2 })
    expect(resp.total).toBe(41)
    expect(resp.items[0]?.applicant_name).toBe('Ada Lovelace')
    expect(resp.items[0]?.applicant_email).toBe('ada@example.com')
    expect(resp.items[0]?.applicant_kyc_status).toBe('approved')
  })
})

describe('fetchUsers', () => {
  it('sends the search the staff member typed', async () => {
    const get = vi
      .spyOn(api, 'get')
      .mockResolvedValue({ items: [], total: 0, page: 1, per_page: 20 })
    await fetchUsers({ search: 'ada@', kyc_status: 'submitted', page: 1, per_page: 20 })
    const url = String(get.mock.calls[0]?.[0])
    expect(url).toContain('search=ada%40')
    expect(url).toContain('kyc_status=submitted')
  })
})

describe('deactivateStaff', () => {
  it('posts to the staff PROFILE id, not the user id', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ id: 'p1', is_active: false })
    await deactivateStaff('p1')
    expect(post.mock.calls[0]?.[0]).toBe('/api/v1/staff/users/p1/deactivate')
  })
})
