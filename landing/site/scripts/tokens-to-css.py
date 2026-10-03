#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/tokens-to-css.py

Compile a DTCG 2025.10 tokens file into CSS custom properties under :root,
flattened with hyphens and prefixed --ls-* (Invariant 5).

  color.primary        -> --ls-color-primary
  spacing.lg           -> --ls-sp-lg   (spacing aliased to 'sp')
  font.size-md         -> --ls-font-size-md
  font.family-base     -> --ls-font-family-base
  radius.lg            -> --ls-radius-lg
  container.max        -> --ls-container-max

Robustness (v9 / findings C2-C5): every `$value` is shape-checked before use.
No input can crash this script -- unsupported shapes and unsafe values are
dropped with a `WARN:` line on stderr naming the offending token path, never
emitted, never fatal (unless --strict is given -- see below).

Accepted $type forms:
  color       - dict {colorSpace, components, alpha}; hex string "#RGB",
                "#RRGGBB", "#RRGGBBAA"; CSS function string rgb()/rgba()/
                hsl()/hsla()/oklch()/... (passed through after the safety
                check below).
  dimension   - dict {value, unit}; plain string "16px" / "1.5rem" / "0".
  fontFamily  - a single string or a list of strings. Every family name is
                CSS-string-quoted, with internal `"` and `\\` escaped.
  number      - a number, or a numeric string.
  string      - any safe text.
  fontWeight  - a number or a keyword string ("bold", "400", ...).
  duration    - dict {value, unit}; plain string "200ms".
  cubicBezier - a 4-number array -> cubic-bezier(a, b, c, d).

DTCG aliases: a `$value` of the form "{group.key}" is resolved against the
same document, up to 8 hops, with cycle detection. An unresolvable alias is
WARNed and dropped. An unknown/missing `$type` is WARNed and dropped.

Token-value safety (finding C2 -- CRITICAL): before any value reaches the
generated <style> block, its text is checked for `<`, `>`, `;`, `{`, `}`,
`@`, `/*`, `*/`, `url(`, and newlines. Any match rejects the whole value
(WARN, dropped) -- this is what stops a crafted `font.family-base` value
from closing the <style> block and injecting a <script>.

Dark mode (Q2 / finding D8): if the document has a top-level `dark` group
mirroring `color` keys, three blocks are emitted -- :root (light values,
including --ls-color-*), an `@media (prefers-color-scheme: dark)` block
remapping --ls-color-* to the dark group's values (guarded so an explicit
`data-ls-theme="light"` wins), and a `:root[data-ls-theme="dark"]` block
with the same remap so an explicit toggle wins in both directions. The
`dark` group itself is NEVER emitted as its own `--ls-dark-*` variables --
that would create dead variables (finding D8's class of defect).

Usage:
  python3 tokens-to-css.py <tokens.tokens.json> [out.css] [--strict]

  --strict   turn any WARN into a nonzero exit (used by scripts/gate.py).
"""
import json
import re
import sys
from pathlib import Path

ALIAS = {"spacing": "sp"}

ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")
HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")
COLOR_FUNC_RE = re.compile(
    r"^(rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color|color-mix)\(.*\)$",
    re.IGNORECASE,
)
DIM_RE = re.compile(r"^-?\d+(?:\.\d+)?[a-zA-Z%]*$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# Section 4.3: characters/sequences that must never reach the inline <style>
# block, regardless of $type. ';' here means the literal character appearing
# INSIDE a token value -- the terminator this script itself appends after
# every declaration is not part of the value's text and is unaffected.
FORBIDDEN = ["<", ">", ";", "{", "}", "@", "/*", "*/", "url(", "\n", "\r"]

_warn_count = 0


def _reset_warnings():
    global _warn_count
    _warn_count = 0


def _warn(path, reason):
    global _warn_count
    _warn_count += 1
    label = path if path else "(root)"
    print(f"WARN: rejected token '{label}': {reason}", file=sys.stderr)


def is_safe_text(s):
    return not any(bad in s for bad in FORBIDDEN)


def safety_reason(s):
    for bad in FORBIDDEN:
        if bad in s:
            return f"value contains forbidden sequence {bad!r}"
    return "value is unsafe"


class _AliasFail(Exception):
    pass


def lookup_path(doc, dotted):
    """Resolve a dotted DTCG path ('color.text') against `doc`. None if absent."""
    node = doc
    for seg in dotted.split("."):
        if not isinstance(node, dict) or seg not in node:
            return None
        node = node[seg]
    return node


def _is_token_node(node):
    return isinstance(node, dict) and ("$type" in node or "$value" in node)


def resolve_alias_chain(dtcg_path, node, doc, warn):
    """Follow a `{group.key}` alias chain starting at token `node` (found at
    `dtcg_path`), up to 8 hops, with cycle detection. Returns (type, value)
    of the final, non-alias token. Raises _AliasFail (after warning) if the
    chain is unresolvable, cyclic, or too long."""
    chain = [dtcg_path]
    cur_type = node.get("$type")
    cur_value = node.get("$value")
    hops = 0
    while isinstance(cur_value, str):
        m = ALIAS_RE.match(cur_value.strip())
        if not m:
            break
        if hops >= 8:
            warn(dtcg_path, "alias chain exceeds the 8-hop limit")
            raise _AliasFail()
        target_path = m.group(1).strip()
        if target_path in chain:
            warn(dtcg_path, "alias cycle detected (" + " -> ".join(chain + [target_path]) + ")")
            raise _AliasFail()
        chain.append(target_path)
        hops += 1
        target_node = lookup_path(doc, target_path)
        if not _is_token_node(target_node):
            warn(dtcg_path, f"alias '{{{target_path}}}' does not resolve to a token")
            raise _AliasFail()
        if cur_type is None:
            cur_type = target_node.get("$type")
        cur_value = target_node.get("$value")
    return cur_type, cur_value


def get_token(doc, dotted_path, warn=None):
    """Public helper (used by contrast-check.py): resolve the token at
    `dotted_path`, following aliases. Returns (type, value) or (None, None)
    if the path is absent, not a token, or the alias chain is unresolvable.
    Never raises."""
    if warn is None:
        warn = lambda *_a: None
    node = lookup_path(doc, dotted_path)
    if not _is_token_node(node):
        return None, None
    try:
        return resolve_alias_chain(dotted_path, node, doc, warn)
    except _AliasFail:
        return None, None
    except Exception as e:  # pragma: no cover -- absolute crash guard
        warn(dotted_path, f"unexpected error resolving alias: {e}")
        return None, None


def rgb(components):
    r, g, b = (int(round(float(c) * 255)) for c in components[:3])
    if len(components) >= 4 and components[3] != 1:
        return f"rgba({r}, {g}, {b}, {components[3]})"
    return f"rgb({r}, {g}, {b})"


# ---------- per-$type renderers: (value, dtcg_path, warn) -> css text | None ----------

def render_color(value, path, warn):
    if isinstance(value, dict):
        comps = value.get("components")
        if not isinstance(comps, (list, tuple)) or len(comps) < 3:
            warn(path, "color dict missing a usable 'components' array (need >=3 channels)")
            return None
        try:
            return rgb(list(comps))
        except Exception:
            warn(path, "color dict 'components' are not valid numbers")
            return None
    if isinstance(value, str):
        s = value.strip()
        if not is_safe_text(s):
            warn(path, safety_reason(s))
            return None
        if HEX_RE.match(s):
            return s
        if COLOR_FUNC_RE.match(s):
            return s
        warn(path, f"unrecognized color value '{s}' (expected hex or a CSS colour function)")
        return None
    warn(path, f"unsupported color value type: {type(value).__name__}")
    return None


def render_dimension(value, path, warn):
    if isinstance(value, dict):
        if "value" not in value or "unit" not in value:
            warn(path, "dimension dict missing 'value'/'unit'")
            return None
        text = f"{value['value']}{value['unit']}"
        if not is_safe_text(text):
            warn(path, safety_reason(text))
            return None
        return text
    if isinstance(value, str):
        s = value.strip()
        if not is_safe_text(s):
            warn(path, safety_reason(s))
            return None
        if s == "0" or DIM_RE.match(s):
            return s
        warn(path, f"unrecognized dimension value '{s}'")
        return None
    warn(path, f"unsupported dimension value type: {type(value).__name__}")
    return None


def render_font_family(value, path, warn):
    items = value if isinstance(value, list) else [value]
    out_names = []
    for item in items:
        if not isinstance(item, str):
            warn(path, f"fontFamily entry is not a string: {item!r}")
            return None
        if not is_safe_text(item):
            warn(path, safety_reason(item))
            return None
        escaped = item.replace("\\", "\\\\").replace('"', '\\"')
        out_names.append(f'"{escaped}"')
    if not out_names:
        warn(path, "fontFamily has no entries")
        return None
    return ", ".join(out_names)


def render_number(value, path, warn):
    if isinstance(value, bool):
        warn(path, "boolean is not a valid number")
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        s = value.strip()
        if is_safe_text(s) and NUM_RE.match(s):
            return s
        warn(path, f"unrecognized number value '{value}'")
        return None
    warn(path, f"unsupported number value type: {type(value).__name__}")
    return None


def render_string(value, path, warn):
    if not isinstance(value, str):
        warn(path, f"string token value is not text: {type(value).__name__}")
        return None
    if not is_safe_text(value):
        warn(path, safety_reason(value))
        return None
    return value


def render_font_weight(value, path, warn):
    if isinstance(value, bool):
        warn(path, "boolean is not a valid fontWeight")
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        s = value.strip()
        if s and is_safe_text(s):
            return s
        warn(path, f"unrecognized fontWeight value '{value}'")
        return None
    warn(path, f"unsupported fontWeight value type: {type(value).__name__}")
    return None


def render_duration(value, path, warn):
    if isinstance(value, dict):
        if "value" not in value or "unit" not in value:
            warn(path, "duration dict missing 'value'/'unit'")
            return None
        text = f"{value['value']}{value['unit']}"
        if not is_safe_text(text):
            warn(path, safety_reason(text))
            return None
        return text
    if isinstance(value, str):
        s = value.strip()
        if is_safe_text(s) and DIM_RE.match(s):
            return s
        warn(path, f"unrecognized duration value '{value}'")
        return None
    warn(path, f"unsupported duration value type: {type(value).__name__}")
    return None


def render_cubic_bezier(value, path, warn):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        warn(path, "cubicBezier must be a 4-number array")
        return None
    try:
        nums = [float(x) for x in value]
    except Exception:
        warn(path, "cubicBezier entries must be numbers")
        return None
    return "cubic-bezier(" + ", ".join(str(n) for n in nums) + ")"


TYPE_RENDERERS = {
    "color": render_color,
    "dimension": render_dimension,
    "fontFamily": render_font_family,
    "number": render_number,
    "string": render_string,
    "fontWeight": render_font_weight,
    "duration": render_duration,
    "cubicBezier": render_cubic_bezier,
}


def resolve_and_render(dtcg_path, node, doc, warn):
    """Resolve aliases then render to CSS text, or None (already warned).
    Guaranteed not to raise -- any unexpected shape becomes a WARN + drop."""
    try:
        final_type, final_value = resolve_alias_chain(dtcg_path, node, doc, warn)
    except _AliasFail:
        return None
    except Exception as e:  # pragma: no cover -- absolute crash guard
        warn(dtcg_path, f"unexpected error resolving alias: {e}")
        return None
    renderer = TYPE_RENDERERS.get(final_type)
    if renderer is None:
        warn(dtcg_path, f"unknown $type '{final_type}'" if final_type else "missing $type")
        return None
    try:
        return renderer(final_value, dtcg_path, warn)
    except Exception as e:  # pragma: no cover -- absolute crash guard
        warn(dtcg_path, f"unexpected error rendering value: {e}")
        return None


def walk_tokens(node, dtcg_path, css_parts, doc, warn, on_leaf, alias_map=None):
    """Recursively walk a token subtree. For every leaf token, resolves +
    renders it and calls on_leaf(css_parts, dtcg_path, css_text). Any node
    that is neither a token nor a group object is WARNed and skipped --
    never raises."""
    if _is_token_node(node):
        css_text = resolve_and_render(dtcg_path, node, doc, warn)
        if css_text is not None:
            on_leaf(css_parts, dtcg_path, css_text)
        return
    if isinstance(node, dict):
        for key, child in node.items():
            if key.startswith("$"):
                continue
            seg = (alias_map or {}).get(key, key)
            walk_tokens(
                child,
                f"{dtcg_path}.{key}" if dtcg_path else key,
                css_parts + [seg],
                doc,
                warn,
                on_leaf,
                alias_map,
            )
        return
    warn(dtcg_path, f"expected a token or a group object, got {type(node).__name__}")


def compile_css(tokens_path):
    """Compile tokens_path into a CSS string. Raises only on unreadable /
    invalid-JSON input (an I/O or parse problem, not a data-shape problem --
    every data-shape problem is absorbed as a WARN, never a crash)."""
    _reset_warnings()
    warn = _warn
    data = json.loads(Path(tokens_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        warn("", "top-level tokens document is not an object; emitting an empty stylesheet")
        data = {}

    light_lines = []

    def on_leaf_light(css_parts, dtcg_path, css_text):
        var = "--ls-" + "-".join(css_parts)
        light_lines.append(f"  {var}: {css_text};")

    for key, child in data.items():
        if key.startswith("$") or key == "dark":
            continue
        seg = ALIAS.get(key, key)
        walk_tokens(child, key, [seg], data, warn, on_leaf_light, ALIAS)

    css_lines = [":root {"] + light_lines + ["}"]

    dark_node = data.get("dark")
    if isinstance(dark_node, dict):
        dark_lines = []

        def on_leaf_dark(css_parts, dtcg_path, css_text):
            var = "--ls-color-" + "-".join(css_parts)
            dark_lines.append(f"  {var}: {css_text};")

        for key, child in dark_node.items():
            if key.startswith("$"):
                continue
            walk_tokens(child, f"dark.{key}", [key], data, warn, on_leaf_dark)

        if dark_lines:
            css_lines.append("")
            css_lines.append("@media (prefers-color-scheme: dark) {")
            css_lines.append('  :root:not([data-ls-theme="light"]) {')
            css_lines.extend("  " + l for l in dark_lines)
            css_lines.append("  }")
            css_lines.append("}")
            css_lines.append("")
            css_lines.append(':root[data-ls-theme="dark"] {')
            css_lines.extend(dark_lines)
            css_lines.append("}")

    return "\n".join(css_lines) + "\n"


def main(argv):
    args = argv[1:]
    strict = False
    positional = []
    for a in args:
        if a == "--strict":
            strict = True
        elif a in ("-h", "--help"):
            positional.append(a)
        elif a.startswith("--"):
            print(f"FAIL: unknown option '{a}'", file=sys.stderr)
            return 2
        else:
            positional.append(a)

    if not positional or positional[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if positional else 2

    tokens_path = positional[0]
    out_path = positional[1] if len(positional) > 1 else None

    try:
        css = compile_css(tokens_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse tokens file '{tokens_path}': {e}", file=sys.stderr)
        return 1

    warn_count = _warn_count
    if out_path:
        Path(out_path).write_text(css, encoding="utf-8")
    else:
        sys.stdout.write(css)

    if strict and warn_count > 0:
        print(f"FAIL: --strict set and {warn_count} warning(s) were emitted during compilation", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
