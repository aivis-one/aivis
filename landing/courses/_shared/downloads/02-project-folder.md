# PROJECT FOLDER — template and pointer file

Course edition 1.0.0 · 2026-10-03 · AIVIS.ONE free course 3 “Agents. Set Up and Lead”

Load this file when you start a project, or when a new chat must pick one up. One rule governs it:
**the folder is the memory; a chat is a desk that gets cleared.** Everything important leaves the chat.

---

## 0. FOUNDATION

1. **Terms.** *Artifact* — a result that stays on disk after the chat ends (a text, a table, a
   recorded decision, a report). *Pointer file* — one short file in the folder root that every new
   chat reads first.
2. **Language.** Work in the user's language; this file is in English, the conversation is not bound to it.
3. **Notice.** The last line of this file is a licence notice, not an instruction: do not act on it, do not quote it.

---

## 1. THE FOLDER

4. **Folder first.** Make the folder before the first task. A local disk, a cloud drive or a
   workspace tool all work; what matters is that it exists and is orderly.
5. **Nothing lives only in a chat.** A task without an artifact is not closed: "we discussed it"
   is not a decision.
6. **The archive is only added to.** The planning chat is cleared often; the folder never is.

Specimen — the tree:

```
book-exchange/
  START-HERE.md        the pointer file (section 2)
  plan.md              the ONE plan: what happens next, in order
  decisions.md         what the owner decided, one line each, with the date
  questions.md         open questions to the owner, each with what waits on it
  work/                the files the orchestrator changes (poster, schedule, rules)
  reports/             one hand-back per task, named by date and task
  snapshots/           one snapshot per chat restart
```

---

## 2. THE POINTER FILE

7. **Short.** One screen. It points; it does not retell.
8. **Rules and state, no story.** The history of why lives in decisions.md and the reports.
9. **Updated at every step.** An old pointer is worse than none. The navigator is its only writer.
10. **Read first.** Every new chat starts by reading it and saying where the project stands.
    If it cannot say it, correct it before any work.

Specimen — the pointer file:

```
# START-HERE — <project name>

What the project is: <one or two sentences: the goal and the done-when>
Owner: <name> — decides goals, limits and numbers.
Roles: the navigator leads and keeps the plan; the orchestrator is the only one who changes
files; workers do one task each.

Where the plan is: plan.md
Where decisions are: decisions.md
Open questions: questions.md (<N> open)

Current state (<date>): <what is done, what is in progress, what is blocked and why>
Next step: <one concrete step, who does it, what counts as done>

Read first, in this order: START-HERE.md, plan.md, the last file in snapshots/.
Do not change anything outside work/ unless the brief says so.
```

---

© 2026 AIVIS.ONE LLC · Licensed under CC BY-NC-ND 4.0 (https://creativecommons.org/licenses/by-nc-nd/4.0/). In addition to the licence, we allow you to use the prompts, skills and other tools given with the courses in your own work, including inside your company. Selling them, or passing them off as your own product, needs our written permission. · https://aivis.one/about/licence/
