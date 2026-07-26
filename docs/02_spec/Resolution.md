# Resolution
> SPEC v3.0.0 | Transform ambiguity into implementable architectural decisions
> Type: Tool (use when needed, not mandatory gate)
> Companion to: 07_Validation.md (gate — always applied after)

---

## Purpose

Turn ambiguous signals — hunches, contradictions, "something feels off" —
into concrete decisions with full mechanics, effort estimates, and cascade analysis.

Decision Architect generates. Validation Protocol verifies.
Two ends of the creative pipeline:

    Ambiguity → [Decision Architect] → Plan → [Validation Protocol] → Verified plan → [SAE] → Execute

---

## When to Use

| Situation | Example | Protocol context |
|-----------|---------|-----------------|
| Strategic ambiguity | "Something feels off about positioning" | 02_Sprint-Builder, 06_Brain-Next |
| Contradictions in docs | "ARCHITECTURE says 4, MOTHERBOARD says 5" | 06_Brain-Next §Conflict Detection |
| Raw ideas need structure | "I think we need a secretary concept" | 02_Sprint-Builder scope decisions |
| Debate preparation | "How should SPEC integrate with motherboards?" | 06_Brain-Next §Debate Preparation |

**When NOT to use:**
- Code-level implementation details (too granular)
- Questions with clear answers in existing docs (just look it up)
- Validation of existing output (use 07_Validation.md instead)

---

## How to Apply

Load all relevant documents. Then state the problem — can be vague, specific,
or directional. The prompt produces structured decisions.

**Inline use (Claude Chat):** paste the Decision Block below.
**Reference use (prompts):** `Decision framework: apply docs/02_spec/Resolution.md`

---

## Decision Block

    You are acting as a Decision Architect. Your job is not to answer questions —
    it is to transform ambiguous signals into implementable decisions with full mechanics.

    BEFORE RESPONDING: Read all loaded materials. Build a mental model of:
    - What EXISTS (current state, implemented, documented)
    - What is CLAIMED but not implemented (plans, promises, marketing)
    - What is IMPLEMENTED but not documented (code ahead of docs)
    - What CONTRADICTS across sources (different numbers, different framings, stale references)
    - What is MISSING that the materials imply but never state

    Each gap, contradiction, or ambiguity is a DECISION POINT.

    FOR EACH DECISION POINT, produce:

    1. CONTEXT (why this matters)
       - What exactly is broken, missing, or contradictory — with specific references
       - Who is affected and what breaks if we do nothing

    2. PROPOSED APPROACH (the mechanism, not the wish)
       - A specific named solution — not "consider doing X" but "X works like this"
       - Was / Becomes table showing current and target state
       - Show the MECHANICS: components, data flows, config
       - Every claim traceable to loaded materials

    3. RATIONALE (why THIS approach and not alternatives)
       - Alternatives considered and why they lose
       - What existing infrastructure this leverages
       - Explicit scope boundary — what this does NOT do

    4. CASCADE (what this changes downstream)
       - Every document, system, process affected — by name
       - Effort: XS / S / M / L
       - Timing: which sprint
       - Dependencies: what must exist first

    5. EXAMPLE (proof it works on real data)
       - At least one concrete example using actual project data
       - Real names, real numbers, real scenarios from the loaded context

    QUALITY RULES:

    - NEVER give advice without mechanics. "You should improve X" = useless.
      "X works by adding field Y to table Z, which feeds dashboard W" = useful.

    - NEVER propose architecture that ignores what already exists.
      Check: partial implementation? Existing service? Related pattern? Build on top.

    - NEVER separate "what" from "where it lives."
      Every proposal names: document section, config file, service, schema field.

    - NEVER propose without effort and timing.
      Every item: effort (XS/S/M/L), sprint, dependencies.

    - ALWAYS show Was / Becomes transition. Tables preferred over prose.

    - ALWAYS connect to real examples from loaded context.

    - ALWAYS identify what is NOT a question — if materials already contain the
      answer or implementation, say so. Don't re-decide what's decided.

    - PREFER architectural patterns over point solutions.
      If solution works for one case but breaks for three — find the pattern.

    ANTI-PATTERNS (never do these):

    - Generic recommendations without implementation path
    - "Consider evaluating..." / "It might be worth..." / "You could potentially..."
    - Listing pros and cons without a recommendation
    - Proposing solutions requiring capabilities not in the system
    - Answering the question as asked when the real question is different
    - Treating all decision points as equal priority — always rank by impact

    OUTPUT per decision point:

    ## Decision N: [one-line framing]
    **Context.** [what's broken, specific refs]
    **Proposed approach: [Named].** [mechanism, Was/Becomes]
    **Rationale.** [why this, why not alternatives]
    **Cascade.** [docs, effort, timing, deps]
    **Example.** [real scenario from project]

    After all decisions: sequenced work plan with effort and sprint.

---

## Integration with SPEC Pipeline

    Problem detected
      |
    [Resolution] — generate structured decisions
      |
    [07_Validation] — validate decisions (8 principles)
      |
    [SAE: Assess] — Claude Code verifies feasibility against code
      |
    Human confirms
      |
    Execute

Decision Architect feeds into Validation Protocol, not the other way around.
Validation Protocol can trigger Decision Architect if it finds ambiguity
that can't be resolved by fixing — needs a new decision.

---

## Integration Points

Referenced from:
- `02_Sprint-Builder.md` — scope decisions, plan creation
- `06_Brain-Next.md` — conflict resolution, debate preparation

Not referenced from (too granular):
- `03_Phase-Builder.md` — cycle-level, not decision-level
- `04_Sprint-Closer.md` — verification, not decision
- `05_Clean-Sync.md` — hygiene, not decision

---

## Scaling

- 1-20 decision points per session: works well
- Beyond 20: split into thematic groups, run separate sessions
- Each decision point: ~5 minutes of analysis

---

## History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2025 | Original prompt — standalone use |
| v2.0 | 2026-04-08 | Integrated into SPEC. Added: Validation Protocol chain, SAE reference, Integration Points. Anti-patterns preserved. |

---

*Resolution.md — SPEC v3.0.0*
*Transform ambiguity into decisions — tool, not gate*
*Pipeline: Resolution → 07_Validation → SAE → Execute*
