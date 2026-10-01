# Running and hosting the AI-MAP tools

Two processes, one database:

- **Collection server**: serves the web questionnaire, the dashboard, and receives submissions.
  Needs a public HTTPS address, because respondents load it in a browser.
- **Telegram bot**: long polling, so it makes only *outbound* connections to Telegram. **No public
  IP, no open port, no inbound firewall rule, no TLS certificate of its own.**

Both write through `tools/aimap_db.py` to the same SQLite file. `AIMAP_DB` must be identical for
both, or you get two datasets and the mode comparison the citizen-survey design depends on becomes
impossible.

> **The bot must run on the same host as the server.** Its lack of a public IP means no inbound
> port; it does **not** mean the bot can live somewhere else. SQLite is a local file, not a service:
> two processes share it by sharing a filesystem. Running the bot on a laptop while the server is
> hosted gives you two databases that never reconcile, and the failure is silent, because each one
> looks healthy on its own. Do not put the file on NFS or SMB either; SQLite's locking is not safe
> across those, and a corrupted field database has no undo.
>
> If the bot genuinely has to run elsewhere, do not point it at a copied file. Either move both
> services to that host, or change the bot to submit through `POST /api/submit` like any other
> client, which is a code change, not a configuration one.

### What syncs, and what does not

| | Shared across channels? | |
|---|---|---|
| Completed responses | **Yes** | One `responses` table, `mode` recorded as a variable, not two systems reconciled later |
| Scores | **Yes** | Computed on ingest by one reference implementation, whichever channel wrote the row |
| Progress heartbeats | **Yes** | One `partials` table, so drop-off is comparable by channel |
| Invitation codes | **Yes** | A code minted in Telegram redeems on the web and vice versa, so a referral chain can cross channels and still be one chain |
| Targets, quotas, flag rates | **Yes** | The dashboard reads the same file both processes write |
| **A half-finished questionnaire** | **No** | See below |

A respondent who abandons the Telegram bot partway cannot pick up where they left off in a browser.
That is a deliberate limit, not an oversight: linking a browser session to a Telegram account needs
an identifier, and the consent text promises not to collect one. Within a channel, resumption works: the bot restores the session on `/start`, and the web form offers to restore its local draft.

If cross-channel resumption is wanted later, the way to get it without breaking the promise is an
opt-in resume code the respondent chooses to carry, on the same mechanism as the invitation codes.
It is not built.

---

## 1. Local, in five minutes

```bash
cd /path/to/AImaping

python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

export AIMAP_ADMIN_TOKEN=$(openssl rand -hex 32)
export AIMAP_BOT_TOKEN='123456:ABC...'        # optional at this stage

./run-all.sh
```

That starts the collection server (questionnaire **and** dashboard), and the Telegram bot together,
both pointed at the same database by construction: `run_all.py` resolves the path once and hands
the same absolute value to both children. Ctrl-C stops both, and if either dies the other is stopped
too, so you never end up with a server quietly collecting while the bot has been dead for an hour.

Leave `AIMAP_BOT_TOKEN` unset and it starts the server alone and tells you the bot was skipped.

To run the two separately, which is what the systemd units below do, so each can be restarted on its
own: use `./run-server.sh` and `./run-bot.sh`.

Open <http://127.0.0.1:8000>. To also run the bot, in a second terminal:

```bash
export AIMAP_BOT_TOKEN="123456:AA..."      # from @BotFather
./run-bot.sh
```

Check that both are landing in one place:

```bash
curl -s http://127.0.0.1:8000/api/stats | python3 -m json.tool
```

`by_mode` should show `web` and `telegram` under the same instruments.

> **Use a dedicated venv.** On this machine `python3` currently resolves to an unrelated project's
> virtualenv, so a bare `pip install` would install into that. The `run-*.sh` scripts always use
> `./.venv/bin/python` and refuse to start if it is missing.

---

## 2. Setting up the Telegram bot

### Getting the token

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Give it a **display name**: what respondents see, e.g. `AI-MAP Ethiopia`.
4. Give it a **username**: must be unique across Telegram and must end in `bot`,
   e.g. `aimap_ethiopia_bot`. This one matters operationally: invitation deep links are built
   from it (`https://t.me/aimap_ethiopia_bot?start=ref_ABC123`), so it will appear on
   printed material and in people's chat histories. Changing it later breaks every link
   already handed out.
5. BotFather replies with the token:

   ```
   123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```

   **This token is the bot.** Anyone holding it can read every message sent to it and post as
   it. Treat it like a password: never commit it, never paste it into a chat or an issue.
   If it leaks, `/revoke` in BotFather issues a new one and invalidates the old immediately.

### Where to put it

| Running with | Set it here |
|---|---|
| `docker compose` | `AIMAP_BOT_TOKEN=` in `.env` (gitignored: see `.env.example`) |
| `./run-all.sh` | `export AIMAP_BOT_TOKEN='123456:AAH...'` |
| systemd | `/etc/aimap/aimap.env`, `chmod 600`, owned by root |

Leave it empty and the questionnaire and dashboard run normally without a Telegram channel; the
bot says so and stops. That is a supported configuration, not a broken one.

### What the bot configures by itself

**Do not use `/setcommands`.** The bot registers its own command menu with Telegram on every
start, so the menu cannot drift from the handlers actually installed:

```
start     - Begin, or carry on where you left off
progress  - How far you have got, and how long is left
invite    - Get a link to pass on to someone else
restart   - Start over from the beginning
privacy   - How your answers are handled
help      - What this bot is for
```

Worth setting by hand in BotFather, because respondents see them before they ever press Start:
`/setdescription` (shown on the empty chat screen), `/setabouttext` (shown on the bot's profile), and `/setuserpic`. Say plainly who is running the study and that participation is anonymous; this
is the first consent-relevant text anyone reads.

### Confirming it works

```bash
docker compose logs bot | grep authenticated
# 2026-09-12 ... INFO aimap authenticated with Telegram as @aimap_ethiopia_bot (id 123456789)
# 2026-09-12 ... INFO aimap invitation links will look like https://t.me/aimap_ethiopia_bot?start=ref_ABC123
```

That line only appears once Telegram has accepted the token, so it is the proof. Then open the bot
in Telegram and send `/start`.

### One token, one running bot

Telegram allows a single long-polling consumer per token. Start a second copy: `./run-all.sh` on
a laptop while `docker compose` is running on the server, say, and the two will fight over
`getUpdates`, each stealing messages from the other, and respondents will see the conversation
stall mid-question. There is no error that makes this obvious from the respondent's side.

**Use a second bot with its own token for testing.** Ten seconds in BotFather, and it keeps the
field bot's chat history clean of test traffic.

### Why polling, not webhooks

Polling needs no webhook, no certificate and no inbound firewall rule, and it recovers by itself
from the network interruptions the paper documents. Do not switch to webhooks without a specific
reason.

---

## 3. Docker (recommended)

Two containers from **one image**, sharing **one volume**. They run the same code because they
must produce identical scores, and they share a volume because SQLite is a local file: the bot
needs no inbound port, but it does need the same filesystem as the server.

```bash
cp .env.example .env
nano .env                      # set AIMAP_ADMIN_TOKEN, and AIMAP_BOT_TOKEN if you have one
docker compose up -d --build
docker compose logs -f
```

That is the whole deployment. The compose file pins both services' database path to `/data/aimap.db`
from a single YAML anchor, so they cannot be pointed at different files without editing one line
that visibly serves both.

| | |
|---|---|
| Survey | `http://127.0.0.1:8000/` |
| Dashboard | `http://127.0.0.1:8000/dashboard.html` |
| Data | Docker volume `aimap-data`, surviving `down`, `up` and rebuilds |
| Telegram | Outbound only: no published port on the bot container, ever |

`AIMAP_BIND` in `.env` controls the host side. It defaults to `127.0.0.1:8000` **on purpose**: this
is plain HTTP, and the consent text promises respondents that their answers travel securely. Put
Caddy or nginx in front for TLS (§4, *TLS and reverse proxy*) before anyone outside your machine
sees it. Binding
`0.0.0.0:8000` and handing out the address is how a study ends up collecting personal data over
cleartext.

### Reading the state honestly

Each failure has its own signal, and none of them is "it looks fine":

```bash
docker compose ps -a
```

| What you see | What it means |
|---|---|
| bot `Exited (0)` | No `AIMAP_BOT_TOKEN`. Not an error: the Telegram channel is simply not configured |
| bot restart count climbing (`docker inspect aimap-bot --format '{{.RestartCount}}'`) | The token was rejected. `docker compose logs bot \| grep rejected` confirms it |
| bot `unhealthy` | The process is up but its event loop has stopped turning. The bot touches a liveness file every 30s from inside the loop; a stale mtime is the one liveness signal that cannot lie |
| server `unhealthy` | `/api/stats` stopped answering: the database is unreadable, not merely the process gone |

A crash-looping container never leaves health status `starting`, so a rejected token shows up as a
climbing restart count rather than as `unhealthy`. That is the check to run.

### Everyday operations

```bash
docker compose logs -f server                  # follow one service
docker compose restart bot                     # after changing the token in .env
docker compose up -d --build                   # after changing code or the schema
docker compose down                            # stop; the volume and its data survive
docker compose down -v                         # stop AND DELETE the responses. There is no undo

# exports, straight out of the running container
docker compose exec -T server python -c "
import sys; sys.path.insert(0,'tools'); import aimap_db as db
cols, rows = db.export_rows('ORG'); import csv; w=csv.writer(sys.stdout); w.writerow(cols); w.writerows(rows)
" > aimap-ORG.csv

# a consistent copy of the database, safe against a live writer
docker compose exec -T server sqlite3 /data/aimap.db ".backup '/data/snapshot.db'"
docker compose cp server:/data/snapshot.db ./aimap-$(date -u +%Y%m%d).db
```

`docker compose cp` of a live SQLite file without `.backup` first will hand you an archive that
restores to a corrupt database. The extra step is not optional.

### Nightly backups

```bash
docker compose --profile backup up -d
```

An opt-in third container running `sqlite3 .backup` once a day into the `aimap-backups` volume,
keeping `AIMAP_BACKUP_KEEP` days. Copy that volume somewhere else regularly: a backup on the same
host as the database is a copy, not a backup.

### Updating

```bash
git pull
docker compose up -d --build
```

The image rebuilds, containers are replaced, the volume is untouched. Run
`./.venv/bin/python tools/scripts/validate_schema.py` before deploying a schema change: the
container will happily serve a broken questionnaire.

---

## 4. Hosting without Docker

### Where

The paper argues about data sovereignty, so the deployment should not contradict it. Ranked:

| Option | Notes |
|---|---|
| **Ethiopian hosting** (university data centre, Ethio Telecom / local IaaS) | Best alignment with Proclamation 1321/2024, no cross-border transfer question, lowest latency for respondents |
| **Host institution's own infrastructure** | Usually the pragmatic choice for a university-led study; document the transfer basis |
| Generic cloud (Hetzner, DigitalOcean, AWS) | Works, but you must state the cross-border transfer basis in the consent text and ethics submission |

Requirements are modest: the questionnaire is a few tens of kilobytes and SQLite handles this
volume comfortably. **1 vCPU / 1 GB RAM / 20 GB disk** is ample for the target of 4,900 responses.

### Steps (Debian/Ubuntu)

```bash
sudo adduser --system --group --home /srv/aimap aimap
sudo -u aimap git clone <your-repo> /srv/aimap        # or rsync the directory
cd /srv/aimap
sudo -u aimap python3 -m venv .venv
sudo -u aimap ./.venv/bin/pip install -r requirements.txt

sudo mkdir -p /etc/aimap
sudo cp deploy/aimap.env.example /etc/aimap/aimap.env
sudo chmod 600 /etc/aimap/aimap.env
sudo nano /etc/aimap/aimap.env        # set the two tokens

sudo cp deploy/aimap-server.service deploy/aimap-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aimap-server aimap-bot
systemctl status aimap-server aimap-bot
```

The unit files are hardened: `ProtectSystem=strict` with write access only to
`/srv/aimap/tools/data`.

### TLS and reverse proxy

**Caddy** is the least work; it obtains and renews certificates automatically:

```bash
sudo apt install caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile        # set your hostname and admin IP ranges
sudo systemctl reload caddy
```

**nginx + certbot** if you prefer: `deploy/nginx-aimap.conf`, then
`sudo certbot --nginx -d survey.example.et`.

Both configs restrict `/admin/*` by IP *in addition to* the token. The token alone is sufficient, but
keeping the export endpoints off the open internet means a leaked token is not immediately a data
breach.

---

## 5. Configuration

| Variable | Used by | Notes |
|---|---|---|
| `AIMAP_DB` | both | **Must be identical for both processes.** Default `tools/data/aimap.db` |
| `AIMAP_ADMIN_TOKEN` | server | Required. Admin endpoints return 503 without it, 401 on mismatch |
| `AIMAP_BOT_TOKEN` | bot | From @BotFather |
| `HOST`, `PORT` | `run-server.sh` | Default `127.0.0.1:8000` |

Generate the admin token with `openssl rand -hex 32`. Never commit it; `.gitignore` already excludes
the database.

---

## 6. Operating during field work

```bash
# progress by instrument and channel (public, safe to share with the team)
curl -s https://survey.example.et/api/stats | python3 -m json.tool

# data quality: flag rates and the mean self-vs-computed maturity gap
curl -s -H "x-admin-token: $TOKEN" https://survey.example.et/admin/quality | python3 -m json.tool

# analysis export
curl -s -H "x-admin-token: $TOKEN" \
  "https://survey.example.et/admin/export.csv?instrument=ORG" -o aimap-ORG.csv

# re-score from the reference implementation, never trust client-side scores
./.venv/bin/python tools/scripts/scoring.py --rescore aimap-ORG.csv

# follow-up contact list (kept separate from responses)
curl -s -H "x-admin-token: $TOKEN" https://survey.example.et/admin/contacts.csv -o contacts.csv

# once follow-up closes: required by the data-management plan
curl -X DELETE -H "x-admin-token: $TOKEN" https://survey.example.et/admin/contacts
```

```bash
# sector league table, which sector is ahead, on what
curl -s -H "x-admin-token: $TOKEN" https://survey.example.et/admin/sectors | python3 -m json.tool
```

### Getting into the dashboard

Open `https://survey.example.et/dashboard.html`. An unauthenticated visitor gets a **sign-in page**,
not the dashboard: the page is gated as well as the data, so a scanner does not learn that an admin
surface is here to be attacked. Paste the value of `AIMAP_ADMIN_TOKEN` and sign in.

What that gives you is a **session cookie**, not a stored token:

| | |
|---|---|
| `HttpOnly` | JavaScript cannot read it, so a script injected into the page cannot steal it |
| `SameSite=Strict` | never sent on a request originating from another site |
| `Secure` over HTTPS | set automatically when the request arrived over TLS |
| 12 hours | one field working day, then sign in again |
| Server-side | held in the server's memory, so **restarting the server signs everyone out**, and the ⎋ button in the header is a real logout rather than a cleared browser field |

Scripts and `curl` still send `X-Admin-Token:` instead; that is what the export commands below use.
Both routes are checked in constant time, and **five wrong attempts from one address locks that
address out for five minutes**. An already-valid session is unaffected by someone else's failures,
so a brute-force attempt from behind the same office NAT cannot lock out the team.

Every admin request is written to the `aimap.audit` logger, who, what path, and whether it was
accepted. Under Proclamation 1321/2024 you need to be able to say who looked at the response data
and when; this is that record.

```bash
journalctl -u aimap-server | grep aimap.audit      # or: docker compose logs server | grep audit
```

**The token is a password.** Generate it with `openssl rand -hex 32`, never a memorable phrase.
Anyone holding it can read every response.

Look at it **daily**, not weekly and not at the end. The Overview tab evaluates the triggers from
`tools/schema/sampling.json` and tells you which ones have been crossed and what to do about each.
Five of them cannot be recovered afterwards:

| What to watch | Why it cannot wait |
|---|---|
| Flag rate above 10% in a channel | Every further response from that channel is also unusable |
| Drop-off at one question above 15% of starts | It is a wording problem; fixing it mid-wave costs a documented change, fixing it after costs the item |
| An enumerator below 0.6× the team median | Re-contacting their respondents is possible this week and not next month |
| Any client-versus-server score divergence | A stale deployed build is still collecting; investigate the same day |
| A quota cell below 50% at the halfway point | Cells do not catch up on their own: field effort has to be redirected while there is still field time |

The **Findings & report** tab produces a Markdown draft with every figure carrying its `n` and its
caveat, for pasting into the paper. It is a draft, not an output: read it before you send it
anywhere.

Two things the dashboard deliberately will not do. It will not show a figure computed over fewer
responses than the minimum in `sampling.json`; it shows the reason instead, because a caveat under
a number does not stop the number being quoted. And it will not pool the citizen panel with the
enumerator booster into a single national figure; that number is the most misleading one this study
could produce, so it is not computed anywhere.

**There is no Telegram dashboard, on purpose.** Fieldwork is not supervised from a chat client, and
an admin surface reachable by anyone who finds the bot is a credential leak waiting for a careless
forward.

### If the dashboard shows no drop-off at all

That means no position heartbeats are arriving, not that nobody is abandoning the questionnaire.
Check that `POST /api/progress` is reachable: a reverse proxy that only forwards `/api/submit`, or
a CSP that blocks the beacon, produces exactly this symptom, and it reads as good news.

```bash
curl -s -X POST https://survey.example.et/api/progress \
  -H 'Content-Type: application/json' \
  -d '{"response_id":"probe","instrument":"CIT","mode":"web","pct":10}'
# expect {"ok":true}
```

### Referral chains

```bash
# recruitment edges, for computing RDS weights outside this tool
curl -s -H "x-admin-token: $TOKEN" \
  "https://survey.example.et/admin/chains.csv?instrument=IND" -o chains-IND.csv
```

A code identifies the *inviting response*, never a person. An unresolvable code is logged and the
response reclassified to the open arm rather than recorded as a referral: a chain with an invented
parent corrupts every RDS weight below it.

### Backups

```bash
sudo cp deploy/backup.sh /srv/aimap/deploy/
sudo crontab -u aimap -e
#   0 2 * * *  /srv/aimap/deploy/backup.sh
```

Uses `sqlite3 .backup`, which is safe against a live writer: plain `cp` of a WAL-mode database is
not. Keeps 30 days by default and copies off-host if you point `AIMAP_BACKUP_DIR` at mounted storage.

---

## 7. Enumerators and offline work

The web questionnaire works with no network. Responses queue in `localStorage` and flush
automatically when connectivity returns.

For a laptop that will be offline all day:

1. Load `https://survey.example.et` once while online, so the page and schema are cached.
2. Collect responses offline; the header shows `offline · N queued`.
3. Back on a network, they submit automatically, or click **enumerator tools** in the footer and
   press *Try to submit all now*.
4. If a device may not come back online, export from the same panel as JSON or CSV and transfer the
   file.

Serving the questionnaire without the API server at all also works, for a purely offline device:

```bash
cd tools/web && python3 -m http.server 8080
```

Submissions then stay in the browser until exported. `tools/web/schema` is a symlink to
`tools/schema`, which `http.server` follows.

> The collection server mounts `/schema` explicitly rather than relying on that symlink, because
> `StaticFiles` refuses to follow symlinks out of its mount root. Without the explicit mount the
> questionnaire 404s on its own schema and will not load, which only shows up when you serve it the
> real way rather than with `http.server`.

---

## 8. Before you take respondents

- [ ] HTTPS working; HTTP redirects to it
- [ ] `AIMAP_ADMIN_TOKEN` set to a random 32-byte value, not the example
- [ ] `/admin/*` unreachable from the public internet (test from a phone on mobile data)
- [ ] Both services point at the **same** `AIMAP_DB`: `journalctl -u aimap-server -u aimap-bot | grep 'shared database'` prints two identical paths, and `/api/stats` shows
      `by_mode` counting both channels once a test response has gone through each
- [ ] Database file not inside any web-served directory
- [ ] Nightly backup running and a restore tested at least once
- [ ] Consent text names the real data controller and DPO, not the placeholder
- [ ] Cross-border transfer basis documented if hosting outside Ethiopia
- [ ] `/setcommands` configured on the bot; `/privacy` returns the right text
- [ ] Tested on a real low-end Android phone over mobile data, not only on a laptop

---

## 9. Troubleshooting

| Symptom | Cause |
|---|---|
| Questionnaire loads but shows "Could not load the survey" | `/schema/*.json` returning 404. Check the `/schema` mount and that `tools/schema/` shipped with the deploy |
| Telegram responses missing from the server's exports | The two processes have different `AIMAP_DB`. Both announce the resolved absolute path at startup in the same format: `journalctl -u aimap-server -u aimap-bot \| grep 'shared database'` should print two identical paths |
| `503 admin token is not set` | `AIMAP_ADMIN_TOKEN` missing from the unit's `EnvironmentFile` |
| `address already in use` | An earlier instance is still running: `lsof -nP -iTCP:8000 -sTCP:LISTEN` |
| Bot starts then exits | Bad token, or a second instance already polling: Telegram allows only one |
| `scoring_errors` above zero in `/admin/quality` | A bug in `tools/scripts/scoring.py`. Responses are stored and flagged, not lost: fix, then `scoring.py --rescore` |
| `client_divergence` rising | Enumerators running a stale cached build of the web form. Hard-refresh their devices |
| `database is locked` | Two processes on different filesystems, or a network mount. SQLite WAL needs real local storage |
