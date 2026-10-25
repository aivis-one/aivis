// A document in a sandboxed frame takes the theme's text and link colours: the style goes
// into the text handed to the frame, first in the head, with a colour the page computed
// and nothing else.

import { describe, it, expect } from 'vitest'
import { themeDocument } from './themeDocument'

const DARK = { scheme: 'dark', text: '#f4f4f5', link: 'rgb(120, 140, 255)' } as const

describe('themeDocument', () => {
  it('adds the style first in the head', () => {
    const out = themeDocument('<html><head><title>T</title></head><body>x</body></html>', DARK)
    expect(out).toContain('<head><style>:root{color-scheme:dark}')
    expect(out).toContain('body,body *{color:#f4f4f5!important;background:transparent!important}')
    expect(out).toContain('a,a *{color:rgb(120, 140, 255)!important}')
    expect(out.indexOf('<style>')).toBeLessThan(out.indexOf('<title>'))
  })

  it('makes a head when the document has only an html element, and a style alone when it has neither', () => {
    expect(themeDocument('<html><body>x</body></html>', DARK)).toContain('<html><head><style>')
    expect(themeDocument('<p>x</p>', DARK).startsWith('<style>')).toBe(true)
  })

  it('leaves the document as it is when a colour is not a colour', () => {
    const html = '<html><head></head><body>x</body></html>'
    expect(themeDocument(html, { ...DARK, text: '' })).toBe(html)
    expect(themeDocument(html, { ...DARK, link: 'red;}</style><script>1' })).toBe(html)
  })
})
