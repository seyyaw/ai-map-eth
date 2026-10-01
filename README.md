# AI-MAP Ethiopia

A research program measuring how artificial intelligence is actually being adopted in
Ethiopia, and the tools used to field it.

This repository holds three things: the questionnaire and the software that collects
responses to it (web and Telegram), the planning documents and resources behind a
four-volume research series, and templates for drafting each of those four volumes.

---

## Layout

```
ai_map_research_program.docx   the research program proposal (unmodified source document)
ai_map_workstreams.docx        the workstream and assignment proposal (unmodified source document)
chapters/                      a template document for each of the four research volumes
resources/                     policy documents, reports and prior research to draw on while writing
tools/                         the questionnaire, the collection server, and the Telegram bot
docker-compose.yml             runs the collection server and the bot together, one shared database
Dockerfile                     one image, both roles
docs/                          study design decisions
deploy/                        systemd units and a Caddy config for a production host
DEPLOY.md                      hosting instructions
requirements.txt, run-*.sh     running the tools without Docker
```

## The research program

`ai_map_research_program.docx` and `ai_map_workstreams.docx` are the two planning
documents this repository is built around. They are kept exactly as written; nothing
in this repository edits them. Everything else here, the chapter templates, the
resource folder, the questionnaire, exists to carry out what they propose.

### Four volumes

The research program proposes a four-volume series. Each volume has a template in
`chapters/`:

| Volume | Central question | Template |
|---|---|---|
| I. The state of AI in Ethiopia | What activity and capabilities exist, and what can available evidence establish? | `chapters/volume-1-state-of-ai-in-ethiopia.docx` |
| II. AI adoption and value in practice | How does experimentation become sustained use, and what benefits result? | `chapters/volume-2-adoption-and-value-in-practice.docx` |
| III. Public priorities, language, and access | What do people need, who can participate, and who benefits? | `chapters/volume-3-public-priorities-language-and-access.docx` |
| IV. Institutional and investment choices | Which arrangements and investments are justified by the evidence? | `chapters/volume-4-institutional-and-investment-choices.docx` |

Each template is an outline, not a draft. Every point in it is written so it can be
acted on directly: it either names a specific existing resource (a chapter, a report,
a filename in `resources/`) that already supports the point, names the specific
survey question id(s) that will answer it once the questionnaire has been fielded, or
is flagged as a genuine evidence gap, naming which workstream would plausibly close
it. Volume I is the most developed of the four, since it is the nearer-term
deliverable and the one with the most existing material to draw on; Volumes II
through IV are lighter outlines to be built out as that work begins.

The mapping from survey sections to volumes lives in
[`tools/schema/common.json`](tools/schema/common.json) under the `"volumes"` key, so
it stays next to the schema it describes rather than drifting out of sync with it.

### Five workstreams

The workstreams document proposes organizing contributors into five streams: research
coordination and synthesis; policy and institutional landscape; research talent and
technical foundations; applications and organizational activity; and professional
perspectives and survey research. The evidence gaps flagged in each chapter template
are tagged by which of these streams would plausibly take them on, as a starting point
for assignment, not a final allocation.

## Resources

`resources/` holds the material gathered so far to write from:

- `resources/landscape-materials/`: government strategy documents and proclamations,
  ecosystem and funding reports, partner and multilateral reports, and academic
  research papers relevant to the Ethiopian AI landscape. Filenames are prefixed by
  kind (`gov-`, `ecosystem-`, `partner-`, `research-`) so the collection can be
  scanned without opening each file.
- `resources/curated-sources/`: a smaller, actively maintained set of primary
  sources with a README explaining what each one is good for and where it was
  retrieved from, including dated snapshots of web-only sources that would otherwise
  change without notice.
- `resources/mapping paper_v1.docx` and `resources/State-of-AI-Landscape-Assessment-Ethiopia.docx`,
  prior landscape mapping work that the research program document references as a
  foundation for this series.

When writing a chapter from its template, check `resources/` for the named file
before looking elsewhere; most of the pointers in the templates refer to something
already in this folder.

## The questionnaire

One questionnaire, not several: `tools/schema/questionnaire.json` defines every
section and question once. A respondent answers a short consent question, then a
single routing question asking whether they are answering on behalf of an
organization, as an individual practitioner, or as a member of the public. That
answer determines which of the three branches of the questionnaire they see; nothing
about the respondent's path is decided in advance. The web form and the Telegram bot
both render from this one file, so the two can never drift apart, and a response
collected through either channel lands in the same database.

Organization-branch section and question ids are unchanged from the project's
earlier, separate organizational instrument. Practitioner-branch ids are all prefixed
`P`; citizen-branch ids are all prefixed `Z`. This is only relevant if you are editing
the schema directly; it does not affect a respondent, who only ever sees one
continuous set of questions in plain language.

A short form exists for the practitioner and citizen branches (the organization
branch is long form only in chat, since its tables and matrices do not render
sensibly one message at a time): the respondent is offered a quick version right
after the routing question, and its answers pool with the full form's item by item
rather than being a second questionnaire.

`tools/schema/common.json` carries the shared configuration: instrument metadata,
the maturity and technical-depth ladders, the readiness index and its crosswalk to
external frameworks, validation rules, and the volume mapping described above.

## Running the tools

### With Docker

```bash
cp .env.example .env
nano .env                      # set AIMAP_ADMIN_TOKEN, and AIMAP_BOT_TOKEN if you have one
docker compose up -d --build
docker compose logs -f
```

This builds one image and starts two services from it, the collection server and the
Telegram bot, sharing one database through a Docker volume. Starting the stack starts
both; there is no separate step for the bot. If `AIMAP_BOT_TOKEN` is left empty, the
bot container exits on purpose with an explanation in its logs, rather than
crash-looping, and the web questionnaire and dashboard still run normally.

```bash
docker compose --profile backup up -d   # optional: adds a nightly database backup
```

The server listens on `127.0.0.1:8000` by default (set `AIMAP_BIND` in `.env` to
change it). Put a TLS proxy such as Caddy or nginx in front of it before any
respondent reaches it; see `DEPLOY.md` and the ready-made config in `deploy/`.

### Without Docker

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

export AIMAP_ADMIN_TOKEN=$(openssl rand -hex 32)
export AIMAP_BOT_TOKEN="from @BotFather"      # optional; the bot is skipped without it

./run-all.sh
```

`./run-all.sh` starts the collection server and the bot together from one command,
resolving the database path once and passing the same path to both, so the two
cannot be pointed at different files by accident. `./run-server.sh` and
`./run-bot.sh` still exist for running either one alone.

### Development

```bash
./.venv/bin/python tools/scripts/validate_schema.py     # run after any schema edit
./.venv/bin/python tools/scripts/scoring.py --selftest   # verify the scoring gates
./.venv/bin/python tools/scripts/test_channels.py        # web/Telegram parity check
./.venv/bin/python tools/aimap_db.py                      # init the database, show stats
./.venv/bin/python tools/scripts/audit_logic.py           # check for contradictory answer combinations
```

### Seeing the dashboard with data in it

```bash
./.venv/bin/python tools/scripts/seed_demo.py --db /tmp/demo.db --n 400
AIMAP_DB=/tmp/demo.db AIMAP_ADMIN_TOKEN=demo ./run-server.sh
# then open http://127.0.0.1:8000/dashboard.html and sign in with the token
```

The seeder refuses to write to the real collection database.

## Testing locally before publishing

Before pushing this repository anywhere, build and run it locally and confirm:

1. `docker compose up -d --build` completes without error.
2. The web questionnaire loads at `http://127.0.0.1:8000/`, the consent and routing
   questions appear first, and choosing each of the three paths (organization,
   practitioner, citizen) leads into the right set of questions.
3. If you have a Telegram bot token, message the bot and confirm `/start` leads
   through the same consent and routing step, and that a response submitted through
   Telegram shows up in the dashboard alongside web responses.
4. `docker compose logs -f` shows no repeating errors from either service.

Once that looks right, the repository is ready to commit and push.

## Committing and deploying

Nothing in this repository has been committed. To do so:

```bash
cd ai-map-eth
git init
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin <your GitHub repository URL>
git push -u origin main
```

To run it on a server:

```bash
ssh <your server>
git clone <your GitHub repository URL>
cd ai-map-eth
cp .env.example .env
nano .env                      # set AIMAP_ADMIN_TOKEN and AIMAP_BOT_TOKEN
docker compose up -d --build
```

That starts the web questionnaire, the dashboard, and the Telegram bot together, all
reading and writing the same database. `DEPLOY.md` covers putting a TLS proxy in
front of the server, systemd units as a Docker alternative, backups, and the
field-work runbook in more detail.

## Writing in this repository

New content added to this repository, chapter drafts, documentation, code comments,
should avoid em dashes and en dashes (use a comma, a colon, or two sentences
instead), avoid promotional or exaggerated language, and should not name any
individual contributor; refer to roles or workstreams instead. The two source
documents from the research program are the one deliberate exception, since they are
kept exactly as given to the team.
