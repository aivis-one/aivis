"""The shell chrome has ONE source, and the storefront is deliberately outside it.

WHY THIS EXISTS. Four shells -- AgentShell, CompanyShell, InvestorShell,
StaffShell -- each carried the same `@media (min-width: 820px)` block byte for
byte, plus the same `.shell` / `.shell__content` / `.shell__measure` rules and
the same two comments. A tier change had to be made in four places and would
one day have been made in three. It now lives once, in
`frontend/src/styles/shell.css`.

FOUR THINGS ARE EASY TO UNDO BY ACCIDENT, AND EACH IS ASSERTED HERE:

1. ONE SOURCE. Exactly one `@media (min-width: 820px)` block in the whole of
   frontend/src sets `--tab-bar-height`, and it is in shell.css.

2. THE TIER RULES ARE GATED ON `.shell--tabbed`, WHICH PublicShell DOES NOT
   CARRY. The storefront has no tab bar and no side nav. Whether it should get
   the tier system is an open product question; a plain `.shell` selector would
   answer it silently by handing it `--tab-bar-height: 0px`. Adding the class to
   PublicShell's root is how you say yes -- deliberately, not by widening a
   selector here.

3. THE TAB-BAR HIDE RULE KEEPS ITS SPECIFICITY. CTabBar sets `display: flex` on
   its own root from its own chunk, at (0,2,0). Written `.shell--tabbed
   .c-tabbar` the hide rule would ALSO be (0,2,0) -- a tie decided by which CSS
   chunk the browser loads second, which is stated in no stylesheet. Written
   `.shell.shell--tabbed .c-tabbar` it is (0,3,0) and the outcome is a property
   of the CSS instead of the bundler's output order.

4. StaffShell KEEPS ITS OWN `--maxw-wide` CAP. Staff screens cap content wider
   than the other four. Whether that asymmetry is deliberate is an open product
   question, so it stays visible in one place rather than being folded into a
   single value here.

CSideNav is NOT part of this. It has its own 820 and 1472 blocks plus a
reduced-motion block, and they are its own rules, not the shell tier. The check
asserts it still holds three and that the shell rules have not leaked into them.
"""
from __future__ import annotations

import os
import re

from lib.css import mask_comments, media_blocks, style_css

CABINET = ["AgentShell", "CompanyShell", "InvestorShell", "StaffShell"]


def _layout(root: str) -> str:
    return os.path.join(root, "frontend", "src", "components", "layout")


def _css_of(path: str) -> str:
    return mask_comments(style_css(path, open(path, encoding="utf-8").read()))


def run(root: str) -> tuple[bool, list[str]]:
    layout = _layout(root)
    shell_css = os.path.join(root, "frontend", "src", "styles", "shell.css")
    src = os.path.join(root, "frontend", "src")
    problems: list[str] = []
    notes: list[str] = []

    # 1 - one source for the tier block
    tier = []
    for dirpath, dirnames, names in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "node_modules"]
        for name in sorted(names):
            if not name.endswith((".vue", ".css")):
                continue
            path = os.path.join(dirpath, name)
            for condition, _whole, body in media_blocks(_css_of(path)):
                if "820px" in condition and "tab-bar-height" in body:
                    tier.append(path)
    if len(tier) != 1:
        problems.append("the 820 tier block must exist exactly ONCE in frontend/src; found %d: %s"
                        % (len(tier), [os.path.relpath(p, root) for p in tier]))
    elif os.path.abspath(tier[0]) != os.path.abspath(shell_css):
        problems.append("the tier block is in %s, not styles/shell.css"
                        % os.path.relpath(tier[0], root))
    else:
        notes.append("one tier block, in frontend/src/styles/shell.css")

    # the four cabinet shells own no media queries at all any more
    for name in CABINET:
        n = len(media_blocks(_css_of(os.path.join(layout, name + ".vue"))))
        if n:
            problems.append("%s still owns %d @media block(s) of its own" % (name, n))

    # 2 - the gate is the modifier class
    for name in CABINET:
        text = open(os.path.join(layout, name + ".vue"), encoding="utf-8").read()
        root_class = _root_class(text)
        if root_class is None:
            problems.append("%s: cannot read the root element's class attribute" % name)
        elif "shell--tabbed" not in root_class.split():
            problems.append("%s's root element does not carry shell--tabbed" % name)
    public = open(os.path.join(layout, "PublicShell.vue"), encoding="utf-8").read()
    public_root = _root_class(public)
    # read the ROOT ELEMENT's class attribute, not the file text: the file's own
    # comment explains why it does not carry the class, and a bare substring
    # search finds that comment and reports a failure that is not there.
    if public_root is None:
        problems.append("PublicShell: cannot read the root element's class attribute")
    elif "shell--tabbed" in public_root.split():
        problems.append("PublicShell's root carries shell--tabbed -- that is an open product "
                        "decision, not something a refactor should make")
    else:
        notes.append("PublicShell does not carry the tier gate")

    # 3 - the hide rule keeps (0,3,0)
    shell = mask_comments(open(shell_css, encoding="utf-8").read())
    if not re.search(r"\.shell\.shell--tabbed\s+\.c-tabbar", shell):
        problems.append("the tab-bar hide rule is no longer written "
                        "`.shell.shell--tabbed .c-tabbar`; the tie with CTabBar's own "
                        "display:flex comes back and the winner depends on chunk order")
    else:
        notes.append("the hide rule keeps its (0,3,0) form")

    # 4 - StaffShell keeps the wide cap, shell.css does not hard-code it
    staff = _css_of(os.path.join(layout, "StaffShell.vue"))
    if "--maxw-wide" not in staff:
        problems.append("StaffShell no longer caps at --maxw-wide")
    if "--maxw-wide" in shell:
        problems.append("styles/shell.css hard-codes --maxw-wide; the per-role difference "
                        "belongs in StaffShell where it is visible")

    # CSideNav is untouched
    sidenav = _css_of(os.path.join(layout, "CSideNav.vue"))
    blocks = media_blocks(sidenav)
    if len(blocks) != 3:
        problems.append("CSideNav should hold THREE @media blocks (820, 1472, reduced-motion), "
                        "found %d" % len(blocks))
    for condition, _whole, body in blocks:
        if "820px" in condition and "tab-bar-height" in body:
            problems.append("CSideNav's 820 block has absorbed the shell tier rules")

    return (not problems), (notes + problems)


def _root_class(vue_source: str) -> str | None:
    # THE REGION MATCH IS GREEDY ON PURPOSE. `<template>` with no attributes is
    # the SFC root; `</template>` is NOT unique -- 47 of the 101 .vue files here
    # hold more than one `<template`, and a slot template closes with the same
    # tag. A non-greedy `(.*?)` stops at the FIRST `</template>`, so it returns a
    # TRUNCATED region: it reports a smaller thing and never errors, which is how
    # a check comes to pass for the wrong reason.
    #
    # THIS READER WAS NOT ACTUALLY BITTEN, AND THE HONEST VERSION IS WORTH MORE
    # THAN THE ALARMING ONE. A single-root SFC puts its root element FIRST in the
    # template region -- in PublicShell.vue the root `<div class=` sits at offset
    # 3, with 238 characters of the truncated region still to spare -- and across
    # all 101 .vue files the two forms return the SAME root class. The old code
    # was safe by structure here, not by luck. It is changed because the next
    # reader of this region will look for something that is NOT first, and
    # because a region match should mean the region.
    #
    # The selftest below plants a slot template ABOVE the root div, which is the
    # shape that does reach the defect, and proves the two forms disagree there.
    m = re.search(r"<template>(.*)</template>", vue_source, re.S)
    if not m:
        return None
    c = re.search(r'<div\s+class="([^"]*)"', m.group(1))
    return c.group(1) if c else None


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

    plant("components/layout/PublicShell.vue", 'class="shell"',
          'class="shell shell--tabbed"', "the storefront given the tier gate")
    plant("components/layout/AgentShell.vue", 'class="shell shell--tabbed"',
          'class="shell"', "a cabinet shell losing the tier gate")
    plant("styles/shell.css", ".shell.shell--tabbed .c-tabbar",
          ".shell--tabbed .c-tabbar", "the hide rule dropped to (0,2,0)")
    plant("components/layout/StaffShell.vue", "max-width: var(--maxw-wide);",
          "max-width: var(--maxw);", "StaffShell's wide cap silently removed")
    plant("styles/shell.css", "@media (min-width: 820px) {\n  .shell--tabbed {",
          "@media (min-width: 900px) {\n  .shell--tabbed {", "the tier block moved off 820")

    # A SURVIVAL PLANT, not a break: a slot template ABOVE the root <div>. This is
    # legal Vue and changes nothing the check is about, so the check must still
    # PASS. It exists because the region match used to be non-greedy, and a
    # truncating region match fails SILENTLY -- it reports a smaller region and
    # no error. The plant asserts three things in order, so it can never rot into
    # a no-op: the text changed, the OLD form now gives a DIFFERENT answer from
    # the shipped one (proving the plant reaches the defect), and the check still
    # passes.
    pub_rel = "components/layout/PublicShell.vue"
    pub_path = os.path.join(base, "frontend", "src", pub_rel)
    original = open(pub_path, encoding="utf-8").read()
    anchor = '<div class="shell"'
    assert anchor in original, "selftest anchor missing for the slot-above-root plant"
    slotted = original.replace(anchor, '<template #decoy><span /></template>\n    ' + anchor, 1)
    assert slotted != original, "slot-above-root plant changed nothing"
    non_greedy = re.search(r"<template>(.*?)</template>", slotted, re.S)
    truncated = None
    if non_greedy:
        d = re.search(r'<div\s+class="([^"]*)"', non_greedy.group(1))
        truncated = d.group(1) if d else None
    assert truncated != _root_class(slotted), \
        "the slot-above-root plant does not separate the greedy and non-greedy forms"
    open(pub_path, "w", encoding="utf-8").write(slotted)
    survived, _ = run(base)
    open(pub_path, "w", encoding="utf-8").write(original)
    assert survived, ("a slot template above the root div broke the check -- the region "
                      "match is truncating again")
    restored, _ = run(base)
    assert restored, "the slot-above-root plant left the copy broken"
    out.append("  survives: a slot template above the root <div> (the truncating region match)")

    shutil.rmtree(base, ignore_errors=True)
    return out
