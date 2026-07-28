# AIVIS.ONE — Manual Deploy Runbook

> **This repo is PUBLIC.** This document contains no secrets and never will — every credential it
> references is a POINTER to `AIVIS-Server/CREDENTIALS.md`, a file that lives outside this repo,
> outside git entirely, on the operator's own machine. If you don't have access to that file, get it
> from whoever manages the server before you start.
>
> This runbook exists so that running `scripts/install_aivis.sh` — and everything after it — is a
> job any operator can do alone, without having sat in on the sessions that built the script.

---

## 1. Before you start — have these ready

- **The Telegram bot token** (`AIVIS-Server/CREDENTIALS.md` §2, the target `@aivisonebot` row) —
  you'll type this in during the install, once.
- **A browser tab open on GitHub → `aivis-one/aivis` → Settings → Deploy keys**, logged in as
  someone with admin rights on the repo. You'll paste a key here mid-install and the script will
  wait for you.
- **The Mailgun API key** (`CREDENTIALS.md` §3), if you want it in `.env` now rather than editing
  the file by hand later. Optional — mail is out of scope for the current migration wave (see §7).
- Root SSH access to the target box (`CREDENTIALS.md` §1).

## 2. Run inside `tmux` — do not run this over a bare SSH session

```
tmux new -s install
```

The install takes several minutes and includes long-running steps (package installs, a Docker
build, database migrations). **If your SSH connection drops partway through, a bare session dies
with it and leaves the box half-built** — some system packages installed, no application running,
no clean way to tell how far it got. `tmux` keeps the install running on the server itself; if you
get disconnected, reconnect and `tmux attach -t install` to pick up exactly where you left off.

## 3. Download the script and verify it — never pipe `curl` straight into `bash`

The script's own header comment suggests `curl -fsSL <url> | bash`. **Don't do that here.** If the
download is interrupted partway — a network blip, a dropped connection — `bash` receives a
truncated script and starts executing it anyway; by the time it hits a syntax error and stops, it
may already have run `apt-get install`, written files, or worse, and it reports nothing that looks
like a download failure.

Instead:

```
curl -fsSL https://raw.githubusercontent.com/aivis-one/aivis/main/scripts/install_aivis.sh -o install_aivis.sh
sha256sum install_aivis.sh
```

Compare that hash against the same file computed independently — from your own clone of the repo
(`git show main:scripts/install_aivis.sh | sha256sum`), or by checking the file's byte count and
hash on GitHub's own web UI for the commit you expect to be running. Only once they match:

```
bash install_aivis.sh
```

## 4. Every prompt, in the order you will actually meet them

The script pauses **nine times on a first install** — **ten** if `/opt/aivis/repo` already exists on
the box and prompt 1 below fires too (a re-install, not a malfunction). Each one is listed here in
execution order, with the exact answer.

1. **`Remove existing installation and start fresh? (y/n)`** — only appears if `/opt/aivis/repo`
   already exists (i.e. this is not the first install on this box). Answer **`y`** if you intend to
   wipe and redo it; **anything else aborts the script immediately** — there is no "keep what's
   there and continue" option, so don't answer this one absent-mindedly.
2. **`Press ENTER after adding the deploy key to GitHub...`** — the script generates a fresh SSH
   keypair and prints the public half to your terminal just before this prompt. Copy it, go to the
   GitHub tab you opened in §1, add it as a Deploy Key with **Read/write access checked** (`update`
   later commits and pushes a regenerated file — a read-only key breaks that silently, much later).
   **Only press ENTER once the key is visibly saved on GitHub's page**, not right after pasting it —
   the very next thing the script does is `git clone` using that key, and it will fail if the key
   hasn't actually landed yet.
3. **Telegram Bot Token** — type the value from `CREDENTIALS.md` §2 (the `@aivisonebot` row).
4. **SumSub API Key (optional)** — press **ENTER**. No KYC integration exists in this project;
   `CREDENTIALS.md` §6 confirms this is intentionally left empty.
5. **SumSub Secret Key (optional)** — press **ENTER**, same reason.
6. **Mailgun API Key (optional)** — type the value from `CREDENTIALS.md` §3 if you have it handy,
   or press **ENTER** to leave it for later. Either is fine — mail is out of scope this wave (§7).
7. **MinIO Root User** — **press ENTER.** ⚠
8. **MinIO Root Password** — **press ENTER.** ⚠
9. **MinIO Console basic-auth password** — **press ENTER.** ⚠

   **Prompts 7–9 together: press ENTER three times, type nothing.** The script already generated
   three independent random values for these before asking (it says so on screen right above the
   first one). Typing any value into any of the three — even the same one into all three "to keep
   it simple" — is exactly how a previous install ended up with one hand-typed, publicly-readable
   password gating both the nginx login gate and the MinIO console behind it. ENTER three times is
   not the cautious choice here, it's the only correct one.
10. **`Add this DKIM DNS record... Press ENTER to continue.`** — the script prints a DNS TXT record
    it will not show you again. Copy it down even if you're not adding it right now (mail/DKIM is
    out of scope for this migration wave — see §7) — you'll need it whenever that work does happen.
    Press ENTER once you've copied it.

## 5. Post-install verification

```
docker ps
```
Expect five `aivis-*` containers (`aivis-app`, `aivis-frontend`, `aivis-postgres`, `aivis-redis`,
`aivis-minio`), all `Up ... (healthy)`.

```
sudo certbot certificates
```
Expect two certificate lineages: one covering `api.aivis.one` + `app.aivis.one` together, one for
`storage-mc-admin.aivis.one`. Both should show as issued by Let's Encrypt's production CA with
roughly 90 days of validity — **if either says "STAGING" anywhere in its issuer, `AIVIS_CERTBOT_STAGING`
was set when it shouldn't have been for a real cutover** (see §8's final note on that flag).

```
curl -s https://api.aivis.one/health
curl -s https://app.aivis.one
```
The first should return JSON with `"status":"ok"` (and `"db":"ok"`, `"redis":"ok"`). The second
should return the frontend's HTML, HTTP 200.

## 6. The browser acceptance check — this is the one that actually matters

Command-line checks above prove the box is up. They do **not** prove the browser can actually talk
to it — the frontend's Content-Security-Policy is baked in at build time to allow connections to
exactly one API host, and a mismatch there is invisible to every check above; the browser just
silently blocks the request.

Open `https://app.aivis.one` in a real browser with DevTools open (Console + Network tabs). Filter
Network to `api.aivis.one`. Do anything that triggers an API call (loading the page is usually
enough, or attempting to log in).

**What you're looking for:**
- The CORS preflight request (`OPTIONS`) to `api.aivis.one` returns **200**.
- The real request that follows returns **401**.
- **Zero CSP errors in the Console.**

**401 is the success signal here — read that twice if it doesn't feel right.** A 401 means the
request physically reached the backend, went through CORS, went through the CSP, and got a real
application-level response back; you're simply not logged in yet, which is exactly what a fresh
install with no session should show. Anyone who hasn't been told this will see "401 Unauthorized"
in red in their Network tab and assume something is broken. It isn't — it's the proof that nothing
upstream of the backend is broken. The failure mode this check exists to catch is a *CSP error and
no request at all*, not a 401.

## 7. Expected warnings — do not treat these as install failures

- **Anything mail-related** — Postfix, OpenDKIM, a Mailgun-shaped complaint in `.env`. Mail is
  entirely out of scope for this migration wave (decision 30). The install no longer aborts on a
  mail-service restart failure (it warns and continues) — but even a clean mail warning is not a
  real problem right now. Don't chase it as if it were.
- **"Storefront seeded" completes but adds zero companies or products.** Intentional — the demo
  company/product/installment lists were emptied deliberately (owner, 2026-07-25; see the comment
  at the top of `backend/scripts/seed_storefront.py`). An empty storefront after this step is the
  expected result until real company data is loaded as a separate, later task — not a bug.
- **"Test accounts seeded" may silently create nothing.** `seed_test_accounts` refuses to create the
  well-known `seedpass123` test logins when `APP_ENV=production` (which this install sets) unless
  `AIVIS_SEED_TEST_ACCOUNTS=1` was exported before running. This is a deliberate production safety
  guard, not a failure — don't export that variable on a real cutover.
- **No `needrestart` dialogs should appear at all.** If one does anyway, `NEEDRESTART_MODE=a` didn't
  take effect — check `env | grep NEEDRESTART` before doing anything else; something about how the
  script was invoked (e.g. running individual sections by hand instead of the whole file) likely
  skipped the top of the script where it's set.

## 8. If it stops here, this is why

The script aborts on its own (not by design) at a handful of points. In order of how bad the
half-finished state is if you land there:

- **Docker build/start fails** (`docker compose build` / `up`) — almost always means the four ports
  (8000/3000/9000/9001) are already in use. Check `ss -ltnp`; something from a previous attempt
  probably never got torn down.
- **`nginx -t` fails** at either of its two checkpoints (right after the API/frontend sites are
  written, or right after the storage site is written) — this **usually** means something *outside*
  this install's own files is broken (nginx was already in a bad state before you started), but the
  site file the script just wrote could itself be malformed too. Read the error `nginx -t` prints —
  it names the offending file either way, so start there rather than assuming which case you're in.
- **`git clone` fails** — the deploy key from prompt 2 above wasn't actually saved on GitHub, or was
  saved without write access, before you pressed ENTER. Go back to the GitHub tab, confirm it's
  really there, then re-run.
- **A seeding step fails** partway through — generic application-level issue at that point, not
  specific to this being a fresh install. Check `docker compose logs app` from
  `/opt/aivis/repo`.
- **Mail service restart (OpenDKIM/Postfix) reports a warning, not a failure** — this used to abort
  the whole install; it no longer does. If you see the warning, the install continued regardless;
  mail itself is out of scope this wave (§7 above) so this is not something to fix right now.

**One knob worth knowing about if you expect to retry more than once:** setting
`AIVIS_CERTBOT_STAGING=1` before running the script makes both certificate requests use Let's
Encrypt's staging environment instead of issuing real, trusted certificates — useful if you're
rehearsing and might fail-and-retry several times, since real issuances are capped at 5 per domain
set per rolling week. **Unset it (or don't set it at all) for the actual cutover run** — a staging
certificate is not trusted by real browsers and §6's acceptance check will not pass with one.
