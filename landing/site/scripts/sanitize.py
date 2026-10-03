#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/sanitize.py

Recover a landing page corrupted by Cloudflare email-obfuscation injection or
write-time truncation. Strips known cdn-cgi / __cf_email__ patterns, restores the
literal email behind data-cfemail when present, and ensures the file ends with
</html>. Writes in place after a backup. (Prevention: avoid raw emails in inline JS;
disable Email Obfuscation / Auto-Minify in the Cloudflare dashboard -- see references/cloudflare.md.)

Backups (finding C13): never clobber an existing backup. The first backup is
`<file>.bak`; if that already exists, `<file>.bak.2`, `<file>.bak.3`, ... is
used instead, so a second run can never destroy the only copy of the true
original.

CF_SCRIPT (finding C12): matches the *opening* `<script ...>` tag up to its
own `>`, then non-greedily up to the next `</script>` -- so an injected
script whose body itself contains `<` (e.g. `1<2`) is still matched and
stripped in full, not left behind with the marker gone but the payload intact.

Post-sanitize re-verify (finding C13's twin defect): after writing the
sanitized text, the file is re-read and re-scanned for `cdn-cgi` /
`__cf_email__`. If either still occurs, this prints FAIL and exits 1 --
it can never print OK while a marker remains.

Usage:
  python sanitize.py <page.html> [more.html ...]
"""
import re
import shutil
import sys
from pathlib import Path

# Match the opening <script ...cdn-cgi...> tag up to ITS OWN '>', then
# non-greedily up to the next </script> -- the body may contain '<' safely.
CF_SCRIPT = re.compile(r'<script\b[^>]*cdn-cgi[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE)
CF_LINK = re.compile(r'<a[^>]*class="__cf_email__"[^>]*data-cfemail="([0-9a-fA-F]+)"[^>]*>.*?</a>', re.DOTALL)
CF_LINK_NODATA = re.compile(r'<a[^>]*class="__cf_email__"[^>]*>.*?</a>', re.DOTALL)
CF_ATTR = re.compile(r'\s*data-cfemail="[^"]*"')


def decode_cfemail(hexstr):
    try:
        data = bytes.fromhex(hexstr)
        key = data[0]
        return "".join(chr(b ^ key) for b in data[1:])
    except Exception:
        return ""


def sanitize(text):
    text = CF_SCRIPT.sub("", text)
    text = CF_LINK.sub(lambda m: decode_cfemail(m.group(1)) or "", text)
    text = CF_LINK_NODATA.sub("", text)
    text = CF_ATTR.sub("", text)
    text = text.rstrip()
    if not text.endswith("</html>"):
        text += "\n</html>\n"
    return text


def backup_path(path):
    """Never clobber an existing backup: <file>.bak, then .bak.2, .bak.3, ..."""
    candidate = Path(str(path) + ".bak")
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = Path(str(path) + f".bak.{n}")
        if not candidate.exists():
            return candidate
        n += 1


def still_contaminated(text):
    markers = []
    if "cdn-cgi" in text:
        markers.append("cdn-cgi")
    if "__cf_email__" in text:
        markers.append("__cf_email__")
    return markers


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) >= 2 else 2
    rc = 0
    for a in argv[1:]:
        path = Path(a)
        if not path.exists():
            print(f"FAIL: not found: {path}", file=sys.stderr)
            rc = 1
            continue
        bak = backup_path(path)
        shutil.copy(path, bak)
        original = path.read_text(encoding="utf-8")
        cleaned = sanitize(original)
        path.write_text(cleaned, encoding="utf-8")

        # Re-verify: never print OK while a marker remains (finding C13's twin).
        reread = path.read_text(encoding="utf-8")
        remaining = still_contaminated(reread)
        if remaining:
            print(f"FAIL: {path} still contains {', '.join(remaining)} after sanitizing "
                  f"(backup at {bak})", file=sys.stderr)
            rc = 1
            continue
        print(f"OK: sanitized {path} (backup at {bak})")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
