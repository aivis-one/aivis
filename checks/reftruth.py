"""A ref is an object, so testing one for truth always says yes.

WHY THIS EXISTS. `const canDoKycApprove = canDo('kyc_approve')` returns a
ComputedRef. `if (!canDoKycApprove)` negates the OBJECT, which is never falsy, so
the guard is dead in the always-permitted direction. Two of those sat in
StaffUsersView.vue (305 and 322) while the same file wrote `.value` correctly
four lines further down; every staff member without kyc_approve fired a request
that answered 403 and got a red toast on every card they opened. H13 fixed the
two sites and nothing guarded the fix -- which is what this check is.

WHY THE TYPE CHECKER CANNOT DO IT. `if (obj)` is legal TypeScript for any
object. `vue-tsc` is right to accept it; the mistake is semantic, not typed. The
unit tests cannot see it either: the branch is not wrong, it is unreachable.

WHAT IT LOOKS AT. Declarations in the same file, of the form
`const NAME = <factory>(...)` for a factory that returns a ref, plus names
destructured from `storeToRefs(...)`. A name so declared is then reported
wherever it is used as a truth value without `.value`.

============================ THE HONEST BORDER ============================
An incomplete check that does not say where it stops is worse than none: the
next person reads a green run as "no such defect exists".

1. AN EXPRESSION INSIDE `${...}` IS NOT EXAMINED. Template literals are masked
   whole, so `${!canDoX ? a : b}` inside one would not be reported. This is a
   deliberate trade: the alternative is brace counting with nesting and escapes
   inside a check that gates CI, and its false positive would stop the line for
   everybody, whereas this omission can only fail to find. The count of
   interpolations skipped is PRINTED ON EVERY RUN so the blind spot announces
   itself in the log rather than waiting to be read here. It was zero-cost when
   written: 294 interpolations in frontend/src, none of them testing a declared
   ref for truth.

2. Refs that arrive any way other than a same-file `const` declaration are
   invisible: destructured from a composable (`const { loading } = useThing()`,
   which exists in this tree), passed in as a prop or a parameter, held in an
   object or an array, imported from another module, or reached through an
   alias (`const a = canDoX; if (!a)`). Naming a ref by where it CAME FROM would
   need cross-file type resolution; this check trades that reach for having no
   false positives at all.

3. A local variable that shadows a ref of the same name inside a nested scope
   would be reported wrongly. There is no such case in the tree today.

4. Five double-quoted string literals exist in the script regions of
   frontend/src; the string masker imported from `routes` handles single quotes.
   A `!someRefName` written inside one of those five would be reported as a
   finding. It would be a false positive, and it would be visible on the line.

5. Only truth TESTS are reported: `unref(x)`, `watch(x, ...)`, `toValue(x)` and
   `x.value ? a : b` are correct and are not touched.
===========================================================================

WHY IT FAILS WHEN IT FINDS NOTHING TO LOOK AT. Zero declarations across the
whole of frontend/src is not a clean tree, it is a broken derivation -- a
changed declaration style, a moved directory, a masker that ate the file. A
check that reports PASS in that state is the failure mode the runner's header
warns about, and the same one preauth.py guards with "no route carries a width
query at all".
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

# The comment masker and the string pattern are IMPORTED, not re-declared.
# There are already three copies of this line-comment pattern in checks/
# (breakpoints:49, routes:24, tokens:29) and consolidating them is its own
# piece of work, P-69 -- but a fourth copy would be added by this file, and
# that is the one decision belonging to this file. `_mask` blanks // and
# /* */ preserving length and newlines, which is what keeps the line numbers
# below exact; `STRING` handles backslash escapes, so 'don\'t' does not
# terminate a string early. preauth.py:38 already imports from routes the
# same way.
from routes import STRING, _mask  # noqa: F401

SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
TEMPLATE_LITERAL = re.compile(r"`[^`]*`", re.S)
INTERPOLATION = re.compile(r"\$\{")

# Factories whose return value is a ref. `canDo` is this project's own --
# useStaffPermissions returns ComputedRef<boolean> from it -- and it is the
# one this check was written for. The Vue primitives are here because the
# defect is identical for them and there are more of them: 678 ref-family
# declarations against 471 computed ones when this was written.
FACTORIES = ("computed", "ref", "shallowRef", "shallowReadonly", "toRef", "canDo")

DECLARATION = re.compile(
    r"\bconst\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(%s)\s*[(<]"
    % "|".join(FACTORIES)
)
STORE_TO_REFS = re.compile(r"\bconst\s*\{([^}]*)\}\s*=\s*storeToRefs\s*\(")
NAME = re.compile(r"[A-Za-z_$][\w$]*")

# Every way of asking "is this thing true", each written so that a following
# `.value` disqualifies it. %s is the declared name.
TRUTH_TESTS = [
    (r"!\s*%s\b(?!\s*\.\s*value)", "negated"),
    (r"\bif\s*\(\s*%s\b(?!\s*\.\s*value)", "if condition"),
    (r"\bwhile\s*\(\s*%s\b(?!\s*\.\s*value)", "while condition"),
    (r"\b%s\s*\?(?!\?|\.)", "ternary condition"),
    (r"\b%s\b(?!\s*\.\s*value)\s*&&", "&& operand"),
    (r"\b%s\b(?!\s*\.\s*value)\s*\|\|", "|| operand"),
    (r"\bBoolean\s*\(\s*%s\b(?!\s*\.\s*value)", "Boolean()"),
]


def _blank(match: re.Match) -> str:
    """Overwrite with spaces, keeping length and newlines -- so every offset
    below still points at the character it pointed at in the file."""
    return "".join("\n" if ch == "\n" else " " for ch in match.group(0))


def script_surface(path: str, text: str) -> str:
    """The TypeScript of a file, at its original offsets.

    A .vue file is three languages, and only <script> is one this check can
    read: `v-if="canDoX"` in a template is CORRECT -- Vue unwraps refs there --
    so scanning the template would report the right code as wrong.

    Note the direction. tokens.py:47-48 does the mirror of this: it blanks the
    <script> bodies to be left with the template. Same technique, opposite
    polarity; the shared piece is P-69, not this file.
    """
    if path.endswith(".ts"):
        return text
    if not path.endswith(".vue"):
        return ""
    out = ["\n" if ch == "\n" else " " for ch in text]
    for m in SCRIPT.finditer(text):
        for i in range(m.start(1), m.end(1)):
            out[i] = text[i]
    return "".join(out)


def mask(src: str) -> tuple[str, int]:
    """-> (source with comments and string literals blanked, interpolations skipped)

    ORDER IS LOAD-BEARING, and the reason is the asymmetry of the two failures
    rather than which pattern would match first.

    Comments first: `const s = 'a // b'` loses the tail of that one line, so a
    finding on that line is missed -- local, and in the safe direction.

    Strings first would be far worse: an apostrophe in `// it's fine` opens a
    string that STRING does not stop at a newline, so it runs to the next
    apostrophe however many lines away and hides a real finding nowhere near
    the place that caused it.

    Template literals go before quoted strings for the same asymmetry: six
    backticked literals in frontend/src contain an apostrophe, and to STRING
    each of those is an opening quote. No quoted string in the tree contains a
    backtick, so this order costs nothing.
    """
    src = _mask(src)
    skipped = 0
    for m in TEMPLATE_LITERAL.finditer(src):
        skipped += len(INTERPOLATION.findall(m.group(0)))
    src = TEMPLATE_LITERAL.sub(_blank, src)
    src = STRING.sub(_blank, src)
    return src, skipped


def declared_refs(src: str) -> set[str]:
    names = {m.group(1) for m in DECLARATION.finditer(src)}
    for m in STORE_TO_REFS.finditer(src):
        for part in m.group(1).split(","):
            # `const { a, b: renamed } = storeToRefs(store)` binds `renamed`.
            candidate = part.split(":")[-1].strip()
            if NAME.fullmatch(candidate):
                names.add(candidate)
    return names


def _files(root: str) -> list[str]:
    src = os.path.join(root, "frontend", "src")
    out = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(filenames):
            if name.endswith((".vue", ".ts")):
                out.append(os.path.join(dirpath, name).replace("\\", "/"))
    return sorted(out)


def scan(root: str) -> tuple[list[tuple[str, int, str, str]], int, int, int]:
    """-> (findings, files, declarations, interpolations skipped)"""
    findings: list[tuple[str, int, str, str]] = []
    files = _files(root)
    if not files:
        raise ValueError("FAILED RUN: zero .vue/.ts files under frontend/src")

    declarations = 0
    skipped_total = 0
    for path in files:
        text = open(path, encoding="utf-8").read()
        surface = script_surface(path, text)
        if not surface.strip():
            continue
        surface, skipped = mask(surface)
        skipped_total += skipped
        names = declared_refs(surface)
        declarations += len(names)
        for name in sorted(names):
            for pattern, label in TRUTH_TESTS:
                for m in re.finditer(pattern % re.escape(name), surface):
                    line = surface.count("\n", 0, m.start()) + 1
                    findings.append((path, line, name, label))
    return sorted(findings), len(files), declarations, skipped_total


def run(root: str) -> tuple[bool, list[str]]:
    findings, files, declarations, skipped = scan(root)
    lines = [
        "files with a script surface scanned            : %d" % files,
        "refs and computeds declared in them            : %d" % declarations,
        "template-literal interpolations NOT examined   : %d (see the border "
        "in this check's docstring)" % skipped,
    ]
    problems = []

    if declarations == 0:
        problems.append(
            "not one ref or computed declaration found in the whole of "
            "frontend/src -- the derivation is broken, not the product")

    for path, line, name, label in findings:
        problems.append(
            "%s:%d  `%s` is %s without .value -- a ref is an object, so this "
            "test always passes" % (path, line, name, label))

    if not problems:
        lines.append("every one of them carries .value where it is tested for truth")
    return (not problems), (lines + problems)


def selftest(root: str) -> list[str]:
    """Six plants, in a throwaway copy of frontend/src -- never the real tree.

    Two prove the check catches the defect, and the first of them puts it back
    into the file it actually shipped in, so the .vue script extraction is
    exercised on a real SFC rather than on a .ts fixture. Two prove it does NOT
    fire where the code is right, which is the half that decides whether a green
    run means anything: a check that flagged `.value` and comments would be
    reverted within a week. The last proves the check fails rather than passes
    when it has nothing to read.
    """
    out = []
    ok, _ = run(root)
    assert ok, "the real tree does not pass its own ref-truthiness check"

    base = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(root, "frontend", "src"),
                        os.path.join(base, "frontend", "src"))
        ok, _ = run(base)
        assert ok, "the untouched copy already fails"

        # plant 1 -- the historical defect, back in the file it shipped in.
        victim = os.path.join(base, "frontend", "src", "views", "staff",
                              "StaffUsersView.vue")
        real = open(victim, encoding="utf-8").read()
        anchor = "if (!applicationId || !canDoKycApprove.value) {"
        assert anchor in real, "selftest anchor missing -- P-54's site moved or was renamed"
        open(victim, "w", encoding="utf-8").write(
            real.replace(anchor, "if (!applicationId || !canDoKycApprove) {", 1))
        ok, lines = run(base)
        assert not ok and any("canDoKycApprove" in ln and "negated" in ln for ln in lines), \
            "the exact defect H13 fixed was not caught when put back"
        out.append("  caught: P-54 put back into StaffUsersView.vue -- a real SFC, "
                   "through the <script> extraction")
        open(victim, "w", encoding="utf-8").write(real)
        ok, _ = run(base)
        assert ok, "restoring the victim file left the copy failing"

        planted = os.path.join(base, "frontend", "src", "zz_plant.ts")

        def plant(body: str) -> tuple[bool, list[str]]:
            open(planted, "w", encoding="utf-8").write(body)
            return run(base)

        ok, lines = plant(
            "const isOpen = ref(false)\n"
            "const label = computed(() => 1)\n"
            "function f() { return isOpen ? label : null }\n")
        assert not ok and any("isOpen" in ln and "ternary" in ln for ln in lines), \
            "a ref used as a ternary condition was not caught"
        out.append("  caught: a ref as a ternary condition")

        ok, lines = plant(
            "const isOpen = ref(false)\n"
            "function f() { if (!isOpen.value) { return } }\n"
            "watch(isOpen, () => {})\n"
            "const x = unref(isOpen)\n")
        assert ok, "correct .value code was reported as a defect: %s" % lines
        out.append("  quiet on: .value written correctly, watch(), unref()")

        ok, lines = plant(
            "const isOpen = ref(false)\n"
            "// if (!isOpen) -- this is a comment, not code\n"
            "const url = 'https://example.test/a' // if (!isOpen)\n"
            "const msg = `it's fine`\n"
            "function f() { return isOpen.value }\n")
        assert ok, "a comment or a string was read as code: %s" % lines
        out.append("  quiet on: the same defect written inside a comment, and an apostrophe "
                   "in a template literal")

        os.remove(planted)
        ok, _ = run(base)
        assert ok, "the plants left the copy broken"
    finally:
        shutil.rmtree(base, ignore_errors=True)

    # last plant -- nothing to read at all. A check that says PASS here is the
    # failure mode the runner's header is about.
    empty = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(empty, "frontend", "src"))
        open(os.path.join(empty, "frontend", "src", "empty.ts"), "w").write("\n")
        ok, lines = run(empty)
        assert not ok and any("derivation is broken" in ln for ln in lines), \
            "a tree with no declarations at all was reported as clean"
        out.append("  caught: a tree where no declaration is found -- fails, does not pass")
    finally:
        shutil.rmtree(empty, ignore_errors=True)

    findings, files, declarations, skipped = scan(root)
    out.append("  the real tree passes: %d declarations over %d files, %d interpolations "
               "not examined" % (declarations, files, skipped))
    return out
