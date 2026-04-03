---
name: sanitize
description: "v1.4.0 | Cleanup downloaded/corrupted files"
---

# sanitize

## Purpose

Cleanup files downloaded from external sources.

| Creates | Cleaned mockup.html |
|---------|---------------------|
| Layer | Recovery |

---

## Triggers

- `sanitize`
- `очистить`
- `файл не работает`
- `мокап сломан`

---

## Requirements

| Input | Check |
|-------|-------|
| Corrupted HTML file | In uploads |

---

## Pre-read

| # | Read | Why |
|---|------|-----|
| 1 | reference/integrity.md | Patterns |

---

---

## Step 1: Detect

```bash
FILE="mockup.html"
tail -1 "$FILE"              # → </html>?
grep -c "cdn-cgi" "$FILE"    # → 0?
```

| Result | Action |
|--------|--------|
| All OK | → test protocol |
| Fail | → Step 2 |

---

## Step 2: Remove Injections

Find and delete:
```html
<script data-cfasync="false" src="/cdn-cgi/..."></script>
```

---

## Step 3: Restore Truncated

Add if missing:
```html
  </script>
</body>
</html>
```

---

## Step 4: Validate

Re-run checks from Step 1.

---

## Step 5: Continue

```
sanitize → test → deliver
```

---

## Anchor

🎨 livemockup-studio v1.4.0 · sanitize
🟢 | NEXT: test

---

1 → test
2 → re-run sanitize

---

*sanitize v1.4.0*
