---
name: generate
description: "v1.0.0 | P2: Generate interactive HTML visualization from manifest.yaml"
---

# P2: Generate

Transform manifest.yaml into an interactive single-file HTML visualization.

| Creates | `mockups/project-map/index.html` |
|---------|----------------------------------|
| Phase | P2 -- Visualization |

---

## Requirements

| Input | Check |
|-------|-------|
| `mockups/project-map/manifest.yaml` | Must exist (run P1 scan first) |

If missing -> Run `protocols/scan.md` first.

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/html-template.md | Page structure, CSS tokens, JS architecture |
| 2 | reference/status-model.md | Status colors, Mermaid node classes |
| 3 | mockups/project-map/manifest.yaml | Data to visualize |

---

## Steps

### Step 1: Build L0 Overview Diagrams

Create one Mermaid `graph LR` diagram per role (investor, agent, company, staff).

Each diagram has three `subgraph` columns:
- **Left -- Screens**: node per screen, colored by worst-status of its endpoints
- **Center -- API Modules**: group endpoints by module (auth, investor, products, etc.)
- **Right -- Models**: node per model used by the module

Edges:
- Screen -> API Module (if screen requires endpoints from that module)
- API Module -> Model (if module's service uses that model)

Apply Mermaid `classDef` for status colors (see status-model.md §Mermaid Node CSS Classes).

Also create one **Business Flows** diagram showing all named flows from manifest as sequential graphs.

### Step 2: Build L1 Screen-Endpoint Cards

For each screen in manifest, create an expandable card containing:

1. **Header row**: role badge, screen ID, prod-readiness score badge
2. **Endpoint list**: for each required endpoint:
   - Status dot (colored circle)
   - HTTP method badge (GET=teal, POST=orange, PATCH/PUT=yellow, DELETE=red)
   - Full API path in monospace
   - Sprint label (if assigned)
3. **Navigation targets**: links to other screen cards
4. **Data entities**: list of CSS classes detected
5. **Endpoint markers**: toast texts that indicate needed features

Group cards by role with role section headers.
Sort within role: highest score first (ready screens on top).

### Step 3: Build L2 Field-Model Tables

For each model in manifest, create a card containing:

1. **Header**: model name, table name, file path
2. **Field table**: columns with name, type, nullable, default
3. **Used by**: list of screen IDs that reference data from this model

Sort by: models with most screen references first.

### Step 4: Assemble HTML Page

Build a single HTML file following the template in html-template.md:

1. **DOCTYPE + head**: charset, viewport, Google Fonts (Montserrat + JetBrains Mono), Mermaid CDN
2. **Inline CSS**: all design tokens from html-template.md, responsive adjustments
3. **Header bar**: logo text, stats counters (from manifest.cross_reference.coverage), scan metadata
4. **Filter bar**: role toggle buttons, status toggle buttons, search input
5. **Tab bar**: L0 / L1 / L2 / Dead-Ends / Prod-Readiness
6. **5 panels**: content from Steps 1-3 + Steps 6-7
7. **Inline JavaScript**: PM state object, event binding, tab/filter/search/expand logic
8. **Mermaid init**: with CBS theme configuration

### Step 5: Add Interactivity

JavaScript features:
- **Tab switching**: show/hide panels by CSS class, update active tab
- **Role filter**: show/hide cards by `data-role` attribute
- **Status filter**: show/hide endpoint rows by `data-status` attribute
- **Text search**: filter cards by text content match (screen ID, endpoint path)
- **Card expand/collapse**: toggle `.open` class on card click
- **Mermaid rendering**: initialize after DOM ready

### Step 6: Build Dead-End Panel

Two sections:

1. **Frontend Orphans**: screens with score = 0%
   - Group by role
   - Show screen ID + "Blocked by Sprint X.Y" (earliest required sprint)
   - Count total

2. **Backend Orphans**: implemented endpoints with no screen consumer
   - Exclude system endpoints (`/`, `/health`, `/ready`)
   - Show method + path
   - Count total

3. **Near-Orphans**: screens with score 1-49%
   - Show partial progress info

### Step 7: Build Prod-Readiness Dashboard

Three groups:

1. **Ready for Prod** (score = 100%): green traffic lights
2. **Nearest to Ready** (score 50-99%): yellow traffic lights, show missing endpoints
3. **Blocked** (score 0-49%): red traffic lights, show blocking sprint

Plus **Business Flows** section:
- For each flow in manifest.flows:
  - Flow name
  - Progress bar (filled to score %)
  - Score badge
  - List of steps with status icons

### Step 8: Finalize

1. Ensure all Mermaid code blocks are wrapped in `<pre class="mermaid">`
2. Verify no console errors in generated JS
3. Write to `mockups/project-map/index.html`

---

## Checklist

- [ ] L0 Mermaid diagrams render for all roles
- [ ] L1 cards exist for all screens (match manifest count)
- [ ] L2 tables exist for all models
- [ ] Tab switching works (5 tabs)
- [ ] Role filter shows/hides cards correctly
- [ ] Status filter works on endpoint rows
- [ ] Search filters cards by text
- [ ] Cards expand/collapse on click
- [ ] Dead-end panel shows correct orphan counts
- [ ] Prod-readiness shows correct scores
- [ ] Business flow bars show correct fill
- [ ] CBS dark theme applied (colors match mockup hub)
- [ ] Montserrat + JetBrains Mono fonts load
- [ ] Mermaid.js loads from CDN
- [ ] No JS console errors

---

## Anchor

project-map v1.0.0 | generate | complete

NEXT: validate (P3)

---

*generate v1.0.0*
