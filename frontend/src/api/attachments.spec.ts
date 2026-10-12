// =============================================================================
// api/attachments -- DOWNLOAD IS A NAVIGATION (H32 P-121)
// =============================================================================
//
// The download used to fetch() the endpoint, follow its 302 across origins
// into the storage, carry the Authorization header through that redirect,
// and save a blob. It could not work: the link pointed at an address no
// browser reaches. Now the endpoint answers { url, ttl_seconds } and the
// browser is sent to the url.
//
// Pinned here: the right endpoint is asked through the API client (which
// carries the session the way every call does), the browser goes to
// exactly the url the backend returned, no fetch() is made by this module,
// and a failed request navigates nowhere.
// =============================================================================

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { downloadAttachment, downloadPublicAttachment } from './attachments'
import { api, ApiResponseError } from './client'

const LINK = {
  url: 'https://files.aivis.one/aivis-attachments/companies/c1/attachments/a1/doc.pdf?X-Amz-Signature=abc',
  ttl_seconds: 900,
}

const spyGet = () => vi.spyOn(api, 'get')
let get: ReturnType<typeof spyGet>
let assign: ReturnType<typeof vi.fn>
let fetchSpy: ReturnType<typeof vi.fn>
const originalLocation = window.location

beforeEach(() => {
  get = spyGet()
  assign = vi.fn()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, assign },
  })
  fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
})

describe('downloadAttachment', () => {
  it('asks the authenticated endpoint and goes to the returned link', async () => {
    get.mockResolvedValue(LINK)

    await downloadAttachment('c1', 'a1')

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/api/v1/companies/c1/attachments/a1/download')
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith(LINK.url)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('navigates nowhere when the endpoint refuses', async () => {
    get.mockRejectedValue(new ApiResponseError(404, 'Attachment not found'))

    await expect(downloadAttachment('c1', 'a1')).rejects.toBeInstanceOf(ApiResponseError)
    expect(assign).not.toHaveBeenCalled()
  })
})

describe('downloadPublicAttachment', () => {
  it('asks the public endpoint and goes to the returned link', async () => {
    get.mockResolvedValue({ ...LINK, ttl_seconds: 86400 })

    await downloadPublicAttachment('c1', 'a1')

    expect(get).toHaveBeenCalledWith('/api/v1/public/companies/c1/attachments/a1/download')
    expect(assign).toHaveBeenCalledWith(LINK.url)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('navigates nowhere when the endpoint refuses', async () => {
    get.mockRejectedValue(new ApiResponseError(429, 'Too many requests'))

    await expect(downloadPublicAttachment('c1', 'a1')).rejects.toBeInstanceOf(ApiResponseError)
    expect(assign).not.toHaveBeenCalled()
  })
})
