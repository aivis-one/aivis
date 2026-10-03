# AIVIS.ONE testing guide (landing and every page after it)

Scope: static multilingual site, EN base, RU now, RTL (Arabic) later; mobile first; strict CSP with
hashed inline blocks, no third-party scripts; Cloudflare static hosting. Written 2026-10-02 from the
sources in section S. Every rule carries a source key; the URL and the date seen are in S.

How to use it. Run `python guides/run-checks.py` (stdlib and Chrome only) for everything a machine can
decide; the rule id in its output (A2, B7, F10 ...) is the id in this guide. Then do the rows marked
MANUAL. The one-page version is `test-checklist.md`. A rule whose "how" says `run-checks` is
automated; `curl` and `chrome` rows can be run by hand.

Verdict words: FAIL blocks release of the page; WARN is fixed or consciously accepted in writing;
INFO is a fact to look at. Numbers marked HOUSE are this guide's proposal and belong to the owner,
not to the standard they sit beside.

## Does the checker itself work? `python run-checks.py --self-test`

A check that cannot fail proves nothing. `--self-test` starts a throwaway server on a free
port (own thread, stopped at the end), serves `guides/fixtures/` (a page with one planted defect per
FAIL-class check, plus a clean control pair), runs the checks against both, and prints per check
FIRED or NOT FIRED, and whether the clean control stayed quiet. It exits 1 if any planted defect is
missed or any control is dirty. Run it after every change to `run-checks.py` and before trusting a
green normal run. Not covered by a planted defect: the "Tab reached fewer than 5 controls" branch of B8.

## What run-checks cannot see (read before trusting a green run)

Chromium only (no Gecko or WebKit); no network throttling, so LCP and CLS are smoke tests, not field
data; contrast covers flat backgrounds only; it cannot judge whether a translation is good, whether
an icon means what it should, or how a screen reader sounds. Those are the MANUAL rows.

---

## A. Mobile layout

Breakpoints to test, always all nine: 320, 360, 375, 390, 414 (phones), 768 (tablet portrait),
1024 (tablet landscape / small laptop), 1280, 1440 (desktop), plus landscape 812x375. Material 3 groups
widths into compact 0-599, medium 600-840, expanded 840+ [S8]; the nine widths put at least two on
each side of every class boundary and the 320 floor that WCAG reflow names [S1].

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| A1 | Viewport meta is `width=device-width, initial-scale=1`; zoom is never disabled (no `user-scalable=no`, no `maximum-scale` below 5) | run-checks A1; or `curl -s URL \| grep -i viewport` | meta present, no zoom lock | S1 (1.4.4), S9 |
| A2 | No horizontal scroll at any width, down to 320 CSS px (reflow); `scrollWidth <= width` and no element's right edge past the viewport | run-checks A2 (nine widths); by hand: Chrome DevTools device toolbar, width 320, check for a horizontal scrollbar | scrollWidth equals the width at all nine widths | S1 (1.4.10) |
| A3 | Touch targets: at least 24x24 CSS px for every control (AA hard rule); at least 44x44 pt for primary touch controls on phone (Apple) and 48 dp (Material) as the design target. Inline links inside a sentence are exempt | run-checks A3 (FAIL under 24, WARN under 44 at 360 and 390) | zero under 24; list of those under 44 reviewed | S1 (2.5.8), S7, S8, S2 |
| A4 | Safe areas: with `viewport-fit=cover`, fixed bars and edge-hugging content pad with `env(safe-area-inset-*)`; landscape notch is not covered | run-checks A4 (static); MANUAL: iPhone landscape or Chrome device toolbar "iPhone 14 Pro Max" landscape | env() used wherever cover is set; nothing under the notch | S10 |
| A5 | Body text 16 px or larger on mobile, nothing under 12 px; text resizes to 200% without loss | run-checks A5; MANUAL: Chrome settings font size "Very large" and browser zoom 200% | no text under 12 px; majority of elements at 16 px or more; nothing clipped at 200% | S1 (1.4.4), S7 |
| A6 | HOUSE number, reported as WARN, never FAIL: line length target 45-75 characters, ceiling 80. The 80 is WCAG 1.4.8, a Level AAA criterion, so it is not an AA requirement; the owner sets the real number | run-checks A6 (measures real lines of ten paragraphs at 320, 390, 1280) | longest line at most 80 at every width, else WARN | S1 (1.4.8 AAA), S11 |
| A7 | Every page is looked at in all nine widths, light and dark, EN and RU, before it ships | process: run-checks plus screenshots `python run-checks.py --shots` (saves to `guides/shots/`) | nine screenshots per locale reviewed by a person | S8 |
| A8 | Orientation is never locked; landscape phone works | run-checks A8 (812x375) | no horizontal scroll, nothing unreachable | S1 (1.3.4) |
| A9 | Hover is never the only way to reach anything; tap equivalents exist; hover styles sit in `@media (hover: hover)` | run-checks A9 (INFO count); MANUAL: Chrome DevTools "Sensors" touch emulation, tap every control | every hover effect has a focus or tap equivalent | S1 (1.4.13) |
| A10 | Text spacing override does not clip or overflow (line-height 1.5, paragraph spacing 2x, letter-spacing 0.12em, word-spacing 0.16em) | run-checks A10 (injects the four values at 390 and 1280) | no overflow, no clipped text in an open section | S1 (1.4.12) |
| A11 | Sticky headers do not eat the viewport on a short landscape screen (header under 20 percent of the height at 375 px high) | MANUAL: device toolbar 812x375, scroll | content readable, header does not dominate | S8 (HOUSE threshold) |

## B. Accessibility (WCAG 2.2 AA, static landing)

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| B1 | `<html lang>` is set and matches the locale; `dir` is set | run-checks B1 | `lang=en` on EN, `lang=ru` on RU | S1 (3.1.1), S5 |
| B2 | Each page has a unique, descriptive `<title>` | run-checks E1 | present, unique per page and locale | S1 (2.4.2) |
| B3 | One `<h1>`; heading levels never skip down; headings describe sections | run-checks B3 | one h1; no jump larger than one level | S1 (1.3.1, 2.4.6) |
| B4 | Landmarks: header, nav (each labelled), main, footer; a skip link to main is the first tab stop | run-checks B4 | all present; first Tab stop is "Skip to content" | S1 (2.4.1, 1.3.1) |
| B5 | Every `<img>` has `alt` (empty alt for decoration; meaningful alt for content) | run-checks B5; MANUAL: read each alt aloud | none missing; alt describes purpose | S1 (1.1.1) |
| B6 | Every link, button and `summary` has an accessible name; icon-only buttons carry `aria-label` in the page language | run-checks B6 and C3 (RU names still English fail) | none empty | S1 (4.1.2, 2.4.4) |
| B7 | Contrast: text 4.5:1 (large text 3:1); UI components and graphics 3:1; measured in BOTH themes, at rest (after reveal animations finish) | run-checks B7 (flat backgrounds); MANUAL: DevTools "CSS Overview" and the colour picker for gradients and images; non-text 3:1 by eye on borders, focus ring, icons | zero failing text in light and dark | S1 (1.4.3, 1.4.11) |
| B8 | Keyboard: everything reachable by Tab in a logical order; visible focus indicator; focused control never entirely hidden behind the sticky header (2.4.11); no keyboard trap | run-checks B8 (presses Tab through the page, checks outline or shadow, checks what covers each stop) | all controls reached, indicator on each, none hidden | S1 (2.1.1, 2.4.7, 2.4.11) |
| B9 | Reduced motion: with `prefers-reduced-motion: reduce` no looping or long animation runs; the CSS contains the media query whenever it has motion | run-checks B9 (static and emulated) | zero running long animations | S12, S1 (2.2.2, 2.3.3) |
| B10 | Target size: see A3 (WCAG 2.5.8) | run-checks A3 | see A3 | S1 |
| B11 | No duplicate `id`; every `aria-controls` / `href="#x"` target exists | run-checks B11 and H1 | zero duplicates, zero dangling | S1 (4.1.2) |
| B12 | The drawer behaves as a modal dialog: opens by tap and Enter, focus moves in, Escape closes, focus returns to the button, `aria-expanded` and `aria-modal` are truthful | run-checks B12 and H5; MANUAL: keyboard only | all four behaviours | S1 (2.1.2, 4.1.2), S14 |
| B13 | Decorative SVG icons are `aria-hidden` and not focusable | MANUAL: `curl -s URL \| grep -o '<svg[^>]*>' \| sort \| uniq -c`, every svg has aria-hidden or a title | all hidden or labelled | S1 (1.1.1) |
| B14 | Link text makes sense out of context ("Pre-order on sankord.com", never "click here"); links opening a new tab say so or are expected | MANUAL: read the list of links (VoiceOver/NVDA links list) | no ambiguous names | S1 (2.4.4) |
| B15 | Screen reader pass on the real devices: NVDA + Chrome on Windows, VoiceOver on iPhone Safari, TalkBack on Android Chrome | MANUAL: walk heading list, landmarks, language switch, theme toggle, drawer | each announces role, name, state; language switch announces language | S1, S15 |
| B16 | Zoom: 400 percent browser zoom at 1280 wide is the 320 reflow case | MANUAL: Ctrl+ to 400 percent | single column, no horizontal scroll, nothing clipped | S1 (1.4.10) |
| B17 | Language switch links carry `lang` and `hreflang`; the current language has `aria-current` | run-checks B17 | present on each | S1 (3.1.2), S5 |
| B18 | Forced colours (Windows High Contrast): the page stays usable; icons and focus ring remain visible | MANUAL: Chrome DevTools Rendering tab, "Emulate CSS media feature forced-colors: active" | all controls distinguishable | S1 (1.4.11) |
| B19 | Consistent help and navigation across pages (2.4.x, 3.2.3, 3.2.4, 3.2.6): same header, footer, order on every page | MANUAL on each new page | same order, same labels | S1 |
| B20 | Authentication and forms (when they arrive): no cognitive tests, paste allowed, no re-asking known data, `autocomplete` tokens, visible labels, error text names the field and the fix | MANUAL per form (see H6) | no 3.3.7 or 3.3.8 failure | S1 |

## C. Internationalisation and translation quality

### C.1 Machine checks (run-checks does all of these)

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| C1 | Structure parity between locales: same ids, same counts of headings, links, images, buttons, sections, list items, paragraphs | run-checks C1 | counts equal; no id in only one locale | S16 (MQM "design and markup", "omission") |
| C2 | `lang` and `dir` match locale; `hreflang`/`lang` on switch links; `dir="rtl"` on `<html>` for Arabic | run-checks B1, B17 | match | S5, S17 |
| C3 | No untranslated strings: no Latin-only text in RU nodes (brand allowlist: AIVIS, SANKORD, EXSPECS, LLC, FAQ) and no English `alt`, `aria-label`, `title` in RU | run-checks C3 | none outside the allowlist | S16 (accuracy: untranslated) |
| C4 | Length expansion: RU text roughly 10-30 percent longer than EN; layout holds at 320 with RU, and with 40 percent more text for later languages | run-checks C4 (ratio and strings above x1.5); MANUAL: paste a 40 percent longer string into the longest button and card at 320 | total ratio at most 1.3; no overflow | S18 (W3C i18n: text expansion) |
| C5 | RU typography: quotes are «ёлочки» (nested „лапки“); dash is the em dash, with a non-breaking space before it; no hyphen-with-spaces as a dash; one-and-two-letter words (в, к, с, у, о, и, а, на, по, за, из, от, до, не, но) are glued to the next word with a no-break space; decimal comma; thousands separated by a no-break space | run-checks C5 and C7 (regex over every text node and alt) | zero straight quotes, balanced « », zero hyphen-dashes; the no-break space WARNs are fixed or accepted | S19, S20 |
| C6 | Typographic hygiene in both languages: real ellipsis, no double spaces, no space before punctuation, every sentence-length block ends with terminal punctuation | run-checks C6 | zero | S19 |
| C7 | Numbers, dates, currency follow locale: RU `1 000,50`; EN `1,000.50`; dates by `Intl.DateTimeFormat` or written out, never ambiguous `03/04` | run-checks C5/C7 (decimals, thousands); MANUAL for dates; `grep -nE '[0-9]{2}/[0-9]{2}' ` over the sources | none ambiguous | S21 (CLDR) |
| C8 | RTL readiness (Arabic later): logical properties (`margin-inline-start`, `inset-inline`, `text-align: start`) instead of left/right; `dir=rtl` simulation shows no overflow; directional icons mirrored; mixed-direction runs (brand names, numbers) isolated with `<bdi>` or `dir=auto`; an Arabic-capable font loaded | run-checks C8 (physical CSS declarations counted; rtl simulation at 390 and 1280); MANUAL: view the page with `dir=rtl` and a few Arabic paragraphs | zero physical declarations that matter; mirrored layout correct | S4, S17, S22 |
| C9 | The language switch keeps the user on the same page (page maps to its sibling, not to the home) and sets the preference | MANUAL on every new page; run-checks H3 opens the menu | lands on the equivalent page | S17 |
| C10 | Brand and product terms are identical in every locale (AIVIS.ONE, SANKORD, EXSPECS) and appear in both | run-checks C11 | none missing | S16 (terminology) |
| C11 | `<title>`, meta description and Open Graph text are translated, not copied | run-checks C13 | differ from EN | S5, S23 |

### C.2 Native-reader checklist (MANUAL; a machine cannot do these)

Use the MQM categories [S16] as the review form; one reader who is a native speaker of the target
language reads the whole page on a phone, once for meaning against the EN source, once without it.
Record each defect as category, severity, quote, fix. Severity: critical (changes a claim or breaks
the page), major (misleads or confuses), minor (reads wrong but is understood). Release rule (HOUSE):
zero critical, zero major, minor listed.

| MQM category | Ask |
|---|---|
| Accuracy | Is every claim, number, date and condition the same as the source? Anything added, dropped or softened? Refund, price and legal sentences word for word in meaning |
| Terminology | Same word for the same concept everywhere? Product terms match the glossary and the other pages |
| Fluency (linguistic conventions) | Grammar, spelling, punctuation, agreement, case; no calque from English; no stacked genitives |
| Style | Tone matches the brand voice for this audience (formal "вы", no slang); sentence length natural; headings read as headings |
| Locale conventions | Dates, numbers, currency, quotes, dashes, address forms, units |
| Audience appropriateness | Nothing culturally off; examples make sense for this market |
| Design and markup | Line breaks, orphans and one-word last lines, truncated text, text in buttons fits, nothing left in English |
| Verity | Are the claims still true for this market and law |

Also: read headings and buttons aloud with a screen reader in the target language (voice and
pronunciation of brand names); read the page at 320 and in dark mode, where line breaks differ.

## D. Performance

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| D1 | LCP at most 2.5 s at the 75th percentile; the LCP image is discoverable in HTML, `fetchpriority=high`, never `loading=lazy` | run-checks D1 (lab, unthrottled, smoke); optional: `npx lighthouse URL --form-factor=mobile --throttling-method=simulate --only-categories=performance` | 2.5 s or less lab on simulated slow 4G | S24, S25 |
| D2 | INP at most 200 ms; keep main-thread tasks short; a landing with a few small scripts should show no long tasks | run-checks D2 (long-task proxy); MANUAL: DevTools Performance, tap menu and theme toggle | no task over 50 ms on interaction | S24 |
| D3 | CLS at most 0.1: images carry `width` and `height`; fonts do not reflow text; no content injected above existing content | run-checks D3 and D7 | 0.1 or less on mobile and desktop loads | S24, S26 |
| D4 | Page weight budget on first load (HOUSE): 500 KB transferred soft, 1 MB hard, per page, EN and RU each | run-checks D4 | at most 500 KB | S24 (HOUSE number) |
| D5 | No third-party host is contacted; no third-party script | run-checks D5 (static and runtime) | none | S1 (privacy), S27 |
| D6 | Fonts: WOFF2 only, subset per script (latin, cyrillic, later arabic) with `unicode-range`, self-hosted, `font-display` set, `size-adjust` fallback to prevent shifts; load only the weights used | run-checks D6 (formats and sizes) | WOFF2, each file under about 60 KB | S28 |
| D7 | Images: `width`/`height` set; intrinsic size at most 1.5x of rendered size times DPR; modern formats (AVIF/WebP) with fallback for photos; `srcset`/`sizes` for the photo; SVG for marks | run-checks D7 (finds oversize images) | no image more than 1.5x oversize | S26, S28 |
| D8 | Cache and compression: `Cache-Control: public, max-age=31536000, immutable` on hashed assets; HTML revalidated; Brotli or gzip on text | `curl -sI -H "accept-encoding: br" https://aivis.one/assets/...` on the deployed host; `_headers` file | immutable on assets; `content-encoding: br` | S29 |
| D9 | No render-blocking third-party CSS or JS; inline critical CSS acceptable under hashed CSP | run-checks D5, F10 | none | S25 |
| D10 | Optional full audit: `npx lighthouse http://127.0.0.1:8731/ --form-factor=mobile --only-categories=performance,accessibility,best-practices,seo --chrome-flags="--headless=new" --output=json --output-path=guides/lh.json` (needs an npm download; not installed by this guide) | run once per release on the deployed URL | performance 90 or more, accessibility 100, best-practices 100, seo 100 | S30 |

## E. SEO and sharing

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| E1 | Unique, descriptive title, about 30-60 characters | run-checks E1 | in range | S31 |
| E2 | Meta description 70-160 characters, unique per page and locale | run-checks E2 | in range | S31 |
| E3 | One absolute `https` canonical per page, pointing at itself | run-checks E3 | one, self | S31 |
| E4 | hreflang: each locale lists itself and all others, plus `x-default`; links are reciprocal; codes valid (`en`, `ru`, `ar`); in the head | run-checks E4; `curl -s URL \| grep -i hreflang` on every page of every locale | complete set on every page; every target returns 200 and links back | S3 |
| E5 | `robots.txt` references the sitemap; sitemap lists every indexable page in every locale, optionally with `xhtml:link` alternates; URLs match the canonicals | run-checks E5; `curl -s https://aivis.one/sitemap.xml` | all pages listed, status 200 | S3, S31 |
| E6 | Open Graph: `og:title`, `og:type`, `og:url`, `og:image` (with `og:image:alt`, width, height); `twitter:card`; `og:locale` and alternates per locale; image 1200x630 | run-checks E6; MANUAL: paste the URL into a messenger or the Telegram preview | all four required properties present, image loads | S32 |
| E7 | Mobile-first indexing: the mobile page has the same content, title and description as the desktop one (one responsive page satisfies it); nothing primary behind lazy-load that needs interaction | MANUAL: compare run-checks text at 390 and 1280; run-checks G4 (no JS) | same content | S33 |
| E8 | Indexable: HTTP 200, no `noindex`, not blocked by robots.txt | run-checks E8, H0 | indexable | S31 |
| E9 | Favicon (SVG plus PNG fallback) and apple-touch-icon | run-checks E11 | present | S31 |
| E10 | Structured data (Organization) optional; a JSON-LD block needs a CSP check (data blocks are not executed, but keep the hash policy) | MANUAL: Rich Results Test on the deployed URL | valid or absent | S31 |

## F. Security headers and CSP

The landing delivers its CSP in a meta element. A meta CSP cannot set `frame-ancestors`, `report-to`
or `sandbox`; those only work as HTTP headers, so the Cloudflare `_headers` file is the deploy truth
and must carry them [S34, S29].

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| F1 | CSP present; no `'unsafe-inline'`, no `'unsafe-eval'`, no wildcard in script or style sources; hashes or nonces for inline blocks | run-checks F1 | present, strict | S34 |
| F2 | `object-src 'none'` (or `default-src 'none'`), `base-uri` set, `form-action` set | run-checks F2 | all set | S34 |
| F3 | Clickjacking: `frame-ancestors 'none'` (or `X-Frame-Options: DENY`) as a header | run-checks F3 (reads the `_headers` file); `curl -sI URL \| grep -i -E 'frame-ancestors\|x-frame'` on the deployed host | present as header | S34, S35 |
| F4 | `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` (only after every subdomain is https) | run-checks F4; `curl -sI https://aivis.one/ \| grep -i strict` | present, max-age at least one year | S35 |
| F5 | `X-Content-Type-Options: nosniff` | run-checks F5 | present | S35 |
| F6 | `Referrer-Policy: strict-origin-when-cross-origin` (or stricter) | run-checks F6 | present | S35 |
| F7 | `Permissions-Policy: geolocation=(), camera=(), microphone=()` | run-checks F7 | present | S35 |
| F8 | `Cross-Origin-Opener-Policy: same-origin` (and `Cross-Origin-Resource-Policy: same-site` for assets) | run-checks F8 | present | S35 |
| F9 | No inline event handlers, no `style=` attributes, no external hosts in the CSP | run-checks F9 | zero | S34 |
| F10 | Every inline `<script>` and `<style>` block is covered by a `sha256` in the CSP, and no stale hash remains. Hash the text after newline normalisation (CRLF to LF); a build that changes a byte changes the hash | run-checks F10 | all inline blocks hashed, zero stale | S34 |
| F11 | No CSP violation and no console error at runtime, on both locales and both themes | run-checks F11, H11; MANUAL: DevTools console after using the drawer, theme toggle and language switch | zero | S34 |
| F12 | After deploy, scan the live URL: `https://developer.mozilla.org/en-US/observatory` or `https://securityheaders.com/?q=aivis.one` | MANUAL on the deployed host (needs the public URL) | grade A or better | S35 |
| F13 | Storage: only the theme preference in `localStorage`; no cookies; no tracking | DevTools Application tab; run-checks D5 | one key | S34 |

## G. Cross-browser and devices

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| G1 | Engines and versions (HOUSE list): Chromium (Chrome and Edge, latest and previous major), WebKit (Safari iOS and macOS, latest and previous), Gecko (Firefox, latest and ESR); Samsung Internet latest as a spot check | run-checks G1 reports the Chromium build it used; the other two are MANUAL | page works in all three engines | S36, S37 |
| G2 | Emulation: Chrome DevTools device toolbar and `Emulation.setDeviceMetricsOverride` (run-checks does it); Firefox Responsive Design Mode; Safari Responsive Design Mode. Emulation checks layout, never touch, fonts, rendering or safe-area; at least one real iPhone and one real Android phone per release | run-checks (nine widths); MANUAL real devices | no layout difference between emulation and device | S38 |
| G3 | Newer CSS in use is Baseline in every engine of G1 (`text-wrap`, `color-mix`, `:has`, `dvh`, container queries) with a fallback where it is not | run-checks G3 lists the features found; check each on MDN Baseline or caniuse | Baseline widely or newly available, or graceful fallback | S36, S37 |
| G4 | Works without JavaScript: all text readable, links work, theme falls back to system | run-checks G4 (script execution disabled) | main text present | S1 (1.3.1) |
| G5 | Opens from `file://` double-click (relative asset paths) | run-checks H10; MANUAL: double-click the built `index.html` | assets load | HOUSE (delivery contract) |
| G6 | Dark mode and light mode both fully styled; the preboot sets `data-theme` before first paint with no flash | run-checks H4 (light and dark, both emulated) | correct first paint | S39 |
| G7 | Print is readable (optional) | MANUAL: DevTools Rendering, "Emulate CSS media type: print" | no cut text | S36 |
| G8 | Slow network and CPU: 4x CPU slowdown and "Slow 4G" in DevTools Performance panel still usable | MANUAL | content visible under 5 s | S24 |

## H. Functional

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| H1 | Every internal link resolves (200) and every in-page anchor exists; sub-resources do not 404 | run-checks H1 (files, anchors, sub-resources); root routes such as `/login` are checked by hand on the deployed host | zero 404 | S1 (2.4.4) |
| H2 | External links answer; `target=_blank` links carry `rel=noopener` | run-checks H2 | answer 200 or 3xx | S34 |
| H3 | Language switch: opens by tap and keyboard, current language marked, link goes to the same page in the other locale | run-checks H3; MANUAL per page (C9) | works | S17 |
| H4 | Theme toggle: flips, saves the choice, `aria-pressed` reflects it, survives reload, defaults to system | run-checks H4 | all true | S39 |
| H5 | Drawer: opens, closes, focus handling (B12), links inside work, closes after choosing an anchor | run-checks H5 and B12 | works | S14 |
| H6 | Forms (none on the landing; `form-action 'none'`). When one arrives: visible label per field, `autocomplete`, correct `type` and `inputmode`, error messages name the field and the fix, success is announced, no data lost on error, works without JS if it posts, CSP `form-action` updated and CSRF/abuse protection decided | MANUAL per form | no WCAG 3.3.x failure | S1 (3.3.1, 3.3.2, 3.3.7, 3.3.8) |
| H7 | Section anchors land below the sticky header (`scroll-margin-top`) | run-checks H7 | target top at or below header bottom | S1 (2.4.11) |
| H8 | 404 page exists, is localised and keeps navigation | run-checks H8 (status 404); MANUAL: view the page | 404 status, usable page | S31 |
| H9 | Back and forward after a language switch and after the drawer open | MANUAL | no stuck state | S1 |
| H10 | Relative asset paths (see G5) | run-checks H10 | none root-absolute for assets | HOUSE |
| H11 | No JS errors and no console warnings | run-checks H11 | zero | S34 |

## I. Visual consistency

| ID | Rule | How to test | Pass | Source |
|---|---|---|---|---|
| I1 | Text measure (HOUSE, WARN): body and lead paragraphs 45-75 characters (see A6); the container, not the font size, controls it (`max-width: 65ch` or similar) | run-checks A6 | at most 80 everywhere | S11, S1 (1.4.8) |
| I2 | Balanced text in headings and cards: no one-word last line (orphan); use `text-wrap: balance` for headings and `pretty` for paragraphs, and a no-break space before the last short word | run-checks I2 (last-line word count at 320, 390, 1280, EN and RU) | WARN list reviewed; headings with zero | S40 |
| I3 | Spacing rhythm: section padding and gaps come from one scale (multiples of 4 px or 8 px); same value for the same role on every page | run-checks I3 | on grid | S8 (HOUSE grid) |
| I4 | Equal height of sibling cards in a row; same radius, border and padding | run-checks I4 | spread at most 2 px | S8 |
| I5 | Consistent icon size, stroke and alignment with text; icons from one set | MANUAL: screenshots at 390 and 1280 | consistent | S2, S8 |
| I6 | Type scale: a small fixed set of sizes, same role same size on every page | run-checks I6 (distinct sizes, INFO) | about 8-10 sizes | S11 |
| I7 | Visual regression: take screenshots of every page at nine widths, light and dark, EN and RU, before and after any CSS change and compare by eye (or a pixel diff tool) | `python run-checks.py --shots`; compare `guides/shots/` folders | no unintended difference | HOUSE |
| I9 | Revealed content ends at full opacity: after scrolling to the end of the page, with animations left to run (never forced to finish), every element with a reveal or animation class, or with a running animation, has effective opacity 1 (its own opacity times every ancestor's). A scroll-driven reveal (`animation-timeline: view()`) inside an ancestor with `overflow: hidden` or `overflow: clip` can stay part-way and leave content dim for good | run-checks I9 (390 and 1280); MANUAL: scroll to the bottom and look for dim cards | zero elements below 0.99 | S12 (motion), HOUSE (found on home v3: `.courses-sec { overflow: hidden }` left course cards at 0.46-0.89) |
| I8 | Same layout in RU and EN: translation does not change the number of lines in a way that breaks a card row, no overlap | MANUAL at 320, 390, 1280 | none | S18 |

---

## S. Sources (URL, date seen)

"fetched" means the page was read in this session on 2026-10-02; "cited" means the rule is stated from
the named standard and the URL was not re-read in this session (re-check before quoting a number).

| Key | Source | URL | Seen |
|---|---|---|---|
| S1 | W3C, WCAG 2.2 (2.5.8 target size 24x24; 1.4.3, 1.4.10, 1.4.11, 1.4.12; 2.4.11; new criteria list) | https://www.w3.org/TR/WCAG22/ | 2026-10-02 fetched |
| S2 | Apple, Human Interface Guidelines, accessibility (44x44 pt touch target) | https://developer.apple.com/design/human-interface-guidelines/accessibility | 2026-10-02 fetched |
| S3 | Google Search Central, localized versions / hreflang (reciprocal, self-reference, x-default, codes) | https://developers.google.com/search/docs/specialty/international/localized-versions | 2026-10-02 fetched |
| S4 | W3C CSS Writing Modes 4 and MDN CSS logical properties | https://www.w3.org/TR/css-writing-modes-4/ ; https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Logical_properties_and_values | 2026-10-02 fetched |
| S5 | W3C Internationalization, language declarations in HTML (lang, no http-equiv Content-Language) | https://www.w3.org/International/questions/qa-html-language-declarations | 2026-10-02 fetched |
| S7 | WCAG 2.5.8 Understanding (24x24 minimum, spacing, inline exceptions) | https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | 2026-10-02 fetched |
| S8 | Material Design 3, layout structure (window size classes compact 0-599, medium 600-839, expanded 840+; 48 dp targets) | https://m3.material.io/foundations/designing/structure | 2026-10-02 fetched |
| S9 | MDN, viewport meta | https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport | cited |
| S10 | MDN, CSS env() and safe-area-inset-*, viewport-fit=cover | https://developer.mozilla.org/en-US/docs/Web/CSS/env | 2026-10-02 fetched |
| S11 | W3C WCAG 1.4.8 (80 characters) and web.dev typography guidance on measure | https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation.html ; https://web.dev/learn/design/typography | cited |
| S12 | MDN, prefers-reduced-motion | https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion | 2026-10-02 fetched |
| S14 | W3C ARIA Authoring Practices, modal dialog pattern | https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ | cited |
| S15 | WebAIM, screen reader user survey and testing guidance | https://webaim.org/projects/screenreadersurvey10/ | cited |
| S16 | MQM Council, error typology and severities (accuracy, terminology, linguistic conventions/fluency, style, locale convention, audience appropriateness, design and markup, verity) | https://themqm.org/error-types-2/typology/ | 2026-10-02 (search result, page body not fetched) |
| S17 | W3C Internationalization, structural markup and right-to-left text (`dir`, logical properties, `dir=auto`, bidi) | https://www.w3.org/International/questions/qa-html-dir | 2026-10-02 fetched |
| S18 | W3C Internationalization, text size in translation (expansion) | https://www.w3.org/International/articles/article-text-size | cited |
| S19 | Type.Today manual on quotation marks and the dash; Pimp My Type on Russian typography | https://type.today/en/journal/quotes ; https://type.today/en/journal/dash ; https://pimpmytype.com/russian-typography/ | 2026-10-02 (search result, page bodies not fetched) |
| S20 | Lebedev Studio "Ководство" (Russian typographic rules: nbsp before dash, short words) | https://www.artlebedev.ru/kovodstvo/sections/ | cited |
| S21 | Unicode CLDR, locale number and date patterns; MDN Intl | https://cldr.unicode.org/ ; https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl | cited |
| S22 | W3C Internationalization, bidirectional text: `bdi`, isolation | https://www.w3.org/International/articles/inline-bidi-markup/ | cited |
| S23 | Open Graph protocol (og:title, og:type, og:image, og:url; og:image:alt) | https://ogp.me/ | 2026-10-02 fetched |
| S24 | web.dev, Core Web Vitals thresholds (LCP 2.5 s, INP 200 ms, CLS 0.1, 75th percentile) | https://web.dev/articles/vitals | 2026-10-02 fetched |
| S25 | web.dev, Optimize LCP | https://web.dev/articles/optimize-lcp | 2026-10-02 fetched |
| S26 | web.dev, Optimize CLS | https://web.dev/articles/optimize-cls | 2026-10-02 fetched |
| S27 | OWASP, third-party JavaScript management cheat sheet | https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html | cited |
| S28 | web.dev, font best practices | https://web.dev/articles/font-best-practices | 2026-10-02 fetched |
| S29 | Cloudflare Pages, `_headers` file | https://developers.cloudflare.com/pages/configuration/headers/ | 2026-10-02 fetched |
| S30 | Chrome for Developers, Lighthouse overview and CLI | https://developer.chrome.com/docs/lighthouse/overview | 2026-10-02 fetched |
| S31 | Google Search Central, SEO starter guide, titles, snippets, canonicalization | https://developers.google.com/search/docs/fundamentals/seo-starter-guide | cited |
| S32 | Open Graph (see S23); X/Twitter cards | https://developer.x.com/en/docs/x-for-websites/cards/overview/abouts-cards | cited |
| S33 | Google Search Central, mobile-first indexing best practices | https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing | 2026-10-02 fetched |
| S34 | MDN, Content Security Policy (strict CSP: hashes for static content, `object-src 'none'`, `base-uri`, `frame-ancestors` only by header, report-only) | https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP | 2026-10-02 fetched |
| S35 | OWASP, HTTP Security Headers cheat sheet (HSTS, nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options, COOP, CORP); MDN Observatory | https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html | 2026-10-02 fetched |
| S36 | MDN, Baseline and browser compatibility data | https://developer.mozilla.org/en-US/docs/Glossary/Baseline/Compatibility | cited |
| S37 | web.dev, Baseline; caniuse | https://web.dev/baseline ; https://caniuse.com | cited |
| S38 | Chrome DevTools, device mode and sensors | https://developer.chrome.com/docs/devtools/device-mode | cited |
| S39 | MDN, prefers-color-scheme | https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-color-scheme | cited |
| S40 | MDN / Chrome, `text-wrap: balance` and `pretty` | https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap | cited |

S6 and S13 are unused numbers. HOUSE marks a threshold or procedure that is this guide's own proposal.

Optional tools, not installed here and needing an npm download if you want them: Lighthouse CLI
(`npx lighthouse`, S30), axe-core (`npx @axe-core/cli URL`) for a second opinion on B-rules, Playwright
(`npx playwright install webkit firefox`) to run the same page in WebKit and Gecko (closes G1 without
real devices, still not a real iPhone).
