# Changelog

## v1.0.0 — 2026-04-10

### Features
- **8 responsive probes**: viewport meta, safe area, touch target size (44x44px WCAG 2.5.5), flex/grid layout, sticky vs fixed, RTL layout, breakpoint consistency, dvh units
- **Device-aware breakpoints**: phone (≤480px), tablet (481-1024px), desktop (>1024px)
- **Notch/safe-area support**: env(safe-area-inset-*) detection for modern devices
- **WCAG alignment**: touch target minimum from WCAG 2.5.5
- **RTL-aware**: logical properties (start/end) instead of left/right
- **CBS HOME calibration**: targets mockups/frontend/src/ Vue 3 components
- **Scored report**: severity-based scoring with totals table
- **Audit tracker integration**: appends to AUDIT-TRACKER.md

Toolchain: probekit-tools-CBS-Home
