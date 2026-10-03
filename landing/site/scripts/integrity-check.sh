#!/usr/bin/env bash
# landing-studio v10.0.0 -- scripts/integrity-check.sh
# Per-page integrity gate. Detects truncation, Cloudflare email-obfuscation injection,
# unbalanced structural tags, and leftover template-placeholder residue.
# Exits 0 on PASS, 1 on FAIL, 2 on usage error.
#
# Carrier note (section 4.12): this script is the SINGLE implementation of the
# integrity checks. scripts/gate.py's Q-INTEGRITY gate CALLS this script
# rather than re-implementing the checks -- keep it that way so there is one
# carrier, not two drifting copies (this is the same defect class as C8/C9).
#
# Every count below is an OCCURRENCE count via `grep -o ... | wc -l`, never
# `grep -c` (finding C8/C9): `grep -c` counts matching LINES, so a page with
# 2 `<script` opens and 1 close on a single line reports "balanced" and a
# live `<script>alert(1)</script>` payload can pass a naive line-count gate.
#
# Usage: integrity-check.sh <page.html> [more.html ...]

set -u
[ "$#" -ge 1 ] || { echo "usage: $0 <page.html> [...]"; exit 2; }

occurrences() {
  # $1 = pattern (extended regex via grep -oE), $2 = file
  grep -oE "$1" "$2" 2>/dev/null | wc -l | tr -d ' '
}

overall=0
for FILE in "$@"; do
  [ -f "$FILE" ] || { echo "FAIL: not found: $FILE"; overall=1; continue; }
  fail=0

  last="$(tail -1 "$FILE" | tr -d '[:space:]')"
  # Tail may be the __LS_CANON__ comment close or </html>; accept either as a clean end.
  case "$last" in
    "</html>"|"-->") : ;;
    *) echo "FAIL[$FILE]: tail not </html> or comment close (got '$last')"; fail=1 ;;
  esac

  cf=$(occurrences 'cdn-cgi' "$FILE")
  [ "$cf" -eq 0 ] || { echo "FAIL[$FILE]: cdn-cgi occurrence count = $cf (Cloudflare injection)"; fail=1; }
  em=$(occurrences '__cf_email__' "$FILE")
  [ "$em" -eq 0 ] || { echo "FAIL[$FILE]: __cf_email__ occurrence count = $em (email obfuscation)"; fail=1; }

  so=$(occurrences '<script' "$FILE"); sc=$(occurrences '</script>' "$FILE")
  [ "$so" -eq "$sc" ] || { echo "FAIL[$FILE]: script tags unbalanced (open=$so close=$sc)"; fail=1; }
  ho=$(occurrences '<html[^a-zA-Z]' "$FILE"); hc=$(occurrences '</html>' "$FILE")
  { [ "$ho" -eq 1 ] && [ "$hc" -eq 1 ]; } || { echo "FAIL[$FILE]: html tags (open=$ho close=$hc; want 1/1)"; fail=1; }
  bo=$(occurrences '<body[^a-zA-Z]' "$FILE"); bc=$(occurrences '</body>' "$FILE")
  { [ "$bo" -eq 1 ] && [ "$bc" -eq 1 ]; } || { echo "FAIL[$FILE]: body tags (open=$bo close=$bc; want 1/1)"; fail=1; }

  # Placeholder-residue check: no NAMED template placeholder may survive into a
  # rendered page (section 4.1/4.12). Scoped to the real placeholder names rather
  # than to any double-brace pair, so legitimate copy that merely contains braces
  # does not false-FAIL a valid page while a genuine unsubstituted marker still
  # does (trial defect 6). The name list is the template's own placeholder set.
  po=$(occurrences '\{\{(BASE_CSS|BODY|CANON|CANONICAL|COMPONENTS_CSS|DESCRIPTION|DIR|HREFLANG|INTERACTIONS_JS|LANG|LANG_SWITCH_JS|MOTION_CSS|OG|SECTIONS_CSS|TITLE|TOKENS_CSS)\}\}' "$FILE")
  [ "$po" -eq 0 ] || { echo "FAIL[$FILE]: template placeholder residue present (count=$po)"; fail=1; }

  if [ "$fail" -eq 0 ]; then echo "PASS: $FILE"; else overall=1; fi
done

exit "$overall"
