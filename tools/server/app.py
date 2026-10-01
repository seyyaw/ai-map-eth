#!/usr/bin/env python3
"""
AI-MAP Ethiopia: collection server.

Serves the web questionnaire and receives its submissions. Storage goes through
`tools/aimap_db.py`, the SAME module and the SAME database file the Telegram bot
writes to, so every channel lands in one `responses` table with `mode` recorded
as a variable (see that module's docstring for why this matters to the design).

Run:
    pip install -r requirements.txt
    export AIMAP_ADMIN_TOKEN="a-long-random-string"
    export AIMAP_DB=../data/aimap.db          # optional; same default as the bot
    uvicorn app:app --host 0.0.0.0 --port 8000

Then open http://localhost:8000/
"""

import csv
import io
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aimap_db as db                                    # noqa: E402  (path set above)
import aimap_dashboard as dash                           # noqa: E402
import aimap_schema_store as store                       # noqa: E402

BASE = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = os.environ.get("AIMAP_ADMIN_TOKEN", "")

DB_PATH = db.init()


@asynccontextmanager
async def lifespan(_app):
    """Announce the RESOLVED, absolute database path, exactly as the bot does.

    The failure this guards against -- the two processes pointing at different
    files -- is silent: each service looks healthy on its own, and the datasets
    simply never meet until someone notices at analysis that `by_mode` has only
    ever shown one channel. Two log lines that can be held side by side is the
    cheapest way to catch that on day one instead.

    Emitted from the lifespan hook rather than at import, because uvicorn
    installs its own logging configuration after importing this module and
    anything logged at import time goes nowhere visible.
    """
    # Uvicorn attaches its handlers to the "uvicorn.*" loggers, not to root, so an
    # INFO record from our own logger has nowhere to go and vanishes -- while a
    # WARNING still surfaces via logging's last-resort handler. Borrowing uvicorn's
    # handlers puts these lines in the same place as every other startup line,
    # which is where an operator will actually look for them.
    log = logging.getLogger("aimap")
    if not log.handlers:
        uv = logging.getLogger("uvicorn.error").handlers
        if uv:
            log.handlers = uv
        else:
            logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s",
                                level=logging.INFO)
    log.setLevel(logging.INFO)
    log.info("shared database: %s", DB_PATH)
    log.info("the Telegram bot must report this same path, or you have two datasets")
    if not ADMIN_TOKEN:
        log.warning("AIMAP_ADMIN_TOKEN is not set: the dashboard and every export "
                    "endpoint will refuse to answer until it is")
    yield


app = FastAPI(title="AI-MAP Ethiopia collection API", version=db.INSTRUMENT_VERSION,
              lifespan=lifespan)


# ---------------------------------------------------------------- admin auth
#
# Two things need protecting and they are not the same thing: the response DATA,
# and the dashboard PAGE that reads it. An earlier version guarded only the data
# and left /dashboard.html on the public static mount, which meant the admin
# surface was world-readable -- useless without a token, but it announced itself
# to anyone scanning, and there is no reason to advertise it.
#
# Credentials are accepted two ways because the callers differ. A browser logs in
# once and gets an HttpOnly session cookie, which JavaScript cannot read, so an
# injected script on the page cannot steal it. Scripts and curl send the token in
# a header, which is what CI and the export commands in DEPLOY.md use.

SESSION_COOKIE = "aimap_admin"
SESSION_TTL = 12 * 3600          # one field working day

# Session ids live in memory, so a restart logs everyone out. That is the right
# trade for a single-process deployment: it makes logout real, and it means a
# leaked cookie cannot outlive the process it was issued by. A multi-replica
# deployment would need shared storage -- and this study does not have one.
_sessions = {}

# Brute-force throttle, per client address. A 32-hex token is not guessable, but
# nothing stops an operator setting "admin123", and an unthrottled endpoint turns
# that into an open door rather than a bad habit.
_failures = {}
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
WEAK_TOKEN_LENGTH = 24

audit = logging.getLogger("aimap.audit")


def _client(request: Request):
    """Best-effort client address. Behind a proxy this is the forwarded one,
    which is why the server runs with --proxy-headers."""
    return request.client.host if request.client else "unknown"


def _locked_out(ip):
    entry = _failures.get(ip)
    if not entry:
        return 0
    count, until = entry
    remaining = int(until - time.time())
    return remaining if remaining > 0 else 0


def _record_failure(ip):
    count, _ = _failures.get(ip, (0, 0))
    count += 1
    until = time.time() + LOCKOUT_SECONDS if count >= MAX_FAILURES else 0
    _failures[ip] = (count, until)
    return count


def _new_session(ip):
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = time.time() + SESSION_TTL
    _failures.pop(ip, None)
    # Opportunistic sweep: this dict is tiny and never worth a background task.
    now = time.time()
    for old_sid in [k for k, exp in _sessions.items() if exp < now]:
        _sessions.pop(old_sid, None)
    return sid


def _valid_session(sid):
    if not sid:
        return False
    expiry = _sessions.get(sid)
    if not expiry:
        return False
    if expiry < time.time():
        _sessions.pop(sid, None)
        return False
    return True


def _token_ok(candidate):
    """Constant-time comparison.

    `!=` leaks the length of the matching prefix through timing. The attack is
    marginal over a network, and the fix is one function call, so there is no
    version of this trade worth taking the other way.
    """
    if not ADMIN_TOKEN or not candidate:
        return False
    return secrets.compare_digest(str(candidate), ADMIN_TOKEN)


def require_admin(request: Request, x_admin_token: str = Header(default="")):
    """Accept a valid session cookie OR a valid token header."""
    if not ADMIN_TOKEN:
        raise HTTPException(503, "AIMAP_ADMIN_TOKEN is not set on the server")

    if _valid_session(request.cookies.get(SESSION_COOKIE)):
        audit.info("admin %s %s (session)", request.method, request.url.path)
        return True

    ip = _client(request)
    wait = _locked_out(ip)
    if wait:
        audit.warning("admin %s from %s refused: locked out for %ss",
                      request.url.path, ip, wait)
        raise HTTPException(429, f"too many failed attempts; try again in {wait}s")

    if _token_ok(x_admin_token):
        audit.info("admin %s %s (token header) from %s",
                   request.method, request.url.path, ip)
        return True

    n = _record_failure(ip)
    audit.warning("admin %s from %s REJECTED (failure %d of %d)",
                  request.url.path, ip, n, MAX_FAILURES)
    raise HTTPException(401, "admin token required")


def _is_secure(request: Request):
    """Whether the browser reached us over TLS, including via a proxy."""
    return (request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https")


def _csv_response(cols, rows, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter(["﻿" + buf.getvalue()]),           # BOM so Excel reads Ethiopic correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------- collection

@app.post("/api/submit")
async def submit(request: Request):
    try:
        rec = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")
    rec.setdefault("mode", "web")
    try:
        rid, n_contact = db.save_response(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "response_id": rid, "contact_fields_stored": n_contact}


@app.post("/api/progress")
async def progress(request: Request):
    """Position heartbeat from an in-progress questionnaire.

    Unauthenticated on purpose: the payload carries no answers, only where the
    respondent has reached. Requiring a token here would mean the web form could
    not report progress at all, and drop-off would stay structurally unmeasurable
    -- reading as zero rather than as unknown, which is the worse failure.
    """
    try:
        rec = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")
    rec.setdefault("mode", "web")
    for key in ("answers", "scores"):
        rec.pop(key, None)                  # belt and braces: never accept content here
    try:
        db.save_partial(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/referral")
async def referral(request: Request):
    """Mint an invitation code for the respondent-driven arm (web side).

    Codes identify the inviting RESPONSE, never a person. The web form calls this
    after a submission so a respondent can pass an invitation on -- the same
    mechanism the Telegram bot's /invite uses, writing to the same table, because
    a chain that spans channels is still one chain.
    """
    try:
        rec = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")
    rid, inst = rec.get("response_id"), rec.get("instrument")
    if not rid or inst not in db.VALID_INSTRUMENTS:
        raise HTTPException(400, "response_id and a valid instrument are required")
    code = db.issue_referral(db.hash_ref("web", rid), inst)
    return {"ok": True, "code": code}


@app.get("/api/referral/{code}")
def check_referral(code: str):
    """Is this invitation code real? Answers only yes/no and which instrument.

    Never returns the owner or the chain: a respondent typing a code must not be
    able to enumerate who else is in the study.
    """
    row = db.referral(code)
    if not row:
        return {"ok": False}
    return {"ok": True, "instrument": row["instrument"]}


@app.get("/api/response/{response_id}")
def load_response(response_id: str):
    """Return a stored response so the browser can review and revise it.

    The id is a client-generated UUID the respondent's own device recorded when
    it submitted; nothing else can produce it, so holding it is the only claim to
    the response. Direct identifiers are never in `answers` -- storage splits
    them into `contacts` on the way in -- so this cannot return contact details
    even for the right id.
    """
    row = db.response_by_id(response_id)
    if not row:
        raise HTTPException(404, "no such response")
    return row


@app.get("/api/stats")
def stats():
    """Public progress counter. No response content, safe to expose."""
    s = db.stats()
    s.pop("db", None)
    return s


# ---------------------------------------------------------------- admin

@app.post("/admin/login")
async def login(request: Request, response: Response):
    """Exchange the admin token for an HttpOnly session cookie.

    The cookie carries a random session id, never the token itself: a value that
    is replayed on every request should not also be the long-lived credential.
    """
    if not ADMIN_TOKEN:
        raise HTTPException(503, "AIMAP_ADMIN_TOKEN is not set on the server")
    ip = _client(request)
    wait = _locked_out(ip)
    if wait:
        audit.warning("login from %s refused: locked out for %ss", ip, wait)
        raise HTTPException(429, f"too many failed attempts; try again in {wait}s")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not _token_ok(body.get("token", "")):
        n = _record_failure(ip)
        audit.warning("login from %s REJECTED (failure %d of %d)", ip, n, MAX_FAILURES)
        raise HTTPException(401, "incorrect token")

    sid = _new_session(ip)
    secure = _is_secure(request)
    response.set_cookie(SESSION_COOKIE, sid,
        max_age=SESSION_TTL,
        httponly=True,          # JavaScript cannot read it, so an XSS cannot steal it
        samesite="strict",      # never sent on a cross-site request
        secure=secure,          # omitted on plain HTTP, or the browser drops it entirely
        path="/",
    )
    audit.info("login from %s SUCCEEDED (secure=%s)", ip, secure)
    if not secure:
        audit.warning("that session cookie was issued over plain HTTP: put TLS in "
                      "front before this is reachable from anywhere but localhost")
    return {"ok": True, "expires_in": SESSION_TTL, "secure": secure}


@app.post("/admin/logout")
def logout(request: Request, response: Response):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        _sessions.pop(sid, None)
    response.delete_cookie(SESSION_COOKIE, path="/")
    audit.info("logout from %s", _client(request))
    return {"ok": True}


@app.get("/admin/whoami")
def whoami(request: Request):
    """Is this browser logged in? Used by the dashboard on load. Deliberately
    unauthenticated, and deliberately says nothing except yes or no."""
    return {"authenticated": _valid_session(request.cookies.get(SESSION_COOKIE))}


@app.get("/admin/export.csv")
def export_csv(instrument: str = "ORG", _=Depends(require_admin)):
    if instrument not in db.VALID_INSTRUMENTS:
        raise HTTPException(400, f"instrument must be one of {sorted(db.VALID_INSTRUMENTS)}")
    cols, rows = db.export_rows(instrument)
    if not rows:
        raise HTTPException(404, "no responses for that instrument")
    return _csv_response(cols, rows, f"aimap-{instrument}.csv")


@app.get("/admin/quality")
def quality(_=Depends(require_admin)):
    """Flag rates and the mean self-versus-computed maturity gap."""
    return db.quality()


@app.get("/admin/sectors")
def sectors(_=Depends(require_admin)):
    """Sector league table: readiness by dimension, adoption and technical depth.
    Each row carries its N and a flag for whether that N supports a ranking."""
    return db.by_sector()


@app.get("/admin/status")
def status(_=Depends(require_admin)):
    return db.stats()


@app.get("/admin/dashboard")
def dashboard(_=Depends(require_admin)):
    """Everything the surveyor's dashboard renders, in one request.

    One payload rather than a dozen endpoints: the views cross-reference each
    other (an alert points at a quota cell, an insight rests on a distribution),
    and assembling them from separate requests would let the page show two
    figures computed seconds apart and quietly disagreeing.
    """
    return dash.dashboard()


@app.get("/admin/report.md")
def report(_=Depends(require_admin)):
    """The findings draft as Markdown, for pasting into the paper."""
    text = dash.report_markdown(dash.dashboard())
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aimap-findings-draft.md"'})


@app.get("/admin/chains.csv")
def chains(instrument: str = "IND", _=Depends(require_admin)):
    """Referral edges, for computing RDS weights outside this tool."""
    rows = db.recruitment_chains(instrument)
    if not rows:
        raise HTTPException(404, "no referral chains recorded for that instrument")
    cols = ["response_id", "referrer", "referrer_owner", "instrument", "recruit_arm", "submitted_at"]
    return _csv_response(cols, [[r.get(c) for c in cols] for r in rows],
                         f"aimap-chains-{instrument}.csv")


@app.get("/admin/contacts.csv")
def contacts(_=Depends(require_admin)):
    rows = db.contacts()
    return _csv_response(["response_id", "org_name", "contact", "contact_all", "created_at"],
        [[r["response_id"], r["org_name"], r["contact"],
          r.get("contact_all"), r["created_at"]] for r in rows],
        "aimap-contacts.csv",
    )


@app.delete("/admin/contacts")
def purge(_=Depends(require_admin)):
    """Delete all direct identifiers. Run once the follow-up window closes."""
    return {"deleted": db.purge_contacts()}


RESET_PHRASE = "RESET ALL DATA"


@app.post("/admin/reset-data")
async def reset_data(request: Request, _=Depends(require_admin)):
    """Wipe every response, partial session, contact and referral -- the whole
    collected dataset -- while leaving the published questionnaire untouched.

    For clearing out test submissions before real fieldwork begins. There is no
    undo, so the caller must echo an exact confirmation phrase rather than just
    POSTing with no body.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if (body or {}).get("confirm") != RESET_PHRASE:
        raise HTTPException(400, f'send {{"confirm": "{RESET_PHRASE}"}} to proceed -- this cannot be undone')
    counts = db.reset_responses()
    audit.warning("ALL RESPONSE DATA RESET: %s", counts)
    return {"ok": True, "deleted": counts}


# ------------------------------------------------------- the dashboard itself
# Registered BEFORE the catch-all static mount so these win: otherwise the
# dashboard would be served as an ordinary public file, which is how the admin
# surface ended up world-readable in the first place.
#
# The page is gated as well as the data. Not because the page is secret -- it is
# inert without a session -- but because an unauthenticated visitor has no reason
# to learn that this study exists, what it collects, or that an admin surface is
# here to be attacked.

LOGIN_PAGE = """<!doctype html>
<html lang="en" data-appearance="light" data-bg="paper" class="dash">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AI-MAP Ethiopia: Sign in</title>
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/dashboard-login.css">
</head><body><main class="wrap"><section id="gate" class="card">
<h1>Surveyor's dashboard</h1>
<p class="lede">Fieldwork monitoring and findings for AI-MAP Ethiopia.</p>
<p><label for="tok"><strong>Admin token</strong></label><br>
<span class="fine">The value of <code>AIMAP_ADMIN_TOKEN</code> on this server. Signing in sets a
session cookie for this browser; it is not stored anywhere a script can read it.</span></p>
<p><input id="tok" type="password" autocomplete="current-password" spellcheck="false"
   placeholder="paste the admin token" autofocus></p>
<p id="err" class="err" hidden></p>
<div class="row"><button type="button" class="btn" id="go">Sign in</button></div>
<p class="fine">Aggregate figures only. Respondent contact details are never loaded here.</p>
</section></main><script>
const err = document.getElementById('err');
async function signIn() {
  const token = document.getElementById('tok').value.trim();
  if (!token) return;
  err.hidden = true;
  try {
    const r = await fetch('/admin/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    if (r.ok) { location.reload(); return; }
    const body = await r.json().catch(() => ({}));
    err.textContent = r.status === 429
      ? (body.detail || 'Too many attempts. Wait and try again.')
      : 'That token was not accepted.';
    err.hidden = false;
  } catch (e) { err.textContent = 'Could not reach the server.'; err.hidden = false; }
}
document.getElementById('go').addEventListener('click', signIn);
document.getElementById('tok').addEventListener('keydown', e => {
  if (e.key === 'Enter') signIn();
});
</script></body></html>"""

WEB = BASE / "web"
DASHBOARD_ASSETS = {
    "/dashboard.js": "application/javascript",
    "/dashboard.css": "text/css",
}


def _signed_in(request: Request):
    return _valid_session(request.cookies.get(SESSION_COOKIE))


@app.get("/dashboard.html", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if not _signed_in(request):
        return HTMLResponse(LOGIN_PAGE, status_code=200)
    return FileResponse(WEB / "dashboard.html", media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/dashboard-login.css")
def dashboard_login_css():
    """The login page's own styling, public by necessity -- it is the one thing an
    unauthenticated visitor is allowed to load, and it contains nothing."""
    return FileResponse(WEB / "dashboard.css", media_type="text/css")


@app.get("/dashboard.js")
@app.get("/dashboard.css")
def dashboard_asset(request: Request):
    if not _signed_in(request):
        # 404 rather than 401: an unauthenticated visitor learns nothing about
        # what is or is not here.
        raise HTTPException(404, "not found")
    path = request.url.path
    return FileResponse(WEB / path.lstrip("/"), media_type=DASHBOARD_ASSETS[path],
                        headers={"Cache-Control": "no-store"})


# --------------------------------------------------------- schema: editor & gate
#
# GET /api/schema/state is public and deliberately tiny: it is what index.html
# calls before deciding whether to show the picker or the build/conduct choice,
# and a respondent must never need a login just to load the questionnaire.

@app.get("/api/schema/state")
def schema_state():
    return {"published": store.is_published(), "published_at": store.published_at()}


# The questionnaire used to be three separate drafted files (org.json,
# ind.json, cit.json), each with its own explicit route below -- NOT a
# "{name}.json" catch-all, which would intercept /schema/common.json and
# /schema/sampling.json too and 404 them, since a matched route's exception is
# the response; it never falls through to the static mount below for those
# two files to be served from. They have since been merged into one file,
# tools/schema/questionnaire.json, so there is one explicit route for the
# real document plus three aliases for the old filenames, kept only so a
# client that has not switched to the merged file yet does not break.

def _questionnaire_document():
    """The live questionnaire content.

    Once published this is byte-identical to reading the file, because publish
    already wrote the file -- this only diverges while UNPUBLISHED, when
    "Conduct" is the admin's own test run of a draft nobody else can see yet.
    """
    return store.effective("QUESTIONNAIRE")


@app.get("/schema/questionnaire.json")
def schema_questionnaire():
    return _questionnaire_document()


@app.get("/schema/org.json")
def schema_org():
    return _questionnaire_document()


@app.get("/schema/ind.json")
def schema_ind():
    return _questionnaire_document()


@app.get("/schema/cit.json")
def schema_cit():
    return _questionnaire_document()


@app.get("/admin/schema")
def get_schema_draft(_=Depends(require_admin)):
    code = "QUESTIONNAIRE"
    return {
        "code": code, "content": store.draft(code), "has_draft": store.has_draft(code),
        "published": store.is_published(),
    }


@app.put("/admin/schema")
async def put_schema_draft(request: Request, _=Depends(require_admin)):
    code = "QUESTIONNAIRE"
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")
    content = body.get("content", body)          # accept either {"content": {...}} or the doc itself
    try:
        store.save_draft(code, content, updated_by="admin")
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.info("schema draft saved")
    return {"ok": True}


@app.post("/admin/schema/discard")
def discard_schema_draft(_=Depends(require_admin)):
    store.discard_draft("QUESTIONNAIRE")
    audit.info("schema draft discarded")
    return {"ok": True}


@app.post("/admin/schema/publish")
def publish_schema(_=Depends(require_admin)):
    """Validate the questionnaire and either write the file or none of it.

    This is a SAFETY NET, not the authoritative pre-fieldwork check -- it does
    not verify routing order or full constraint reachability. Run
    `tools/scripts/validate_schema.py` by hand before real fieldwork regardless
    of what this endpoint accepted; see README "Before fielding".
    """
    ok, errors = store.publish(updated_by="admin")
    audit.info("schema publish %s%s", "SUCCEEDED" if ok else "REJECTED",
              "" if ok else f" ({len(errors)} error(s))")
    if not ok:
        raise HTTPException(422, {"errors": errors})
    return {"ok": True, "published_at": store.published_at()}


@app.post("/admin/schema/unpublish")
def unpublish_schema(_=Depends(require_admin)):
    store.unpublish()
    audit.info("schema unpublished: back to build mode")
    return {"ok": True}


# ---------------------------------------------------------------- static
# Order matters: /schema is mounted BEFORE the catch-all web mount so it wins.
#
# tools/web/schema is a symlink to tools/schema, which is convenient when serving
# the folder with `python -m http.server`, but StaticFiles refuses to follow
# symlinks out of its mount root (a correct path-traversal guard). Without an
# explicit mount the questionnaire 404s on its own schema and will not load.
SCHEMA = BASE / "schema"
if SCHEMA.is_dir():
    app.mount("/schema", StaticFiles(directory=str(SCHEMA)), name="schema")

if WEB.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
else:
    @app.get("/", response_class=HTMLResponse)
    def root():
        return "<h1>AI-MAP collection API</h1><p>Web questionnaire directory not found.</p>"
