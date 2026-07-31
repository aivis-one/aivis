# AIVIS.ONE — Manual Deploy & Operations Runbook

> **This repo is PUBLIC.** This document contains no secrets and never will — every credential it
> references is a POINTER to `AIVIS-Server/CREDENTIALS.md`, a file that lives outside this repo,
> outside git entirely, on the operator's own machine. If you don't have access to that file, get it
> from whoever manages the server before you start.
>
> This runbook exists so that running `scripts/install_aivis.sh` — and everything after it — is a
> job any operator can do alone, without having sat in on the sessions that built the script. It
> covers two different situations, not one — a brand-new machine and a re-install of a box that
> already has this stack on it — and says explicitly, at every point they diverge, which one you're
> doing. §1 asks you to decide which before you start.
>
> **This document has two parts, not one (decision 44).** Part One (§1-§8) is the install itself —
> follow it top to bottom and stop; nothing after it is required reading to get the product running.
> Part Two (§9-§12) covers the commands the install leaves permanently on the box — `aivis update`,
> `aivis backup`, and the rest — for whenever you come back to operate a live box later. Decision 33
> makes both the same person's job, by hand, forever, which is why they live in one file instead of
> two.

---

**PART ONE — INSTALL**

## 1. Before you start — decide which install this is, then gather what you need

**This runbook covers two permanent situations, not one:**
- **Clean-box install** — nothing at `/opt/aivis` yet on this machine. This is what a brand-new
  production box gets: production eventually migrates to a new machine, and this is the path that
  runs there.
- **Re-install** — `/opt/aivis/repo` already exists on this box. This is what today's box gets, every
  time, from now on. A re-install tears down the running containers and the cloned code, but it does
  **not** touch the nginx site files, the certificates, the deploy user, `/opt/aivis` itself,
  `/root/.mc/config.json`, or the deploy key — several prompts and checks below behave differently as
  a result, and are marked **RE-INSTALL:** where that matters. **It also doesn't touch the host-level
  packages the script installs** — Docker, Nginx, Certbot, the `mc` CLI. Each of those is only ever
  installed once; every later run, including this one, finds them already present and leaves the
  version exactly as it was. A re-install is not a way to upgrade any of them.

Know which one this is before you continue — you cannot tell from the script's banner, only from
whether `/opt/aivis/repo` exists on the box you're on.

What to have ready either way:

- **The Telegram bot token** (`AIVIS-Server/CREDENTIALS.md` §2, the target `@aivisonebot` row) —
  you'll type this in during the install, once.
- **A browser tab open on GitHub → `aivis-one/aivis` → Settings → Deploy keys**, logged in as
  someone with admin rights on the repo. On a clean-box install you'll paste a key here mid-install
  and the script will wait for you; on a re-install you likely won't need to touch this tab at all
  (§4 item 2).
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

**A mismatch here is not automatically a tampered download — a fresh `git clone` can produce one on
its own.** If you compare against a hash taken by running `sha256sum` on a file checked out of *your
own clone* rather than the command above, and that clone was made with `core.autocrlf=true` (a
common default on Windows), git rewrites the file's line endings the moment it's checked out — the
bytes on disk are no longer the bytes in the git blob, and that `sha256sum` will never match,
regardless of whether the download is genuine. The command given above
(`git show main:scripts/install_aivis.sh | sha256sum`) reads the blob directly and is immune to
this; use it, don't run `sha256sum` on a file your clone checked out. **Always compute the
comparison hash fresh, in this same session** — a value copied from an earlier chat, note, or
transcript is a hash of whatever commit was current back then, not of what you're installing now,
and a stale value will read as a tampered download even when nothing is wrong.

## 4. Every prompt, in the order you will actually meet them

The script pauses **nine times on a clean-box install** — **ten** on a re-install, where prompt 1
below also fires. Each one is listed here in execution order, with the exact answer.

1. **`Remove existing installation and start fresh? (y/n)`** — only appears on a **RE-INSTALL**
   (§1); skip straight to item 2 on a clean-box install.
   **`y` here is destructive far beyond the code.** It runs `docker compose down -v`, and the `-v`
   removes the named Docker volumes — the Postgres database, Redis, and every object stored in
   MinIO, not just the running containers. It then deletes `/opt/aivis/repo` entirely, which takes
   `backend/.env` with it: **every credential in that file that you have not already copied into
   `AIVIS-Server/CREDENTIALS.md` is gone for good the instant you answer `y`.** Treat this prompt as
   if it read "delete the database, forever?" — on a box carrying real data, that is exactly what it
   does; today's box is empty enough that the cost is low, but the prompt does not know which box
   it's running on. **Anything other than `y` aborts the script immediately** — there is no "keep
   what's there and continue" option, so don't answer this one absent-mindedly.
   **A second, quieter failure lives in the same line.** If the script's `cd` into the old install
   directory fails for any reason, the teardown command is silently skipped — but the directory
   removal that follows still runs regardless. The result is a wiped `/opt/aivis/repo` with the old
   Docker volumes left behind and still consuming disk, and nothing the script prints tells you
   which of the two outcomes you got. If in doubt, check yourself afterward: `docker volume ls |
   grep aivis`.
2. **`Press ENTER after adding the deploy key to GitHub...`**
   - **CLEAN-BOX:** the script generates a fresh SSH keypair and prints the public half to your
     terminal just before this prompt. Copy it, go to the GitHub tab you opened in §1, add it as a
     Deploy Key with **Read/write access checked** (`update` later commits and pushes a regenerated
     file — a read-only key breaks that later, and loudly, not silently: the push fails with a printed
     error and recovery steps, but only whenever `update` first needs to push, which may be long after
     this key was added). **Only press ENTER once the key is
     visibly saved on GitHub's page**, not right after pasting it — the very next thing the script
     does is `git clone` using that key, and it fails if the key hasn't actually landed yet.
   - **RE-INSTALL:** the script does **not** generate a new key if one already exists on the box at
     `/root/.ssh/id_ed25519_aivis_deploy` — it just reprints the same public key you already added
     to GitHub during a previous install. Adding it again is a no-op at best and a rejected duplicate
     at worst. **Correct action: press ENTER immediately.** Waiting for the key to "become visibly
     saved" describes something that will never happen here, because it already is.
   - **Either path:** the line the script prints right after this ("GitHub SSH connection verified"
     / "Could not verify GitHub SSH connection. Proceeding anyway.") does not gate anything — its
     failure branch only warns and lets the script continue, so neither outcome tells you anything
     reliable. **The real check is the `git clone` immediately after it**: if the key genuinely isn't
     on GitHub, or lacks write access, that step fails outright and stops the script (see §8).
3. **Telegram Bot Token** — type the value from `CREDENTIALS.md` §2 (the `@aivisonebot` row).
   **This prompt, and every secret prompt through item 9 below, uses hidden input: the terminal
   shows nothing as you type, not even asterisks.** That's deliberate — a secret typed here never
   lands in your terminal scrollback — but if you don't expect it, typing a long token into total
   silence reads exactly like a frozen terminal. It isn't: type the full value and press Enter;
   nothing appears on screen until you do.
4. **SumSub API Key (optional)** — press **ENTER**. No KYC integration exists in this project.
   **Pressing ENTER does not leave this field empty** — it keeps whatever `.env` already holds
   (`SUMSUB_API_KEY=PLACEHOLDER` on a fresh install), a non-empty placeholder string, not a blank
   one. That's expected and harmless; `CREDENTIALS.md` §6 has no real value to give you here.
5. **SumSub Secret Key (optional)** — press **ENTER**, same reason: `.env` keeps the `PLACEHOLDER`
   string it already had, not an empty value.
6. **Mailgun API Key (optional)** — type the value from `CREDENTIALS.md` §3 if you have it handy, or
   press **ENTER** to keep whatever `.env` already holds (`PLACEHOLDER` on a fresh env, or an
   earlier install's value on a re-install) — again not an empty field. Either is fine — mail is out
   of scope this wave (§7).
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
    it will not show you again this run. Copy it down even if you're not adding it right now (mail/DKIM
    is out of scope for this migration wave — see §7) — you'll need it whenever that work does happen.
    **On a RE-INSTALL, this is very likely the SAME record as last time, not a new one:** the DKIM key
    pair is only generated if it doesn't already exist on the box — the same guarded pattern as the
    deploy key at item 2 — and nothing in the wipe branch touches it. If you already added a DKIM TXT
    record from an earlier install, you don't need to add this one again; copying it down still costs
    nothing and confirms the two match.
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

**Renewal-failure notices from Let's Encrypt go to `admin@aivis.one`** — fixed in the script, not
something you configure here. Confirm that mailbox is actually read before you rely on this cutting
over cleanly again in 90 days: nothing else in this install surfaces a silent renewal failure.

**On a RE-INSTALL, two valid lineages here is not proof this run did anything.** The teardown in §4
item 1 never removes certificates, so if they were already valid from an earlier install, this
command reports them as fine whether or not this run's certificate steps changed anything at all —
and both of those steps end in `|| warn`, so a failure in them is silent. **A check that cannot fail
here is not a check; treat this command as informational, not as proof.** The two `curl` lines below
are what actually gate the install.

```
curl -s https://api.aivis.one/health
curl -s https://app.aivis.one
```
The first should return JSON with `"status":"ok"` (and `"db":"ok"`, `"redis":"ok"`). The second
should return the frontend's HTML, HTTP 200.

**If either HTTPS `curl` above hangs, refuses the connection, or fails TLS — while `sudo certbot
certificates` just showed a valid, non-staging lineage covering that domain — this is the specific
failure to expect on a RE-INSTALL, and it is reasoned, not something anyone has observed yet on a
real run.** The script rewrites the nginx site files from scratch on every install, and those files
are plain HTTP until `certbot --nginx --redirect` adds the TLS block back in; against a certificate
that's already valid for the same names, certbot can decide there's nothing to reissue and skip
adding that block, and because that certbot call ends in `|| warn`, nothing in the script's own
output would flag it. The result is a site serving plain HTTP again even though the certificate
itself is fine, and `sudo certbot certificates` above cannot see the difference. **Repair:**
```
certbot --nginx -d api.aivis.one -d app.aivis.one
```
Run the same shape against `storage-mc-admin.aivis.one` on its own if that site shows the identical
symptom — it's a separate certificate lineage, issued by a separate `certbot` call in the script,
and carries the same risk for the same reason.

**Also verify — do not assume — that `https://storage-mc-admin.aivis.one` is reachable again.** The
script re-links this site's nginx config unconditionally on every run, clean-box or re-install
alike. That's the desired outcome: it closes any earlier credential exposure by pointing the site at
the fresh MinIO console password this run just generated. But it hasn't been checked yet at this
point in the runbook:
```
curl -s -o /dev/null -w "%{http_code}\n" https://storage-mc-admin.aivis.one/
```
**No `-k` here, deliberately** — this domain used to carry a hard TLS failure while its console site
was disabled, and `-k` was right for that. After a re-install it carries a real Let's Encrypt
certificate, and this line sits directly under the GAP-6 risk above (a re-install silently leaving a
site on plain HTTP). Skipping TLS verification would hide exactly the failure this check exists to
catch, so run it without `-k`. Expect `401` — the basic-auth gate is active, TLS is fine, and this is
not a broken site. If the command instead fails outright (connection refused, certificate error), that
failure IS the TLS symptom from the GAP-6 branch above — go there and use the repair command. Any other
non-`401` result means the basic-auth gate itself isn't serving correctly.

**Record the three MinIO values this run just generated — nothing in the install does it for you.**
§4 items 7-9 had you press ENTER three times; the resulting random values live in
`/opt/aivis/repo/backend/.env` under these names:
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `MINIO_CONSOLE_BASIC_AUTH_PASSWORD` — the password the `401` check just above is gating, and the one
  you actually need to open `https://storage-mc-admin.aivis.one` in a browser.

**Treat all three as gone for good the moment you next answer `y` at §4 item 1.** That prompt deletes
this exact `.env` file and tears down the running containers in the same run. This runbook makes no
claim about any other place these values might also happen to exist — record them now, on the
assumption that this is the only chance you get.

Read them off the box:
```
grep -E '^(MINIO_ROOT_USER|MINIO_ROOT_PASSWORD|MINIO_CONSOLE_BASIC_AUTH_PASSWORD)=' /opt/aivis/repo/backend/.env
```
**That command prints the values to your screen — do not run it during a screenshare or a recorded
session.** Copy the three into `AIVIS-Server/CREDENTIALS.md` yourself, by hand, right now. Nothing in
this runbook writes them anywhere for you, and no agent should ever be asked to do that copying either
— it's exactly how a previous set of these same three values ended up exposed.

**These three are not the only secrets `.env` holds — the rest get no prompt at all, and that's
expected.** The database password, the Redis password, the session-signing key, two webhook secrets,
and the backend's own MinIO service-account pair (separate from the root credentials above) are all
generated the same way at install time: silently, never shown on screen, never asked about. **None of
it needs recording, by you.** Every one of them regenerates from scratch on the next install, and the
systems they authenticate — the database, Redis, and the object store — are destroyed by that same `y`
at §4 item 1. This step asks nothing of you: no value here requires action on your part, and there is
nowhere you need to copy anything to.

**That is a statement about what you need to do, not about what the box does on its own.** The daily
backup (§11) already keeps its own, separate, unencrypted trail of these same values regardless of
anything you do here — that trail exists whether or not you act on this paragraph, and this paragraph
still asks nothing of you. If the backup's retention matters to you, §11 is where it's covered.

**That holds only as long as it stays true that nothing outside this box has a copy of any of them —
which is the case today.** If a crypto payment provider or any other external service is ever
configured with `CRYPTO_WEBHOOK_SECRET` (or any of the other six), a re-install silently invalidates it
without telling anyone; that is the one circumstance under which this paragraph stops holding.

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

- **A wall of OS/RAM/disk/DNS warnings before you see any prompt at all.** The very first thing the
  script does, before item 1 of §4, is a set of automated checks — OS version, RAM, disk space, and DNS
  resolution for all four subdomains — and every one of them only ever warns, never aborts the script.
  Several `[WARN]` lines scrolling by before you've typed anything is normal, not a sign the install has
  already failed. **The DNS ones are worth reading anyway** — a warning that a domain doesn't resolve to
  this box yet is telling you, right at the start, about the exact certificate failure you'd otherwise
  only meet later at §5/§8; fixing the DNS record before the script reaches certbot avoids the retry.
- **Ubuntu's default nginx site disappears.** The script removes
  `/etc/nginx/sites-enabled/default` unconditionally while writing its own site files. Harmless on a
  box dedicated to this product (the only case this runbook covers) — worth knowing only if this nginx
  instance is ever asked to serve anything else, since that config is gone without asking.
- **`docker compose build` starts by pruning the entire host's Docker build cache**, not just this
  project's. Same as above — harmless on a dedicated box, worth knowing if this box is ever asked to
  build anything else with Docker.
- **A live mail relay starts on this box regardless of whether product mail is ever configured.**
  Postfix and OpenDKIM are installed and started unconditionally by this section — this isn't optional,
  and nothing in this runbook turns it off, whether or not decision 30's mail features are ever used.
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
  saved without write access, before you pressed ENTER. **On a RE-INSTALL there's a second possible
  cause with the identical symptom:** the script reuses whatever deploy key already exists on the
  box rather than generating a new one (§4 item 2), so if an *earlier* install ever added that same
  key to GitHub as read-only, this step fails for a permissions reason that has nothing to do with
  today's run. Either way, go back to the GitHub tab, confirm the key is really there with
  Read/write access, then re-run.
- **The app health check times out (`App did not respond within 120s`), but the script does not stop
  there.** It's a warning, not an abort — the very next steps (the `mc` alias, database migrations,
  seeding) all assume the app and its dependencies are actually up. If the app genuinely isn't healthy,
  one of those steps — most likely the migration step right after — fails immediately, with nothing
  protecting it. A health-check warning followed by a hard failure a few lines later is one connected
  problem, not two: check `docker compose logs app` for why the app never became healthy.
- **A seeding step fails** partway through — generic application-level issue at that point, not
  specific to this being a fresh install. Check `docker compose logs app` from
  `/opt/aivis/repo`.
- **Mail service restart (OpenDKIM/Postfix) reports a warning, not a failure** — this used to abort
  the whole install; it no longer does. If you see the warning, the install continued regardless;
  mail itself is out of scope this wave (§7 above) so this is not something to fix right now.

**This list is not exhaustive, and it cannot be — read this before assuming a failure you hit isn't
covered above.** Every command in this script runs under a blanket trap that catches any unhandled
failure anywhere in the file: `[ERROR] Installation failed at line N` is not vague noise — `N` is a
literal, directly-readable line number in `scripts/install_aivis.sh`, and opening the file to that line
is a real next step, not a formality. The points listed above are the ones common enough, or
consequential enough, to walk through individually; any *other* command failing anywhere in the
script's roughly two thousand lines aborts exactly the same way, even though it isn't named here.

**The permanently-installed `/opt/aivis/aivis` management script (Part Two) does not work this way.**
Unlike the installer, it has no equivalent blanket protection — each of its commands only stops on a
failure if that specific line explicitly checks for one. This is why, for example, `aivis db restore`
(§11) can print "✓ Database restored" even after a restore that partly failed: the installer would have
caught and stopped on that kind of failure; the management script it leaves behind does not.

**One knob worth knowing about if you expect to retry more than once:** setting
`AIVIS_CERTBOT_STAGING=1` before running the script makes both certificate requests use Let's
Encrypt's staging environment instead of issuing real, trusted certificates — useful if you're
rehearsing and might fail-and-retry several times, since real issuances are capped at 5 per domain
set per rolling week. **Unset it (or don't set it at all) for the actual cutover run** — a staging
certificate is not trusted by real browsers and §6's acceptance check will not pass with one.

---

**PART TWO — OPERATING THE BOX AFTER INSTALL**

Everything from here on is a different moment in time from Part One, not a different reader. It
documents `/opt/aivis/aivis` (symlinked to `/usr/local/bin/aivis`) — the management script the install
leaves permanently on the box — and what its commands actually do once the box is live. You do not
need any of this to install the product; come back to it when you're about to run one of these
commands, not before.

## 9. `aivis update` — the command you will run for the rest of this product's life

The single most important thing to know before you ever run it: **a plain `aivis update` takes the
whole site offline for the entire run, not just the backend.** `docker compose down` with no service
name stops every container, frontend included; only the backend, database, Redis, and MinIO come back
immediately after. The frontend does not return until the very end — after the backend image rebuilds,
migrations run, the database reseeds, a smoke check runs, and (unless you pass `--skip-tests`) the full
test suite runs. If you assumed `update` was a quick, low-impact refresh, it isn't: budget for a full
outage window, not a blip. `aivis update --frontend-only` is the one mode that skips all of this — it
refuses outright if anything backend-side changed in the pulled commits, so it can't silently do the
wrong thing, but when it does run, only the frontend goes down.

**A failed migration and a failed test suite are not the same kind of failure, even though both can
print in red.** If the database migration fails, or the post-seed smoke check fails, `aivis update`
stops right there — the frontend rebuild never happens, and the site stays down until you fix whatever
broke and re-run it. If instead the *test suite* fails, the update keeps going: the frontend still
rebuilds and comes back up, on the theory that a broken test shouldn't take a working site offline —
only the command's own exit code tells you something failed. Read the last few lines of output rather
than assuming "it printed red, the site must be down" or "it finished, the site must be fine" — neither
follows automatically from the other here.

**`aivis update` can commit and push to the public GitHub repo without asking you first.** If the
regenerated OpenAPI-derived frontend types differ from what's committed, the script commits the change
under a bot identity (`aivis-bot`) and pushes it to `origin` on your current branch — automatically, no
confirmation. If you think of `update` as something that only touches this box, it doesn't: it can also
change the public repo's history. This is also why the deploy key needs write access (§4 item 2) — a
read-only key makes this specific step fail, loudly, with a printed error and recovery instructions,
but not until the first time a schema change actually triggers a push.

**Its own destructive confirmation prompt is the script's second one, and deserves the same reading as
§4 item 1's wipe prompt.** If `update` finds uncommitted changes in `/opt/aivis/repo`, it asks
`Discard local changes and update? (y/n)`. Answering `y` discards every edit to every file already
tracked by git in that checkout — if anyone has ever hand-edited a file directly on the server (a quick
fix, a config tweak), it is gone the moment you answer `y` here. Untracked new files are not touched,
only edits to files git already knows about. If you don't recognize the changes it's warning you about,
stop and look at them (`git -C /opt/aivis/repo status`) before answering — the prompt itself does not
tell you what the changes are, only that they exist.

**"✓ Update complete" is not the same assurance §6 asks you to get after an install.** The command's own
final check is a single local `curl` to the backend's health endpoint, checked only for the word
`"status"` in the response — no HTTPS, no browser, no CSP check. If you want the level of confidence §6
describes, repeat §6 by hand after an update; the command finishing successfully does not give you that
on its own.

## 10. `aivis status`

Read-only and safe to run anytime. One thing worth knowing if you're troubleshooting a certificate
problem: its check of the MinIO console domain skips TLS verification, the same kind of check §5's
GAP-6 discussion warns against trusting. A `✓` from `aivis status` on that one line does not rule out
the plain-HTTP regression §5 describes — if you suspect that failure mode, use §5's own check (or its
repair command), not this one.

## 11. `aivis backup` and `aivis db restore`

**`aivis db restore <file>` warns "This will overwrite the current database!" — against a database that
already has data in it, it does not actually overwrite.** The dumps this system produces (by `aivis
backup` or `aivis db dump`) are not built with a "clean" flag, so they contain no instruction to drop
existing objects first. Restoring one into a database that still has the old schema and data replays
the dump's statements on top of what's already there, which fails, statement by statement, rather than
cleanly replacing anything — and the command reports "✓ Database restored" whether or not any of those
statements actually succeeded, because (per §8) the management script has no built-in mechanism to
notice a partial failure. **Treat `db restore` as safe only against a database you have already emptied
or recreated** — restoring into a live, populated database is not the clean swap the prompt describes,
and you cannot rely on the printed output to tell you it went wrong.

**The daily backup keeps a rolling week of unencrypted copies of every secret in `.env` — including the
ones §5 tells you don't need recording.** `aivis backup` runs automatically every day (cron, 4 AM) and
archives `backend/.env` in full, alongside a database dump and a MinIO snapshot, into
`/opt/aivis/backups/` — a location the install's wipe (§4 item 1) never reaches, on a 7-day rotation.
§5 is still right that *you* don't need to act on this — every one of those secrets regenerates on the
next install regardless — but the box itself is quietly keeping week-old copies of them anyway, on
disk, without restricted permissions. Nothing in this runbook asks you to manage these files; it's
worth knowing they exist if that matters to you.

**The backup's MinIO half can fail without you finding out.** If mirroring the object-storage bucket
fails, the backup still completes — database and `.env` only — and prints a warning, but on the
scheduled daily run that warning goes into `/var/log/aivis-backup.log`, a file nothing in this runbook
or the script itself tells you to check. A backup that "succeeded" every night for weeks could still be
missing every object stored in MinIO; the only way to know is to read that log yourself.

## 12. A few more worth knowing

- **`aivis seed --reset` has no confirmation prompt at all** — unlike the install wipe, `update`'s
  discard, and `db restore`, this one just runs. It resets seeded storefront and test-account data with
  no "are you sure?" of any kind.
- **`aivis storage console` prints the MinIO Console URL and all three values §5 asks you to record by
  hand** — it's the box's own built-in equivalent of §5's `grep` command, and easier to remember. It
  doesn't change who does the recording: still read it yourself, still copy it into
  `AIVIS-Server/CREDENTIALS.md` by hand, still not on a screenshare.
- **After you hand-edit `.env`** (adding a SumSub or Mailgun key you skipped during install, per §4
  items 4-6) **the install's own completion banner tells you to run `aivis restart app`** — this
  runbook otherwise never mentions that step, but the app container needs a restart to pick up a
  hand-edited `.env`.
- **`aivis deploy` is a working, undocumented synonym for `aivis update`** — same command, absent from
  the script's own help text.
