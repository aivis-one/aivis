#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/contrast-check.py

Compute WCAG 2.x relative-luminance contrast ratios for the fixed pair table
below (finding T3), in the light palette and, when the tokens document has a
top-level `dark` group, in the dark palette too (each `color.X` pair is
re-resolved against `dark.X` when that key exists, else it falls back to the
light value for that side of the pair).

This is the contrast SSOT (references/tokens.md points here). `scripts/gate.py`
(Q-CONTRAST) delegates to this script.

Every colour form scripts/tokens-to-css.py accepts is handled here too: a DTCG
colour dict {colorSpace, components, alpha}, hex strings ("#RGB"/"#RRGGBB"/
"#RRGGBBAA"), and the CSS function forms rgb()/rgba()/hsl()/hsla()/oklch().
DTCG `{group.key}` aliases are resolved (8-hop limit, cycle-detected) via the
same machinery tokens-to-css.py uses (imported from it -- one alias-resolution
implementation, not two).

Usage:
  python3 contrast-check.py tokens.tokens.json [--json out.json]

Prints one line per pair with its ratio to two decimals and PASS/FAIL.
Exit 0 only if every pair in every checked palette passes. Exit 2 on usage
error.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path
import importlib.util


def _load_tokens_to_css():
    here = Path(__file__).parent
    spec = importlib.util.spec_from_file_location("t2c_for_contrast", here / "tokens-to-css.py")
    mod = importlib.util.module_from_spec(spec)
    # Do not leave a __pycache__ behind inside the skill tree: a gate run must
    # not add files to the tree it is checking, and a packaged child's
    # round-trip diff reads any addition as drift. Same mechanism as
    # claims-check.py's import of render-page.py -- saved and restored, so this
    # never changes the interpreter state a caller relies on.
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = saved
    return mod


# fg token path, bg token path, minimum ratio (spec section 5)
PAIRS = [
    ("color.text", "color.background", 4.5),
    ("color.text", "color.surface", 4.5),
    ("color.text", "color.surface-muted", 4.5),
    ("color.text-muted", "color.background", 4.5),
    ("color.text-muted", "color.surface", 4.5),
    ("color.text-muted", "color.surface-muted", 4.5),
    ("color.on-primary", "color.primary", 4.5),
    ("color.text", "color.border", 3.0),
]

HEX_RE = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")
FUNC_RE = re.compile(r"^([a-zA-Z-]+)\((.*)\)$", re.DOTALL)
NUM_TOKEN_RE = re.compile(r"[-+]?\d*\.?\d+%?")


def srgb_channel_to_linear(c):
    c = max(0.0, min(1.0, c))
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(l1, l2):
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _num(tok, as_alpha=False):
    tok = tok.strip()
    if tok.endswith("%"):
        return float(tok[:-1]) / 100.0
    v = float(tok)
    return v if as_alpha else v


def parse_hex(s):
    h = s.lstrip("#")
    if len(h) == 3:
        r, g, b = (int(c * 2, 16) for c in h)
        a = 255
    elif len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = 255
    elif len(h) == 8:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16)
    else:
        return None
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def parse_rgb_fn(body):
    nums = NUM_TOKEN_RE.findall(body)
    if len(nums) < 3:
        return None

    def chan(tok):
        return float(tok[:-1]) / 100.0 if tok.endswith("%") else float(tok) / 255.0

    r, g, b = chan(nums[0]), chan(nums[1]), chan(nums[2])
    a = 1.0
    if len(nums) >= 4:
        a = _num(nums[3], as_alpha=True)
    return (r, g, b, a)


def parse_hsl_fn(body):
    nums = NUM_TOKEN_RE.findall(body)
    if len(nums) < 3:
        return None
    h = float(nums[0].rstrip("%")) % 360
    s = float(nums[1].rstrip("%")) / 100.0
    l = float(nums[2].rstrip("%")) / 100.0
    a = 1.0
    if len(nums) >= 4:
        a = _num(nums[3], as_alpha=True)
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    if h < 60:
        r1, g1, b1 = c, x, 0.0
    elif h < 120:
        r1, g1, b1 = x, c, 0.0
    elif h < 180:
        r1, g1, b1 = 0.0, c, x
    elif h < 240:
        r1, g1, b1 = 0.0, x, c
    elif h < 300:
        r1, g1, b1 = x, 0.0, c
    else:
        r1, g1, b1 = c, 0.0, x
    return (r1 + m, g1 + m, b1 + m, a)


def parse_oklch_fn(body):
    if "/" in body:
        main, alpha_part = body.split("/", 1)
    else:
        main, alpha_part = body, None
    nums = NUM_TOKEN_RE.findall(main)
    if len(nums) < 3:
        return None
    l_tok, c_tok, h_tok = nums[0], nums[1], nums[2]
    L = float(l_tok.rstrip("%")) / 100.0 if l_tok.endswith("%") else float(l_tok)
    C = float(c_tok.rstrip("%")) / 100.0 * 0.4 if c_tok.endswith("%") else float(c_tok)
    H = float(h_tok.rstrip("%")) % 360
    a = 1.0
    if alpha_part:
        a = _num(alpha_part.strip(), as_alpha=True)
    hr = math.radians(H)
    aa = C * math.cos(hr)
    bb = C * math.sin(hr)
    l_ = L + 0.3963377774 * aa + 0.2158037573 * bb
    m_ = L - 0.1055613458 * aa - 0.0638541728 * bb
    s_ = L - 0.0894841775 * aa - 1.2914855480 * bb
    l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
    lr = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    lg = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    lb = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3
    lr = min(max(lr, 0.0), 1.0)
    lg = min(max(lg, 0.0), 1.0)
    lb = min(max(lb, 0.0), 1.0)
    return ("linear", lr, lg, lb, a)


def token_to_linear_rgb(final_type, value, path, warn):
    """Resolve a (already alias-resolved) DTCG token value to linear-light
    sRGB channels (r, g, b, a), each in [0, 1]. Returns None (and warns) if
    the value cannot be interpreted as a colour -- never raises."""
    if final_type != "color":
        warn(path, f"not a color token (resolved $type={final_type!r})")
        return None
    if isinstance(value, dict):
        comps = value.get("components")
        if not isinstance(comps, (list, tuple)) or len(comps) < 3:
            warn(path, "color dict missing a usable 'components' array")
            return None
        try:
            r, g, b = float(comps[0]), float(comps[1]), float(comps[2])
        except Exception:
            warn(path, "color dict 'components' are not valid numbers")
            return None
        a = value.get("alpha", 1)
        try:
            a = float(a)
        except Exception:
            a = 1.0
        return (srgb_channel_to_linear(r), srgb_channel_to_linear(g), srgb_channel_to_linear(b), a)
    if isinstance(value, str):
        s = value.strip()
        if HEX_RE.match(s):
            parsed = parse_hex(s)
            if not parsed:
                warn(path, f"malformed hex colour '{s}'")
                return None
            r, g, b, a = parsed
            return (srgb_channel_to_linear(r), srgb_channel_to_linear(g), srgb_channel_to_linear(b), a)
        m = FUNC_RE.match(s)
        if m:
            fn, body = m.group(1).lower(), m.group(2)
            try:
                if fn in ("rgb", "rgba"):
                    parsed = parse_rgb_fn(body)
                elif fn in ("hsl", "hsla"):
                    parsed = parse_hsl_fn(body)
                elif fn == "oklch":
                    parsed = parse_oklch_fn(body)
                else:
                    parsed = None
            except Exception:
                parsed = None
            if parsed is None:
                warn(path, f"could not parse colour function '{s}'")
                return None
            if fn == "oklch":
                _, r, g, b, a = parsed
                return (r, g, b, a)
            r, g, b, a = parsed
            return (srgb_channel_to_linear(r), srgb_channel_to_linear(g), srgb_channel_to_linear(b), a)
        warn(path, f"unrecognized colour value '{s}'")
        return None
    warn(path, f"unsupported colour value type: {type(value).__name__}")
    return None


def resolve_pair_side(doc, t2c, palette, color_path, warnings):
    """color_path is 'color.X'. In the light palette, resolve as-is. In the
    dark palette, resolve 'dark.X' if it exists, else fall back to the light
    value (so a partially-specified dark group never crashes the check)."""
    used_path = color_path
    if palette == "dark":
        alt = "dark" + color_path[len("color"):]
        if t2c.lookup_path(doc, alt) is not None:
            used_path = alt

    def warn(p, msg):
        warnings.append(f"[{palette}] {p}: {msg}")

    final_type, final_value = t2c.get_token(doc, used_path, warn)
    if final_type is None and final_value is None:
        warn(used_path, "token not found or unresolvable")
        return used_path, None
    rgb = token_to_linear_rgb(final_type, final_value, used_path, warn)
    return used_path, rgb


def evaluate_palette(doc, t2c, palette, warnings):
    results = []
    for fg_path, bg_path, minimum in PAIRS:
        fg_used, fg_rgb = resolve_pair_side(doc, t2c, palette, fg_path, warnings)
        bg_used, bg_rgb = resolve_pair_side(doc, t2c, palette, bg_path, warnings)
        if fg_rgb is None or bg_rgb is None:
            results.append({
                "palette": palette, "fg": fg_used, "bg": bg_used,
                "min": minimum, "ratio": None, "pass": False,
            })
            continue
        l1 = relative_luminance(*fg_rgb[:3])
        l2 = relative_luminance(*bg_rgb[:3])
        ratio = contrast_ratio(l1, l2)
        results.append({
            "palette": palette, "fg": fg_used, "bg": bg_used,
            "min": minimum, "ratio": ratio, "pass": ratio >= minimum - 1e-9,
        })
    return results


def main(argv):
    p = argparse.ArgumentParser(
        prog="contrast-check.py",
        description="WCAG contrast check for landing-studio DTCG tokens (finding T3).",
    )
    p.add_argument("tokens_path")
    p.add_argument("--json", dest="json_out", default=None)
    try:
        args = p.parse_args(argv[1:])
    except SystemExit as e:
        return e.code if e.code is not None else 2

    try:
        doc = json.loads(Path(args.tokens_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read/parse tokens file '{args.tokens_path}': {e}", file=sys.stderr)
        return 2
    if not isinstance(doc, dict):
        print("FAIL: top-level tokens document is not an object", file=sys.stderr)
        return 2

    t2c = _load_tokens_to_css()
    warnings = []
    all_results = []

    print("=== light palette ===")
    light_results = evaluate_palette(doc, t2c, "light", warnings)
    all_results.extend(light_results)
    for r in light_results:
        ratio_text = f"{r['ratio']:.2f}:1" if r["ratio"] is not None else "ERROR"
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{status}  {ratio_text:>8}  min {r['min']:.1f}:1  {r['fg']} on {r['bg']}")

    has_dark = isinstance(doc.get("dark"), dict)
    if has_dark:
        print("=== dark palette ===")
        dark_results = evaluate_palette(doc, t2c, "dark", warnings)
        all_results.extend(dark_results)
        for r in dark_results:
            ratio_text = f"{r['ratio']:.2f}:1" if r["ratio"] is not None else "ERROR"
            status = "PASS" if r["pass"] else "FAIL"
            print(f"{status}  {ratio_text:>8}  min {r['min']:.1f}:1  {r['fg']} on {r['bg']}")

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    failed = [r for r in all_results if not r["pass"]]
    overall = "PASS" if not failed else "FAIL"
    print(f"RESULT: {overall}  pairs={len(all_results)}  failed={len(failed)}  "
          f"palettes={'light+dark' if has_dark else 'light'}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "result": overall,
            "pairs": all_results,
            "warnings": warnings,
        }, indent=2), encoding="utf-8")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
