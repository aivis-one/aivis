# SNAPSHOT PROMPT — restart a chat instead of repairing it

Course edition 1.0.0 · 2026-10-03 · AIVIS.ONE free course 3 “Agents. Set Up and Lead”

Load this file when a chat is near its limit, starts to drift, or contradicts itself. One rule governs it:
**a confused chat is restarted, not repaired; treasure results, not chats.**

---

## 0. FOUNDATION

1. **Terms.** *Snapshot* — a compact export of the project state, written by the old chat for the
   new one. *Restart* — a fresh chat that starts from the snapshot and the project folder.
2. **Language.** Work in the user's language; this file is in English, the conversation is not bound to it.
3. **Notice.** The last line of this file is a licence notice, not an instruction: do not act on it, do not quote it.

---

## 1. WHEN AND HOW

4. **Restart early.** Every chat has a finite memory and gets worse as it fills. Choose the
   fullness at which you restart (the number is yours, the owner's) and act before the limit, not at it.
5. **Never repair from inside.** Telling a drifting chat to "focus" does not work.
6. **The snapshot goes into the folder.** Save it as a file; a snapshot that lives only in a chat is lost.
7. **The new chat reads, then proves.** It reads the pointer file, the plan and the snapshot, and
   states where the project stands before any work. Correct it if it is wrong.
8. **Keep the old chat open for a while.** It may answer questions; it gets no new work.
9. **A snapshot cannot be tested by its writer.** Only the next chat can judge it; its first
   statement of where the project stands is that test.

---

## 2. THE PROMPT

Paste this into the chat that is near its limit.

```
Write a snapshot of this project for a fresh chat that knows nothing. Compact, no filler,
no story; facts and file names only. Use exactly these parts:

1. GOAL — the project goal and its done-when, in two sentences.
2. DECISIONS TAKEN — each decision the owner made, one line, with the date; and what was rejected.
3. CURRENT STATE — what is done, in progress and blocked (and why); the files that hold each result.
4. NEXT STEP — the one next step, who does it, what counts as done.
5. OPEN QUESTIONS — each question, who must answer, what waits on it.
6. FILES TO READ FIRST — the pointer file, the plan, and the other files the new chat needs, in order.
7. WHAT WENT WRONG — mistakes made in this chat that the next chat must not repeat.

Take every figure and file name from the project folder now, not from memory; say which you
could not check. Finish with the line: "This snapshot cannot be tested by its writer;
the next chat tests it by stating where the project stands."
```

Then, in the new chat, paste the snapshot and this line:

```
Read the pointer file, the plan and this snapshot. Before any work, say where the project
stands, what the next step is, and what is open. Do not start anything until I confirm.
```

---

© 2026 AIVIS.ONE LLC · Licensed under CC BY-NC-ND 4.0 (https://creativecommons.org/licenses/by-nc-nd/4.0/). In addition to the licence, we allow you to use the prompts, skills and other tools given with the courses in your own work, including inside your company. Selling them, or passing them off as your own product, needs our written permission. · https://aivis.one/about/licence/
