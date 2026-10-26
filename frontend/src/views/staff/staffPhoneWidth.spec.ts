// The phone-width rule of the staff screens (the admin cabinet in Telegram's in-app browser,
// ~390 px): no grid track may size to its content, or the sub-navigation (a row that scrolls
// inside itself) and the long rows widen the page and shift it sideways. happy-dom has no
// layout, so this reads the stylesheets; the measured check at 375 px (document scrollWidth
// 435 before, 375 after) was run in a real browser against the same CSS.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(__dirname, '..', '..')
const dirs = [join(root, 'views', 'staff'), join(root, 'components', 'staff')]

function styleRules(file: string): string[] {
  const src = readFileSync(file, 'utf-8')
  const i = src.indexOf('<style')
  if (i < 0) return []
  return src.slice(i).match(/[^{}]*\{[^{}]*\}/g) ?? []
}

describe('staff screens at phone width', () => {
  it('every grid in a staff screen has an explicit shrinkable column', () => {
    const bad: string[] = []
    for (const d of dirs) {
      for (const f of readdirSync(d).filter((n) => n.endsWith('.vue'))) {
        for (const rule of styleRules(join(d, f))) {
          if (/display:\s*grid/.test(rule) && !/grid-template-columns/.test(rule)) {
            bad.push(`${f}: ${rule.split('{')[0].trim()}`)
          }
        }
      }
    }
    expect(bad).toEqual([])
  })

  it('the design system keeps the sub-navigation, the dialog body and the shell from widening the page', () => {
    const css = readFileSync(join(root, 'styles', 'ds', 'components.css'), 'utf-8')
    expect(css).toMatch(/\.ds-subnav \{\s*min-inline-size: 0;/)
    expect(css).toMatch(
      /\.ds-dialog__body \{ display: grid; grid-template-columns: minmax\(0, 1fr\);/,
    )
    expect(css).toMatch(/overflow-x: clip;\s*\}\s*\.ds-shell--framed/)
  })
})
