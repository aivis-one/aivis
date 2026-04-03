---
name: deliver
description: "v1.4.0 | L4 - UAT checklist and final delivery"
---

# deliver

## Purpose

Final delivery with User Acceptance Testing.

| Creates | User-confirmed HTML |
|---------|---------------------|
| Layer | L4 |

---

## Requirements

| Input | Check |
|-------|-------|
| mockup.html | Passed test (0 BLOCKER) |
| brief.md | In context |

---

## Step 1: Generate UAT Checklist

Based on brief.md:

```markdown
## 🧪 Проверь мокап: {project_name}

### Shell
- [ ] Toolbar виден
- [ ] Phone/Tablet/Desktop работают
- [ ] Zoom +/− работает

### Навигация  
- [ ] {screen_1} → {screen_2}
- [ ] Кнопки "Назад" работают

### Взаимодействия
- [ ] {button_1} работает
- [ ] Popup открывается/закрывается
- [ ] Toast появляется

---
Есть проблемы? Опиши.
```

---

## Step 2: Present

1. Copy to outputs
2. Show checklist
3. Wait for feedback

---

## Step 3: Collect Feedback

| Response | Action |
|----------|--------|
| "Всё ок" | ✅ Complete |
| "Не работает X" | → Fix → Re-deliver |

---

## Step 4: Confirm

```
✅ Мокап доставлен и принят.
Файл: Save to project's mockup directory (e.g., `mocups/{name}/mockup.html`){name}-final.html

📝 Если сломается после скачивания → sanitize
```

---

## Anchor

🎨 livemockup-studio v1.4.0 · deliver
🟢 | Delivered

---

1 → new mockup
2 → fix issues

---

*deliver v1.4.0*
