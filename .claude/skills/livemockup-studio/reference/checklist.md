---
name: checklist
description: "v1.3.0 | Quality gates with Navigation Map checks"
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
| N1 | Map button visible in toolbar | 🔴 | Look for 📍 Map button |
| N2 | Map popup opens on click | 🔴 | Click 📍 Map — popup appears |
| N3 | Map popup closes on × or overlay click | 🔴 | Click × or outside popup |
| N4 | Stats show correct counts | 🟡 | Verify экранов / путей / финальных точек |
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
| E2 | Endpoint toast format correct | 🟡 | Must be `📌 {Name} — финальная точка` |
| E3 | Tabs show yellow toast | 🔴 | Click tabs → `🟡 Таб "{Name}" — переключает контент` |
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
| **Total** | **38** | **23** | **5** | **66** |

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

RESULT: ___ BLOCKER / ___ MAJOR / ___ MINOR
```

---

*checklist v1.3.0*
