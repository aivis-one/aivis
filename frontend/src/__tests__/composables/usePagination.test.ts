import { describe, it, expect } from 'vitest'
import { usePagination } from '@/composables/usePagination'

describe('usePagination', () => {
  it('initializes with page 1 and total 0', () => {
    const p = usePagination()
    expect(p.page.value).toBe(1)
    expect(p.total.value).toBe(0)
    expect(p.perPage.value).toBe(10)
  })

  it('accepts custom perPage', () => {
    const p = usePagination(20)
    expect(p.perPage.value).toBe(20)
  })

  it('computes totalPages correctly', () => {
    const p = usePagination(10)
    p.setTotal(25)
    expect(p.totalPages.value).toBe(3)
  })

  it('next advances page', () => {
    const p = usePagination(10)
    p.setTotal(30)
    p.next()
    expect(p.page.value).toBe(2)
  })

  it('prev decrements page', () => {
    const p = usePagination(10)
    p.setTotal(30)
    p.next()
    p.next()
    p.prev()
    expect(p.page.value).toBe(2)
  })

  it('cannot go below page 1', () => {
    const p = usePagination()
    p.prev()
    expect(p.page.value).toBe(1)
  })

  it('cannot go above totalPages', () => {
    const p = usePagination(10)
    p.setTotal(20)
    p.next()
    p.next()
    expect(p.page.value).toBe(2)
  })

  it('goTo sets specific page', () => {
    const p = usePagination(10)
    p.setTotal(50)
    p.goTo(3)
    expect(p.page.value).toBe(3)
  })

  it('goTo ignores invalid pages', () => {
    const p = usePagination(10)
    p.setTotal(20)
    p.goTo(0)
    expect(p.page.value).toBe(1)
    p.goTo(99)
    expect(p.page.value).toBe(1)
  })

  it('hasNext and hasPrev reflect state', () => {
    const p = usePagination(10)
    p.setTotal(20)
    expect(p.hasPrev.value).toBe(false)
    expect(p.hasNext.value).toBe(true)
    p.next()
    expect(p.hasPrev.value).toBe(true)
    expect(p.hasNext.value).toBe(false)
  })

  it('reset restores initial state', () => {
    const p = usePagination(10)
    p.setTotal(50)
    p.next()
    p.reset()
    expect(p.page.value).toBe(1)
    expect(p.total.value).toBe(0)
  })
})
