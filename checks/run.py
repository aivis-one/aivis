#!/usr/bin/env python3
"""Run every frontend check in this folder.

    python checks/run.py              # the checks; exit 0 = all pass, 1 = a failure
    python checks/run.py --selftest   # prove each check can FAIL, then that it passes

WHAT THIS IS. Static checks on the frontend source that the type checker and the
unit tests cannot express: things that are true of the CSS and the router as a
whole rather than of one module. Each one exists because the product actually
had the defect it looks for.

WHY --selftest MATTERS AS MUCH AS THE CHECKS. A check that cannot fail passes
forever and proves nothing. `--selftest` plants the defect each check is meant
to catch -- in a throwaway copy, never in the real tree -- and asserts the check
rejects it, then restores and asserts it accepts again. If you change a check,
run the selftest before trusting a green run.

NOT WIRED INTO `npm run gate` YET. This is deliberate: it adds a Python step to
a JavaScript build, and that is a decision for whoever owns the pipeline. Python
is already a project dependency (see backend/pyproject.toml), so the cost is a
line in package.json, not a new toolchain. Nothing here needs pip -- standard
library only.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import breakpoints  # noqa: E402
import routes  # noqa: E402
import shell_layout  # noqa: E402
import tokens  # noqa: E402

CHECKS = [
    ("breakpoints", "every width breakpoint used is a declared one", breakpoints),
    ("shell layout", "the shell chrome has one source and the storefront is outside it",
     shell_layout),
    ("tokens", "every var(--x) that paints resolves to a declared token", tokens),
    ("routes", "the router table is well formed and every name is unique", routes),
]


def main(argv: list[str]) -> int:
    selftest = "--selftest" in argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("frontend checks -- repository root: %s" % ROOT)
    print()
    failed = []
    for name, blurb, module in CHECKS:
        print("=== %s -- %s" % (name, blurb))
        try:
            if selftest:
                for line in module.selftest(ROOT):
                    print(line)
                print("  SELFTEST OK")
            else:
                ok, lines = module.run(ROOT)
                for line in lines:
                    print("  " + line)
                print("  %s" % ("PASS" if ok else "FAIL"))
                if not ok:
                    failed.append(name)
        except Exception as exc:  # a check that cannot run is a failure, never a skip
            print("  ERROR: %s: %s" % (type(exc).__name__, exc))
            failed.append(name)
        print()

    if failed:
        print("FAILED: %s" % ", ".join(failed))
        return 1
    print("ALL %d CHECKS %s" % (len(CHECKS), "SELFTESTED" if selftest else "PASS"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
