// =============================================================================
// EventCard -- THE AFFORDANCE CONTRACT
// =============================================================================
//
// WHAT THIS GUARDS. EventCard has TWO root branches, and only one of them is a
// click target:
//
//   compact -- a real <button> that emits click. The dashboard widget listens
//              and pushes to the events screen.
//   full    -- a plain <div>. It does NOT emit, and it must paint NOTHING that
//              says otherwise.
//
// THE DEFECT THIS WAS WRITTEN FOR. `full` used to carry cursor:pointer, a
// :hover lift, an :active depress AND an @click that emitted -- while its only
// call site attached no listener. Every card on /investor/events looked
// pressable and did nothing; with no tabindex and no role, a keyboard user
// could not even discover it was inert. Two root branches is exactly why a
// scan that reads only a component's first root missed it.
//
// WHY THE SOURCE-READING HALF IS HERE AND NOT ONLY IN A SCRIPT. The behaviour
// half (does it emit?) is testable by mounting. The PAINT half (does it look
// pressable?) is not: scoped styles are not applied in happy-dom, so a mounted
// assertion cannot see cursor:pointer. Reading the SFC's own <style> block is
// the only way to assert the paint half in a file the whole team can run --
// and the paint half is the half a user actually sees.
//
// Every test here was watched to FAIL before it was kept -- an assertion that
// has never failed has not been shown to assert anything.
// =============================================================================

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import EventCard from './EventCard.vue'
import type { EventResponse } from '@/api/types'

const event = {
  id: 1,
  title: 'Quarterly investor call',
  starts_at: '2026-09-01T15:00:00Z',
  location: 'Dubai',
  description: 'A description long enough to render the preview line.',
  url: 'https://example.com/event',
} as unknown as EventResponse

// -----------------------------------------------------------------------------
// Behaviour
// -----------------------------------------------------------------------------
// ⚠ SELECT THE BRANCH, NEVER THE WRAPPER. The template's first root node is an
// HTML comment, so this is a FRAGMENT component: `wrapper.element` is the test
// wrapper div, not the button, and `wrapper.trigger('click')` therefore fires
// on nothing and records no emit. That reads exactly like "compact is broken".
// The same two-root shape is why scans that read only a component's first root
// missed the dead affordance in the first place.
describe('EventCard — which branch is a click target', () => {
  it('compact renders a real <button>, and not the full card', () => {
    const w = mount(EventCard, { props: { event, variant: 'compact' } })
    expect(w.find('button.event-card--compact').exists()).toBe(true)
    expect(w.find('.event-card--full').exists()).toBe(false)
  })

  it('compact emits click, because its call site listens', async () => {
    const w = mount(EventCard, { props: { event, variant: 'compact' } })
    await w.get('button.event-card--compact').trigger('click')
    expect(w.emitted('click')).toBeTruthy()
  })

  it('full does NOT emit click', async () => {
    const w = mount(EventCard, { props: { event, variant: 'full' } })
    await w.get('.event-card--full').trigger('click')
    expect(w.emitted('click')).toBeFalsy()
  })

  it('full is a plain div — not a button, and not given a fake role', () => {
    const w = mount(EventCard, { props: { event, variant: 'full' } })
    const card = w.get('.event-card--full')
    expect(card.element.tagName).toBe('DIV')
    expect(w.find('button.event-card--compact').exists()).toBe(false)
    expect(card.attributes('role')).toBeUndefined()
    // No tabindex either: an inert card must not be reachable by Tab. If the
    // card ever GAINS a destination, it gets a real button or a role AND a
    // listener -- not a tabindex on its own.
    expect(card.attributes('tabindex')).toBeUndefined()
  })

  it('full still offers the external link, which is the one real affordance', () => {
    const w = mount(EventCard, { props: { event, variant: 'full' } })
    const a = w.find('a.event-card__link')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('https://example.com/event')
    expect(a.attributes('rel')).toContain('noopener')
  })
})

// -----------------------------------------------------------------------------
// Paint
// -----------------------------------------------------------------------------
// LOCATING THE SFC. Not via import.meta.url: under the vitest transform that is
// not a file: URL and fileURLToPath throws on it. Not via a bare
// resolve(process.cwd(), ...) either -- that pins the spec to being run from
// frontend/, and a second party running it from the repo root got ENOENT before
// a single test executed. Since the whole reason this check lives in the
// tracked tree is that ANYONE can run it, it walks up instead.
//
// It still fails LOUDLY: if the file is genuinely gone, the throw below names
// every path tried. The one thing it must never do is degrade into reading
// nothing and passing.
const REL = 'src/components/shared/EventCard.vue'

function locateSfc(): string {
  const tried: string[] = []
  let dir = process.cwd()
  for (let i = 0; i < 6; i++) {
    for (const rel of [REL, `frontend/${REL}`]) {
      const p = resolve(dir, rel)
      tried.push(p)
      if (existsSync(p)) return p
    }
    const up = dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error(
    `EventCard.spec.ts could not locate ${REL} from ${process.cwd()}.\nTried:\n  ${tried.join('\n  ')}`,
  )
}

const sfc = readFileSync(locateSfc(), 'utf8')

/** Blank comment bodies, keeping length. Without this the selector capture
 *  swallows the preceding comment, and a comma inside that comment splits the
 *  selector list so a selector never matches as a whole token. */
function maskComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
}

/** Body of the FIRST rule whose selector list contains `selector` as a whole
 *  token, or null. Bounded to one rule: an unbounded scan would swallow the
 *  next rule and report properties that are not in this one. */
function ruleBody(selector: string): string | null {
  const style = /<style[^>]*>([\s\S]*)<\/style>/.exec(sfc)
  if (!style) return null
  const css = maskComments(style[1])
  const re = /([^{}]+)\{([^{}]*)\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    if (m[1].split(',').map((s) => s.trim()).includes(selector)) return m[2]
  }
  return null
}

describe('EventCard — the full variant paints nothing pressable', () => {
  it('the rules under test actually exist (guard: a typo must not pass as absence)', () => {
    expect(ruleBody('.event-card--full')).not.toBeNull()
    expect(ruleBody('.event-card--compact')).not.toBeNull()
  })

  it('.event-card--full has no cursor', () => {
    expect(ruleBody('.event-card--full')).not.toMatch(/cursor/)
  })

  it('.event-card--full has no :hover rule', () => {
    expect(ruleBody('.event-card--full:hover')).toBeNull()
  })

  it('.event-card--full has no :active rule', () => {
    expect(ruleBody('.event-card--full:active')).toBeNull()
  })

  it('compact KEEPS cursor:pointer — the fix must not flatten both variants', () => {
    expect(ruleBody('.event-card--compact')).toMatch(/cursor:\s*pointer/)
  })
})
