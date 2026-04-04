---
name: livemockup-studio
description: "v1.8.0 | Interactive HTML prototypes with Device Preview + Navigation Map + CBS HOME brand"
---

# livemockup-studio v1.8.0

Interactive HTML mockups: device preview, Navigation Map, microinteractions, realistic data.
CBS HOME brand-native: Orange triad / Teal palette, Montserrat font, rectangular aesthetic.
Ecosystem mode: shared CSS/JS + index hub for multi-mockup projects.
i18n: RU/EN/DE with 242 keys. Element-map-driven color system.

---

## Invariants

| Rule | Description |
|------|-------------|
| **Always** single file | Output = 1 HTML file |
| **Always** device shell | Wrap content in preview shell |
| **Always** realistic data | No Lorem ipsum ever |
| **Always** feedback | Every action shows toast/state |
| **Always** sticky inside | Use sticky, not fixed, inside mockup |
| **Always** pointer-events fix | Children of onclick containers need `pointer-events: none` |
| **Always** flex chain | Full flex from device-screen to main |
| **Always** scroll reset | Aggressive scroll reset on device switch |
| **Always** flex-start container | `align-items: flex-start` + `margin: auto` on frame |
| **Always** navigation map | Include Map button with screen tree |
| **Always** adaptive toolbar | Toolbar adapts to mobile (<480px) |
| **Always** endpoint marking | Toast for endpoints: `📌 [name] — финальная точка` |
| **Always** theme + i18n | Include theme toggle (T key) and lang switcher (L key) |
| **Never** multiple files | No separate CSS/JS files |
| **Always** test after build | Auto-run test protocol after build completes |
| **Always** test after polish | Auto-run test protocol after polish completes |
| **Always** 3-language i18n | ru/en/de with default Russian text in HTML |
| **Always** logo-icon-bg | U-icon uses `var(--logo-icon-bg)` #cc3203, not `var(--accent)` |
| **Never** hardcode colors | Use CSS variables from reference/brand-cbs.md |
| **Never** skip test | Validate before delivery |
| **Never** align-items: center on container | Causes top clipping |

---

## Flow

```
brief → design → build → polish → test → deliver
 L0       L1       L2       L3      L3.5    L4
```

| Layer | Protocol | Creates |
|-------|----------|---------|
| L0 | brief | Requirements + data plan |
| L1 | design | Tokens + interaction map |
| L2 | build | HTML with shell |
| L3 | polish | Animations + realistic data |
| L3.5 | test | Validated mockup |

### Ecosystem Mode

For multi-mockup projects, run `ecosystem` protocol after completing individual mockups:
```
[individual mockups ready] → ecosystem → shared CSS/JS + index hub
```

---

## Quick Reference

| Goal | Path |
|------|------|
| New mockup | brief → design → build → polish → test |
| Skip to building | build (if requirements clear) |
| Polish existing | polish → test |
| CBS HOME brand tokens | reference/brand-cbs.md |
| Fix shell issues | reference/shell.md |
| Add interactions | reference/interactions.md |
| Validate quality | reference/checklist.md |
| Realistic data | reference/data.md |
| UI components | reference/components.md |
| CBS HOME patterns | reference/cbs-patterns.md |
| Ecosystem mode | reference/ecosystem.md + protocols/ecosystem.md |
| Theme + i18n | js/theme.js + js/i18n.js |

---

## Communication Style

| Aspect | Style |
|--------|-------|
| Language | Russian primary |
| Tone | Professional, concise |
| Output | Single HTML file |

---

## Recovery

| Issue | Reference |
|-------|-----------|
| Shell broken | reference/shell.md |
| Clicks not working | reference/shell.md → Clickability Fix |
| Tab bar floats | reference/shell.md → Flex Chain |
| Header clipped | reference/shell.md → Container Alignment |
| No nav map | reference/shell.md → Navigation Map |
| Toolbar broken on mobile | reference/shell.md → Adaptive Toolbar |
| Animations not working | reference/interactions.md |
| Data looks fake | reference/data.md |
| Quality issues | reference/checklist.md |
| File corrupted | reference/integrity.md |
| Shared CSS/JS broken | reference/ecosystem.md |
