// =============================================================================
// api/payments -- WHAT THE SERVICE'S ANSWERS MUST NOT BE TURNED INTO
// =============================================================================
//
// This module is the only place in the frontend that reads the payments
// contract, so it is where the three axes live: a repeated call, an
// empty or null answer, and an answer that is missing something.
//
// Every assertion here was watched to FAIL before it was kept.
//
// WHY THIS FILE AND NOT A VIEW TEST. There is no view-test harness in
// this tree -- the four existing specs are component-level -- and
// building one as a side effect of an integration delivery would be
// scope no one asked for. What can be pinned without it is the request
// shapes and the response handling, which is where the contract lives.
// =============================================================================

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  createInvoice,
  getCurrentInvoice,
  getInvoice,
  submitInvoiceTxid,
} from './payments'
import { api } from './client'

const INVOICE = {
  id: '11111111-1111-4111-8111-111111111111',
  network: 'USDT-TRC20',
  address: 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
  invoice_amount_cents: 10000,
  status: 'created',
  expires_at: '2026-08-28T12:00:00+00:00',
  attempts_remaining: 3,
}

// Typed through the factories rather than through a bare
// ReturnType<typeof vi.spyOn>: the bare form erases the argument types
// and vue-tsc rejects it, and widening these to `any` would drop the
// very checks that make the request-shape assertions below meaningful.
const spyPost = () => vi.spyOn(api, 'post')
const spyGet = () => vi.spyOn(api, 'get')

let post: ReturnType<typeof spyPost>
let get: ReturnType<typeof spyGet>

beforeEach(() => {
  post = spyPost()
  get = spyGet()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('createInvoice — the request shape', () => {
  it('sends network and amount_cents, and nothing else', async () => {
    // The service refuses unknown fields outright (extra="forbid"), so
    // an extra key here is not harmless padding -- it is a 422 on every
    // deposit.
    post.mockResolvedValue(INVOICE)
    await createInvoice({ network: 'USDT-TRC20', amount_cents: 10000 })

    expect(post).toHaveBeenCalledWith('/api/v1/payments/invoices', {
      network: 'USDT-TRC20',
      amount_cents: 10000,
    })
  })

  it('posts to the product, never to the payments service', async () => {
    // The service token lives on the backend. A path that pointed at
    // the service would either fail CORS or, worse, need the token in
    // a browser.
    post.mockResolvedValue(INVOICE)
    await createInvoice({ network: 'USDT-TRC20', amount_cents: 1 })

    const path = post.mock.calls[0][0] as string
    expect(path.startsWith('/api/v1/payments/')).toBe(true)
    expect(path).not.toContain('invoices/')
  })
})

describe('getCurrentInvoice — EMPTY: null is an answer', () => {
  it('resolves null rather than throwing when no invoice is open', async () => {
    // The failure this pins: treating a falsy result as an error puts
    // an error screen in front of every user who has not yet made a
    // deposit, which is all of them at first.
    get.mockResolvedValue(null)
    await expect(getCurrentInvoice('USDT-TRC20')).resolves.toBeNull()
  })

  it('passes the network as a query parameter', async () => {
    get.mockResolvedValue(null)
    await getCurrentInvoice('USDT-TRC20')

    const path = get.mock.calls[0][0] as string
    expect(path).toContain('/invoices/current')
    expect(path).toContain('network=USDT-TRC20')
  })

  it('does not collide with the by-id route', async () => {
    // "current" must not be sent down a path that reads as an id. The
    // backend declares its route first for the same reason; this is the
    // half of that pairing the frontend owns.
    get.mockResolvedValue(null)
    await getCurrentInvoice('USDT-TRC20')

    expect(get.mock.calls[0][0]).toMatch(/\/invoices\/current\?/)
  })
})

describe('getInvoice — REPEAT: polling is side-effect free here', () => {
  it('issues one identical GET per call and mutates nothing', async () => {
    // Polling is how this screen learns a status, so a wrapper that
    // accumulated state across calls would drift from the service.
    get.mockResolvedValue(INVOICE)

    const first = await getInvoice(INVOICE.id)
    const second = await getInvoice(INVOICE.id)

    expect(first).toEqual(second)
    expect(get.mock.calls[0][0]).toBe(get.mock.calls[1][0])
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('submitInvoiceTxid — a 200 is a verdict, not a success', () => {
  it('resolves for a rejecting result_code instead of throwing', async () => {
    // Five of the six verdicts mean the hash was not accepted, and all
    // six arrive as a resolved promise. A caller that reads "no
    // exception" as "accepted" is wrong five times out of six.
    get.mockResolvedValue(INVOICE)
    post.mockResolvedValue({
      status: 'created',
      result_code: 'not_found',
      attempts_used: 1,
      attempts_remaining: 2,
    })

    const result = await submitInvoiceTxid(INVOICE.id, '0xdeadbeef')
    expect(result.result_code).toBe('not_found')
  })

  it('reports the attempt budget the service reports, spent or not', async () => {
    // invalid_format never reaches an explorer and spends nothing. A UI
    // that decremented per submission would show a budget the user has
    // not used -- so this wrapper must relay, not compute.
    post.mockResolvedValue({
      status: 'created',
      result_code: 'invalid_format',
      attempts_used: 0,
      attempts_remaining: 3,
    })

    const result = await submitInvoiceTxid(INVOICE.id, 'nonsense')
    expect(result.attempts_used).toBe(0)
    expect(result.attempts_remaining).toBe(3)
  })

  it('sends the hash under the key the service expects', async () => {
    // SHORTFALL: a body missing `txid`, or carrying it under another
    // name, is a 422 from the service rather than a verdict.
    post.mockResolvedValue({
      status: 'awaiting_confirmations',
      result_code: 'matched',
      attempts_used: 1,
      attempts_remaining: 2,
    })

    await submitInvoiceTxid(INVOICE.id, '0xabc')
    expect(post).toHaveBeenCalledWith(
      `/api/v1/payments/invoices/${INVOICE.id}/txid`,
      { txid: '0xabc' },
    )
  })

  it('passes an empty hash through rather than refusing locally', async () => {
    // EMPTY. The service answers 200 invalid_format and spends nothing,
    // and that answer carries an explanation a local refusal would not.
    // The view stops an empty field earlier; that is a separate decision
    // made in a separate place, and this layer must not duplicate it.
    post.mockResolvedValue({
      status: 'created',
      result_code: 'invalid_format',
      attempts_used: 0,
      attempts_remaining: 3,
    })

    await submitInvoiceTxid(INVOICE.id, '')
    expect(post).toHaveBeenCalledWith(
      `/api/v1/payments/invoices/${INVOICE.id}/txid`,
      { txid: '' },
    )
  })
})
