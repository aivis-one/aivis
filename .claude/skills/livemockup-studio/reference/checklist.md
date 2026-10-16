---
name: checklist
description: "v1.8.0 | Quality gates with Navigation Map + Brand compliance + Theme & Language + i18n & Color validation"
---

# Checklist

Quality gates for validating live mockups before delivery.

---

## Criticality Levels

| Level | Symbol | Rule |
|-------|--------|------|
| BLOCKER | 🔴 | 0 allowed — must fix before delivery |
| MAJOR | 🟡 | ≤2 allowed — should fix |
| MINOR | 🟢 | No limit — nice to fix |

---

## Integrity Checks ⚠️ GATE

| ID | Check | Level | Command | Expected |
|----|-------|-------|---------|----------|
| INT1 | File ends `</html>` | 🔴 | `tail -1` | `</html>` |
| INT2 | No cdn-cgi | 🔴 | `grep -c "cdn-cgi"` | `0` |
| INT3 | No __cf_email__ | 🔴 | `grep -c "__cf_email__"` | `0` |
| INT4 | Script balanced | 🔴 | Compare counts | Equal |
| INT5 | Body closed | 🔴 | `grep -c "</body>"` | `1` |
| INT6 | HTML closed | 🔴 | `grep -c "</html>"` | `1` |

**FAIL = STOP → sanitize protocol**

---

## Form Checks

| ID | Check | Level |
|----|-------|-------|
| F1 | Form buttons work | 🔴 |
| F2 | No form+onsubmit | 🟡 |

---

## Shell Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| S1 | Toolbar visible at top | 🔴 | Visual — toolbar spans full width |
| S2 | Toolbar not overlapping content | 🔴 | Visual — content starts below toolbar |
| S3 | Phone (390px) switch works | 🔴 | Press `1` or click Phone button |
| S4 | Tablet (820px) switch works | 🔴 | Press `2` or click Tablet button |
| S5 | Desktop (1280px) switch works | 🔴 | Press `3` or click Desktop button |
| S6 | Scroll resets on device switch | 🔴 | Switch devices — content at top |
| S7 | Header visible on all devices (no top clipping) | 🔴 | Switch Phone/Tablet/Desktop at 50% zoom — header must be visible |

---

## Navigation Map Checks ⭐

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| N1 | Map button visible in toolbar | 🔴 | Look for Map button (Lucide map-pin icon) |
| N2 | Map popup opens on click | 🔴 | Click Map button — popup appears |
| N3 | Map popup closes on × or overlay click | 🔴 | Click × or outside popup |
| N4 | Stats show correct counts | 🟡 | Verify screens / paths / endpoints |
| N5 | 🟢 Screen items navigate correctly | 🔴 | Click green item → navigates to screen |
| N6 | 🔴 Endpoint items show toast | 🔴 | Click red item → navigates + shows endpoint toast |
| N7 | All screens present in map | 🟡 | Cross-check with actual screens |
| N8 | All endpoints documented | 🟡 | Verify no hidden dead-ends |
| N9 | Traffic light colors correct | 🟡 | 🟢=screen, 🟡=tab, 🔴=endpoint |
| N10 | Sections have counters `(N)` | 🟡 | Each section title shows item count |
| N11 | Sections collapse/expand on click | 🟡 | Click section header — toggles content |
| N12 | Default state = all collapsed | 🟢 | Open map — all sections collapsed |
| N13 | 🟡 Tab items show yellow toast | 🔴 | Click yellow item → shows tab toast |

---

## Endpoint Checks ⭐

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| E1 | All dead-ends show endpoint toast | 🔴 | Click every non-navigating element |
| E2 | Endpoint toast format correct | 🟡 | Must be `📌 {Name} — endpoint` |
| E3 | Tabs show yellow toast | 🔴 | Click tabs → `🟡 Tab "{Name}" — switches content` |
| E4 | List items without detail show endpoint | 🔴 | Click items without detail screens |
| E5 | No confusing toasts | 🟡 | No toasts that suggest something works when it doesn't |

---

## Mobile Toolbar Checks ⭐

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| M1 | Toolbar adapts at <480px | 🟡 | Resize browser window |
| M2 | Device sizes hidden on mobile | 🟡 | Check .device-size display |
| M3 | Zoom value hidden on mobile | 🟡 | Check .zoom-value display |
| M4 | Map label hidden on mobile | 🟡 | Check .map-label display |
| M5 | All controls still functional | 🔴 | Test all buttons at mobile size |

---

## Layout Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| L1 | Content inside device frame | 🔴 | Visual — no overflow outside frame |
| L2 | No horizontal scroll inside frame | 🔴 | Try scrolling horizontally |
| L3 | Header sticky at top when scrolling | 🟡 | Scroll down — header stays |
| L4 | Tab bar sticky at bottom | 🟡 | Scroll up — tab bar stays |
| L5 | Popups open inside frame | 🟡 | Click popup trigger — stays in frame |
| L6 | Tab bar at bottom (not floating up) | 🔴 | Visual — tab bar touches bottom edge |
| L7 | Main content fills space between header/tab-bar | 🔴 | Visual — no empty gap |

---

## Clickability Checks ⚠️ CRITICAL

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| C1 | All cards with onclick respond | 🔴 | Click center of each card |
| C2 | Clicks work on card children | 🔴 | Click text/icons inside cards |
| C3 | Nested buttons still work | 🔴 | Click buttons inside clickable cards |
| C4 | Table rows with onclick work | 🔴 | Click any cell in clickable rows |
| C5 | Progress bars don't block clicks | 🔴 | Click on metric rows with bars |
| C6 | Labels/values don't block clicks | 🔴 | Click directly on text in clickable rows |

---

## Responsive Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| R1 | Phone layout readable | 🔴 | Switch to phone, check layout |
| R2 | Tablet layout uses space | 🔴 | Switch to tablet, check layout |
| R3 | Desktop layout fills width | 🔴 | Switch to desktop, check layout |
| R4 | Touch targets ≥44×44px | 🟡 | Measure buttons/links |
| R5 | Body text ≥14px | 🟡 | Check font-size |

---

## Interaction Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| I1 | All buttons respond to click | 🔴 | Click each button |
| I2 | Screen navigation works | 🔴 | Navigate between screens |
| I3 | Toast notifications appear | 🟡 | Trigger action — toast shows |
| I4 | Hover effects visible | 🟢 | Hover over cards/buttons |
| I5 | Transitions smooth (no jank) | 🟢 | Observe animations |

---

## Visual Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| V1 | No "Lorem ipsum" text | 🟡 | Read all visible text |
| V2 | No placeholder images | 🟡 | Check all images load |
| V3 | CSS variables used for colors | 🟡 | Check source — no hardcoded colors |
| V4 | Consistent spacing | 🟢 | Visual — gaps look even |
| V5 | Icons consistent style | 🟢 | Visual — same icon family |

---

## Theme & Language Checks ⭐

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| T1 | Theme toggle button visible in toolbar | 🔴 | Look for monitor/sun/moon icon button |
| T2 | Theme cycle works: auto → light → dark | 🔴 | Click 3 times, observe icon change |
| T3 | Dark mode changes mockup colors | 🟡 | Set dark → check background, text colors |
| T4 | No light flash on dark-mode page load | 🔴 | Set dark, reload page |
| T5 | Theme persists on reload | 🟡 | Set theme, reload, check state |
| T6 | Keyboard T toggles theme | 🟡 | Press T, observe change |
| I1 | Language buttons visible (RU/EN) | 🔴 | Look for RU|EN in toolbar |
| I2 | Language switch changes text | 🔴 | Click EN → check headings, labels |
| I3 | No i18n keys showing as text | 🟡 | Read all text — no "auth.login.title" etc. |
| I4 | Language persists on reload | 🟡 | Switch to EN, reload, verify |
| I5 | Keyboard L toggles language | 🟡 | Press L, observe change |

---

## Brand Compliance (CBS HOME) ⭐

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| B1 | Primary color = teal (#1A6B6A) | 🔴 | Check --primary in :root |
| B2 | Accent color = orange (#E8651A) | 🔴 | Check --accent in :root |
| B3 | Font = Montserrat | 🔴 | Check font-family in body, Google Fonts link |
| B4 | No hardcoded hex in mockup content | 🟡 | `grep -c "color: #" mockup.html` — only in :root and shell |
| B5 | Border-radius ≤ 12px (rectangular) | 🟡 | Check --radius-lg ≤ 12px |
| B6 | Focus rings: teal for inputs, orange for buttons | 🟡 | Check --shadow-focus-teal and --shadow-accent-focus |

---

## Quick Reference

| Category | BLOCKER | MAJOR | MINOR | Total |
|----------|---------|-------|-------|-------|
| Integrity | 6 | 0 | 0 | 6 |
| Form | 1 | 1 | 0 | 2 |
| Shell | 7 | 0 | 0 | 7 |
| Navigation Map | 5 | 7 | 1 | 13 |
| Endpoint | 3 | 2 | 0 | 5 |
| Mobile Toolbar | 1 | 4 | 0 | 5 |
| Layout | 4 | 3 | 0 | 7 |
| Clickability | 6 | 0 | 0 | 6 |
| Responsive | 3 | 2 | 0 | 5 |
| Interaction | 2 | 1 | 2 | 5 |
| Visual | 0 | 3 | 2 | 5 |
| Brand | 3 | 3 | 0 | 6 |
| Theme & Language | 4 | 7 | 0 | 11 |
| i18n Validation | 4 | 2 | 0 | 6 |
| Color Validation | 3 | 2 | 0 | 5 |
| **Total** | **52** | **37** | **5** | **94** |

---

## Pass Criteria

| Result | Action |
|--------|--------|
| 0 BLOCKER, ≤2 MAJOR | ✅ Ready to deliver |
| 1+ BLOCKER | ❌ Fix blockers, retest |
| >2 MAJOR | ⚠️ Fix majors, retest |

---

## Common Bugs & Fixes

### Bug: Header clipped on Phone/Desktop (top cut off)

**Symptom:** Header not visible on Phone or Desktop, but visible on Tablet  
**Cause:** `align-items: center` on `.preview-container` clips top when device frame is taller than viewport  
**Why Tablet works:** Tablet (624px total) fits in viewport; Phone (908px) and Desktop (824px) don't  
**Fix:**
```css
/* ⚠️ CRITICAL: Use flex-start, NOT center */
.preview-container {
  display: flex;
  align-items: flex-start;  /* NOT center */
  justify-content: center;
  overflow: auto;
  /* ... */
}

/* ⚠️ CRITICAL: margin: auto centers when frame fits */
.device-frame {
  margin: auto;
  /* ... */
}
```

---

### Bug: Children block clicks on parent

**Symptom:** Card has onclick but clicks don't work  
**Cause:** Child elements (text, icons, progress bars) intercept clicks  
**Fix:**
```css
/* Disable pointer-events on children of clickable containers */
.card[onclick] *,
.master-card[onclick] *,
.metric-row[onclick] *,
table tr[onclick] * {
  pointer-events: none;
}

/* Re-enable for nested interactive elements */
button, input, select, textarea, .checkbox {
  pointer-events: auto;
}
```

---

### Bug: Tab bar floats up

**Symptom:** Tab bar not at bottom, empty space below it  
**Cause:** Missing flex layout chain  
**Fix:**
```css
.device-screen {
  display: flex;
  flex-direction: column;
}

.mockup-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.screen.active {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.main {
  flex: 1;
}
```

---

### Bug: Scroll not reset on device switch

**Symptom:** Content stays scrolled when switching devices  
**Cause:** Single scrollTop = 0 not reliable  
**Fix:**
```javascript
setDevice(type) {
  // ... device switch code ...
  
  // Aggressive scroll reset
  const resetScroll = () => {
    this.screen.scrollTop = 0;
    this.screen.scrollTo({ top: 0, behavior: 'instant' });
  };
  resetScroll();
  requestAnimationFrame(resetScroll);
  setTimeout(resetScroll, 100);
}
```

---

## Checklist Template (copy-paste)

```
## Integrity ⚠️ GATE
□ INT1 File ends </html>
□ INT2 No cdn-cgi
□ INT3 No __cf_email__
□ INT4 Scripts balanced
□ INT5 Body closed
□ INT6 HTML closed

## Form
□ F1 Form buttons work
□ F2 No form+onsubmit

## Shell
□ S1 Toolbar visible
□ S2 No overlap
□ S3 Phone works
□ S4 Tablet works
□ S5 Desktop works
□ S6 Scroll resets on switch
□ S7 Header visible all devices (no top clipping)

## Navigation Map ⭐
□ N1 Map button visible
□ N2 Map opens
□ N3 Map closes
□ N4 Stats correct
□ N5 🟢 Screens navigate
□ N6 🔴 Endpoints show toast
□ N7 All screens in map
□ N8 All endpoints documented
□ N9 Traffic light colors correct
□ N10 Sections have counters
□ N11 Sections collapse/expand
□ N12 Default = collapsed
□ N13 🟡 Tabs show yellow toast

## Endpoints ⭐
□ E1 Dead-ends show toast
□ E2 Endpoint toast format correct
□ E3 Tabs show yellow toast
□ E4 List items show endpoint
□ E5 No confusing toasts

## Mobile Toolbar ⭐
□ M1 Adapts at <480px
□ M2 Device sizes hidden
□ M3 Zoom value hidden
□ M4 Map label hidden
□ M5 Controls functional

## Layout
□ L1 Content in frame
□ L2 No h-scroll
□ L3 Header sticky
□ L4 Tab bar sticky
□ L5 Popups in frame
□ L6 Tab bar at bottom
□ L7 Main fills space

## Clickability
□ C1 Cards respond
□ C2 Card children clickable
□ C3 Nested buttons work
□ C4 Table rows work
□ C5 Progress bars don't block
□ C6 Labels don't block

## Responsive
□ R1 Phone readable
□ R2 Tablet uses space
□ R3 Desktop fills width
□ R4 Touch targets ≥44px
□ R5 Text ≥14px

## Interaction
□ I1 Buttons work
□ I2 Navigation works
□ I3 Toasts appear
□ I4 Hover effects
□ I5 Smooth transitions

## Visual
□ V1 No Lorem ipsum
□ V2 No placeholders
□ V3 CSS variables
□ V4 Consistent spacing
□ V5 Consistent icons

## Brand (CBS HOME) ⭐
□ B1 Primary = teal #1A6B6A
□ B2 Accent = orange #E8651A
□ B3 Font = Montserrat
□ B4 No hardcoded hex in content
□ B5 Radius ≤ 12px
□ B6 Focus ring = orange

## Theme & Language ⭐
□ T1 Theme button visible
□ T2 Theme cycle works
□ T3 Dark mode colors change
□ T4 No flash on load
□ T5 Theme persists
□ T6 Keyboard T works
□ I1 Language buttons visible
□ I2 Language switch works
□ I3 No i18n keys visible
□ I4 Language persists
□ I5 Keyboard L works

## i18n Validation ⭐
□ IV1 🔴 Every data-i18n key exists in i18n.js dictionary
□ IV2 🔴 Every key has 3 translations (ru, en, de)
□ IV3 🟡 Default text in HTML = Russian translation
□ IV4 🟡 Nav-map items default text is Russian
□ IV5 🔴 No raw i18n keys visible in rendered page
□ IV6 🔴 Language switcher shows RU/EN/DE (3 buttons)

## Color Validation ⭐
□ CV1 🔴 Zero hardcoded hex in mockup-content (outside :root)
□ CV2 🔴 All colors use CSS variables
□ CV3 🟡 Primary UI = teal family, not orange
□ CV4 🟡 Accent/CTA = orange family, not teal
□ CV5 🔴 Logo icon-bg = #cc3203 via --logo-icon-bg

RESULT: ___ BLOCKER / ___ MAJOR / ___ MINOR
```

---

### i18n Validation Details

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| IV1 | Every `data-i18n` key in HTML has matching entry in i18n.js | 🔴 | `grep -oP 'data-i18n="[^"]*"' mockup.html \| sort -u` then verify each in i18n.js |
| IV2 | Every dictionary key has `ru`, `en`, `de` translations | 🔴 | Check i18n.js `_dict` object — each key needs 3 sub-keys |
| IV3 | Default text in HTML matches Russian translation | 🟡 | Compare `<h1 data-i18n="key">Text</h1>` — Text should be Russian |
| IV4 | Nav-map items default to Russian labels | 🟡 | Visual check nav-map overlay — all section/item labels in Russian |
| IV5 | No raw i18n keys visible when page renders | 🔴 | Open page, check no `auth.login.title` style keys showing |
| IV6 | Language switcher has 3 buttons: RU, EN, DE | 🔴 | Check `.lang-switcher` in toolbar — must have 3 `.lang-btn` |

---

### Color Validation Details

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| CV1 | No hardcoded hex colors in mockup-content | 🔴 | `grep -n "#[0-9a-fA-F]\{3,8\}" mockup.html \| grep -v ":root" \| grep -v "favicon" \| grep -v "svg.*icon"` — must be 0 |
| CV2 | All styling uses CSS variables | 🔴 | All `color:`, `background:`, `border-color:` reference `var(--*)` |
| CV3 | Primary UI elements use teal, not orange | 🟡 | Headers, nav, cards use `var(--primary)` family |
| CV4 | CTA buttons and badges use orange, not teal | 🟡 | `.btn-primary` uses `var(--accent)`, active indicators use `var(--accent)` |
| CV5 | Logo icon bg = #cc3203 via variable | 🔴 | `.cbs-logo-icon` or `.header-logo` uses `var(--logo-icon-bg)`, not `var(--accent)` |

---

## Toolbar & Hub Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| H1 | Home button in toolbar | 🔴 | `grep -c 'home-btn' mockup.html` — must be 1 |
| H2 | Home button links to index | 🔴 | `grep 'home-btn' mockup.html` — href = `../index.html` |
| H3 | Device buttons use Lucide icons | 🔴 | `grep 'data-device' mockup.html` — each has `data-lucide="smartphone\|tablet\|monitor"`, no emoji |
| H4 | Hub card icons use Lucide | 🟡 | `index.html` — `.hub-card-icon` contains `<i data-lucide="...">`, no emoji |

---

## i18n Coverage Checks

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| I6 | All stat labels have data-i18n | 🔴 | `grep 'stat-label' mockup.html` — every `.stat-label` has `data-i18n` attr |
| I7 | All section titles have data-i18n | 🔴 | `grep 'section-title' mockup.html` — every `.section-title` has `data-i18n` attr |
| I8 | All button text has data-i18n | 🟡 | Button labels (not icons) wrapped in `<span data-i18n="...">` |
| I9 | Settings screen labels have data-i18n | 🔴 | All setting row text in screen-settings has `data-i18n` |
| I10 | Nav-map default text is Russian | 🔴 | All `data-i18n` elements have Russian default text (not English) |

---

## Nav Map Checks (v1.8.0)

| ID | Check | Level | How to Test |
|----|-------|-------|-------------|
| N14 | Items render as horizontal chips | 🔴 | `.nav-map-section-content` has `display:flex; flex-wrap:wrap` |
| N15 | No nav-map-level wrapper divs | 🔴 | `grep -c 'nav-map-level' mockup.html` — must be 0 |
| N16 | Legend text = "Endpoint" | 🟡 | `grep 'nav.legend.endpoint' mockup.html` — default text consistent |

---

*checklist v1.8.0*
