"""The screens a person meets BEFORE logging in are deliberately fixed-width,
and every one of them says so.

WHY THIS EXISTS. Twelve of the seventy-one named routes declare no `@media`
width condition anywhere in their closure -- their own component, every ancestor
shell, and all transitive local imports. That set was read once as "the pre-auth
funnel has no width behaviour at all", which is not the same statement:

    NO BREAKPOINT  is not  NO WIDTH BEHAVIOUR.

Measured 2026-08-25 in a headless browser at 320 / 360 / 390 / 820 / 1280 / 1920:
every one of the twelve caps its content with a design-system token
(`--maxw-form` 360px, `--maxw-form-wide` 400px, `--maxw-prose` 680px, or
`PublicShell`'s `--maxw` 1080px) and CENTRES it at every one of those widths.
Zero horizontal overflow, zero clipped boxes over 72 measurements. A centred
card is the correct shape for a login form, and a breakpoint would add nothing
to it -- so the right outcome was a recorded decision, not a repair.

WHAT THIS CHECK ACTUALLY GUARDS, and it is the silence rather than the layout:
the set is re-derived from the router on every run and compared against the
register below. A THIRTEENTH pre-auth screen with no width behaviour cannot be
added silently, and an entry that stops being true -- because someone gave that
route a breakpoint -- fails as a STALE entry rather than sitting there agreeing
with nothing. Each register line carries its reason, and a blank reason fails:
the failure this check was built against is a done-test that terminated with one
route unverdicted and PASSED.
"""
from __future__ import annotations

import os
import re

from lib.css import mask_comments, media_blocks, style_css

# The tree walker is imported rather than re-implemented: a route table is a
# TREE, and two checks with two walkers is how they come to disagree about how
# many routes exist.
from routes import _children, _join, _mask, _objects, _own_key  # noqa: F401

WIDTH_QUERY = re.compile(r"\(\s*(?:min|max)-width\s*:\s*(\d+)\s*px", re.I)

# name -> why it is deliberately fixed-width. Measured, not asserted; the
# reasons are the finding, and a blank one is a failure.
REGISTER = {
    "root": "a redirect record -- it renders LoadingView for an instant and lands on /login or a "
            "dashboard; there is no content to reflow.",
    "loading": "a centred logo and a spinner, 230px at every width. Nothing to lay out.",
    "referral-link": "a redirect record -- /r/<code> resolves and leaves. Nothing renders.",
    "not-found": "the code and one line of prose, capped at --maxw-prose and centred.",
    "login": "a centred auth card at --maxw-form (360px). A wider login form is a worse login form.",
    "register": "a centred auth card at --maxw-form (360px), same shape as login.",
    "verify": "a centred auth card at --maxw-form (360px); the per-digit code inputs are a fixed row.",
    "onboarding-role": "centred role cards at --maxw-form-wide (400px).",
    "onboarding-profile": "a centred auth card at --maxw-form (360px).",
    "kyc-verification": "a centred auth card at --maxw-form (360px) -- one heading, two lines of prose and at most two buttons. H10 replaced onboarding-kyc, which was the same shape.",
    "onboarding-docs": "a centred document list at --maxw-form-wide (400px); measured with eight "
                       "rows, centred and un-clipped from 390 to 1920.",
    "password-reset-request": "a centred auth card at --maxw-form (360px) -- the same shape as login "
                              "and register, which it sits between in the funnel. Measured: "
                              ".auth-form caps at var(--maxw-form) and .auth-content centres it with "
                              "align-items:center, identical to LoginView's registered treatment.",
    "password-reset-confirm": "a centred auth card at --maxw-form (360px), same treatment as its "
                              "request sibling above -- .auth-form capped at var(--maxw-form), "
                              "centred by .auth-content's align-items:center. The new-password pair "
                              "is a plain stacked field group, nothing that reflows.",
    "public-attachment-landing": "it renders inside PublicShell, which caps content at --maxw "
                                 "(1080px) and centres it. PublicShell carries no tier gate ON "
                                 "PURPOSE -- whether the storefront joins the tier system is the "
                                 "owner's open call, B-3.1.",
}


def _own_imports(src: str, start: int, end: int) -> list[str]:
    """`import('...')` specs at this object's OWN depth, never a child's."""
    out, depth, i = [], 0, start
    pattern = re.compile(r"import\(\s*'([^']+)'\s*\)")
    while i <= end:
        c = src[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif depth == 1:
            m = pattern.match(src, i)
            if m:
                out.append(m.group(1))
                i = m.end()
                continue
        i += 1
    return out


def _walk_specs(src, start, end, parent_path, inherited, out):
    for obj_start, obj_end in _objects(src, start, end):
        path = _own_key(src, obj_start, obj_end, "path")
        if path is None:
            continue
        full = _join(parent_path, path)
        specs = inherited + _own_imports(src, obj_start, obj_end)
        name = _own_key(src, obj_start, obj_end, "name")
        if name:
            out[name] = {"path": full, "specs": specs}
        kids = _children(src, obj_start, obj_end)
        if kids:
            _walk_specs(src, kids[0], kids[1], full, specs, out)


def _route_specs(root: str) -> dict[str, dict]:
    path = os.path.join(root, "frontend", "src", "router", "index.ts")
    src = _mask(open(path, encoding="utf-8").read())
    m = re.search(r"routes\s*:\s*\[|const\s+routes[^=]*=\s*\[", src)
    if not m:
        raise ValueError("cannot find the routes array in router/index.ts")
    open_at = src.index("[", m.start())
    depth, i = 0, open_at
    while i < len(src):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    out: dict[str, dict] = {}
    _walk_specs(src, open_at + 1, i, "", [], out)
    return out


def _index(src_dir: str) -> dict[str, str]:
    files = {}
    for dirpath, dirnames, names in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for n in names:
            if n.endswith((".vue", ".ts", ".css")):
                p = os.path.join(dirpath, n).replace("\\", "/")
                files[p] = open(p, encoding="utf-8").read()
    return files


def _resolve(spec: str, frm: str, src_dir: str, files: dict[str, str]) -> str | None:
    if spec.startswith("@/"):
        cand = (src_dir + "/" + spec[2:]).replace("\\", "/")
    elif spec.startswith("."):
        cand = os.path.normpath(os.path.join(os.path.dirname(frm), spec)).replace("\\", "/")
    else:
        return None
    for ext in ("", ".ts", ".vue", ".css", "/index.ts"):
        if cand + ext in files:
            return cand + ext
    return None


SPEC = re.compile(r"""(?:from|import\()\s*['"]([^'"]+)['"]""")


def _declares_width(path: str, text: str) -> bool:
    css = mask_comments(style_css(path, text))
    if not css:
        return False
    return any(WIDTH_QUERY.search(cond) for cond, _w, _b in media_blocks(css))


def derive(root: str) -> tuple[set[str], set[str], int]:
    """-> (no_width_routes, with_width_routes, files_declaring_a_width)"""
    src_dir = os.path.join(root, "frontend", "src").replace("\\", "/")
    router = src_dir + "/router/index.ts"
    files = _index(src_dir)
    if not files:
        raise ValueError("FAILED RUN: zero source files under frontend/src")
    carriers = {p for p, t in files.items() if _declares_width(p, t)}

    cache: dict[str, set[str]] = {}

    def closure(start: str) -> set[str]:
        if start in cache:
            return cache[start]
        seen, stack = set(), [start]
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            for s in SPEC.findall(files[p]):
                r = _resolve(s, p, src_dir, files)
                if r and r not in seen:
                    stack.append(r)
        cache[start] = seen
        return seen

    nowidth, withwidth = set(), set()
    for name, rec in _route_specs(root).items():
        reach: set[str] = set()
        for spec in rec["specs"]:
            p = _resolve(spec, router, src_dir, files)
            if p:
                reach |= closure(p)
        (withwidth if reach & carriers else nowidth).add(name)
    return nowidth, withwidth, len(carriers)


def run(root: str) -> tuple[bool, list[str]]:
    nowidth, withwidth, carriers = derive(root)
    lines, problems = [], []
    total = len(nowidth) + len(withwidth)
    lines.append("routes with a width breakpoint in their closure : %d of %d" % (len(withwidth), total))
    lines.append("routes with NONE -- must each carry a reason    : %d" % len(nowidth))
    lines.append("files in frontend/src declaring a width query   : %d" % carriers)

    if not withwidth:
        problems.append("no route carries a width query at all -- the derivation is broken, "
                        "not the product")

    missing = sorted(nowidth - set(REGISTER))
    stale = sorted(set(REGISTER) - nowidth)
    blank = sorted(k for k, v in REGISTER.items() if not v.strip())
    if missing:
        problems.append("no declared reason for: %s -- either give it a tier rule or register "
                        "WHY it is deliberately fixed-width" % ", ".join(missing))
    if stale:
        problems.append("registered as fixed-width but now carries a width query: %s -- the entry "
                        "is stale, remove it" % ", ".join(stale))
    if blank:
        problems.append("registered with an EMPTY reason: %s -- a blank verdict is the failure "
                        "this check exists to stop" % ", ".join(blank))
    if not problems:
        lines.append("all %d are registered, every reason non-empty" % len(nowidth))
    return (not problems), (lines + problems)


def selftest(root: str) -> list[str]:
    """Four plants. Three move the REGISTER, which is this check's own input;
    the fourth moves the ROUTER, because a register that agrees with a broken
    derivation would pass all three."""
    import shutil
    import tempfile

    out = []
    ok, _ = run(root)
    assert ok, "the real tree does not pass its own pre-auth check"

    real = dict(REGISTER)
    try:
        victim = sorted(real)[0]
        REGISTER.pop(victim)
        assert REGISTER != real, "plant 1 changed nothing"
        broke, lines = run(root)
        assert not broke and any("no declared reason for" in ln for ln in lines), \
            "an unregistered fixed-width route was not caught"
        out.append("  caught: a pre-auth route with no declared reason")

        REGISTER.clear()
        REGISTER.update(real)
        REGISTER["zz-not-a-route"] = "a reason for a route that does not exist"
        broke, lines = run(root)
        assert not broke and any("stale" in ln for ln in lines), "a stale entry was not caught"
        out.append("  caught: a stale entry for a route that is not in the set")

        REGISTER.clear()
        REGISTER.update(real)
        REGISTER[sorted(real)[0]] = "   "
        broke, lines = run(root)
        assert not broke and any("EMPTY reason" in ln for ln in lines), "a blank reason was not caught"
        out.append("  caught: a registered route whose reason is blank")
    finally:
        REGISTER.clear()
        REGISTER.update(real)

    restored, _ = run(root)
    assert restored, "the selftest left the register broken"

    # plant 4 -- the DERIVATION, in a throwaway copy of the tree
    base = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(root, "frontend", "src"),
                        os.path.join(base, "frontend", "src"))
        ok, _ = run(base)
        assert ok, "the untouched copy already fails"
        router = os.path.join(base, "frontend", "src", "router", "index.ts")
        text = open(router, encoding="utf-8").read()
        anchor = "    path: '/login',"
        assert anchor in text, "selftest anchor missing for the new-route plant"
        planted = text.replace(
            anchor,
            "    path: '/zz-plant',\n"
            "    name: 'zz-plant',\n"
            "    component: () => import('@/views/auth/LoadingView.vue'),\n"
            "  },\n"
            "  {\n" + anchor, 1)
        assert planted != text, "the new-route plant changed nothing"
        open(router, "w", encoding="utf-8").write(planted)
        nowidth, _w, _c = derive(base)
        assert "zz-plant" in nowidth, \
            "the plant did not reach the derivation -- it is a no-op, not a test"
        broke, lines = run(base)
        assert not broke and any("zz-plant" in ln for ln in lines), \
            "a NEW pre-auth route with no width behaviour was not caught"
        out.append("  caught: a new route with no width behaviour, added to the router")
        open(router, "w", encoding="utf-8").write(text)
        again, _ = run(base)
        assert again, "the new-route plant left the copy broken"
    finally:
        shutil.rmtree(base, ignore_errors=True)

    out.append("  the real tree passes: %d registered, all reasons non-empty" % len(REGISTER))
    return out
