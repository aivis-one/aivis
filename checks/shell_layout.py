"""The frame has ONE source, and the storefront is deliberately outside its menu.

WHY THIS EXISTS. Four shells -- AgentShell, CompanyShell, InvestorShell,
StaffShell -- each carried the same `@media (min-width: 880px)` block byte for
byte, plus the same `.shell` / `.shell__content` / `.shell__measure` rules and
the same two comments. A tier change had to be made in four places and would
one day have been made in three. The frame is now ONE component, `AppShell`,
drawn by the design system's own shell (K25: `.ds-shell`, `.ds-header`,
`.ds-nav`) -- the system alone decides how it lies at each width.

FOUR THINGS ARE EASY TO UNDO BY ACCIDENT, AND EACH IS ASSERTED HERE:

1. ONE SOURCE. The frame's tiers live in the design system's own stylesheet
   (the copy under styles/ds/) and nowhere else: no `@media (min-width: 880px)`
   block in the rest of frontend/src touches the frame (`.ds-shell`, `.ds-nav`,
   `.ds-header` or a tab-bar height). The cabinet's layout components own no
   media query at all, and no second shell or menu component exists beside
   AppShell and AppNav.

2. THE STOREFRONT HAS NO MENU, AND AppShell SAYS SO IN ONE PLACE. A route with
   no `meta.shell` gets the nav-less variant (`ds-shell--navless`) and AppNav is
   not rendered for it. Whether the storefront should get the menu is an open
   product question; a refactor must not answer it silently.

3. THE ROLES COME FROM THE ROUTE, NOT FROM FIVE FILES. AppShell reads the tabs
   from `tabsFor(route.meta.shell)`; the old wrappers do not come back.

4. STAFF KEEPS ITS OWN, WIDER, MEASURE. Staff screens are tables and lists;
   AppShell sets `data-measure="wide"` for the staff shell and for no other, and
   styles/variables.css does not hard-code the wide cap.
"""
from __future__ import annotations

import os
import re

from lib.css import mask_comments, media_blocks, style_css

OLD_WRAPPERS = ["AgentShell", "CompanyShell", "InvestorShell", "StaffShell", "PublicShell",
                "CSideNav", "CTabBar", "CHeader"]


def _layout(root: str) -> str:
    return os.path.join(root, "frontend", "src", "components", "layout")


def _css_of(path: str) -> str:
    return mask_comments(style_css(path, open(path, encoding="utf-8").read()))


def _template(vue_source: str) -> str | None:
    # THE REGION MATCH IS GREEDY ON PURPOSE. `<template>` with no attributes is
    # the SFC root; `</template>` is NOT unique -- a slot template closes with the
    # same tag. A non-greedy `(.*?)` stops at the FIRST `</template>`, so it
    # returns a TRUNCATED region: it reports a smaller thing and never errors,
    # which is how a check comes to pass for the wrong reason. The selftest below
    # plants a slot template ABOVE the root and proves the check survives it.
    m = re.search(r"<template>(.*)</template>", vue_source, re.S)
    return m.group(1) if m else None


def run(root: str) -> tuple[bool, list[str]]:
    layout = _layout(root)
    variables_css = os.path.join(root, "frontend", "src", "styles", "variables.css")
    src = os.path.join(root, "frontend", "src")
    problems: list[str] = []
    notes: list[str] = []

    # 1 - one source for the frame's tiers: the design system's copy under styles/ds
    ds_dir = os.path.join(src, "styles", "ds")
    tier = []
    for dirpath, dirnames, names in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"
                       and os.path.abspath(os.path.join(dirpath, d)) != os.path.abspath(ds_dir)]
        for name in sorted(names):
            if not name.endswith((".vue", ".css")):
                continue
            path = os.path.join(dirpath, name)
            for condition, _whole, body in media_blocks(_css_of(path)):
                if "880px" in condition and re.search(r"\.ds-(shell|nav|header)(?:__|\b)|tab-bar-height", body):
                    tier.append(path)
    if tier:
        problems.append("the frame's 880 tier belongs to the design system alone; a block in "
                        "frontend/src outside styles/ds touches it: %s"
                        % [os.path.relpath(p, root) for p in tier])
    else:
        notes.append("the frame's tiers are the design system's alone (no 880 frame block outside styles/ds)")

    # the layout components own no media query at all, and the old wrappers are gone
    for name in sorted(os.listdir(layout)):
        if not name.endswith(".vue"):
            continue
        n = len(media_blocks(_css_of(os.path.join(layout, name))))
        if n:
            problems.append("%s owns %d @media block(s) of its own" % (name, n))
    for name in OLD_WRAPPERS:
        if os.path.exists(os.path.join(layout, name + ".vue")):
            problems.append("%s.vue is back: the frame is AppShell and AppNav alone" % name)
    menus = [n for n in sorted(os.listdir(layout)) if n.endswith(".vue")
             and 'class="ds-nav"' in open(os.path.join(layout, n), encoding="utf-8").read()]
    if menus != ["AppNav.vue"]:
        problems.append("exactly one component may draw nav.ds-nav (AppNav.vue); found %s" % menus)
    else:
        notes.append("one menu component, AppNav.vue")

    # 2 and 3 - AppShell: the grid, the nav-less variant, the roles from the route
    shell_path = os.path.join(layout, "AppShell.vue")
    shell_src = open(shell_path, encoding="utf-8").read() if os.path.exists(shell_path) else ""
    tpl = _template(shell_src)
    if tpl is None:
        problems.append("AppShell.vue: cannot read the template")
    else:
        if not re.search(r'<div\s+class="ds-shell"', tpl):
            problems.append("AppShell's root element is not the system's .ds-shell")
        if not re.search(r"'ds-shell--navless'\s*:\s*!tabs", tpl):
            problems.append("AppShell no longer gives a route with no menu the nav-less variant "
                            "(`'ds-shell--navless': !tabs`) -- that is an open product decision, "
                            "not something a refactor should make")
        if not re.search(r"<AppNav\s+v-if=\"tabs\"", tpl):
            problems.append("AppShell draws the menu without the `v-if=\"tabs\"` gate")
        if not re.search(r"route\.meta\.shell\s*===\s*'staff'\s*\?\s*'wide'", tpl):
            problems.append("AppShell no longer sets data-measure=\"wide\" for the staff shell only")
    if not re.search(r"tabsFor\(route\.meta\.shell\)", shell_src):
        problems.append("AppShell no longer reads its tabs from tabsFor(route.meta.shell)")
    if not problems:
        notes.append("AppShell: .ds-shell, nav-less without tabs, tabs from the route, staff wide")

    # 4 - variables.css does not hard-code the wide cap
    if "--maxw-wide" in mask_comments(open(variables_css, encoding="utf-8").read()):
        problems.append("styles/variables.css hard-codes --maxw-wide; the per-role difference "
                        "belongs in AppShell where it is visible")

    return (not problems), (notes + problems)


def selftest(root: str) -> list[str]:
    """Copy frontend/src, break it five different ways and prove each break is
    caught, then plant one thing that must NOT break it and prove that too.
    The copy is thrown away; the real tree is never touched."""
    import shutil
    import tempfile

    out = []
    base = tempfile.mkdtemp()
    shutil.copytree(os.path.join(root, "frontend", "src"),
                    os.path.join(base, "frontend", "src"))
    ok, _ = run(base)
    assert ok, "the untouched copy already fails"

    def plant(rel, old, new, label):
        path = os.path.join(base, "frontend", "src", rel)
        text = open(path, encoding="utf-8").read()
        assert old in text, "selftest anchor missing for %r" % label
        changed = text.replace(old, new, 1)
        assert changed != text, "selftest plant %r changed nothing" % label
        open(path, "w", encoding="utf-8").write(changed)
        broke, _ = run(base)
        assert not broke, "selftest: %s was not caught" % label
        open(path, "w", encoding="utf-8").write(text)
        restored, _ = run(base)
        assert restored, "selftest: %s left the copy broken" % label
        out.append("  caught: %s" % label)

    plant("components/layout/AppShell.vue", "'ds-shell--navless': !tabs",
          "'ds-shell--navless': false", "the storefront given the menu")
    plant("components/layout/AppShell.vue", '<AppNav v-if="tabs"',
          "<AppNav", "the menu drawn without its gate")
    plant("components/layout/AppShell.vue", "route.meta.shell === 'staff' ? 'wide'",
          "route.meta.shell === 'staff' ? undefined", "staff's wide measure silently removed")
    plant("styles/global.css", "button.ds-navtile {",
          "@media (min-width: 880px) {\n  .ds-shell { --_bar: 0; }\n}\n\nbutton.ds-navtile {",
          "a frame tier block written outside the design system")
    plant("components/layout/AppNav.vue", "</template>",
          "</template>\n\n<style scoped>\n@media (min-width: 880px) {\n  .ds-nav { --tab-bar-height: 0; }\n}\n</style>",
          "a second 880 tier block in the menu")

    # A SURVIVAL PLANT, not a break: a slot template ABOVE the root <div>. This is
    # legal Vue and changes nothing the check is about, so the check must still
    # PASS. It exists because the region match used to be non-greedy, and a
    # truncating region match fails SILENTLY -- it reports a smaller region and
    # no error. The plant asserts three things in order, so it can never rot into
    # a no-op: the text changed, the OLD form now gives a DIFFERENT answer from
    # the shipped one (proving the plant reaches the defect), and the check still
    # passes.
    shell_rel = "components/layout/AppShell.vue"
    shell_path = os.path.join(base, "frontend", "src", shell_rel)
    original = open(shell_path, encoding="utf-8").read()
    anchor = '<div class="ds-shell"'
    assert anchor in original, "selftest anchor missing for the slot-above-root plant"
    slotted = original.replace(anchor, '<template #decoy><span /></template>\n    ' + anchor, 1)
    assert slotted != original, "slot-above-root plant changed nothing"
    non_greedy = re.search(r"<template>(.*?)</template>", slotted, re.S)
    assert (non_greedy.group(1) if non_greedy else None) != _template(slotted), \
        "the slot-above-root plant does not separate the greedy and non-greedy forms"
    open(shell_path, "w", encoding="utf-8").write(slotted)
    survived, _ = run(base)
    open(shell_path, "w", encoding="utf-8").write(original)
    assert survived, ("a slot template above the root div broke the check -- the region "
                      "match is truncating again")
    restored, _ = run(base)
    assert restored, "the slot-above-root plant left the copy broken"
    out.append("  survives: a slot template above the root <div> (the truncating region match)")

    shutil.rmtree(base, ignore_errors=True)
    return out
