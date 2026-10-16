---
name: probekit-responsive-audit
description: "v1.0.0 | CBS HOME responsive layout audit. Checks phone/tablet/desktop breakpoints, safe-area, touch targets, viewport meta, RTL layout. Use when: 'responsive audit', 'check breakpoints', 'mobile check', 'layout audit', 'адаптивность'."
---

# responsive-audit v1.0.0

CBS HOME responsive layout audit for Vue 3 frontend.
Verifies components work across phone (390px), tablet (820px), desktop (1280px).

## Configuration

source_dir: mockups/frontend/src
index_html: mockups/frontend/index.html

## Probes

Read `references/probe-definitions.md` for full probe specifications (P1–P8):
P1: Viewport Meta (CRITICAL), P2: Safe Area (HIGH), P3: Touch Target Size (HIGH),
P4: Flex/Grid Layout (MEDIUM), P5: Sticky vs Fixed (HIGH), P6: RTL Layout (MEDIUM),
P7: Breakpoint Consistency (MEDIUM), P8: dvh Units (LOW).

## Execution Steps

1. Read index.html — check viewport meta
2. Read global.css — check safe-area
3. Scan components for P1-P8
4. Classify and report

## Anchor

[*] responsive-audit v1.0.0 * ready
