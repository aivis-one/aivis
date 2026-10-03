# AIVIS.ONE test checklist (one page, run per page)

Rule ids match `testing-guide.md`. Server for local runs: http://127.0.0.1:8731/ (serve `site/dist/` with
`python -m http.server 8731`). Everything with `run-checks` is one command:

    cd landing && python guides/run-checks.py http://127.0.0.1:8731/ http://127.0.0.1:8731/ru/

Prove the checker works first: `cd landing && python guides/run-checks.py --self-test`.
Add `--shots` for screenshots, `--skip-browser` for the static half only, `--no-external` offline.
Exit code 1 means at least one FAIL. A WARN is fixed or accepted in writing.

| ID | Check (pass criterion) | Command or tool |
|---|---|---|
| A1 | viewport meta, zoom not locked | run-checks A1 |
| A2 | no horizontal scroll at 320 360 375 390 414 768 1024 1280 1440 | run-checks A2 |
| A3 | no target under 24x24; list those under 44x44 at 360/390 | run-checks A3 |
| A4 | env(safe-area-inset-*) used when viewport-fit=cover | run-checks A4; real iPhone landscape |
| A5 | no text under 12 px; body at 16 px or more; 200% zoom clean | run-checks A5; browser zoom 200% |
| A6 | longest line at most 80 characters (target 45-75); HOUSE number, WARN not FAIL | run-checks A6 |
| A8 | landscape 812x375 clean | run-checks A8 |
| A9 | hover never the only route | run-checks A9; touch emulation |
| A10 | text-spacing override: no clip, no overflow | run-checks A10 |
| B1 | html lang and dir match locale | run-checks B1 |
| B3 | one h1, no skipped levels | run-checks B3 |
| B4 | landmarks, labelled navs, skip link | run-checks B4 |
| B5 | every img has alt | run-checks B5 |
| B6 | every control has a name, in the page language | run-checks B6, C3 |
| B7 | contrast 4.5:1 text, 3:1 large and UI, both themes | run-checks B7; DevTools colour picker |
| B8 | Tab reaches everything, visible focus, nothing hidden | run-checks B8; keyboard only |
| B9 | reduced motion honoured | run-checks B9 |
| B11 | no duplicate ids, no dangling aria-controls | run-checks B11 |
| B12 | drawer: focus in, Escape closes, focus returns | run-checks B12; keyboard only |
| B15 | NVDA+Chrome, VoiceOver iPhone, TalkBack | manual, headings and landmarks lists |
| B18 | forced-colors usable | DevTools Rendering, forced-colors: active |
| C1 | EN and RU same structure and ids | run-checks C1 |
| C3 | no untranslated strings or aria-labels in RU | run-checks C3 |
| C4 | RU/EN length ratio at most 1.3; layout holds at 320 | run-checks C4; paste 40% longer string |
| C5 | RU: « », em dash with nbsp, glued short words, decimal comma | run-checks C5, C7 |
| C6 | ellipsis, no double spaces, sentences end in a full stop | run-checks C6 |
| C8 | RTL: no physical left/right, dir=rtl simulation clean | run-checks C8; Arabic sample text |
| C9 | language switch lands on the same page | run-checks H3; manual per page |
| C10 | brand terms same in every locale | run-checks C11 |
| C.2 | native reader review, MQM form, zero critical or major | manual, guide section C.2 |
| D1 | LCP at most 2.5 s | run-checks D1; `npx lighthouse` (optional) |
| D2 | no long tasks | run-checks D2 |
| D3 | CLS at most 0.1 | run-checks D3 |
| D4 | at most 500 KB first load (soft), 1 MB (hard) | run-checks D4 |
| D5 | zero third-party hosts | run-checks D5 |
| D6 | fonts WOFF2, each under about 60 KB | run-checks D6 |
| D7 | images sized, none over 1.5x rendered x DPR | run-checks D7 |
| D8 | immutable cache on assets, Brotli | `curl -sI -H "accept-encoding: br" <deployed asset URL>` |
| E1-E2 | title 30-60, description 70-160 chars | run-checks E1, E2 |
| E3-E4 | canonical self, hreflang en ru x-default, reciprocal | run-checks E3, E4 |
| E5 | robots.txt and sitemap list every page and locale | run-checks E5 |
| E6 | og:title type url image(+alt), twitter:card | run-checks E6; paste URL in a messenger |
| E8 | indexable, status 200 | run-checks E8, H0 |
| F1-F2 | CSP strict; object-src, base-uri, form-action set | run-checks F1, F2 |
| F3 | frame-ancestors as a header | run-checks F3; `curl -sI <URL>` |
| F4-F8 | HSTS, nosniff, Referrer-Policy, Permissions-Policy, COOP | run-checks F4-F8; `curl -sI <URL>` |
| F10 | every inline block hashed in CSP, no stale hash | run-checks F10 |
| F11 | no CSP violation at runtime | run-checks F11, H11 |
| F12 | live scan grade A | securityheaders.com, MDN Observatory (deployed URL) |
| G1 | Chromium (run-checks), WebKit and Gecko by hand | Safari/iPhone, Firefox |
| G3 | newer CSS is Baseline in all engines | run-checks G3, MDN Baseline |
| G4 | readable without JavaScript | run-checks G4 |
| G5 | opens from file:// | run-checks H10; double-click index.html |
| G6/H4 | dark and light, preboot sets data-theme, toggle persists | run-checks H4 |
| H1 | every internal link and anchor resolves | run-checks H1 |
| H2 | external links answer | run-checks H2 |
| H3 | language menu opens, entries present | run-checks H3 |
| H5 | drawer opens and closes | run-checks H5 |
| H6 | forms (when added): labels, autocomplete, errors | manual |
| H7 | anchors not hidden under sticky header | run-checks H7 |
| H8 | 404 page | run-checks H8 |
| I1-I2 | measure 45-75; no one-word last line | run-checks A6, I2 |
| I9 | revealed content at opacity 1 after scrolling to the end (animations not forced) | run-checks I9 |
| I3-I4 | spacing on a 4 px grid; equal card heights | run-checks I3, I4 |
| I7 | screenshots at nine widths, light and dark, EN and RU compared | run-checks --shots |

## run-checks --self-test output

Run 2026-10-02, Chrome 154, command `python run-checks.py --self-test`; fixtures in `guides/fixtures/`.

```text
SELF-TEST: one planted defect per FAIL-class check (WARN-class rows marked)

RESULT    CHECK WANT  FIXTURE  PLANTED DEFECT                                       CONTROL (good fixture)
FIRED     H0    FAIL  missing  page does not exist (404)                            clean
FIRED     B1    FAIL  en       html lang="fr" on an English page                    clean
FIRED     E2    FAIL  en       no meta description                                  clean
FIRED     E3    FAIL  en       no canonical link                                    clean
FIRED     E4    FAIL  en       hreflang lists only en                               clean
FIRED     E6    FAIL  en       no og:image                                          clean
FIRED     E8    FAIL  en       meta robots noindex                                  clean
FIRED     A1    FAIL  en       viewport has user-scalable=no                        clean
FIRED     A4    FAIL  en       viewport-fit=cover without env(safe-area-inset-*)    clean
FIRED     B3    FAIL  en       two h1 elements                                      clean
FIRED     B3    FAIL  en       h1 to h4 level jump                                  clean
FIRED     B4    FAIL  en       no nav and no footer landmark                        clean
FIRED     B5    FAIL  en       img without alt                                      clean
FIRED     D7    FAIL  en       img without width and height                         clean
FIRED     B11   FAIL  en       duplicate id                                         clean
FIRED     B11   FAIL  en       aria-controls pointing at nothing                    clean
FIRED     H1    FAIL  en       href=#nope                                           clean
FIRED     H1    FAIL  en       link to a missing page                               clean
FIRED     F1    FAIL  en       CSP with 'unsafe-inline' in script-src               clean
FIRED     F2    FAIL  en       CSP without object-src none                          clean
FIRED     F2    FAIL  en       CSP without base-uri                                 clean
FIRED     F9    FAIL  en       inline onclick                                       clean
FIRED     F9    FAIL  en       style attribute                                      clean
FIRED     F10   FAIL  en       inline blocks not covered by a CSP hash              clean
FIRED     D5    FAIL  en       image from another host in the markup                clean
FIRED     B9    FAIL  en       infinite animation, no prefers-reduced-motion rule   clean
FIRED     A2    FAIL  en       900 px wide block                                    clean
FIRED     A8    FAIL  en       900 px wide block, landscape phone                   clean
FIRED     A3    FAIL  en       10x10 px link target                                 clean
FIRED     A5    FAIL  en       9 px text                                            clean
FIRED     A6    WARN  en       paragraph about 150 characters per line              clean
FIRED     A10   FAIL  en       fixed-height box with overflow hidden                clean
FIRED     C8    FAIL  en       block that is 1500 px wide only under dir=rtl        clean
FIRED     B7    FAIL  en       #bbb text on white                                   clean
FIRED     B8    FAIL  en       link with outline:none on focus                      clean
FIRED     B8    FAIL  en       focusable link fully covered by a fixed box          clean
FIRED     D1    FAIL  en       hero image delayed 3 s                               clean
FIRED     D3    FAIL  en       400 px banner inserted at the top after 400 ms       clean
FIRED     D4    FAIL  en       1.3 MB image                                         clean
FIRED     D5    FAIL  en       request to localhost:PORT, another origin            clean
FIRED     D6    FAIL  en       font served as .ttf                                  clean
FIRED     H1    FAIL  en       image that returns 404                               clean
FIRED     H11   FAIL  en       script that throws                                   clean
FIRED     G4    FAIL  en       main content created by script                       clean
FIRED     H4    FAIL  en       no theme preboot script                              clean
FIRED     H4    FAIL  en       toggle that does not save the choice                 clean
FIRED     H5    FAIL  en       menu button sets aria-expanded but nothing opens     clean
FIRED     B12   FAIL  en       drawer state never closes on Escape                  clean
FIRED     H3    FAIL  en       language switch that never opens                     clean
FIRED     H7    FAIL  en       sticky header without scroll-margin                  clean
FIRED     I9    FAIL  en       element with a reveal class stuck at opacity .6      clean
FIRED     B9    FAIL  en       animation still running under reduce                 clean
FIRED     F1    FAIL  nocsp    no CSP at all                                        clean
FIRED     F11   FAIL  cspv     inline script that the page's own CSP forbids        clean
FIRED     C1    FAIL  ru       RU page has fewer elements than EN                   clean
FIRED     C3    FAIL  ru       aria-label="Open menu" on the RU page                clean
FIRED     C5    FAIL  ru       straight " quotes in Russian text                    clean
FIRED     C5    FAIL  ru       hyphen with spaces as a dash                         clean
FIRED     C5    FAIL  ru       unbalanced guillemet                                 clean
FIRED     C11   FAIL  ru       SANKORD missing from the RU text                     clean
FIRED     C13   FAIL  ru       RU title and description equal to EN                 clean
FIRED     F3    FAIL  hbad     _headers without frame-ancestors                     clean
FIRED     F4    FAIL  hbad     _headers without HSTS                                clean
FIRED     F5    FAIL  hbad     nosniff replaced by a wrong value                    clean
FIRED     F6    FAIL  hbad     _headers without Referrer-Policy                     clean
FIRED     F7    FAIL  hbad     _headers without Permissions-Policy                  clean
FIRED     F8    FAIL  hbad     _headers without COOP                                clean
FIRED     E5    FAIL  sbad     no robots.txt                                        clean
FIRED     E5    FAIL  sbad     no sitemap.xml                                       clean

SELF-TEST SUMMARY: 69 expectations over 55 distinct checks; fired 69, not fired 0; controls clean 69, dirty 0
```

## run-checks output (normal run)

Run 2026-10-02 after the self-test, Chrome 154, URLs http://127.0.0.1:8731/ and /ru/, headers file
`site/dist/_headers`. Command: `python run-checks.py`. Full output follows.

```text
run-checks: http://127.0.0.1:8731/, http://127.0.0.1:8731/ru/ | headers file: site/dist/_headers (found)
PASS  H0   /                          HTTP status 200
PASS  B1   /                          html lang="en" dir="ltr" (locale en)
PASS  E1   /                          title 39 chars: AIVIS.ONE — a visionary for visionaries
PASS  E2   /                          meta description 140 chars
PASS  E3   /                          canonical ['https://aivis.one/']
PASS  E4   /                          hreflang set ['en', 'ru', 'x-default']
PASS  E4   /                          canonical is one of the hreflang targets (self-reference)
PASS  E6   /                          og:title set
PASS  E6   /                          og:type set
PASS  E6   /                          og:url set
PASS  E6   /                          og:image set
PASS  E6   /                          og:description set
PASS  E6   /                          og:image:alt set
PASS  E6   /                          twitter:card set
PASS  E8   /                          robots meta: none (indexable)
PASS  E11  /                          favicon link
PASS  A1   /                          viewport: width=device-width, initial-scale=1, viewport-fit=cover
PASS  B3   /                          h1 count 1
PASS  B3   /                          heading levels never skip down 
PASS  B4   /                          landmarks present (missing: none)
PASS  B4   /                          2 nav landmarks all labelled
PASS  B4   /                          skip link to main content present
PASS  B5   /                          3 img, missing alt: none
PASS  D7   /                          img width+height set (CLS) missing: none
PASS  B6   /                          icon-only buttons carry aria-label (static: buttons without aria-label: 0; text buttons are fine, see browser check)
PASS  B11  /                          39 ids, duplicates: none
PASS  B11  /                          aria-controls targets exist 
PASS  H1   /                          in-page anchors resolve (5) broken: none
PASS  B17  /                          language links carry hreflang+lang (3.1.2): 4
PASS  F1   /                          CSP present via meta
PASS  F1   /                          no unsafe-inline/unsafe-eval/wildcards in script/style sources 
PASS  F2   /                          object-src none (directly or via default-src 'none')
PASS  F2   /                          base-uri set
PASS  F2   /                          form-action set
PASS  F9   /                          CSP lists no external hosts 
PASS  F10  /                          inline blocks 3, hashes in CSP 3, unhashed none, stale hashes none
PASS  F9   /                          inline event handlers: none
PASS  F9   /                          style= attributes (CSP style-src): 0
PASS  D5   /                          third-party resource references in markup: none
PASS  H10  /                          asset paths relative (page must open from file:// double-click): root-absolute none
PASS  A4   /                          viewport-fit=cover True, env(safe-area-inset-*) used in CSS: True
WARN  C8   /                          physical left/right CSS declarations: 1 (logical-property uses: 16). Each one is a rule to re-check under dir=rtl
PASS  B9   /                          CSS has motion: True; honours prefers-reduced-motion: True
PASS  H4   /                          prefers-color-scheme honoured (CSS or preboot)
INFO  A9   /                          :hover rules 21, wrapped in @media (hover: hover): 2 (hover must never be the only way to reach content, 1.4.13)
INFO  G3   /                          newer CSS features used (check Baseline / caniuse for the engines in G1): ['text-wrap', 'color-mix()']
PASS  C6   /                          spaced hyphen or -- in EN text (use em/en dash): none
WARN  C6   /                          text blocks over 50 chars that end without terminal punctuation (copy defect or truncated string): 6 e.g. ['hands-on work with language\xa0models', 'signature, deletion or\xa0publication', 'rvers or in your own cloud\xa0account', 'oes not end your right to a\xa0refund']
PASS  C6   /                          three dots instead of the ellipsis character: none
PASS  C6   /                          double spaces: none
PASS  C6   /                          space before punctuation: none
FAIL  H1   /                          11 internal file links resolve; broken: ['about/index.html -> 404', 'courses/index.html -> 404', 'faq/index.html -> 404', 'about/privacy/index.html -> 404', 'about/terms/index.html -> 404', 'about/imprint/index.html -> 404', 'about/licence/index.html -> 404']
INFO  H1   /                          root-absolute app routes not fetched (judge by hand on the deployed host): ['/login']
WARN  H2   /                          external links answer a HEAD request (st 0 = no response from here: not deployed yet, DNS, TLS or firewall): ['sankord.com -> 0']
PASS  H2   /                          target=_blank without rel=noopener: none (modern browsers imply it; keep explicit)
PASS  H0   /ru/                       HTTP status 200
PASS  B1   /ru/                       html lang="ru" dir="ltr" (locale ru)
PASS  E1   /ru/                       title 35 chars: AIVIS.ONE — визионер для визионеров
PASS  E2   /ru/                       meta description 142 chars
PASS  E3   /ru/                       canonical ['https://aivis.one/ru/']
PASS  E4   /ru/                       hreflang set ['en', 'ru', 'x-default']
PASS  E4   /ru/                       canonical is one of the hreflang targets (self-reference)
PASS  E6   /ru/                       og:title set
PASS  E6   /ru/                       og:type set
PASS  E6   /ru/                       og:url set
PASS  E6   /ru/                       og:image set
PASS  E6   /ru/                       og:description set
PASS  E6   /ru/                       og:image:alt set
PASS  E6   /ru/                       twitter:card set
PASS  E8   /ru/                       robots meta: none (indexable)
PASS  E11  /ru/                       favicon link
PASS  A1   /ru/                       viewport: width=device-width, initial-scale=1, viewport-fit=cover
PASS  B3   /ru/                       h1 count 1
PASS  B3   /ru/                       heading levels never skip down 
PASS  B4   /ru/                       landmarks present (missing: none)
PASS  B4   /ru/                       2 nav landmarks all labelled
PASS  B4   /ru/                       skip link to main content present
PASS  B5   /ru/                       3 img, missing alt: none
PASS  D7   /ru/                       img width+height set (CLS) missing: none
PASS  B6   /ru/                       icon-only buttons carry aria-label (static: buttons without aria-label: 0; text buttons are fine, see browser check)
PASS  B11  /ru/                       39 ids, duplicates: none
PASS  B11  /ru/                       aria-controls targets exist 
PASS  H1   /ru/                       in-page anchors resolve (5) broken: none
PASS  B17  /ru/                       language links carry hreflang+lang (3.1.2): 4
PASS  F1   /ru/                       CSP present via meta
PASS  F1   /ru/                       no unsafe-inline/unsafe-eval/wildcards in script/style sources 
PASS  F2   /ru/                       object-src none (directly or via default-src 'none')
PASS  F2   /ru/                       base-uri set
PASS  F2   /ru/                       form-action set
PASS  F9   /ru/                       CSP lists no external hosts 
PASS  F10  /ru/                       inline blocks 3, hashes in CSP 3, unhashed none, stale hashes none
PASS  F9   /ru/                       inline event handlers: none
PASS  F9   /ru/                       style= attributes (CSP style-src): 0
PASS  D5   /ru/                       third-party resource references in markup: none
PASS  H10  /ru/                       asset paths relative (page must open from file:// double-click): root-absolute none
PASS  A4   /ru/                       viewport-fit=cover True, env(safe-area-inset-*) used in CSS: True
WARN  C8   /ru/                       physical left/right CSS declarations: 1 (logical-property uses: 16). Each one is a rule to re-check under dir=rtl
PASS  B9   /ru/                       CSS has motion: True; honours prefers-reduced-motion: True
PASS  H4   /ru/                       prefers-color-scheme honoured (CSS or preboot)
INFO  A9   /ru/                       :hover rules 21, wrapped in @media (hover: hover): 2 (hover must never be the only way to reach content, 1.4.13)
INFO  G3   /ru/                       newer CSS features used (check Baseline / caniuse for the engines in G1): ['text-wrap', 'color-mix()']
PASS  C5   /ru/                       straight " in RU text (use «ёлочки»): none
PASS  C5   /ru/                       English curly quotes in RU text (nested level only: „лапки“): none
PASS  C5   /ru/                       « » balanced (6/6)
PASS  C5   /ru/                       hyphen used as dash (need em dash): none
PASS  C5   /ru/                       spaced en dash in RU (house style: em dash with nbsp before): none
WARN  C5   /ru/                       em dash not preceded by nbsp (line may start with the dash): 5 nodes e.g. ['Никто не\xa0может вас отключить\xa0— даже\xa0мы.', 'Предзаказ открыт, поставка с\xa0января 2027']
WARN  C5   /ru/                       short word followed by a normal space (orphan risk; use nbsp): 42 nodes e.g. ['Перейти к содержимому', 'Визионер для\xa0визионеров']
PASS  C7   /ru/                       decimal point in RU text (RU uses comma): none
PASS  C7   /ru/                       comma thousands separator in RU (use nbsp): none
WARN  C6   /ru/                       text blocks over 50 chars that end without terminal punctuation (copy defect or truncated string): 6 e.g. ['ческой работы с\xa0языковыми моделями', 'вырос способ вести бизнес вместе с', 'одписи, ни\xa0удаления, ни\xa0публикации', 'ерах или\xa0в\xa0вашем облачном аккаунте']
PASS  C6   /ru/                       three dots instead of the ellipsis character: none
PASS  C6   /ru/                       double spaces: none
PASS  C6   /ru/                       space before punctuation: none
FAIL  H1   /ru/                       11 internal file links resolve; broken: ['about/index.html -> 404', 'courses/index.html -> 404', 'faq/index.html -> 404', 'about/privacy/index.html -> 404', 'about/terms/index.html -> 404', 'about/imprint/index.html -> 404', 'about/licence/index.html -> 404']
INFO  H1   /ru/                       root-absolute app routes not fetched (judge by hand on the deployed host): ['/login']
WARN  H2   /ru/                       external links answer a HEAD request (st 0 = no response from here: not deployed yet, DNS, TLS or firewall): ['sankord.com -> 0']
PASS  H2   /ru/                       target=_blank without rel=noopener: none (modern browsers imply it; keep explicit)
PASS  C1   /ru/                       structure parity EN vs RU (counts of h1-3,a,img,button,section,li,p,nav): EN {'a': 39, 'img': 3, 'nav': 2, 'li': 25, 'button': 4, 'p': 28, 'section': 4, 'h1': 1, 'h2': 3, 'h3': 5} RU {'a': 39, 'img': 3, 'nav': 2, 'li': 25, 'button': 4, 'p': 28, 'section': 4, 'h1': 1, 'h2': 3, 'h3': 5}
PASS  C1   /ru/                       same element ids in both locales (39 vs 39) diff none
PASS  C1   /ru/                       link count parity 39 vs 39
PASS  C3   /ru/                       RU text nodes with Latin words and no Cyrillic (untranslated?): none
PASS  C3   /ru/                       RU accessible names/attributes still English (screen-reader users hear them): none
PASS  C13  /ru/                       title and meta description differ from EN (translated)
INFO  C4   /ru/                       text node count differs (92 vs 97); pairwise expansion check skipped, total ratio 1.00
PASS  C11  /ru/                       brand terms ['AIVIS', 'SANKORD', 'EXSPECS'] appear in both locales (mismatch: none)
PASS  E5   /                          robots.txt status 200, has Sitemap line: True
PASS  E5   /                          sitemap.xml status 200
INFO  E5   /                          sitemap lists 2 page URLs (https://aivis.one/, https://aivis.one/ru/ ...)
PASS  E5   /                          sitemap contains https://aivis.one/
PASS  E5   /                          sitemap contains https://aivis.one/ru/
PASS  H8   /                          unknown path returns 404 (got 404); deployed host must also serve a 404 page
PASS  F4   /                          strict-transport-security: max-age=31536000; includeSubDomains [_headers file]
PASS  F5   /                          x-content-type-options: nosniff [_headers file]
PASS  F6   /                          referrer-policy: strict-origin-when-cross-origin [_headers file]
PASS  F7   /                          permissions-policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=() [_headers file]
PASS  F8   /                          cross-origin-opener-policy: same-origin [_headers file]
PASS  F3   /                          clickjacking protection (frame-ancestors in a HEADER; ignored in a meta CSP): found
INFO  D8   /                          Cache-Control on the page: None (live) -- also check /assets/* in the _headers file: {'cache-control': 'public, max-age=31536000, immutable'}
INFO  D8   /                          content-encoding live: None (Cloudflare compresses at the edge; verify on the deployed host with curl -H 'accept-encoding: br')
INFO  G1   -                          engine under test: Chrome/154.0.8037.93 (Chromium only; Gecko and WebKit are manual, see guide G1)
PASS  A2   /                          320px no horizontal scroll (scrollWidth 320 vs 320) 
PASS  A3   /                          320px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A5   /                          320px no text under 12px: ok
PASS  A6   /                          320px longest line 36 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [33, 36, 36, 36]
WARN  I2   /                          320px last line of a heading/paragraph is one word: ['h1.ls-mo-balance: "forvisionaries"', 'li: "business"', 'li: "February2026"', 'h2.ls-mo-balance: "buildingSANKORD"']
PASS  A2   /                          360px no horizontal scroll (scrollWidth 360 vs 360) 
PASS  A3   /                          360px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A3   /                          360px targets under 44x44 (Apple HIG; Material uses 48): 0 of 22 e.g. []
PASS  A2   /                          375px no horizontal scroll (scrollWidth 375 vs 375) 
PASS  A3   /                          375px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /                          390px no horizontal scroll (scrollWidth 390 vs 390) 
PASS  A3   /                          390px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A3   /                          390px targets under 44x44 (Apple HIG; Material uses 48): 0 of 22 e.g. []
PASS  A5   /                          390px no text under 12px: ok
PASS  A6   /                          390px longest line 45 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [41, 42, 43, 45]
WARN  I2   /                          390px last line of a heading/paragraph is one word: ['li: "languagemodels"', 'li: "February2026"', 'h2.ls-mo-balance: "buildingSANKORD"', 'p: "onsankord.com."']
PASS  A5   /                          390px: 34 of 50 text elements at 16px or larger; sizes in use [12.0, 14.0, 16.0, 17.0, 18.0, 24.0, 28.0, 44.8]
INFO  I6   /                          distinct font sizes: 8 (a type scale should stay near 8-10)
PASS  D7   /                          all 3 visible images loaded: ok
PASS  D7   /                          images no larger than 1.5x of rendered*DPR (wasted bytes): none
PASS  A2   /                          414px no horizontal scroll (scrollWidth 414 vs 414) 
PASS  A3   /                          414px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /                          768px no horizontal scroll (scrollWidth 768 vs 768) 
PASS  A3   /                          768px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /                          1024px no horizontal scroll (scrollWidth 1024 vs 1024) 
PASS  A3   /                          1024px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /                          1280px no horizontal scroll (scrollWidth 1280 vs 1280) 
PASS  A3   /                          1280px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A5   /                          1280px no text under 12px: ok
PASS  A6   /                          1280px longest line 75 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [72, 73, 73, 75]
WARN  I2   /                          1280px last line of a heading/paragraph is one word: ['li: "cloudaccount"']
PASS  A2   /                          1440px no horizontal scroll (scrollWidth 1440 vs 1440) 
PASS  A3   /                          1440px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A8   /                          landscape 812x375 no horizontal scroll (812 vs 812)
PASS  D1   /                          mobile 390 LCP 36 ms (lab, no throttling; target <= 2500)
PASS  D3   /                          mobile 390 CLS 0.000 (target <= 0.1)
PASS  D2   /                          mobile 390 total blocking-time proxy 0 ms from long tasks (INP needs a real interaction; keep main-thread work near zero)
PASS  D4   /                          mobile 390 transferred 214 KB in 11 requests (house proposal: <= 500 KB soft, 1 MB hard; owner's number)
PASS  D5   /                          mobile 390 third-party hosts contacted: none
PASS  H1   /                          mobile 390 sub-resource errors: none
PASS  F11  /                          mobile 390 CSP violations at runtime: none
PASS  H11  /                          mobile 390 uncaught JS errors: none
PASS  H11  /                          mobile 390 console errors/warnings: none
PASS  D6   /                          fonts loaded: ['manrope-400-latin.woff2', 'jbm-700-latin.woff2', 'pjs-800-latin.woff2', 'pjs-700-latin.woff2', 'manrope-700-latin.woff2', 'manrope-600-latin.woff2', 'manrope-600-cyrillic.woff2'] (WOFF2 only)
INFO  D6   /                          font sizes KB (subset check: Latin+Cyrillic under ~60 KB each): [('manrope-400-latin.woff2', 13), ('jbm-700-latin.woff2', 21), ('pjs-800-latin.woff2', 11), ('pjs-700-latin.woff2', 12), ('manrope-700-latin.woff2', 14), ('manrope-600-latin.woff2', 14), ('manrope-600-cyrillic.woff2', 7)]
PASS  D1   /                          desktop 1280 LCP 28 ms (lab, no throttling; target <= 2500)
PASS  D3   /                          desktop 1280 CLS 0.002 (target <= 0.1)
PASS  D2   /                          desktop 1280 total blocking-time proxy 0 ms from long tasks (INP needs a real interaction; keep main-thread work near zero)
PASS  D4   /                          desktop 1280 transferred 209 KB in 11 requests (house proposal: <= 500 KB soft, 1 MB hard; owner's number)
PASS  D5   /                          desktop 1280 third-party hosts contacted: none
PASS  H1   /                          desktop 1280 sub-resource errors: none
PASS  F11  /                          desktop 1280 CSP violations at runtime: none
PASS  H11  /                          desktop 1280 uncaught JS errors: none
PASS  H11  /                          desktop 1280 console errors/warnings: none
PASS  I9   /                          390px after scrolling to the end, animations NOT forced: 14 reveal/animated elements checked, effective opacity below 1 on 0: none
PASS  I9   /                          1280px after scrolling to the end, animations NOT forced: 14 reveal/animated elements checked, effective opacity below 1 on 0: none
PASS  H4   /                          light: data-theme set before paint from system preference -> light
PASS  B7   /                          light theme contrast (flat backgrounds): 66 text elements checked, 0 not measurable (gradient/image), failing: none
PASS  H4   /                          dark: data-theme set before paint from system preference -> dark
PASS  B7   /                          dark theme contrast (flat backgrounds): 66 text elements checked, 0 not measurable (gradient/image), failing: none
PASS  B9   /                          reduce-motion: long or infinite animations still running: none
PASS  G4   /                          JavaScript disabled: main text still readable (2392 chars)
PASS  A10  /                          390px text spacing 1.4.12 (lh 1.5, ls .12em, ws .16em): overflow none, clipped none
PASS  C8   /                          390px dir=rtl simulation: overflow none (scrollWidth 390 vs 390)
PASS  A10  /                          1280px text spacing 1.4.12 (lh 1.5, ls .12em, ws .16em): overflow none, clipped none
PASS  C8   /                          1280px dir=rtl simulation: overflow none (scrollWidth 1280 vs 1280)
PASS  B8   /                          keyboard: Tab reached 26 distinct controls (focus left the document (end of tab order)); first ['a:Skip to content', 'a:AIVIS.ONE', 'a:AIVIS.ONE'], last ['a:Questions', 'a:Log in', 'a:Telegram']
PASS  B8   /                          focus indicator present (outline or box-shadow) on every stop; missing: none
PASS  B8   /                          focused control never ENTIRELY covered by another element (2.4.11 AA): none
PASS  B8   /                          focused control partly covered (sticky header / overlay; 2.4.12 AAA, tune scroll-padding-top): none
PASS  H7   /                          section anchors not hidden under sticky header (scroll-margin-top): ['#ls-main top 65 header 65 sticky', '#aivis top 65 header 65 sticky', '#sankord top 817 header 65 sticky']
PASS  H5   /                          drawer opens on tap: aria-expanded=true visible=True links=7
PASS  B12  /                          focus moves into the dialog on open: True
PASS  B12  /                          Escape closes the drawer: aria-expanded=false visible=False
PASS  B12  /                          focus returns to the menu button after close: True
PASS  H4   /                          theme toggle flips dark->light, saved to storage=light, aria-pressed=false
PASS  H4   /                          theme persists across reload: light
PASS  H3   /                          language menu opens on tap, entries ['en 162x44 current', 'ru 162x44']
PASS  I3   /                          section padding on a 4px grid: off-grid none; values in use {'64': 8}
PASS  I4   /                          sibling cards in one row have equal height: ok
PASS  A2   /ru/                       320px no horizontal scroll (scrollWidth 320 vs 320) 
PASS  A3   /ru/                       320px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A5   /ru/                       320px no text under 12px: ok
PASS  A6   /ru/                       320px longest line 32 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [29, 30, 32, 32]
WARN  I2   /ru/                       320px last line of a heading/paragraph is one word: ['h1.ls-mo-balance: "длявизионеров"', 'li: "бизнесе"', 'li: "моделями"', 'li: "2026года"']
PASS  A2   /ru/                       360px no horizontal scroll (scrollWidth 360 vs 360) 
PASS  A3   /ru/                       360px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A3   /ru/                       360px targets under 44x44 (Apple HIG; Material uses 48): 0 of 22 e.g. []
PASS  A2   /ru/                       375px no horizontal scroll (scrollWidth 375 vs 375) 
PASS  A3   /ru/                       375px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /ru/                       390px no horizontal scroll (scrollWidth 390 vs 390) 
PASS  A3   /ru/                       390px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A3   /ru/                       390px targets under 44x44 (Apple HIG; Material uses 48): 0 of 22 e.g. []
PASS  A5   /ru/                       390px no text under 12px: ok
PASS  A6   /ru/                       390px longest line 40 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [35, 37, 38, 40]
WARN  I2   /ru/                       390px last line of a heading/paragraph is one word: ['h2.ls-mo-balance: "создаюSANKORD"', 'p.statement__cat: "Ввашейвласти."', 'li: "нипубликации"', 'h2.ls-mo-balance: "иприменяйтесразу"']
PASS  A5   /ru/                       390px: 36 of 52 text elements at 16px or larger; sizes in use [12.0, 14.0, 16.0, 17.0, 18.0, 24.0, 28.0, 44.8]
INFO  I6   /ru/                       distinct font sizes: 8 (a type scale should stay near 8-10)
PASS  D7   /ru/                       all 3 visible images loaded: ok
PASS  D7   /ru/                       images no larger than 1.5x of rendered*DPR (wasted bytes): none
PASS  A2   /ru/                       414px no horizontal scroll (scrollWidth 414 vs 414) 
PASS  A3   /ru/                       414px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /ru/                       768px no horizontal scroll (scrollWidth 768 vs 768) 
PASS  A3   /ru/                       768px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /ru/                       1024px no horizontal scroll (scrollWidth 1024 vs 1024) 
PASS  A3   /ru/                       1024px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A2   /ru/                       1280px no horizontal scroll (scrollWidth 1280 vs 1280) 
PASS  A3   /ru/                       1280px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A5   /ru/                       1280px no text under 12px: ok
PASS  A6   /ru/                       1280px longest line 67 chars over 5 paragraphs (HOUSE number: 80 is WCAG 1.4.8 AAA, target 45-75, owner decides); longest-per-paragraph [57, 61, 63, 67]
WARN  I2   /ru/                       1280px last line of a heading/paragraph is one word: ['h2.ls-mo-balance: "иприменяйтесразу"']
PASS  A2   /ru/                       1440px no horizontal scroll (scrollWidth 1440 vs 1440) 
PASS  A3   /ru/                       1440px targets under 24x24 CSS px (WCAG 2.5.8 AA): none
PASS  A8   /ru/                       landscape 812x375 no horizontal scroll (812 vs 812)
PASS  D1   /ru/                       mobile 390 LCP 36 ms (lab, no throttling; target <= 2500)
PASS  D3   /ru/                       mobile 390 CLS 0.000 (target <= 0.1)
PASS  D2   /ru/                       mobile 390 total blocking-time proxy 0 ms from long tasks (INP needs a real interaction; keep main-thread work near zero)
PASS  D4   /ru/                       mobile 390 transferred 254 KB in 16 requests (house proposal: <= 500 KB soft, 1 MB hard; owner's number)
PASS  D5   /ru/                       mobile 390 third-party hosts contacted: none
PASS  H1   /ru/                       mobile 390 sub-resource errors: none
PASS  F11  /ru/                       mobile 390 CSP violations at runtime: none
PASS  H11  /ru/                       mobile 390 uncaught JS errors: none
PASS  H11  /ru/                       mobile 390 console errors/warnings: none
PASS  D6   /ru/                       fonts loaded: ['jbm-700-latin.woff2', 'manrope-400-latin.woff2', 'pjs-800-latin.woff2', 'manrope-700-latin.woff2', 'pjs-700-latin.woff2', 'pjs-700-cyrillic.woff2', 'manrope-400-cyrillic.woff2', 'jbm-700-cyrillic.woff2', 'pjs-800-cyrillic.woff2', 'manrope-700-cyrillic.woff2', 'manrope-600-cyrillic.woff2', 'manrope-600-latin.woff2'] (WOFF2 only)
INFO  D6   /ru/                       font sizes KB (subset check: Latin+Cyrillic under ~60 KB each): [('jbm-700-latin.woff2', 21), ('manrope-400-latin.woff2', 13), ('pjs-800-latin.woff2', 11), ('manrope-700-latin.woff2', 14), ('pjs-700-latin.woff2', 12), ('pjs-700-cyrillic.woff2', 7), ('manrope-400-cyrillic.woff2', 7), ('jbm-700-cyrillic.woff2', 5), ('pjs-800-cyrillic.woff2', 7), ('manrope-700-cyrillic.woff2', 7), ('manrope-600-cyrillic.woff2', 7), ('manrope-600-latin.woff2', 14)]
PASS  D1   /ru/                       desktop 1280 LCP 32 ms (lab, no throttling; target <= 2500)
PASS  D3   /ru/                       desktop 1280 CLS 0.000 (target <= 0.1)
PASS  D2   /ru/                       desktop 1280 total blocking-time proxy 0 ms from long tasks (INP needs a real interaction; keep main-thread work near zero)
PASS  D4   /ru/                       desktop 1280 transferred 249 KB in 16 requests (house proposal: <= 500 KB soft, 1 MB hard; owner's number)
PASS  D5   /ru/                       desktop 1280 third-party hosts contacted: none
PASS  H1   /ru/                       desktop 1280 sub-resource errors: none
PASS  F11  /ru/                       desktop 1280 CSP violations at runtime: none
PASS  H11  /ru/                       desktop 1280 uncaught JS errors: none
PASS  H11  /ru/                       desktop 1280 console errors/warnings: none
PASS  I9   /ru/                       390px after scrolling to the end, animations NOT forced: 14 reveal/animated elements checked, effective opacity below 1 on 0: none
PASS  I9   /ru/                       1280px after scrolling to the end, animations NOT forced: 14 reveal/animated elements checked, effective opacity below 1 on 0: none
PASS  H4   /ru/                       light: data-theme set before paint from system preference -> light
PASS  B7   /ru/                       light theme contrast (flat backgrounds): 69 text elements checked, 0 not measurable (gradient/image), failing: none
PASS  H4   /ru/                       dark: data-theme set before paint from system preference -> dark
PASS  B7   /ru/                       dark theme contrast (flat backgrounds): 69 text elements checked, 0 not measurable (gradient/image), failing: none
PASS  B9   /ru/                       reduce-motion: long or infinite animations still running: none
PASS  G4   /ru/                       JavaScript disabled: main text still readable (2401 chars)
PASS  A10  /ru/                       390px text spacing 1.4.12 (lh 1.5, ls .12em, ws .16em): overflow none, clipped none
PASS  C8   /ru/                       390px dir=rtl simulation: overflow none (scrollWidth 390 vs 390)
PASS  A10  /ru/                       1280px text spacing 1.4.12 (lh 1.5, ls .12em, ws .16em): overflow none, clipped none
PASS  C8   /ru/                       1280px dir=rtl simulation: overflow none (scrollWidth 1280 vs 1280)
PASS  B8   /ru/                       keyboard: Tab reached 26 distinct controls (focus cycled back to 1|#ls-main); first ['a:Перейти к содержимому', 'a:AIVIS.ONE', 'a:AIVIS.ONE'], last ['a:Вопросы', 'a:Войти', 'a:Телеграм']
PASS  B8   /ru/                       focus indicator present (outline or box-shadow) on every stop; missing: none
PASS  B8   /ru/                       focused control never ENTIRELY covered by another element (2.4.11 AA): none
PASS  B8   /ru/                       focused control partly covered (sticky header / overlay; 2.4.12 AAA, tune scroll-padding-top): none
PASS  H7   /ru/                       section anchors not hidden under sticky header (scroll-margin-top): ['#ls-main top 65 header 65 sticky', '#aivis top 65 header 65 sticky', '#sankord top 817 header 65 sticky']
PASS  H5   /ru/                       drawer opens on tap: aria-expanded=true visible=True links=7
PASS  B12  /ru/                       focus moves into the dialog on open: True
PASS  B12  /ru/                       Escape closes the drawer: aria-expanded=false visible=False
PASS  B12  /ru/                       focus returns to the menu button after close: True
PASS  H4   /ru/                       theme toggle flips dark->light, saved to storage=light, aria-pressed=false
PASS  H4   /ru/                       theme persists across reload: light
PASS  H3   /ru/                       language menu opens on tap, entries ['en 162x44', 'ru 162x44 current']
PASS  I3   /ru/                       section padding on a 4px grid: off-grid none; values in use {'64': 8}
PASS  I4   /ru/                       sibling cards in one row have equal height: ok

SUMMARY: PASS 270, FAIL 2, WARN 14, INFO 15
FAIL H1   /                          11 internal file links resolve; broken: ['about/index.html -> 404', 'courses/index.html -> 404', 'faq/index.html -> 404', 'about/privacy/index.html -> 404', 'about/terms/index.html -> 404', 'about/imprint/index.html -> 404', 'about/licence/index.html -> 404']
FAIL H1   /ru/                       11 internal file links resolve; broken: ['about/index.html -> 404', 'courses/index.html -> 404', 'faq/index.html -> 404', 'about/privacy/index.html -> 404', 'about/terms/index.html -> 404', 'about/imprint/index.html -> 404', 'about/licence/index.html -> 404']
```
