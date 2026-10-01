#!/usr/bin/env python3
"""
AI-MAP Ethiopia: shared storage layer.

ONE database for every collection channel. The web questionnaire (via the
collection server), the Telegram bot and enumerator-assisted collection all
write through this module to the same SQLite file, with `mode` recorded as a
variable on each response rather than the channels being split across systems.

That matters methodologically, not just tidily: the citizen-survey design
(methodology §5) depends on comparing the Telegram sample against the
probability-sampled rural booster, which is only possible if both live in one
table with a mode column.

Direct identifiers are written to a separate `contacts` table linked by
response_id only, and the PII field list is DERIVED FROM THE SCHEMA
(`"pii": true`) per instrument -- question ids are unique only *within* an
instrument, so a global key list would file a citizen's consent value as an
organisation name.

Environment:
    AIMAP_DB    path to the SQLite file. Default: tools/data/aimap.db
                Set this identically for the server and the bot.
"""

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCHEMA_DIR = BASE / "schema"

DEFAULT_DB = BASE / "data" / "aimap.db"
DB_PATH = Path(os.environ.get("AIMAP_DB") or DEFAULT_DB)

VALID_INSTRUMENTS = {"ORG", "IND", "CIT"}

# Scoring is applied HERE rather than trusted from the client, so that the web
# form, the Telegram bot and enumerator imports all produce identical scores from
# one implementation. A client-side bug, an old cached build or a tampered
# submission cannot move a published figure. What the client computed is kept in
# `client_scores` so the two can be compared -- a systematic divergence is a bug
# report, not noise.
try:
    import sys as _sys
    _sys.path.insert(0, str(BASE / "scripts"))
    import scoring as _scoring
except Exception as _e:                      # pragma: no cover
    _scoring = None
    _SCORING_ERROR = _e


try:
    import aimap_constraints as _constraints
except Exception:                            # pragma: no cover
    _constraints = None


def consistency_flags(instrument, answers):
    """Cross-field violations recorded on the stored response.

    Both renderers block these before submission, so a violation arriving here
    means the response did not come through a renderer -- an enumerator import, a
    paper form keyed in later, or a client that skipped the check. Those are
    exactly the cases worth surfacing, so they are flagged rather than rejected:
    the data is real and already collected, and refusing it at the door would
    lose it without telling anyone.
    """
    if _constraints is None:
        return {}
    try:
        found = _constraints.flags(instrument, answers)
    except Exception:
        logging.getLogger("aimap").exception("constraint evaluation failed")
        return {}
    if not found:
        return {}
    return {
        "flag_inconsistent": True,
        "inconsistencies": [v["id"] for v in found],
    }


def score_response(instrument, answers):
    """Authoritative scores for one response.

    On failure this returns an explicit error marker rather than an empty dict.
    An earlier version returned {} and the caller fell back to the client's own
    scores -- which meant a bug in this module silently published unverified
    client numbers, the exact failure the server-side scoring exists to prevent.
    A response that could not be scored is stored, flagged, and re-scored later.
    """
    if _scoring is None:
        return {"scoring_error": f"reference implementation unavailable: {_SCORING_ERROR}"}
    try:
        if instrument == "ORG":
            return _scoring.score_all(answers)
        if instrument == "IND":
            return _scoring.score_individual(answers)
        return _scoring.score_citizen(answers)
    except Exception as e:
        logging.getLogger("aimap").exception("scoring failed for %s", instrument)
        return {"scoring_error": f"{type(e).__name__}: {e}"}
VALID_MODES = {"web", "telegram", "enumerator", "ivr", "paper", "import"}

# The long form and the short form are the SAME instrument with the non-core items
# routed out, not two questionnaires -- so their answers pool item by item. Recorded
# per response because the short form's higher completion rate is itself a finding.
VALID_FORMS = {"full", "short"}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS responses (
    response_id        TEXT PRIMARY KEY,
    instrument         TEXT NOT NULL,
    instrument_version TEXT,
    language           TEXT,
    mode               TEXT NOT NULL,
    started_at         TEXT,
    submitted_at       TEXT NOT NULL,
    answers            TEXT NOT NULL,
    scores             TEXT,          -- authoritative, computed here on ingest
    client_scores      TEXT,          -- what the client computed, kept for comparison
    source_ref         TEXT,
    form               TEXT,          -- 'full' or 'short'  (common.json -> short_form)
    recruit_arm        TEXT,          -- 'list' | 'referral' | 'booster' | 'open'
    referrer           TEXT,          -- hashed ref of the respondent who invited this one
    enumerator         TEXT,          -- enumerator id, for interviewer-effect checks
    revision           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_resp_instrument ON responses(instrument);
CREATE INDEX IF NOT EXISTS idx_resp_mode       ON responses(mode);
CREATE INDEX IF NOT EXISTS idx_resp_submitted  ON responses(submitted_at);

-- Direct identifiers. Linked to responses by response_id only, and deleted
-- once the follow-up window closes (purge_contacts).
CREATE TABLE IF NOT EXISTS contacts (
    response_id TEXT PRIMARY KEY,
    org_name    TEXT,
    contact     TEXT,          -- the first reachable value, for the simple export
    contact_all TEXT,          -- every reachable value as JSON, keyed by question id
    created_at  TEXT NOT NULL);

-- Position of an in-progress response. NO ANSWER CONTENT: only where the
-- respondent is and how far they have got. Without this, drop-out is invisible --
-- an abandoned questionnaire simply never arrives -- and "which question loses
-- people" is the one question a pilot most needs to answer. Rows are marked
-- completed when the matching response lands, so the incomplete rows ARE the
-- drop-off, with no separate bookkeeping to fall out of step.
CREATE TABLE IF NOT EXISTS partials (
    response_id TEXT PRIMARY KEY,
    instrument  TEXT NOT NULL,
    mode        TEXT NOT NULL,
    form        TEXT,
    recruit_arm TEXT,
    last_qid    TEXT,
    section_id  TEXT,
    answered    INTEGER,
    total       INTEGER,
    pct         INTEGER,
    started_at  TEXT,
    updated_at  TEXT NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_part_completed ON partials(completed);
CREATE INDEX IF NOT EXISTS idx_part_instrument ON partials(instrument);

-- Referral chains for the respondent-driven arm (docs/study-design-decisions.md
-- §1). A code identifies the INVITING response, never a person: the owner is
-- already a hashed channel reference. Storing the chain is what makes RDS
-- estimators and degree weights computable after the fact; without it the
-- referral arm is just an unweightable convenience sample.
CREATE TABLE IF NOT EXISTS referrals (
    code       TEXT PRIMARY KEY,
    owner_ref  TEXT,
    instrument TEXT,
    created_at TEXT NOT NULL,
    uses       INTEGER NOT NULL DEFAULT 0);

-- The questionnaire's own DRAFT, while it is being edited live in the admin
-- editor. Never the published content -- that lives in tools/schema/*.json on
-- disk, which stays the single source of truth every other tool (scoring,
-- constraints, the CLI validator, the LaTeX generator) reads directly, so none
-- of them need to know a draft exists. A draft is a pending change; publishing
-- writes it to the file and clears the row, so "has a draft" always means
-- "has unpublished changes".
CREATE TABLE IF NOT EXISTS schema_docs (
    code       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT,
    PRIMARY KEY (code, kind)
);

-- One flag: is the questionnaire live? While false, the web form offers a
-- Build/Conduct choice instead of going straight to the picker.
CREATE TABLE IF NOT EXISTS schema_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Telegram conversation state, so a respondent who drops out can resume.
CREATE TABLE IF NOT EXISTS bot_sessions (
    chat_id    INTEGER PRIMARY KEY,
    state      TEXT NOT NULL,
    updated_at TEXT NOT NULL);
"""


# ---------------------------------------------------------------- schema-derived config

def _load_schema():
    common = json.loads((SCHEMA_DIR / "common.json").read_text(encoding="utf-8"))
    instruments = {
        s["code"]: json.loads((SCHEMA_DIR / s["file"]).read_text(encoding="utf-8"))
        for s in common["instruments"]
    }
    return common, instruments


try:
    COMMON, INSTRUMENTS = _load_schema()
except OSError as exc:                      # schema unavailable: fail loudly, not silently
    raise RuntimeError(f"cannot read survey schema from {SCHEMA_DIR}: {exc}") from exc


def reload_schema(path=None):
    """Re-read the schema files and refresh every in-process copy.

    Called once, right after a publish writes new content to
    tools/schema/*.json, so the SAME PROCESS that just wrote the files does not
    keep serving the stale copy it loaded at import. Mutates the existing dict
    objects in place (.clear() + .update()) rather than rebinding COMMON/
    INSTRUMENTS to new objects: bot.py took local aliases of these dicts at
    import time (`INSTRUMENTS = db.INSTRUMENTS`), and a rebind here would leave
    those aliases pointing at the old, stale dict forever. A separate PROCESS
    (the Telegram bot, always) still needs its own trigger to reload -- see
    bot.py's mtime check on /start -- because no amount of in-place mutation in
    this process reaches another process's memory.
    """
    global INSTRUMENT_VERSION
    new_common, new_instr = _load_schema()
    COMMON.clear(); COMMON.update(new_common)
    for code in list(INSTRUMENTS):
        if code not in new_instr:
            del INSTRUMENTS[code]
    for code, doc in new_instr.items():
        INSTRUMENTS.setdefault(code, {}).clear()
        INSTRUMENTS[code].update(doc)
    PII_KEYS.clear(); PII_KEYS.update(_pii_keys())
    TARGETS.clear(); TARGETS.update({s["code"]: s["target_n"] for s in COMMON["instruments"]})
    INSTRUMENT_VERSION = COMMON["version"]
    return Path(path or DB_PATH)


def schema_mtime():
    """The newest modification time across the schema files.

    Cheap enough to check on every /start: the Telegram bot compares this
    against what it saw last, and reloads only when it has actually changed.
    """
    return max((SCHEMA_DIR / n).stat().st_mtime
               for n in ("common.json", "questionnaire.json")
               if (SCHEMA_DIR / n).exists())


def _pii_keys():
    """Question ids marked `"pii": true`, per instrument."""
    out = {}
    for code, inst in INSTRUMENTS.items():
        out[code] = {
            q["id"]
            for sec in inst["sections"]
            for q in sec["questions"]
            if q.get("pii")
        }
    return out


PII_KEYS = _pii_keys()
# Recruitment arm is a design variable, not a channel: the same Telegram bot serves
# both the list arm and the referral arm, and the difference between them is what
# makes either weightable. See docs/study-design-decisions.md §1.
VALID_ARMS = {a["code"] for a in COMMON.get("recruitment", {}).get("arms", [])} or \
             {"list", "referral", "booster", "open"}

# Which pii field carries the organisation name. Everything else marked pii is
# treated as a means of reaching the respondent.
ORG_NAME_KEY = {"ORG": "S2"}

TARGETS = {s["code"]: s["target_n"] for s in COMMON["instruments"]}
INSTRUMENT_VERSION = COMMON["version"]


# ---------------------------------------------------------------- connection

@contextmanager
def connect(path=None):
    """Open the shared database, creating it and its schema if needed."""
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")     # lets the bot and server write concurrently
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA_SQL)
    # Databases created before a column existed are migrated in place rather than
    # rebuilt: field data is never worth a destructive migration.
    cols = {r[1] for r in con.execute("PRAGMA table_info(responses)")}
    for col in ("client_scores", "form", "recruit_arm", "referrer", "enumerator"):
        if col not in cols:
            con.execute(f"ALTER TABLE responses ADD COLUMN {col} TEXT")
    if "revision" not in cols:
        # How many times this response has been revised. Someone who comes back
        # and corrects an answer is giving better data, not corrupting it, but
        # the analysis has to be able to tell a revised response from a fresh
        # one: a second visit is a different cognitive act from the first.
        con.execute("ALTER TABLE responses ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
    ccols = {r[1] for r in con.execute("PRAGMA table_info(contacts)")}
    if "contact_all" not in ccols:
        con.execute("ALTER TABLE contacts ADD COLUMN contact_all TEXT")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init(path=None):
    with connect(path):
        pass
    return Path(path or DB_PATH)


# ---------------------------------------------------------------- writing

def hash_ref(prefix, raw):
    """Stable pseudonymous reference. Raw channel identifiers are never stored."""
    digest = hashlib.sha256(f"{prefix}:{raw}:{INSTRUMENT_VERSION}".encode()).hexdigest()
    return f"{prefix}:{digest[:16]}"


def save_response(record, path=None):
    """Store one response, splitting direct identifiers into `contacts`.

    `record` keys: response_id, instrument, language, mode, started_at,
    submitted_at, answers, scores, source_ref.
    Returns (response_id, n_contact_fields_split_out).
    """
    rid = record.get("response_id")
    inst = record.get("instrument")
    mode = record.get("mode", "web")

    if not rid:
        raise ValueError("response_id is required")
    if inst not in VALID_INSTRUMENTS:
        raise ValueError(f"unknown instrument {inst!r}")
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}")

    answers = dict(record.get("answers") or {})
    answers.pop("__hp", None)                       # honeypot never persists

    keys = PII_KEYS.get(inst, set())
    contact = {k: answers.pop(k) for k in list(answers) if k in keys}

    now = datetime.now(timezone.utc).isoformat()
    client_scores = record.get("scores") or {}
    scores = score_response(inst, answers)
    scores.update(consistency_flags(inst, answers))

    # Timing is only known to the client, so carry it across.
    for k in ("duration_seconds", "flag_speeder", "flag_honeypot"):
        if k in client_scores and k not in scores:
            scores[k] = client_scores[k]

    form = record.get("form") or "full"
    arm = record.get("recruit_arm") or "open"
    if form not in VALID_FORMS:
        raise ValueError(f"unknown form {form!r}")
    if arm not in VALID_ARMS:
        raise ValueError(f"unknown recruitment arm {arm!r}")

    # An invitation code that does not resolve is a typo or a fabrication, and
    # either way it must not become an edge in the referral graph: RDS estimators
    # weight by position in a chain, and a chain with an invented parent silently
    # corrupts every weight downstream of it. Both clients check the code before
    # the respondent starts; this is the check that actually binds, because the
    # client's can be skipped. The response is kept -- it is a real answer -- and
    # reclassified to the arm it actually belongs to.
    referrer = (record.get("referrer") or "").strip().upper() or None
    if referrer and not referral(referrer, path):
        logging.getLogger("aimap").warning("response %s cites unknown referral code %s; recording it as an open-arm response",
            rid, referrer)
        referrer = None
        if arm == "referral":
            arm = "open"

    with connect(path) as con:
        # Columns are named rather than positional: this row has grown twice, and
        # a positional INSERT silently files the next new column under the wrong
        # heading instead of failing.
        con.execute("INSERT OR REPLACE INTO responses "
            "(response_id, instrument, instrument_version, language, mode, started_at, "
            " submitted_at, answers, scores, client_scores, source_ref, form, recruit_arm, "
            " referrer, enumerator, revision) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, inst,
                record.get("instrument_version") or INSTRUMENT_VERSION,
                record.get("language"), mode,
                record.get("started_at"),
                record.get("submitted_at") or now,
                json.dumps(answers, ensure_ascii=False),
                json.dumps(scores, ensure_ascii=False),
                json.dumps(client_scores, ensure_ascii=False),
                record.get("source_ref"),
                form, arm,
                referrer,
                record.get("enumerator"),
                int(record.get("revision") or 0),
            ),
        )
        # The partial row for this response, if any, is now a completion rather
        # than a drop-out. Marking it here -- in the same transaction as the
        # response -- is what keeps the drop-off count honest.
        con.execute("UPDATE partials SET completed=1, updated_at=? WHERE response_id=?",
                    (now, rid))
        if referrer:
            con.execute("UPDATE referrals SET uses = uses + 1 WHERE code=?", (referrer,))
        if contact:
            name_key = ORG_NAME_KEY.get(inst)
            org_name = contact.get(name_key) if name_key else None
            # EVERY reachable value, not just the first. A respondent who offers
            # both an email and a phone has told us the email may not reach them;
            # keeping only the first discards exactly the fallback they took the
            # trouble to give, and the loss is invisible until follow-up fails.
            reach_all = {k: v for k, v in contact.items() if k != name_key and v}
            reach = next(iter(reach_all.values()), None)
            con.execute("INSERT OR REPLACE INTO contacts "
                "(response_id, org_name, contact, contact_all, created_at) "
                "VALUES (?,?,?,?,?)",
                (rid, org_name, reach,
                 json.dumps(reach_all, ensure_ascii=False) if reach_all else None, now),
            )
    return rid, len(contact)


# ---------------------------------------------------------------- progress and referrals

def save_partial(record, path=None):
    """Record where an in-progress respondent has got to.

    Deliberately stores NO answer content -- only position and counts. That keeps
    a heartbeat endpoint safe to leave unauthenticated (it can leak nothing about
    a respondent) while still making the two things a pilot must know measurable:
    how many people start and never finish, and which question they stop on.
    """
    rid = record.get("response_id")
    if not rid:
        raise ValueError("response_id is required")
    inst = record.get("instrument")
    if inst not in VALID_INSTRUMENTS:
        raise ValueError(f"unknown instrument {inst!r}")
    mode = record.get("mode", "web")
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}")
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as con:
        # A partial never overwrites a completion: a late heartbeat from a client
        # that submitted and then flushed a stale queue must not resurrect a
        # finished response as a drop-out.
        con.execute("INSERT INTO partials (response_id, instrument, mode, form, recruit_arm, "
            " last_qid, section_id, answered, total, pct, started_at, updated_at, completed) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0) "
            "ON CONFLICT(response_id) DO UPDATE SET "
            " last_qid=excluded.last_qid, section_id=excluded.section_id, "
            " answered=excluded.answered, total=excluded.total, pct=excluded.pct, "
            " updated_at=excluded.updated_at "
            "WHERE partials.completed = 0",
            (rid, inst, mode, record.get("form") or "full",
             record.get("recruit_arm") or "open",
             record.get("last_qid"), record.get("section_id"),
             record.get("answered"), record.get("total"), record.get("pct"),
             record.get("started_at"), now),
        )
    return rid


def issue_referral(owner_ref, instrument, path=None):
    """Mint an invitation code for the respondent-driven arm.

    The code identifies the inviting RESPONSE, not a person: `owner_ref` is already
    a hashed channel reference. Codes are short and unambiguous by construction --
    they get typed into a chat window by someone who was told them verbally.
    """
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # no O/0, I/1
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as con:
        for _ in range(12):
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            try:
                con.execute("INSERT INTO referrals (code, owner_ref, instrument, created_at) "
                            "VALUES (?,?,?,?)", (code, owner_ref, instrument, now))
                return code
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("could not mint an unused referral code")


def referral(code, path=None):
    if not code:
        return None
    with connect(path) as con:
        row = con.execute("SELECT * FROM referrals WHERE code=?",
                          (str(code).strip().upper(),)).fetchone()
    return dict(row) if row else None


def recruitment_chains(instrument=None, path=None):
    """Edges of the referral graph: (referrer code, recruit response_id).

    Returned raw rather than as a computed RDS weight. The estimator to use
    depends on the analysis and on the degree question, and baking one choice in
    here would quietly decide a methodological question in a storage module.
    """
    q = ("SELECT r.response_id, r.referrer, r.instrument, r.recruit_arm, r.submitted_at, "
         "       f.owner_ref AS referrer_owner "
         "FROM responses r LEFT JOIN referrals f ON f.code = r.referrer "
         "WHERE r.referrer IS NOT NULL")
    args = ()
    if instrument:
        q += " AND r.instrument=?"
        args = (instrument,)
    with connect(path) as con:
        return [dict(r) for r in con.execute(q + " ORDER BY r.submitted_at", args)]


# ---------------------------------------------------------------- bot sessions

def latest_for_source(source_ref, path=None):
    """The most recent response from this chat or device, if there is one.

    Used to OFFER A REVIEW rather than silently start a second response. Someone
    who reaches the questionnaire twice is far likelier to be returning to their
    own answers than to be a different person on the same handset, and quietly
    recording them again would count one respondent twice.
    """
    if not source_ref:
        return None
    with connect(path) as con:
        row = con.execute(
            "SELECT response_id, instrument, form, recruit_arm, referrer, answers, "
            "       submitted_at, revision "
            "FROM responses WHERE source_ref=? ORDER BY submitted_at DESC LIMIT 1",
            (source_ref,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["answers"] = json.loads(out["answers"] or "{}")
    return out


def response_by_id(response_id, path=None):
    """One stored response, for the web form to reload and revise."""
    with connect(path) as con:
        row = con.execute(
            "SELECT response_id, instrument, form, recruit_arm, referrer, answers, "
            "       submitted_at, revision FROM responses WHERE response_id=?",
            (response_id,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["answers"] = json.loads(out["answers"] or "{}")
    return out


def save_session(chat_id, state, path=None):
    with connect(path) as con:
        con.execute("INSERT INTO bot_sessions (chat_id, state, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET state=excluded.state, "
            "updated_at=excluded.updated_at",
            (chat_id, json.dumps(state, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()),
        )


def load_session(chat_id, path=None):
    with connect(path) as con:
        row = con.execute("SELECT state FROM bot_sessions WHERE chat_id=?", (chat_id,)).fetchone()
    return json.loads(row["state"]) if row else None


def clear_session(chat_id, path=None):
    with connect(path) as con:
        con.execute("DELETE FROM bot_sessions WHERE chat_id=?", (chat_id,))


# ---------------------------------------------------------------- reading

def stats(path=None):
    """Progress against targets, broken down by collection channel."""
    with connect(path) as con:
        rows = con.execute("SELECT instrument, mode, COUNT(*) AS n FROM responses "
            "GROUP BY instrument, mode").fetchall()
        total = con.execute("SELECT COUNT(*) AS n FROM responses").fetchone()["n"]

    by_inst = {}
    for r in rows:
        d = by_inst.setdefault(r["instrument"], {"total": 0, "by_mode": {}})
        d["total"] += r["n"]
        d["by_mode"][r["mode"]] = r["n"]
    for code, d in by_inst.items():
        d["target"] = TARGETS.get(code)
        d["pct"] = round(100 * d["total"] / d["target"], 1) if d.get("target") else None
    return {"total": total, "instruments": by_inst, "targets": TARGETS,
            "instrument_version": INSTRUMENT_VERSION, "db": str(Path(path or DB_PATH))}


def fetch(instrument=None, path=None):
    q = "SELECT * FROM responses"
    args = ()
    if instrument:
        q += " WHERE instrument=?"
        args = (instrument,)
    q += " ORDER BY submitted_at"
    with connect(path) as con:
        return [dict(r) for r in con.execute(q, args).fetchall()]


def quality(path=None):
    """Flag rates, the two self-versus-computed gaps, and client/server score
    divergence, by instrument."""
    agg = {}
    for r in fetch(path=path):
        s = json.loads(r["scores"] or "{}")
        c = json.loads(r["client_scores"] or "{}")
        d = agg.setdefault(r["instrument"], {
            "n": 0, "planted": 0, "definition": 0, "attention": 0, "honeypot": 0,
            "speeder": 0, "scratch_unsupported": 0, "client_divergence": 0,
            "scoring_errors": 0,
            "_mg": [], "_tg": [],
        })
        d["n"] += 1
        for name, key in (("planted", "flag_planted"), ("definition", "flag_definition"),
                          ("attention", "flag_attention"), ("honeypot", "flag_honeypot"),
                          ("speeder", "flag_speeder"),
                          ("scratch_unsupported", "flag_scratch_unsupported")):
            if s.get(key):
                d[name] += 1
        if s.get("scoring_error"):
            d["scoring_errors"] += 1
        # A client that disagrees with the reference implementation is a bug
        # report: a stale cached build, or a tampered submission.
        for key in ("maturity_computed", "technical_computed"):
            if key in c and key in s and c[key] != s[key]:
                d["client_divergence"] += 1
                break
        if s.get("maturity_gap") is not None:
            d["_mg"].append(s["maturity_gap"])
        if s.get("technical_gap") is not None:
            d["_tg"].append(s["technical_gap"])
    for d in agg.values():
        d["mean_maturity_gap"] = round(sum(d["_mg"]) / len(d["_mg"]), 2) if d["_mg"] else None
        d["mean_technical_gap"] = round(sum(d["_tg"]) / len(d["_tg"]), 2) if d["_tg"] else None
        d.pop("_mg"), d.pop("_tg")
    return agg


def by_sector(path=None):
    """Sector league table: the point of the whole exercise.

    Reported with each sector's N alongside the scores, because a sector of six
    respondents does not support a ranking and the reader must be able to see
    that without looking it up.
    """
    DIMS = ("infrastructure", "data", "expertise", "economic", "governance")
    agg = {}
    for r in fetch("ORG", path):
        a = json.loads(r["answers"] or "{}")
        s = json.loads(r["scores"] or "{}")
        sector = a.get("S3") or "unknown"
        d = agg.setdefault(sector, {"n": 0, "_dims": {k: [] for k in DIMS},
                                    "_mat": [], "_tech": [], "_overall": [], "_geo": []})
        d["n"] += 1
        for k in DIMS:
            v = s.get(f"readiness_{k}")
            if v is not None:
                d["_dims"][k].append(v)
        for key, bucket in (("maturity_computed", "_mat"), ("technical_computed", "_tech"),
                            ("readiness_overall", "_overall"),
                            ("readiness_overall_geometric", "_geo")):
            if s.get(key) is not None:
                d[bucket].append(s[key])

    mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    out = {}
    for sector, d in agg.items():
        row = {"n": d["n"]}
        for k in DIMS:
            row[k] = mean(d["_dims"][k])
        row["maturity_mean"] = mean(d["_mat"])
        row["technical_mean"] = mean(d["_tech"])
        row["readiness_overall"] = mean(d["_overall"])
        row["readiness_geometric"] = mean(d["_geo"])
        if row["readiness_overall"] is not None and row["readiness_geometric"] is not None:
            row["compensability_gap"] = round(row["readiness_overall"] - row["readiness_geometric"], 1)
        row["band"] = _scoring.band(row["readiness_overall"]) if _scoring else None
        # Guard against reading a ranking off a handful of responses.
        row["sufficient_for_ranking"] = d["n"] >= 15
        out[sector] = row
    return out


def contacts(path=None):
    with connect(path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM contacts ORDER BY created_at").fetchall()]


def purge_contacts(path=None):
    """Delete all direct identifiers. Run once follow-up closes."""
    with connect(path) as con:
        n = con.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()["n"]
        con.execute("DELETE FROM contacts")
    return n


# Every table that holds RESPONDENT data. Deliberately excludes schema_docs and
# schema_settings -- the questionnaire content and its publish state -- so
# wiping test submissions never touches the instrument itself.
RESPONSE_TABLES = ("responses", "partials", "contacts", "referrals", "bot_sessions")


def reset_responses(path=None):
    """Delete every response, in-progress session, contact and referral chain --
    the entire collected dataset -- leaving the published questionnaire
    untouched. For clearing out test submissions before real fieldwork begins.
    There is no undo; the caller is expected to have confirmed with a human."""
    counts = {}
    with connect(path) as con:
        for t in RESPONSE_TABLES:
            counts[t] = con.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            con.execute(f"DELETE FROM {t}")
    return counts


def export_rows(instrument, path=None):
    """Flat analysis rows: answers prefixed a_, scores prefixed s_."""
    rows = fetch(instrument, path)
    meta = ["response_id", "instrument", "instrument_version", "language",
            "mode", "started_at", "submitted_at", "source_ref"]
    # c_ columns are the client's own scores, for divergence checking only.
    akeys, skeys, parsed = set(), set(), []
    for r in rows:
        a = json.loads(r["answers"] or "{}")
        s = json.loads(r["scores"] or "{}")
        akeys.update(a)
        skeys.update(s)
        parsed.append((r, a, s))

    cols = meta + [f"a_{k}" for k in sorted(akeys)] + [f"s_{k}" for k in sorted(skeys)]
    out = []
    for r, a, s in parsed:
        row = [r.get(k) for k in meta]
        for k in sorted(akeys):
            v = a.get(k)
            row.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
        row += [s.get(k) for k in sorted(skeys)]
        out.append(row)
    return cols, out


if __name__ == "__main__":
    p = init()
    print(f"database ready: {p}")
    print(f"instrument version: {INSTRUMENT_VERSION}")
    print("pii fields per instrument:", {k: sorted(v) for k, v in PII_KEYS.items()})
    print(json.dumps(stats(), indent=2))
