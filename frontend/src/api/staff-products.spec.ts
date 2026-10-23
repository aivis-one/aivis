// =============================================================================
// api/staff-products -- the staff list of a project's products in every status,
// the status move, and the moves the screen offers
// =============================================================================

import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'
import {
  allowedProductStatuses,
  fetchStaffCompanyProducts,
  updateStaffProductStatus,
} from './staff-products'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('the moves a product can make', () => {
  it('mirrors the server table', () => {
    expect(allowedProductStatuses('active')).toEqual(['hidden', 'archived'])
    expect(allowedProductStatuses('hidden')).toEqual(['active', 'archived'])
    expect(allowedProductStatuses('archived')).toEqual([])
    expect(allowedProductStatuses('something else')).toEqual([])
  })
})

describe('the staff product calls', () => {
  it('reads the project products with the page and the page size', async () => {
    const get = vi
      .spyOn(api, 'get')
      .mockResolvedValue({ items: [], total: 0, page: 2, per_page: 20 })
    await fetchStaffCompanyProducts('c1', { page: 2, per_page: 20 })
    const url = String(get.mock.calls[0]?.[0])
    expect(url.startsWith('/api/v1/staff/companies/c1/products?')).toBe(true)
    expect(url).toContain('page=2')
    expect(url).toContain('per_page=20')
  })

  it('changes a status through the status endpoint', async () => {
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({})
    await updateStaffProductStatus('p1', 'hidden')
    expect(patch).toHaveBeenCalledWith('/api/v1/staff/products/p1/status', { status: 'hidden' })
  })
})
