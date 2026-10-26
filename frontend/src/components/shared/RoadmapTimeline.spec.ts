// =============================================================================
// RoadmapTimeline -- the buyer reads a month, not a day
// =============================================================================

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import type { RoadmapItemResponse } from '@/api/types'
import RoadmapTimeline from './RoadmapTimeline.vue'

const item = {
  id: 'r1',
  kind: 'milestone',
  title: 'Launch',
  description: null,
  target_date: '2026-03-15',
  status: 'completed',
  order: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
} as unknown as RoadmapItemResponse

function dateText(locale: 'en' | 'ru'): string {
  const i18n = createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })
  const w = mount(RoadmapTimeline, {
    props: { items: [item] },
    global: { plugins: [i18n] },
  })
  return w.find('time.ds-timeline__date').text()
}

describe('RoadmapTimeline dates', () => {
  it('shows the month and the year, no day (English)', () => {
    const text = dateText('en')
    expect(text).toContain('March')
    expect(text).toContain('2026')
    expect(text).not.toMatch(/\b15\b/)
  })

  it('shows the month and the year, no day (Russian)', () => {
    const text = dateText('ru')
    expect(text).toMatch(/март/i)
    expect(text).toContain('2026')
    expect(text).not.toMatch(/\b15\b/)
  })
})

// The backend's roadmap statuses are planned, in_progress and completed
// (companies/constants.py RoadmapItemStatus). The timeline once knew `done`
// only, so every completed item read as upcoming with the raw word on its
// chip.
describe('RoadmapTimeline statuses', () => {
  function mountWith(status: string, locale: 'en' | 'ru' = 'en') {
    const i18n = createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })
    return mount(RoadmapTimeline, {
      props: { items: [{ ...item, status } as unknown as RoadmapItemResponse] },
      global: { plugins: [i18n] },
    })
  }

  it('shows a completed item as done, with its translated, success-looking chip', () => {
    const w = mountWith('completed')
    expect(w.find('li.ds-timeline__item').attributes('data-state')).toBe('done')
    const chip = w.findAll('.ds-badge').find((b) => b.text() === 'Completed')
    expect(chip).toBeDefined()
    expect(chip!.classes()).toContain('ds-badge--success')
    expect(w.text()).not.toContain('completed')
  })

  it('translates the completed chip into Russian', () => {
    const w = mountWith('completed', 'ru')
    expect(w.findAll('.ds-badge').some((b) => b.text() === 'Выполнено')).toBe(true)
  })

  it('shows an in-progress item as current and a planned one as upcoming', () => {
    expect(mountWith('in_progress').find('li.ds-timeline__item').attributes('data-state')).toBe(
      'current',
    )
    expect(mountWith('planned').find('li.ds-timeline__item').attributes('data-state')).toBe(
      'upcoming',
    )
  })
})
