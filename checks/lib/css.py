"""Small CSS helpers shared by the checks.

Deliberately hand-rolled and dependency-free: these run in CI and in the gate,
and pulling a CSS parser in for four functions would be a worse trade.

Two things here are easy to get wrong and are therefore centralised:

1. COMMENTS ARE MASKED, NEVER STRIPPED. Replacing a comment with nothing shifts
   every line number below it, so any file:line a check reports would be wrong.
   `mask_comments` overwrites the comment with spaces and keeps its newlines, so
   offsets and line numbers stay exact.

2. A .vue FILE IS THREE LANGUAGES. `<template>` is HTML, `<script>` is
   TypeScript, `<style>` is CSS, and each needs a different comment rule. A
   single masker run over a whole SFC lets a `/*` inside a `//` comment swallow
   the template. `style_css` returns only the parts that are actually CSS.
"""
from __future__ import annotations

import hashlib
import re

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
_AT_MEDIA = re.compile(r"@media\b([^{]*)\{")


def mask_comments(text: str) -> str:
    """Blank out /* ... */ while preserving length and newlines."""
    def repl(m: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))
    return _CSS_COMMENT.sub(repl, text)


def style_css(path: str, text: str) -> str:
    """The CSS surface of a file: <style> blocks for .vue, the whole file for
    .css, nothing for anything else."""
    if path.endswith(".vue"):
        return "\n".join(m.group(1) for m in _STYLE.finditer(text))
    if path.endswith(".css"):
        return text
    return ""


def style_langs(text: str) -> list[str]:
    """`lang=` attributes on <style> blocks. The checks assume plain CSS; if a
    preprocessor ever lands, they should fail loudly rather than mis-read it."""
    return re.findall(r"<style\b[^>]*\blang=\"([^\"]+)\"", text, re.I)


def media_blocks(css: str) -> list[tuple[str, str, str]]:
    """-> [(condition, whole_block, body)] for each top-level @media.

    `whole_block` runs from `@media` through the matching closing brace and is
    what `block_id` hashes; `body` is the inside only.
    """
    out = []
    for m in _AT_MEDIA.finditer(css):
        depth, i = 0, m.end() - 1
        while i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            raise ValueError("unbalanced @media block")
        out.append((" ".join(m.group(1).split()), css[m.start():i + 1], css[m.end():i]))
    return out


def block_id(whole_block: str) -> tuple[str, int, int]:
    """Identity of a CSS block: (md5, chars_without_whitespace, chars_verbatim).

    Whitespace is removed so re-indenting a block does not change its identity;
    comments are KEPT, because changing what a rule says about itself is a
    change worth noticing. Two blocks are "the same block" exactly when this
    md5 matches -- which is the definition every check here uses, so two checks
    cannot quietly disagree about it.
    """
    squeezed = "".join(whole_block.split())
    return hashlib.md5(squeezed.encode("utf-8")).hexdigest(), len(squeezed), len(whole_block)


def rules(body: str) -> list[tuple[str, dict[str, str]]]:
    """-> [(selector, {property: value})] for a flat rule body.

    The property pattern is bounded at BOTH ends. Unbounded, `color:` also
    matches the tail of `border-color:`; bounded only by whitespace, a
    declaration written straight after `{` is missed. Later declarations
    overwrite earlier ones, which is what the cascade does inside one rule.
    """
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
        props: dict[str, str] = {}
        for d in re.finditer(r'(?:^|[;{"\s])(--?[-a-zA-Z]+|[-a-zA-Z]+)\s*:\s*([^;}]+)', m.group(2)):
            props[d.group(1)] = " ".join(d.group(2).split())
        out.append((" ".join(m.group(1).split()), props))
    return out
