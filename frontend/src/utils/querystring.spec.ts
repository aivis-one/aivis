// =============================================================================
// buildQueryString -- one query component, absent values left out (H40: lists)
// =============================================================================

import { describe, expect, it } from 'vitest'
import { buildQueryString } from './querystring'

describe('buildQueryString', () => {
  it('leaves out absent values and keeps a real zero', () => {
    expect(buildQueryString({ a: undefined, b: null, c: '', d: 0, e: false })).toBe('?d=0&e=false')
    expect(buildQueryString({})).toBe('')
  })

  it('repeats the key once per element of an array, in order (H40)', () => {
    expect(buildQueryString({ category: ['payments', 'tech'], limit: 20 })).toBe(
      '?category=payments&category=tech&limit=20',
    )
  })

  it('emits nothing for an empty array or for absent elements', () => {
    expect(buildQueryString({ category: [] })).toBe('')
    expect(buildQueryString({ category: [undefined, '', null] })).toBe('')
    expect(buildQueryString({ category: ['', 'tech'] })).toBe('?category=tech')
  })

  it('a repeated element is sent as given -- the server counts it once', () => {
    expect(buildQueryString({ category: ['tech', 'tech'] })).toBe('?category=tech&category=tech')
  })
})
