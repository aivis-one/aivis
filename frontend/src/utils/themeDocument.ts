// =============================================================================
// A document shown in a sandboxed frame takes the theme's text and link colours
// =============================================================================
//
// A document in a frame cannot see the page's colour tokens, and the issued agreement
// paints its text in fixed dark colours and no ground, so by night it would be dark text
// on the frame's dark ground. The design system's document viewer (K36) says the app adds a style to the
// document before it is shown: its text colour is `--text-primary`, its links
// `--primary` (values read from the page for the theme in force), and no ground of its
// own, so the frame's ground (`--bg-surface`) shows through. The style goes first in
// the document's head and every declaration is important, so it wins over the colours
// the document itself carries.
//
// Only the text handed to the frame is changed. The file a reader saves is the
// document as it was issued.

export interface DocumentColours {
  /** The theme in force; sets `color-scheme` so the frame's own controls match. */
  scheme: 'light' | 'dark'
  /** `--text-primary` as the page computes it. */
  text: string
  /** `--primary` as the page computes it. */
  link: string
}

// A computed custom property is a colour such as `#1a2b3c` or `rgb(26, 43, 60)`;
// anything else is not put into a stylesheet.
const COLOUR = /^(#[0-9a-f]{3,8}|(rgb|hsl|oklch|color)a?\([0-9a-z\s.,%/-]+\))$/i

function safe(colour: string): string | null {
  const value = colour.trim()
  return COLOUR.test(value) ? value : null
}

/** The document with the theme's style added; the document itself when a colour is not usable. */
export function themeDocument(html: string, colours: DocumentColours): string {
  const text = safe(colours.text)
  const link = safe(colours.link)
  if (!text || !link) return html
  const style =
    `<style>:root{color-scheme:${colours.scheme}}` +
    `body,body *{color:${text}!important;background:transparent!important}a,a *{color:${link}!important}</style>`
  const head = /<head(\s[^>]*)?>/i.exec(html)
  if (head) {
    const at = head.index + head[0].length
    return html.slice(0, at) + style + html.slice(at)
  }
  const root = /<html(\s[^>]*)?>/i.exec(html)
  if (root) {
    const at = root.index + root[0].length
    return html.slice(0, at) + '<head>' + style + '</head>' + html.slice(at)
  }
  return style + html
}
