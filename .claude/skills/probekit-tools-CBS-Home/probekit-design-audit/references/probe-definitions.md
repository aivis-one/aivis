# Design Audit — Probe Definitions

CBS HOME design system compliance probes. Read severity from `probekit-core/references/severity-format.md`.

## P1: Hardcoded Colors (CRITICAL)

Scan all `.vue` and `.css` files for hex colors, rgb(), hsl() values.

**Allowed:**
- `var(--*)` CSS variables
- `currentColor`, `inherit`, `transparent`
- `#fff` / `#ffffff` (pure white — universal constant)
- `#000` / `#000000` (pure black — universal constant)
- Colors inside `variables.css` itself (token definitions)
- Colors inside comments

**Forbidden:**
- Any other hex color (`#cc3203`, `#E8651A`, etc.) — must use token
- `rgb()` / `rgba()` outside variables.css
- `hsl()` / `hsla()` outside variables.css
- CSS named colors (`red`, `blue`, `green`, `white`, `black`, `gray`, `grey`, `orange`, etc.)

**Detection:**
```bash
grep -rn --include='*.vue' --include='*.css' -E '#[0-9a-fA-F]{3,8}' src/ | grep -v variables.css | grep -v node_modules
grep -rn --include='*.vue' -E '\b(red|blue|green|white|black|gray|grey|orange|yellow|purple|pink|teal)\b' src/components/ src/views/
```

## P2: Font Compliance (HIGH)

Verify all font usage goes through `var(--font)`.

**Checks:**
- No `font-family:` declarations except `var(--font)`, `inherit`, `monospace` (for code blocks)
- Font weights: only 400/500/600/700/800 (Montserrat range)
- Font sizes follow typography scale (12/13/14/15/16/17/18/20/24/28/32/48px)

**Detection:**
```bash
grep -rn --include='*.vue' 'font-family' src/ | grep -v 'var(--font)' | grep -v 'inherit'
```

## P3: Spacing Token Usage (MEDIUM)

Verify spacing uses `var(--space-*)` tokens, not hardcoded px values.

**Allowed px values:** `0`, `1px` (borders), `2px` (borders, small gaps), values inside `variables.css`, `env(safe-area-*)` values.

**Detection:**
```bash
grep -rn --include='*.vue' -E '(padding|margin|gap):\s*\d+px' src/ | grep -v variables.css
```

## P4: Radius Token Usage (MEDIUM)

Verify border-radius uses `var(--radius-*)`.

**Detection:**
```bash
grep -rn --include='*.vue' 'border-radius' src/ | grep -v 'var(--radius' | grep -v '50%'
```

## P5: Shadow Token Usage (MEDIUM)

Verify box-shadow uses `var(--shadow-*)`.

**Detection:**
```bash
grep -rn --include='*.vue' 'box-shadow' src/ | grep -v 'var(--shadow' | grep -v 'none'
```

## P6: Dark Mode Completeness (HIGH)

Verify components render correctly in both themes.

**Checks:**
- Background colors use semantic tokens (`--bg`, `--bg-subtle`, `--bg-elevated`)
- Text colors use semantic tokens (`--text`, `--text-secondary`, `--text-tertiary`)
- Border colors use `--border`
- No `background: white` or `color: black` literals

## P7: Logo Icon Color (CRITICAL)

CBS HOME logo icon background MUST be `--o-primary` (#cc3203), NEVER `--accent` (#E8651A).

**Detection:**
```bash
grep -rn 'logo' src/ --include='*.vue' | grep -i 'accent\|E8651A'
```

## P8: Token Sync (HIGH)

Verify `variables.css` in frontend matches source of truth `mockups/css/variables.css`.

**Detection:**
```bash
diff mockups/frontend/src/styles/variables.css mockups/css/variables.css
```
