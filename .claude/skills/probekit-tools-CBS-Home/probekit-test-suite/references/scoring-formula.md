---
name: scoring-formula
description: "Overall quality score formula with density normalization for codebases of any size"
---

# Overall Quality Score v2.0.0

Density-normalized score. Comparable across codebases of different sizes.

**Step 1 — Deduplicate findings** (see inter-skill-context.md § Finding Deduplication Protocol):
```
Use deduplicated finding counts (not raw per-stage counts).
```

**Step 2 — Calculate severity points:**
```
total_critical = deduplicated CRITICAL count
total_warning  = deduplicated WARNING count
total_suggestion = deduplicated SUGGESTION count
total_diamond  = deduplicated DIAMOND count

severity_points = (total_critical x 1.5) + (total_warning x 0.5) + (total_suggestion x 0.1)
```

**Step 3 — Normalize by scope:**
```
files_analyzed = count of unique source files scanned across all stages
                 (exclude tests, configs, migrations, generated, .md)
normalization_baseline = 100   # overridable via .probekit.yml -> scoring.normalization_baseline
scale_factor = max(files_analyzed, 10) / normalization_baseline

severity_density = severity_points / scale_factor
```

100 files = no scaling effect (density = raw points).
365 files = density is ~2.7x lower than raw points.
50 files = density is ~2x higher than raw points.

**Step 4 — Diamond bonus (scales with size):**
```
diamond_bonus = min(total_diamond x 0.1, 0.5 + log2(max(files_analyzed, 50) / 50))
               # floor 0.5 for small projects, grows with size, cap 2.0
diamond_bonus = min(diamond_bonus, 2.0)
```

**Step 5 — Final score:**
```
raw_score = 10.0 - severity_density + diamond_bonus
final_score = max(1, min(10, round(raw_score x 2) / 2))   # round to 0.5, floor 1, ceiling 10
```

Default weights (overridable via `.probekit.yml` -> `scoring.weights`):
- `critical`: 1.5 | `warning`: 0.5 | `suggestion`: 0.1 | `diamond`: 0.1

**Show in report:**
```
## Overall Quality Score: X.X/10  (density N.NN, N files)

Calculation: severity_points=N / scale_factor=N.NN = density N.NN
             10.0 - N.NN + diamond N.NN = X.X -> X.X/10
```

**Examples:**
- 10W on 50 files: points=5.0, scale=0.5, density=10.0 → score ~1.0
- 10W on 100 files: points=5.0, scale=1.0, density=5.0 → score ~5.5
- 10W on 365 files: points=5.0, scale=3.65, density=1.37 → score ~9.0
- 3C+8W+6S on 365 files: points=5.1, scale=3.65, density=1.40 → score ~9.0

# Overall Quality Gate

The suite **PASSES** when:
- All blocking stages pass (code-audit >= 4/10)
- No unaddressed CRITICAL findings across all stages
- Architecture scores >= 3.0/10 (if arch stages ran)

The suite **WARNS** when:
- Architecture score 3.0-4.9/10
- Code audit score 4-6/10
- Non-blocking stages have FAIL gate

The suite **FAILS** when:
- Code audit score < 4/10 (pipeline stopped)
- Any blocking stage has FAIL gate
