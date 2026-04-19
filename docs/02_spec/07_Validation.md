# 07_Validation
> SPEC v3.0.0 | Universal validation standard for all SPEC artifacts
> Used by: every protocol, every execute prompt, every deliverable
> Applies to: Claude Chat output, Claude Code output, plans, documents, code changes

---

## Purpose

Compensate for confirmation bias in AI-generated output. Every artifact —
document, plan, code change, audit report — passes through this protocol
before being considered complete.

This protocol is referenced, not copied. One source of truth.

---

## How to Apply

Insert one line at the end of any prompt, protocol step, or deliverable:

    Validation: apply docs/02_spec/07_Validation.md

Or for inline use (Claude Chat conversations), paste the Validation Block below.

---

## Validation Block

    ATTENTION! You are validating your own output. You are biased toward confirming
    it is correct. Compensate: assume problems exist and hunt for them.
    "VALID" requires more proof than finding issues does.

    BEFORE VALIDATING: Re-read the actual artifact, not your memory of intent.
    Build an explicit map of every claim, reference, version, count, and constraint
    it contains. Validate against the map.

    PRINCIPLES:
    1. COMPLETENESS — everything declared is present, nothing promised is missing
    2. CONSISTENCY — zero contradictions within the material and against context
    3. CASCADE — every change traced to all downstream references
    4. NEGATIVE — everything removed is gone everywhere, no ghost references
    5. ENVIRONMENT — material respects the rules and boundaries of the system
    6. FEASIBILITY — for each claim of "works", "uses", "calls" — can the target
       actually do what's described? A plan that references a component incorrectly
       is worse than a missing plan. If you can't verify — mark [unverified].
    7. NAMING — read every title, label, and term as if you're a new reader.
       Does the name match the actual content? Misleading names cause downstream
       errors in every consumer of this artifact.
    8. SESSION CONSISTENCY — if this artifact builds on earlier decisions in this
       conversation, verify those decisions are faithfully represented, not drifted.
       Check: did we decide X but write Y?

    SPOT-CHECK: numbers, versions, dates, counts, cross-references —
    highest error rate, verify each explicitly.

    DECISION RULE: when fixing, always choose architectural cleanliness over
    minimal patch. Resolve legacy, don't inherit it.

    SEVERITY HONESTY: do not downgrade to make results look cleaner.
    Breaks downstream = BREAK, not GAP.

    OUTPUT:
    - Problems found: numbered list [BREAK|GAP|NIT] + location + problem + fix
    - No problems: "VALID — no issues found"
    - After list: apply all fixes, deliver corrected material.

---

## Principles Detail

### 1-5: Core (original)

| # | Principle | What it catches | Example from practice |
|---|-----------|----------------|----------------------|
| 1 | COMPLETENESS | Missing sections, promised but absent | F148 missing from validation checklist |
| 2 | CONSISTENCY | Contradictions within or across docs | "4 candidates" in ARCHITECTURE vs "5" in MOTHERBOARD |
| 3 | CASCADE | Change not traced downstream | Updated ARCHITECTURE version but not TZ-SPEC cross-ref |
| 4 | NEGATIVE | Removed content still referenced | "Planned-Required" section deleted but workaround text remained |
| 5 | ENVIRONMENT | Violates system rules or boundaries | M-numbers in active docs (should be S-numbers) |

### 6-8: Extended (added from operational experience)

| # | Principle | What it catches | Example from practice |
|---|-----------|----------------|----------------------|
| 6 | FEASIBILITY | Described behavior impossible in code | ActionNode referenced for git/pytest — actually pure passthrough |
| 7 | NAMING | Name misleads about content | "Dual-Write Policy" when intent was "Centralization" |
| 8 | SESSION CONSISTENCY | Earlier decision contradicted later | Decided two-node kill switch pattern but VISION scenario still used single ConditionNode |

---

## Usage Contexts

| Context | Who validates | What's validated | How |
|---------|-------------|-----------------|-----|
| Claude Chat to Human | Claude Chat | Plans, documents, analysis | Inline paste of Validation Block |
| Execute prompt to Claude Code | Claude Code | Code changes, file edits | Reference line in prompt |
| Cross-Validation | Claude Code | Claude Chat's plan | CROSSVAL prompt with FEASIBILITY focus |
| Protocol step | Any agent | Step deliverable | Reference in protocol |
| Sprint close | Claude Code | All sprint artifacts | Full 8-principle sweep |

---

## Integration Points

Referenced from:
- `01_Declaration.md` §Rule 22: Validation Anti-Bias
- `02_Sprint-Builder.md` §Plan Validation Gates
- `03_Phase-Builder.md` §Assess Step
- `04_Sprint-Closer.md` §Quality gate
- `05_Clean-Sync.md` §Cross-document validation
- Every execute prompt (one-line reference)

---

## History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2025 | Original 5 principles (COMPLETENESS through ENVIRONMENT) |
| v2.0 | 2026-04-08 | +3 principles from architecture update session: FEASIBILITY (ActionNode gap), NAMING (Dual-Write to Centralization), SESSION CONSISTENCY (kill switch pattern drift). Extracted to standalone reference doc. |

---

*07_Validation.md — SPEC v3.0.0*
*Universal validation standard — 8 principles*
*One source of truth — reference, don't copy*
