---
name: integrity
description: "v1.5.1 | File integrity patterns and recovery"
---

# Integrity Reference

## Purpose
Detect and recover from file corruption before testing.

---

## Known Corruption Patterns

### Pattern 1: Cloudflare Email Protection

| Field | Value |
|-------|-------|
| Trigger | File downloaded through Cloudflare CDN |
| Injection | `<script src="/cdn-cgi/scripts/.../email-decode.min.js">` |
| Effect | Script 404 → all JS fails |
| Detection | `grep "cdn-cgi" file.html` |
| Fix | Remove injected script tag |

### Pattern 2: Email Obfuscation

| Field | Value |
|-------|-------|
| Trigger | Cloudflare Email Protection |
| Change | `email@domain.com` → `[email&#160;protected]` |
| Detection | `grep "__cf_email__" file.html` |
| Fix | Replace with original emails |

### Pattern 3: File Truncation

| Field | Value |
|-------|-------|
| Trigger | Large file transfer failure |
| Effect | File ends mid-content |
| Detection | `tail -1 file.html` ≠ `</html>` |
| Fix | Restore closing tags |

### Pattern 4: Encoding Corruption

| Field | Value |
|-------|-------|
| Trigger | Character encoding mismatch |
| Effect | Cyrillic → `????` |
| Detection | Visual inspection |
| Fix | Re-save UTF-8 |

---

## Detection Commands

| Check | Command | Expected |
|-------|---------|----------|
| File ends correctly | `tail -1 file.html` | `</html>` |
| No Cloudflare | `grep -c "cdn-cgi" file.html` | `0` |
| No email obfuscation | `grep -c "__cf_email__" file.html` | `0` |
| Script tags balanced | Compare `<script>` vs `</script>` | Equal |
| Body closed | `grep -c "</body>" file.html` | `1` |
| HTML closed | `grep -c "</html>" file.html` | `1` |

---

## Recovery Procedures

### Recovery: Cloudflare Injection

1. Find: `<script data-cfasync="false" src="/cdn-cgi/..."></script>`
2. Remove entire tag
3. Verify JS works

### Recovery: Truncation

1. Check: `tail -10 file.html`
2. Add missing: `</script></body></html>`

---

## Workarounds (Prevention)

| Method | Reliability | How |
|--------|-------------|-----|
| ZIP архив | ✅ Best | Claude заархивирует перед скачиванием |
| Copy-paste | ✅ Good | Скопировать из artifact в редактор |

---

## Bash Script

```bash
#!/bin/bash
FILE=$1
echo "=== Integrity Check: $FILE ==="

# INT1: File ends with </html>
if [[ $(tail -1 "$FILE") == *"</html>"* ]]; then
  echo "✅ INT1: File ends correctly"
else
  echo "🔴 INT1: FAIL - Truncated"
fi

# INT2: No Cloudflare
CF=$(grep -c "cdn-cgi" "$FILE" 2>/dev/null || echo "0")
[[ "$CF" == "0" ]] && echo "✅ INT2: No Cloudflare" || echo "🔴 INT2: FAIL ($CF)"

# INT3: No email obfuscation
EM=$(grep -c "__cf_email__" "$FILE" 2>/dev/null || echo "0")
[[ "$EM" == "0" ]] && echo "✅ INT3: No obfuscation" || echo "🔴 INT3: FAIL ($EM)"

# INT4: Script tags balanced
OPEN=$(grep -c "<script" "$FILE" 2>/dev/null || echo "0")
CLOSE=$(grep -c "</script>" "$FILE" 2>/dev/null || echo "0")
[[ "$OPEN" == "$CLOSE" ]] && echo "✅ INT4: Balanced ($OPEN)" || echo "🔴 INT4: FAIL ($OPEN/$CLOSE)"

# INT5-6: Closing tags
BODY=$(grep -c "</body>" "$FILE" 2>/dev/null || echo "0")
HTML=$(grep -c "</html>" "$FILE" 2>/dev/null || echo "0")
[[ "$BODY" == "1" ]] && echo "✅ INT5: Body closed" || echo "🔴 INT5: FAIL"
[[ "$HTML" == "1" ]] && echo "✅ INT6: HTML closed" || echo "🔴 INT6: FAIL"

echo "=== Done ==="
```

---

*integrity v1.5.1*
