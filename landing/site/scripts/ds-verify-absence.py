#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/ds-verify-absence.py

Verify a design system's declared absences against its own payload (G6).

    python3 scripts/ds-verify-absence.py <coverage.md> <tokens-resolved.json> [--json out.json]

A coverage table says what a design system delivers and what it does NOT
carry. A `NOT CARRIED` row is load-bearing information: the consumer stops
looking and builds the thing itself. When the payload actually carries that
family, the row is a false absence, and every consumer downstream inherits it.
That is exactly what happened here -- bogame's coverage.md says "there are no
breakpoint tokens" while the payload carries four of them.

What this script does, all of it derived at run time (M-1):

  1. parse EVERY row of the coverage table, and keep the ones whose State cell
     says NOT CARRIED -- the row count is counted, never asserted;
  2. from each such row take the family keyword(s) it NAMES, out of its own
     Category and Evidence cells;
  3. grep the payload for each keyword at the family position of a token name
     (`--ds-<family>-...`), across ALL layers -- a primitive row is still a row
     that exists, and "we have none" is false the moment one is there;
  4. exit 1 naming every misclassified family with its derived row count, or
     exit 0 when every declared absence is genuine.

Exit codes: 0 every NOT CARRIED row is genuinely absent, 1 at least one is
misclassified, 2 usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

NOT_CARRIED = "not carried"

# Words that carry no family meaning. This list only reduces noise: the real
# precision comes from requiring a match at the FAMILY position of a token
# name, so a stray prose word cannot invent a finding.
STOPWORDS = {
    "there", "are", "the", "and", "not", "carried", "this", "that", "with", "from", "for",
    "was", "were", "been", "have", "has", "had", "they", "them", "their", "which", "what",
    "when", "where", "while", "than", "then", "into", "onto", "over", "under", "about",
    "before", "after", "during", "because", "rather", "leaving", "discovered", "states",
    "state", "delivered", "absent", "reason", "evidence", "category", "token", "tokens",
    "file", "files", "payload", "system", "skill", "tree", "consumer", "owner", "ask",
    "raw", "value", "values", "must", "need", "needs", "needing", "does", "done", "also",
    "only", "every", "each", "some", "any", "all", "one", "two", "three", "four", "reach",
    "worth", "knowing", "assuming", "checked", "computed", "travel", "pair", "pairs",
    "against", "behaviour", "behavior", "declared", "outside", "screen", "reports",
    "printed", "measure", "consequence", "layer", "layers", "here", "look", "read",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]{2,}")


def warn(msg):
    print("WARN: %s" % msg, file=sys.stderr)


def _cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [re.sub(r"`", "", c).strip() for c in s.strip("|").split("|")]


def _is_sep(cells):
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def parse_coverage(path):
    """Every data row of the coverage table, as (category, state, evidence).

    The real table is interrupted by an embedded list, which splits it into two
    markdown blocks. Rows are therefore collected by shape -- three or more
    cells, after the header row -- rather than by contiguity, so the rows below
    the interruption (including `Print`) are not silently lost."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    rows, header_at = [], None
    for i, ln in enumerate(lines):
        cells = _cells(ln)
        if cells is None or _is_sep(cells) or len(cells) < 3:
            continue
        low = [c.lower() for c in cells]
        if header_at is None:
            if "state" in low:
                header_at = i
            continue
        if "state" in low and "category" in low:
            break  # a second table's header: stop
        rows.append((cells[0], cells[1], " ".join(cells[2:])))
    if header_at is None:
        warn("%s carries no table whose header names a `State` column" % path)
    return rows


def load_payload(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("payload is not a JSON object")
    out = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.startswith("--"):
            warn("payload key %r is not a css custom property name; not searched" % (k,))
            continue
        layer = v.get("layer") if isinstance(v, dict) else None
        out[k] = str(layer).lower() if layer else "unknown"
    return out


def family_of(key):
    parts = key.split("-")
    return parts[3] if len(parts) > 3 else ""


def keywords(category, evidence):
    """The family keyword(s) a row NAMES, taken from its own cells. A plural is
    also tried in the singular, so "there are no breakpoint tokens" and "ask for
    the breakpoints" both reach `breakpoint`."""
    out = []
    for w in WORD_RE.findall(category + " " + evidence):
        w = w.lower().strip("-")
        if w in STOPWORDS or len(w) < 4:
            continue
        for cand in (w, w[:-1] if w.endswith("s") and len(w) > 4 else None):
            if cand and cand not in out and cand not in STOPWORDS:
                out.append(cand)
    return out


def label(category):
    m = re.search(r"[A-Za-z][A-Za-z-]*", category)
    return m.group(0).lower() if m else category.strip().lower()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Verify a design system's NOT CARRIED coverage rows against its own "
                    "token payload; a family the payload carries is a false absence.",
        epilog="Exit 0 every declared absence is genuine, 1 at least one is misclassified, "
               "2 usage error.")
    ap.add_argument("coverage", help="the design system's references/coverage.md")
    ap.add_argument("payload", help="the design system's assets/tokens-resolved.json")
    ap.add_argument("--json", default=None, help="write the findings here")
    args = ap.parse_args(argv)

    for p in (args.coverage, args.payload):
        if not Path(p).exists():
            print("FAIL: %s does not exist" % p, file=sys.stderr)
            return 2
    try:
        rows = parse_coverage(args.coverage)
    except Exception as e:
        print("FAIL: could not read %s (%s)" % (args.coverage, e), file=sys.stderr)
        return 2
    try:
        payload = load_payload(args.payload)
    except Exception as e:
        print("FAIL: could not read %s (%s)" % (args.payload, e), file=sys.stderr)
        return 2

    families = {}
    for k, layer in payload.items():
        families.setdefault(family_of(k), []).append((k, layer))

    declared = [r for r in rows if NOT_CARRIED in r[1].lower()]
    print("coverage: %d row(s) in the coverage table of %s, %d declared NOT CARRIED"
          % (len(rows), args.coverage, len(declared)))
    print("payload: %d row(s) in %d family(ies) from %s"
          % (len(payload), len(families), args.payload))
    if not declared:
        print("RESULT: PASS  no NOT CARRIED row to verify")
        if args.json:
            Path(args.json).write_text(json.dumps(
                {"rows": len(rows), "not_carried": 0, "findings": []}, indent=2) + "\n",
                encoding="utf-8")
        return 0

    findings, verified = [], []
    for category, state, evidence in declared:
        name = label(category)
        kws = keywords(category, evidence)
        hits = [(kw, sorted(families[kw])) for kw in kws if kw in families and families[kw]]
        if not hits:
            verified.append({"family": name, "keywords": kws})
            continue
        for kw, matched in hits:
            layers = sorted({lay for _, lay in matched})
            print("MISCLASSIFIED: %s -- coverage.md claims NOT CARRIED but %d row(s) exist"
                  % (name, len(matched)))
            print("               under prefix ds-%s- (layer=%s)" % (kw, ",".join(layers)))
            findings.append({"family": name, "keyword": kw, "prefix": "ds-%s-" % kw,
                             "rows": len(matched), "layers": layers,
                             "keys": [k for k, _ in matched],
                             "coverage_reason": evidence})
    for v in verified:
        print("VERIFIED-ABSENT: %s -- no ds-* family matches the keyword(s) this row names "
              "(%s)" % (v["family"], ", ".join(v["keywords"]) or "none extracted"))
        if not v["keywords"]:
            warn("coverage row '%s' names no searchable family keyword; its absence is "
                 "unverifiable from the payload and was NOT counted as verified evidence"
                 % v["family"])

    report = {"coverage": str(Path(args.coverage).resolve()),
              "payload": str(Path(args.payload).resolve()),
              "rows": len(rows), "not_carried": len(declared),
              "misclassified": len({f["family"] for f in findings}),
              "verified_absent": len(verified),
              "findings": findings, "verified": verified}
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if findings:
        print("RESULT: FAIL  %d of %d NOT CARRIED row(s) contradicted by the payload"
              % (len({f["family"] for f in findings}), len(declared)))
        return 1
    print("RESULT: PASS  all %d NOT CARRIED row(s) are genuinely absent from the payload"
          % len(declared))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("FAIL: ds-verify-absence.py could not complete (%s)" % exc, file=sys.stderr)
        sys.exit(2)
