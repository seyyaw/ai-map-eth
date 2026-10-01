#!/usr/bin/env python3
"""
AI-MAP Ethiopia: Telegram survey bot.

Delivers the same JSON instruments as the web tool, one question per message,
with button answers wherever possible. Designed for low bandwidth and for the
CIT (citizen pulse) instrument in particular, where Telegram is the primary
field channel (see methodology §5).

Storage goes through `tools/aimap_db.py`, the SAME module and the SAME database
file the web collection server writes to, so responses from every channel land in
one `responses` table with `mode` recorded as a variable.

Run:
    export AIMAP_BOT_TOKEN="123456:ABC..."
    export AIMAP_DB=../data/aimap.db      # optional; same default as the server
    python bot.py

Dependencies: python-telegram-bot>=21  (pip install -r requirements.txt)
"""

import json
import logging
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import InvalidToken
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import aimap_db as db                       # noqa: E402  (path set above)
import aimap_constraints as rules            # noqa: E402

SCHEMA_DIR = BASE / "schema"
TOKEN = os.environ.get("AIMAP_BOT_TOKEN")

# common.json's three instruments (ORG, IND, CIT) all now point their "file"
# at the same tools/schema/questionnaire.json: one document, not three. It
# starts with a section whose id is "R" -- consent, then "how would you like
# to answer this survey?" -- and every other section is reached only through
# that question (directly or, for org's sub-sectors, through a question only
# reachable within one branch). There is no longer a picker that chooses an
# instrument before the questionnaire starts: the questionnaire asks that
# itself, as its second question, and the branch it leads into is read out of
# INSTRUMENTS the same way every other show_if-gated question already is.

# R1's three answer values, as the instrument codes everything else in this
# bot, aimap_db.py and the stored responses already use.
BRANCH_CODE = {"organization": "ORG", "practitioner": "IND", "citizen": "CIT"}

# Until R1 is answered there is no chosen instrument yet, only the one merged
# document that every instrument code indexes into identically. Section R, the
# only section with no show_if, reads the same regardless of which of the
# three keys is used, so this one is picked arbitrarily to look the schema up
# by before routing has happened.
UNROUTED_CODE = "ORG"


def lookup_code(st):
    """Which INSTRUMENTS key to read the schema through: the respondent's own
    branch once R1 has set it, or the placeholder while still on section R."""
    return st.get("code") or UNROUTED_CODE


logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
log = logging.getLogger("aimap")

# ---------------------------------------------------------------- schema

COMMON = db.COMMON
INSTRUMENTS = db.INSTRUMENTS

# The admin editor's Publish button writes straight to tools/schema/*.json --
# see aimap_schema_store.py. The collection server, running as its own process,
# notices immediately because it re-reads the schema on every publish. This bot
# is a SEPARATE process and has no such trigger of its own, so it checks the
# files' own mtime each time someone starts a conversation and reloads in place
# (`db.reload_schema()` mutates COMMON/INSTRUMENTS rather than rebinding them,
# so these two module-level names -- taken once, above, at import -- go on
# pointing at the same, now-refreshed dicts).
_schema_seen_at = db.schema_mtime()


def refresh_schema_if_changed():
    global _schema_seen_at
    current = db.schema_mtime()
    if current != _schema_seen_at:
        db.reload_schema()
        _schema_seen_at = current
        log.info("schema changed on disk -- reloaded (instrument %s)", db.INSTRUMENT_VERSION)

# The study is fielded in English only. Recorded on every response so a later
# multilingual wave stays distinguishable in the same dataset.
LANG = "en"


def tr(bag, lang=LANG):
    """Schema strings are plain English. The object form is still tolerated so a
    partially-migrated or future multilingual schema does not break the bot."""
    if bag is None:
        return ""
    if isinstance(bag, str):
        return bag
    return bag.get("en") or next(iter(bag.values()), "")


def find_question(code, qid):
    for sec in INSTRUMENTS[code]["sections"]:
        for q in sec["questions"]:
            if q["id"] == qid:
                return q
    return None


def resolve_options(code, q):
    """Mirror of the web renderer's option-reference resolution."""
    if q.get("options"):
        return q["options"]
    ref = q.get("options_ref")
    if ref:
        src_code, qid = ref.split(":") if ":" in ref else (code, ref)
        src = find_question(src_code, qid) if src_code in INSTRUMENTS else None
        if src:
            opts = resolve_options(src_code, src) or src.get("row_options") or []
            return list(opts) + list(q.get("extra_options", []))
    return q.get("rows", [])


def show_if(cond, answers):
    if not cond:
        return True
    v = answers.get(cond["q"])
    has = v not in (None, "", [], {})
    op = cond["op"]
    if op == "answered":
        return has
    if op == "eq":
        return str(v) == str(cond["value"])
    if op == "not_eq":
        return str(v) != str(cond["value"])
    if op == "in":
        if isinstance(v, list):
            return any(str(x) in [str(y) for y in cond["value"]] for x in v)
        return str(v) in [str(x) for x in cond["value"]]
    if op == "not_in":
        if isinstance(v, list):
            return has and not any(str(x) in [str(y) for y in cond["value"]] for x in v)
        return has and str(v) not in [str(x) for x in cond["value"]]
    if op in ("gte", "lte"):
        try:
            a, b = float(v), float(cond["value"])
        except (TypeError, ValueError):
            return False
        return a >= b if op == "gte" else a <= b
    if op == "includes":
        return isinstance(v, list) and cond["value"] in v
    if op == "includes_any":
        return isinstance(v, list) and any(x in v for x in cond["value"])
    if op == "scale_gte":
        return isinstance(v, dict) and any(str(x).replace(".", "").isdigit() and float(x) >= float(cond["value"]) for x in v.values())
    return True


SHORT_FORM = COMMON.get("short_form") or {}


def short_form_allowed(code):
    return code in (SHORT_FORM.get("enabled_for") or [])


def in_form(code, q, form):
    """The short form is the SAME instrument with the non-core items routed out.

    Not a second questionnaire: its answers pool with the long form's item by
    item, which is the only reason a short form is worth having. Which items are
    core is a data decision in tools/schema/*.json.
    """
    if form != "short" or not short_form_allowed(code):
        return True
    return bool(q.get("core"))


def flat_questions(code, answers, form="full"):
    """Questions currently in scope, in order, respecting section- and item-level
    routing and the chosen form."""
    out = []
    for sec in INSTRUMENTS[code]["sections"]:
        if not show_if(sec.get("show_if"), answers):
            continue
        for q in sec["questions"]:
            if q.get("hidden") or (q.get("flags") and "honeypot" in q["flags"]):
                continue  # honeypots are meaningless in a bot context
            if not in_form(code, q, form):
                continue
            if show_if(q.get("show_if"), answers):
                out.append((sec, q))
    return out


# ---------------------------------------------------------------- progress
# Deliberately the same model as the web questionnaire (web/app.js
# progressStats): counted over the questions currently IN SCOPE, with grids
# weighted by row count. The two channels must report completion the same way,
# or a respondent who switches between them sees the bar jump.

def is_counted(q):
    return q["type"] != "info" and not (q.get("flags") and "honeypot" in q["flags"])


def question_weight(q):
    if q["type"] == "likert_grid":
        return len(q.get("rows") or []) or 1
    if q["type"] == "matrix":
        return len(q.get("row_options") or []) or 1
    return 1


def answered_weight(q, answers):
    v = answers.get(q["id"])
    if q["type"] in ("likert_grid", "matrix"):
        if not isinstance(v, dict):
            return 0
        return len([x for x in v.values() if x not in (None, "")])
    if v in (None, "", [], False):
        return 0
    return 1


def must_answer(q):
    """Every question blocks progress except display-only items and those the
    schema explicitly marks `optional`. Mirrors mustAnswer() in web/app.js."""
    return is_counted(q) and q["type"] != "consent" and not q.get("optional")


def is_complete(q, answers):
    """Fully answered, not merely started: a grid needs every row."""
    if q["type"] == "consent":
        return answers.get(q["id"]) is True
    return answered_weight(q, answers) >= question_weight(q)


def progress_stats(code, answers, form="full"):
    total = done = 0
    for sec in INSTRUMENTS[code]["sections"]:
        if not show_if(sec.get("show_if"), answers):
            continue
        for q in sec["questions"]:
            if not is_counted(q) or not show_if(q.get("show_if"), answers):
                continue
            if not in_form(code, q, form):
                continue
            w = question_weight(q)
            total += w
            done += min(answered_weight(q, answers), w)
    pct = round(100 * done / total) if total else 0
    return done, total, pct


def minutes_left(code, done, total, form="full"):
    """Minutes remaining, from the schema's estimate scaled by work left.

    A percentage answers "how far am I"; it does not answer "can I finish this
    now", and on a chat surface -- where the respondent is one notification away
    from leaving -- the second question is the one that decides whether they do.
    Rounded up, because an optimistic estimate that turns out wrong costs more
    trust than an honest one.
    """
    meta = next((i for i in COMMON["instruments"] if i["code"] == code), None)
    if not meta or not total:
        return ""
    budget = meta["est_minutes"]
    if form == "short":
        budget = (SHORT_FORM.get("est_minutes") or {}).get(code, budget)
    left = budget * (1 - done / total)
    if left < 0.75:
        return "less than a minute left"
    return f"about {math.ceil(left)} min left"


def progress_bar(pct, width=12):
    """Block-drawing bar. Renders identically on every Telegram client and costs
    no bandwidth, which matters on the connections this instrument targets."""
    filled = round(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


def progress_line(st):
    """The header on every question.

    Shows the bar, the percentage and the time left -- not "12/34 answered",
    which the web questionnaire dropped for being discouraging out of proportion
    to what it tells anyone. The two channels must agree: a respondent who
    switches between them must not see the figure jump.
    """
    done, total, pct = progress_stats(lookup_code(st), st["answers"], st.get("form", "full"))
    # minutes_left reads the real, possibly still-unset code: before R1 is
    # answered there is no instrument to time, and it already returns "" when
    # it cannot find one -- which is the right thing to show on section R.
    left = minutes_left(st["code"], done, total, st.get("form", "full"))

    # Add encouragement at milestones
    milestone = ENCOURAGEMENT.get(pct)
    base = f"{progress_bar(pct)}  {pct}%" + (f"  ·  <i>{left}</i>" if left else "")
    if milestone and not st.get(f"_encouraged_{pct}"):
        st[f"_encouraged_{pct}"] = True
        return f"{base}\n{milestone}"
    return base


# ---------------------------------------------------------------- storage
# All persistence is delegated to tools/aimap_db.py so the bot and the web
# collection server share one database, one schema and one PII rule.

save_session = db.save_session
load_session = db.load_session
clear_session = db.clear_session


def compute_scores(code, answers, started_at):
    s = {}
    if code == "IND":
        aq = find_question("IND", "G5")
        if aq and answers.get("G5") is not None:
            s["flag_attention"] = str(answers["G5"]) != str(aq.get("expected"))
        f3 = answers.get("F3")
        if isinstance(f3, dict):
            vals = [float(f3[k]) for k in ("intent1", "intent2", "intent3")
                    if str(f3.get(k, "")).isdigit()]
            if vals:
                s["emigration_intention"] = sum(vals) / len(vals)
    try:
        dur = (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds()
        s["duration_seconds"] = round(dur)
        s["flag_speeder"] = dur < 60
    except Exception:
        pass
    return s


def persist(st, chat_id):
    """Store the completed response. The Telegram chat id is hashed, never stored raw."""
    db.save_response({
        "response_id": st["resp_id"],
        "instrument": st["code"],
        "instrument_version": db.INSTRUMENT_VERSION,
        "language": st["lang"],
        "mode": "telegram",
        "form": st.get("form", "full"),
        "recruit_arm": st.get("arm", "open"),
        "referrer": st.get("referrer"),
        "started_at": st["started_at"],
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "answers": st["answers"],
        "revision": int(st.get("revision") or 0),
        "scores": compute_scores(st["code"], st["answers"], st["started_at"]),
        "source_ref": db.hash_ref("tg", chat_id),
    })


def heartbeat(st, sec=None, q=None):
    """Record how far this respondent has got. No answer content.

    On a chat surface most abandonment is silent -- the respondent simply stops
    replying -- so without this the Telegram drop-off rate is unmeasurable and
    reads as zero. The write is local SQLite, in the same file as everything
    else, so it costs nothing worth optimising.
    """
    if not st.get("code"):
        return      # still on section R: no instrument chosen yet, nothing to record
    done, total, pct = progress_stats(st["code"], st["answers"], st.get("form", "full"))
    try:
        db.save_partial({
            "response_id": st["resp_id"], "instrument": st["code"], "mode": "telegram",
            "form": st.get("form", "full"), "recruit_arm": st.get("arm", "open"),
            "last_qid": q["id"] if q else st.get("current_qid"),
            "section_id": sec["id"] if sec else None,
            "answered": done, "total": total, "pct": pct,
            "started_at": st["started_at"],
        })
    except Exception:                      # monitoring must never block a respondent
        log.exception("heartbeat failed for %s", st["resp_id"])


# ---------------------------------------------------------------- ui

# ---------------------------------------------------------------- presentation
#
# Telegram gives a bot no control over font size or colour: message text supports
# bold, italic, code and blockquote, and inline buttons have no styling at all.
# So "make each question type look different" has to be carried by a glyph, a
# one-line instruction and consistent spacing, which is what these do. Anything
# claiming otherwise would be a bot that renders differently in the developer's
# client and nowhere else.

TYPE_BADGE = {
    "consent":     ("📋", "Please read and confirm"),
    "single":      ("🔘", "Choose one option"),
    "multi":       ("☑️", "Choose any that apply"),
    "checklist":   ("☑️", "Tick everything that is true"),
    "likert_grid": ("📊", "Rate each statement"),
    "matrix":      ("📊", "Rate each item"),
    "scale":       ("🎚", "Pick a number on the scale"),
    "text":        ("✍️", "Type your answer below"),
    "longtext":    ("✍️", "Type your answer below"),
    "number":      ("🔢", "Type a number"),
    "email":       ("✉️", "Type your email address"),
    "phone":       ("📞", "Type your phone number"),
    "info":        ("ℹ️", ""),
}

# Encouragement messages shown at milestones
ENCOURAGEMENT = {
    25: "🌟 Great start! You're 25% done.",
    50: "🎯 Halfway there! Keep going.",
    75: "🚀 Almost done! Just a few more questions.",
    90: "⭐ Final stretch! You're almost finished.",
}

RULE = "──────────"

VALIDATORS = COMMON.get("validators", {})


def check_format(q, value):
    """Validate a typed answer against the shared rule in common.json.

    The same pattern runs in the web form, so a contact one channel accepts and
    the other rejects cannot happen -- which would otherwise be a contact the
    study simply fails to follow up, discovered months later.
    """
    rule = VALIDATORS.get(q.get("validate") or "")
    if not rule:
        return True, None
    import re
    if re.match(rule["pattern"], value.strip()):
        return True, None
    return False, rule["message"]


def grid_progress(q, answers, current):
    """Which rows of this grid are done, as a monospace strip.

    A ten-row grid asks ten questions off one stem, and without this the
    respondent has no idea whether they are near the end of it. Monospace keeps
    the dots aligned; coloured emoji would wrap on a narrow screen and turn a
    progress strip into a wall.
    """
    got = answers.get(q["id"]) or {}
    rows = q.get("rows") or q.get("row_options") or []
    marks = []
    for i, r in enumerate(rows):
        if i == current:
            marks.append("◉")
        elif isinstance(got, dict) and got.get(r["value"]) not in (None, ""):
            marks.append("●")
        else:
            marks.append("○")
    return "".join(marks)


def grid_block(st, sec, q, row_index, lang=LANG):
    """One row of a grid, rendered so it reads as a SUB-question.

    The stem is repeated on every row -- it has to be, there is no persistent
    header in a chat -- but repeating it in the same weight as the row made the
    two indistinguishable, and the row is the thing being answered. So the stem
    goes into a blockquote, which Telegram indents behind a bar, and the row gets
    the marker, the bold and the count. Telegram gives a bot no colour in message
    text; the marker emoji is the only colour available and is spent here.
    """
    rows = q.get("rows") or q.get("row_options") or []
    row = rows[row_index]
    noun = q.get("row_noun", "item")
    done, total, _ = progress_stats(st["code"], st["answers"], st.get("form", "full"))

    head = (f"{progress_line(st)}\n"
            f"<i>{tr(sec['title'], lang)}</i>\n{RULE}\n"
            f"📊 <i>{noun.capitalize()} {row_index + 1} of {len(rows)}</i>\n\n")
    stem = f"<blockquote>{tr(q['text'], lang)}</blockquote>\n"
    body = (f"🔹 <b>{tr(row['label'], lang)}</b>\n"
            f"<code>{grid_progress(q, st['answers'], row_index)}</code>")
    return head + stem + body


def question_block(st, sec, q, lang=LANG):
    """The whole message body for one question, assembled in one place."""
    glyph, hint = TYPE_BADGE.get(q["type"], ("•", ""))
    code = lookup_code(st)
    done, total, _ = progress_stats(code, st["answers"], st.get("form", "full"))
    qs = flat_questions(code, st["answers"], st.get("form", "full"))
    position = sum(1 for i, (_, x) in enumerate(qs) if i <= st["idx"] and is_counted(x))
    # Counted over the questions currently IN SCOPE, like the bar above it. The
    # total moves as branches open and close, which is honest: a fixed
    # denominator would promise a length the routing does not intend to deliver.
    in_scope = sum(1 for _, x in qs if is_counted(x))

    head = (f"{progress_line(st)}\n"
            f"<i>{tr(sec['title'], lang)}</i>  ·  <i>question {position} of {in_scope}</i>\n"
            f"{RULE}\n")
    if hint:
        head += f"{glyph} <i>{hint}</i>\n\n"
    else:
        head += "\n"

    body = f"<b>{tr(q['text'], lang)}</b>" if q.get("text") else ""
    if q.get("help"):
        body += f"\n<blockquote>{tr(q['help'], lang)}</blockquote>"
    if q.get("max_select"):
        body += f"\n<i>Choose up to {q['max_select']}.</i>"
    rule = VALIDATORS.get(q.get("validate") or "")
    if rule:
        body += f"\n<i>For example: {rule['placeholder']}</i>"
    return head + body


def kb(rows):
    return InlineKeyboardMarkup(rows)


def ask_text(label, placeholder="Type it here"):
    """Open the respondent's keyboard on the reply box, with a placeholder in it.

    Telegram gives a bot no way to put an editable field inside an inline
    keyboard -- a keyboard holds buttons and nothing else. ForceReply is the
    nearest thing it does offer: the client focuses the message box and shows
    `input_field_placeholder` in it, so the respondent is typing immediately
    rather than hunting for where the answer goes.

    Used only for the "Other, please specify" follow-up. A normal text question
    keeps its inline keyboard instead, because ForceReply would replace it and
    take the Back button with it -- and a respondent who mis-taps and cannot go
    back is the most common way a chat survey loses someone.
    """
    return ForceReply(input_field_placeholder=placeholder[:64], selective=False)


def pending_other(code, q, answers):
    """A chosen option that allows free text but has not been given any yet.

    Returns the option, or None. Checked at DONE rather than on the tap itself:
    interrupting a multi-select to demand a specification stops the respondent
    part-way through choosing, and they may have more to tick.
    """
    if answers.get(q["id"] + "_text"):
        return None
    chosen = answers.get(q["id"])
    chosen = chosen if isinstance(chosen, list) else [chosen]
    for o in resolve_options(code, q):
        if o.get("allow_text") and o["value"] in chosen:
            return o
    return None


BACK_LABEL = "⬅️ Back"
SKIP_LABEL = "⏭ Skip"
DONE_LABEL = "➡️ Done"

# Questions that can be skipped without affecting AI adoption analysis
# These are typically demographic or less critical questions
SKIPPABLE_QUESTIONS = {
    "A4",  # Gender - demographic, not AI-specific
    "A5",  # Education level - demographic, not AI-specific  
    "A6",  # Occupation - demographic, not AI-specific
    "A7",  # Years of experience - not directly AI-related
    "B4",  # Internet problems - infrastructure, not AI adoption
    "D1",  # Trust in organizations - general trust, not AI-specific
    "D2",  # Comfort with computer decisions - general attitude
    "D3",  # Knowledge of complaint process - general awareness
    "E2",  # AI concerns - attitudes, not adoption behavior
    "E3",  # Interest in learning - future intention, not current adoption
}


def review_row(st):
    """Keep and Finish, offered on every question while reviewing.

    Both matter. Without Keep, changing one answer near the end means tapping
    through everything before it; without Finish, the only way out of a review is
    to reach the last question, which is precisely what someone returning to fix
    one thing will not do.
    
    CRITICAL: Only show these buttons when actually reviewing (st.get("review") is True).
    On a fresh survey, these buttons are confusing and serve no purpose.
    """
    if not st.get("review"):
        return []
    return [[InlineKeyboardButton("⏭ Keep this answer", callback_data="keep"),
             InlineKeyboardButton("✅ Finish review", callback_data="endreview")]]


def nav_row(q, st, lang, include_skip=True):
    """Back (and optionally Skip) on one row -- the Telegram counterpart of the
    web questionnaire's Back button. Without it a respondent who mis-taps has to
    abandon and restart, which is the single most common cause of drop-out on
    chat-delivered surveys.
    
    Skip is shown for optional questions and non-essential demographic questions
    that don't affect AI adoption analysis.
    """
    row = []
    if st.get("idx", 0) > 0 or st.get("_grid_row", 0) > 0:
        row.append(InlineKeyboardButton(BACK_LABEL, callback_data="back"))
    
    # Show skip for optional questions OR non-essential demographic questions
    skippable = q.get("optional") or q.get("id") in SKIPPABLE_QUESTIONS
    if include_skip and skippable:
        row.append(InlineKeyboardButton(SKIP_LABEL, callback_data="skip"))
    
    return review_row(st) + ([row] if row else [])


def opt_keyboard(q, opts, answers, lang, st=None):
    """One button per option, one per row (long Amharic labels wrap badly side by side)."""
    multi = q["type"] in ("multi", "checklist")
    chosen = answers.get(q["id"], []) if multi else None
    rows = []
    for i, o in enumerate(opts):
        label = tr(o["label"], lang)
        if multi and o["value"] in (chosen or []):
            label = "✓ " + label
        rows.append([InlineKeyboardButton(label[:64], callback_data=f"o|{i}")])
    if multi:
        # Telegram gives buttons no colour and no size, so "prominent" has to be
        # built from the only thing available: the label. The spacer row detaches
        # it from the options above, and the running count doubles as feedback
        # that a tap registered -- which the respondent otherwise has to infer
        # from a tick appearing somewhere in a long list.
        n = len(chosen or [])
        done_label = (f"✅  DONE · {n} selected" if n
                      else "✅  DONE: choose at least one first")
        rows.append([InlineKeyboardButton("· · · · · · · · · · · · · ·", callback_data="noop")])
        rows.append([InlineKeyboardButton(done_label, callback_data="done")])
    if st is not None:
        rows += nav_row(q, st, lang)
    elif q.get("optional"):
        rows.append([InlineKeyboardButton(SKIP_LABEL, callback_data="skip")])
    return kb(rows)


def grid_keyboard(q, row, lang, st=None):
    rows = [[InlineKeyboardButton(tr(c["label"], lang)[:64], callback_data=f"g|{i}")]
            for i, c in enumerate(q["scale"])]
    if st is not None:
        rows += nav_row(q, st, lang)
    return kb(rows)


async def send_question(update_or_q, ctx, st):
    """Render the current question. Auto-advances past info blocks."""
    chat_id = st["chat_id"]
    lang = st["lang"]
    qs = flat_questions(lookup_code(st), st["answers"], st.get("form", "full"))
    if st["idx"] >= len(qs):
        return await finish(ctx, st)

    sec, q = qs[st["idx"]]
    st["current_qid"] = q["id"]
    save_session(chat_id, st)
    heartbeat(st, sec, q)

    header = question_block(st, sec, q, lang) + "\n\n"

    if q["type"] == "consent":
        body = (f"{progress_line(st)}\n<i>{tr(sec['title'], lang)}</i>\n{RULE}\n"
                f"📋 <i>Please read and confirm</i>\n\n"
                + tr(COMMON["consent"]["text"], lang))
        # Keep/Finish belong here too: consent is the first screen of a review,
        # and without them the only way past it is to re-consent.
        markup = kb(review_row(st) +
                    [[InlineKeyboardButton("✅ " + tr(COMMON["consent"]["affirm"], lang)[:60],
                                           callback_data="consent")],
                     [InlineKeyboardButton("❌ No, I do not agree", callback_data="decline")]])
        return await ctx.bot.send_message(chat_id, body, reply_markup=markup, parse_mode=ParseMode.HTML)

    if q["type"] == "info":
        await ctx.bot.send_message(chat_id, header, parse_mode=ParseMode.HTML)
        st["idx"] += 1
        save_session(chat_id, st)
        return await send_question(update_or_q, ctx, st)

    text = header

    if q["type"] in ("single", "multi", "checklist"):
        opts = resolve_options(lookup_code(st), q)
        st["_opts"] = [o["value"] for o in opts]
        save_session(chat_id, st)
        return await ctx.bot.send_message(chat_id, text,
                                          reply_markup=opt_keyboard(q, opts, st["answers"], lang, st),
                                          parse_mode=ParseMode.HTML)

    if q["type"] == "likert_grid":
        st["_grid_row"] = st.get("_grid_row", 0)
        row = q["rows"][st["_grid_row"]]
        save_session(chat_id, st)
        return await ctx.bot.send_message(chat_id, grid_block(st, sec, q, st["_grid_row"], lang),
            reply_markup=grid_keyboard(q, row, lang, st),
            parse_mode=ParseMode.HTML)

    if q["type"] == "scale":
        sc = q["scale"]
        rows = [[InlineKeyboardButton(str(i), callback_data=f"s|{i}") for i in range(sc["min"], sc["max"] + 1)]]
        rows += nav_row(q, st, lang)
        text += f"\n<i>{sc['min']} = {tr(sc.get('min_label'), lang)} · {sc['max']} = {tr(sc.get('max_label'), lang)}</i>"
        return await ctx.bot.send_message(chat_id, text, reply_markup=kb(rows), parse_mode=ParseMode.HTML)

    if q["type"] == "repeatable":
        # Repeatable blocks (list every AI system, dataset, GPU) are a table, and
        # a chat thread is the wrong surface for one. They appear only in ORG,
        # which is not offered here -- this guard exists so that adding an
        # instrument later fails loudly instead of silently collecting prose.
        log.warning("repeatable question %s reached the bot; skipping", q["id"])
        st["answers"][q["id"]] = []
        return await advance(ctx, st)

    # Free text / number / email / phone.
    #
    # Telegram allows one reply_markup per message, so an inline Back button and
    # a focused input box cannot live on the same message. Leaving only the
    # button meant a question whose answer is typed showed no sign of wanting
    # anything typed -- just a Back button above an idle "Write a message..."
    # box, which is a fair thing to stare at.
    #
    # So: the question keeps its Back button, and a second, deliberately tiny
    # message carries the ForceReply that opens the keyboard with a placeholder
    # in it. Two messages is the cost of having both, and the alternative --
    # dropping Back -- removes the only way out of a mis-tap, which is the most
    # common reason someone abandons a chat survey.
    nav = nav_row(q, st, lang)
    st["awaiting_text"] = True
    save_session(chat_id, st)
    if st.get("review") and q["id"] in st["answers"]:
        # Show what is already there, or a review turns into retyping.
        text += f"\n\n<i>Currently:</i> <code>{tr(str(st['answers'][q['id']]))}</code>"
    await ctx.bot.send_message(chat_id, text, reply_markup=kb(nav) if nav else None,
                               parse_mode=ParseMode.HTML)
    rule = VALIDATORS.get(q.get("validate") or "")
    placeholder = (rule or {}).get("placeholder") or {
        "number": "Type a number",
        "longtext": "Type as much or as little as you like",
    }.get(q["type"], "Type your answer here")
    return await ctx.bot.send_message(chat_id, "✍️ <i>Your answer:</i>",
        reply_markup=ask_text("answer", placeholder), parse_mode=ParseMode.HTML)


async def go_back(ctx, st):
    """Step back one question, clearing the answer so it can be given again.

    Routing is recomputed from the answers on every render, so clearing the
    answer is what makes a branch taken by mistake actually reversible -- simply
    decrementing the index would leave the branch open and desynchronise the
    question list from the stored answers.
    """
    if st.get("_grid_row", 0) > 0:            # mid-grid: step back one row
        st["_grid_row"] -= 1
        save_session(st["chat_id"], st)
        return await send_question(None, ctx, st)

    qs = flat_questions(lookup_code(st), st["answers"], st.get("form", "full"))
    if st["idx"] < len(qs):
        st["answers"].pop(qs[st["idx"]][1]["id"], None)   # clear the current one
    st["idx"] = max(0, st["idx"] - 1)
    qs = flat_questions(lookup_code(st), st["answers"], st.get("form", "full"))
    if st["idx"] < len(qs):
        returning_to = qs[st["idx"]][1]["id"]
        st["answers"].pop(returning_to, None)   # and the one we return to
        if returning_to == "R1":
            # Stepping back onto the routing question undoes the routing: the
            # branch it chose, and the form settled for it, no longer apply
            # until R1 is answered again.
            st["code"] = None
            st["form"] = "full"
    st.pop("_grid_row", None)
    st.pop("awaiting_text", None)
    save_session(st["chat_id"], st)
    await send_question(None, ctx, st)


async def advance(ctx, st):
    st["idx"] += 1
    st.pop("_grid_row", None)
    st.pop("awaiting_text", None)
    save_session(st["chat_id"], st)
    await send_question(None, ctx, st)


async def finish(ctx, st):
    persist(st, st["chat_id"])
    chat_id = st["chat_id"]
    clear_session(chat_id)
    done, total, _ = progress_stats(st["code"], st["answers"], st.get("form", "full"))

    # The completion screen was a progress bar with a sentence attached, which
    # after twenty minutes of questions reads as another step rather than the
    # end. Telegram gives a bot no headings and no font sizes, but a message
    # made only of emoji renders LARGE in every client -- so the thank-you is
    # sent as its own message first, and the detail follows in a second. The
    # separation is what makes it feel like an ending.
    if st.get("review"):
        done, total, _ = progress_stats(st["code"], st["answers"], st.get("form", "full"))
        await ctx.bot.send_message(
            chat_id,
            f"<b>SAVED</b>\n{RULE}{RULE}\n"
            f"Your answers have been updated.\n"
            f"<i>{done} of {total} questions · revision {st.get('revision', 1)}</i>\n\n"
            f"You can come back and change them again at any time with /start.",
            parse_mode=ParseMode.HTML)
        return

    await ctx.bot.send_message(chat_id, "🎉")
    await ctx.bot.send_message(chat_id,
        f"<b>THANK YOU</b>\n"
        f"{RULE}{RULE}\n"
        f"Your answers have been recorded.\n"
        f"<i>{done} of {total} questions · {progress_bar(100)} 100%</i>",
        parse_mode=ParseMode.HTML)

    lines = [
        "<b>What happens next</b>",
        "",
        "📊  Your answers are combined with everyone else's. Nothing you sent is "
        "published on its own.",
        "🌍  The results are published openly, free for anyone to read and re-use.",
        "🔒  We never saw your name or phone number. Any contact details you chose "
        "to give are stored apart from your answers and deleted after follow-up.",
    ]
    rows = []
    # The invitation is offered where the arm applies, and only now: a chain
    # seeded by someone who never finished is not a chain.
    if referral_applies(st["code"]):
        lines += [
            "",
            "<b>One more thing, if you have a moment</b>",
            "",
            "This survey reaches people through people. The link below records that "
            "the next person came through you (not who you are), and that is what "
            "lets us correct for whom an online survey would otherwise miss.",
        ]
        rows.append([InlineKeyboardButton("🔗 Invite someone",
                                          callback_data=f"invite|{st['code']}")])
    await ctx.bot.send_message(chat_id, "\n".join(lines),
                               reply_markup=kb(rows) if rows else None,
                               parse_mode=ParseMode.HTML,
                               disable_web_page_preview=True)


def referral_applies(code):
    arms = (COMMON.get("recruitment") or {}).get("arms") or []
    ref = next((a for a in arms if a["code"] == "referral"), None)
    return bool(ref and code in (ref.get("applies_to") or []))


async def issue_invite(ctx, chat_id, code):
    """Mint an invitation code and send it as a t.me deep link.

    The code identifies the RESPONSE, not the person: the owner reference is
    already a hash of the chat id. A respondent can pass the link on without
    passing on anything about themselves.
    """
    ref = db.issue_referral(db.hash_ref("tg", chat_id), code)
    me = await ctx.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{ref}"
    await ctx.bot.send_message(chat_id,
        f"Your invitation link:\n{link}\n\nOr they can send <code>/start ref_{ref}</code> to this bot.",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ---------------------------------------------------------------- handlers

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Begin, resume, or accept an invitation.

    The study is fielded in English only, so there is no language step. A
    `?start=ref_ABC123` deep link carries an invitation code; it is validated
    here rather than at submission, so a mistyped code becomes an open-arm
    response instead of a dangling edge in the referral graph.
    """
    refresh_schema_if_changed()
    chat_id = update.effective_chat.id
    arm, referrer = "open", None
    payload = (ctx.args[0] if getattr(ctx, "args", None) else "") or ""
    if payload.startswith("ref_"):
        code = payload[4:].strip().upper()
        if db.referral(code):
            arm, referrer = "referral", code
            await ctx.bot.send_message(chat_id, 
                "🎉 <b>Welcome!</b> You were invited by someone who already completed the survey. "
                "Your participation helps us understand AI adoption across Ethiopia.",
                parse_mode=ParseMode.HTML)
        else:
            await ctx.bot.send_message(chat_id, "That invitation code was not recognised, so you will be recorded as "
                         "having found the survey yourself. Everything else works the same.")
    elif payload in ("list", "booster"):
        arm = payload

    # Already finished once? Offer to review rather than quietly recording a
    # second response. Someone who opens the bot again is far likelier to be
    # coming back to their own answers than to be a new person on the same
    # handset, and counting them twice is a worse error than one extra tap.
    prior = db.latest_for_source(db.hash_ref("tg", chat_id))
    if prior and not load_session(chat_id):
        when = (prior.get("submitted_at") or "")[:10]
        again = "once" if not prior["revision"] else f"{prior['revision'] + 1} times"
        return await ctx.bot.send_message(
            chat_id,
            f"You already completed this questionnaire on <b>{when}</b>"
            + (f" and have revised it {again}." if prior["revision"] else ".")
            + "\n\nWould you like to look back through your answers and change "
              "anything? Nothing changes unless you choose a different answer.",
            reply_markup=kb([
                [InlineKeyboardButton("📝 Review my answers", callback_data="review")],
                [InlineKeyboardButton("➕ Start a new, separate response",
                                      callback_data="fresh")],
                [InlineKeyboardButton("✖️ No thanks", callback_data="bye")],
            ]),
            parse_mode=ParseMode.HTML)

    # An unfinished session is offered back rather than silently overwritten:
    # on a chat surface people are interrupted constantly, and losing twenty
    # answered questions to a stray /start is how a respondent stops returning.
    st = load_session(chat_id)
    if st and st.get("answers"):
        done, total, pct = progress_stats(lookup_code(st), st["answers"], st.get("form", "full"))
        left = minutes_left(st["code"], done, total, st.get("form", "full"))
        return await ctx.bot.send_message(chat_id,
            f"You have an unfinished questionnaire.\n{progress_bar(pct)}  {pct}%"
            + (f"  ·  <i>{left}</i>" if left else ""),
            reply_markup=kb([[InlineKeyboardButton("▶️ Continue", callback_data="resume")],
                             [InlineKeyboardButton("↺ Start over", callback_data="fresh")]]),
            parse_mode=ParseMode.HTML)

    await begin(ctx, chat_id, arm, referrer)


async def send_length_choice(ctx, chat_id, code):
    """Offered only where the schema defines a short form for this branch, and
    only once R1 has chosen it: "how much time do you have" is unanswerable
    before the respondent knows what they are being asked to do."""
    meta = next(i for i in COMMON["instruments"] if i["code"] == code)
    short_min = (SHORT_FORM.get("est_minutes") or {}).get(code)
    await ctx.bot.send_message(chat_id,
        "How much time do you have?\n\n"
        f"<b>{SHORT_FORM.get('label', 'Quick version')}</b>: the essential questions only. "
        "Every answer still counts.\n"
        f"<b>{SHORT_FORM.get('long_label', 'Full version')}</b>: adds the detail that makes "
        "comparisons possible.",
        reply_markup=kb([
            [InlineKeyboardButton(f"⚡ {SHORT_FORM.get('label', 'Quick')} · about {short_min} min",
                                  callback_data="form|short")],
            [InlineKeyboardButton(f"📋 {SHORT_FORM.get('long_label', 'Full')} · about "
                                  f"{meta['est_minutes']} min",
                                  callback_data="form|full")],
        ]), parse_mode=ParseMode.HTML)


async def continue_after_routing(ctx, st):
    """The common tail of every path through R1: send the branch's own intro,
    once, now that it is known, then carry on into its first question."""
    chat_id = st["chat_id"]
    await ctx.bot.send_message(chat_id, tr(INSTRUMENTS[st["code"]]["intro"]))
    save_session(chat_id, st)
    await advance(ctx, st)


async def route_after_r1(ctx, st, value):
    """R1 has just been answered: translate it into the instrument code every
    other table already uses, then settle the form before moving on.

    Organization always gets the short form here: its full survey runs to
    180+ items with repeatable tables (D6) and eight-plus-row matrices (YH3,
    YF1, K0...), which a chat interface cannot fill in conversationally -- there
    is no way to complete a table one message at a time. The short form is a
    different shape, about 30 plain single/multi/grid questions, the same
    "core" set offered as the web page's Quick version: short and simple enough
    to actually work here. So the length choice below is never offered for it.
    """
    code = BRANCH_CODE[value]
    st["code"] = code
    if code == "ORG":
        st["form"] = "short"
        return await continue_after_routing(ctx, st)
    if short_form_allowed(code):
        save_session(st["chat_id"], st)
        return await send_length_choice(ctx, st["chat_id"], code)
    st["form"] = "full"
    return await continue_after_routing(ctx, st)


async def begin(ctx, chat_id, arm="open", referrer=None):
    """Start a fresh session at the top of the questionnaire: consent, then the
    routing question (R1). Which instrument this becomes is not known yet --
    that is what R1 answers -- so st["code"] starts unset and is filled in once
    R1 is answered, in route_after_r1."""
    st = {
        "chat_id": chat_id, "code": None, "lang": LANG, "form": "full",
        "arm": arm, "referrer": referrer,
        "answers": {}, "idx": 0, "resp_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_session(chat_id, st)
    await ctx.bot.send_message(chat_id,
        "<b>AI-MAP Ethiopia</b>\nAn independent study of how AI is really being used in Ethiopia.\n\n"
        "Your answers are anonymous; we never see your name or phone number.",
        parse_mode=ParseMode.HTML)
    await send_question(None, ctx, st)


async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    clear_session(update.effective_chat.id)
    await begin(ctx, update.effective_chat.id)


async def cmd_progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Where am I, and how much is left. Asked often enough on a chat surface --
    where there is no progress bar pinned to the screen -- to deserve a command."""
    st = load_session(update.effective_chat.id)
    if not st:
        return await update.message.reply_text("No questionnaire in progress. Send /start to begin.")
    done, total, pct = progress_stats(lookup_code(st), st["answers"], st.get("form", "full"))
    left = minutes_left(st["code"], done, total, st.get("form", "full"))
    await update.message.reply_text(f"{progress_bar(pct)}  {pct}%\n{done} of {total} answered" + (f"\n{left}" if left else "")
        + "\n\nSend /start to carry on where you left off.",
        parse_mode=ParseMode.HTML)


async def cmd_invite(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Issue an invitation link at any time, not only at the end."""
    chat_id = update.effective_chat.id
    st = load_session(chat_id)
    code = st["code"] if st else "CIT"
    if not referral_applies(code):
        return await update.message.reply_text("Invitations are not used for this questionnaire.")
    await issue_invite(ctx, chat_id, code)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("AI-MAP Ethiopia: an independent study of how AI is really being used in Ethiopia.\n\n"
        "/start: begin, or carry on where you left off\n"
        "/progress: how far you have got and how long is left\n"
        "/invite: get a link to pass on to someone else\n"
        "/restart: start over from the beginning\n"
        "/privacy: how your data is handled\n\n"
        "You can go ⬅️ Back at any question. Your answers are anonymous: we never see "
        "your name or phone number.")


async def cmd_privacy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tr(COMMON["consent"]["text"], "en") + "\n\n" + COMMON["consent"]["controller"])


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    qd = update.callback_query
    await qd.answer()
    chat_id = update.effective_chat.id
    data = qd.data

    if data == "resume":
        st = load_session(chat_id)
        if not st:
            return await qd.edit_message_text("That session has expired. Send /start to begin again.")
        await qd.edit_message_reply_markup(None)
        return await send_question(None, ctx, st)

    if data == "bye":
        return await qd.edit_message_text(
            "No problem. Your answers are already recorded. Send /start any time.")

    if data == "review":
        prior = db.latest_for_source(db.hash_ref("tg", chat_id))
        if not prior:
            return await qd.edit_message_text(
                "Those answers are no longer available. Send /start to begin again.")
        st = {
            "chat_id": chat_id, "code": prior["instrument"], "lang": LANG,
            "form": prior.get("form") or "full",
            "arm": prior.get("recruit_arm") or "open",
            "referrer": prior.get("referrer"),
            "answers": dict(prior["answers"]),
            "idx": 0,
            "resp_id": prior["response_id"],          # the SAME response, revised
            "revision": int(prior.get("revision") or 0) + 1,
            "review": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        save_session(chat_id, st)
        await qd.edit_message_text(
            "Going through your answers from the start. Every question already has "
            "your answer on it.\n\n"
            "▸ Tap a different option to change it\n"
            "▸ <b>Keep</b> leaves it as it is and moves on\n"
            "▸ <b>Finish</b> saves and stops, wherever you have got to",
            parse_mode=ParseMode.HTML)
        return await send_question(None, ctx, st)

    if data == "fresh":
        # Starting over must not silently drop the recruitment arm. Someone who
        # arrived on an invitation and then restarted is still a referred
        # respondent, and losing that reclassifies them into the one arm that
        # cannot be weighted.
        old = load_session(chat_id) or {}
        arm, referrer = old.get("arm", "open"), old.get("referrer")
        clear_session(chat_id)
        await qd.edit_message_reply_markup(None)
        return await begin(ctx, chat_id, arm, referrer)

    if data.startswith("form|"):
        # The length choice offered after R1, for a branch whose schema defines
        # a short form: the session already has its code, so only the form
        # still needs settling.
        form = data.split("|", 1)[1]
        await qd.edit_message_reply_markup(None)
        st = load_session(chat_id)
        if not st or not st.get("code"):
            return await qd.edit_message_text("That session has expired. Send /start to begin again.")
        st["form"] = form
        return await continue_after_routing(ctx, st)

    if data.startswith("invite|"):
        # The instrument travels in the callback data: by the time this is tapped
        # the session has been cleared, so it cannot be looked up.
        await qd.edit_message_reply_markup(None)
        return await issue_invite(ctx, chat_id, data.split("|", 1)[1])

    st = load_session(chat_id)
    if not st:
        return await qd.edit_message_text("Session expired. Send /start to begin again.")

    qs = flat_questions(lookup_code(st), st["answers"], st.get("form", "full"))
    if st["idx"] >= len(qs):
        return await finish(ctx, st)
    _, q = qs[st["idx"]]
    lang = st["lang"]

    if data == "noop":
        return      # the spacer row above DONE; it exists to separate, not to act

    if data == "decline":
        clear_session(chat_id)
        return await qd.edit_message_text("No problem: thank you for your time.")

    if data == "consent":
        st["answers"][q["id"]] = True
        await qd.edit_message_text("✅ " + tr(COMMON["consent"]["affirm"], lang))
        return await advance(ctx, st)

    if data == "keep":
        await qd.edit_message_reply_markup(None)
        return await advance(ctx, st)

    if data == "endreview":
        await qd.edit_message_reply_markup(None)
        return await finish(ctx, st)

    if data == "back":
        await qd.edit_message_reply_markup(None)
        return await go_back(ctx, st)

    if data == "skip":
        if must_answer(q):        # stale keyboard from an earlier build
            return await qd.answer("Please answer this question before continuing.",
                                   show_alert=True)
        await qd.edit_message_reply_markup(None)
        return await advance(ctx, st)

    if data == "done":
        if must_answer(q) and not is_complete(q, st["answers"]):
            return await qd.answer("Please choose at least one option before continuing.",
                                   show_alert=True)
        bad = rules.blocking(st["code"], st["answers"], q["id"])
        if bad:
            return await qd.answer(bad["message"], show_alert=True)
        other = pending_other(st["code"], q, st["answers"])
        if other:
            # Previously unreachable on a multi-select: this branch returned at
            # the keyboard redraw above, so "Other" was stored as a bare code and
            # what it stood for was never collected.
            await qd.edit_message_reply_markup(None)
            st["awaiting_text"] = True
            st["text_for"] = q["id"] + "_text"
            save_session(chat_id, st)
            label = tr(other["label"], lang)
            return await ctx.bot.send_message(chat_id,
                f"✍️ You chose <b>{label}</b>: please type what it is.",
                reply_markup=ask_text(label, f"{label}: type it here"),
                parse_mode=ParseMode.HTML)
        await qd.edit_message_reply_markup(None)
        return await advance(ctx, st)

    if data.startswith("o|"):
        i = int(data.split("|")[1])
        opts = resolve_options(lookup_code(st), q)
        val = opts[i]["value"]
        if q["type"] in ("multi", "checklist"):
            cur = list(st["answers"].get(q["id"], []))
            if val in cur:
                cur.remove(val)
            else:
                if opts[i].get("exclusive"):
                    cur = [val]
                else:
                    excl = {o["value"] for o in opts if o.get("exclusive")}
                    cur = [c for c in cur if c not in excl] + [val]
                if q.get("max_select") and len(cur) > q["max_select"]:
                    cur.pop(0)
            st["answers"][q["id"]] = cur
            save_session(chat_id, st)
            return await qd.edit_message_reply_markup(opt_keyboard(q, opts, st["answers"], lang, st))
        bad = rules.blocking(lookup_code(st), dict(st["answers"], **{q["id"]: val}), q["id"])
        if bad:
            return await qd.answer(bad["message"], show_alert=True)
        st["answers"][q["id"]] = val
        await qd.edit_message_reply_markup(None)
        if q["id"] == "R1":
            # The routing question: everything after this point depends on
            # which branch was just chosen, so settle that (and the form)
            # before moving on, instead of just advancing to the next question.
            return await route_after_r1(ctx, st, val)
        if opts[i].get("allow_text"):
            # "Other" without a field to say what is a wasted question: it records
            # that the list was wrong without recording what was missing. The web
            # form has always shown a box here; the bot used to store the code and
            # move on.
            st["awaiting_text"] = True
            st["text_for"] = q["id"] + "_text"
            save_session(chat_id, st)
            label = tr(opts[i]["label"], lang)
            return await ctx.bot.send_message(chat_id,
                f"✍️ You chose <b>{label}</b>: please type what it is.",
                reply_markup=ask_text(label, f"{label}: type it here"),
                parse_mode=ParseMode.HTML)
        return await advance(ctx, st)

    if data.startswith("g|"):
        i = int(data.split("|")[1])
        r = st.get("_grid_row", 0)
        cur = dict(st["answers"].get(q["id"], {}))
        cur[q["rows"][r]["value"]] = q["scale"][i]["value"]
        st["answers"][q["id"]] = cur
        if r + 1 < len(q["rows"]):
            st["_grid_row"] = r + 1
            save_session(chat_id, st)
            await qd.edit_message_reply_markup(None)
            return await send_question(None, ctx, st)
        await qd.edit_message_reply_markup(None)
        return await advance(ctx, st)

    if data.startswith("s|"):
        st["answers"][q["id"]] = data.split("|")[1]
        await qd.edit_message_reply_markup(None)
        return await advance(ctx, st)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    st = load_session(chat_id)
    if not st or not st.get("awaiting_text"):
        return await update.message.reply_text("Send /start to begin the survey.")
    qs = flat_questions(st["code"], st["answers"], st.get("form", "full"))
    if st["idx"] >= len(qs):
        return await finish(ctx, st)
    _, q = qs[st["idx"]]
    val = update.message.text.strip()

    # A free-text follow-up to an "Other" option: store it beside the coded
    # answer and stay on the same question, which has already been answered.
    target = st.pop("text_for", None)
    if target:
        st["answers"][target] = val
        st.pop("awaiting_text", None)
        save_session(chat_id, st)
        return await advance(ctx, st)

    if not val and must_answer(q):
        return await update.message.reply_text("Please answer this question before continuing.")
    if q["type"] == "number":
        try:
            val = float(val)
        except ValueError:
            return await update.message.reply_text("Please send a number.")

    # Cross-field consistency, before the answer is stored. Checked here rather
    # than at submission because the respondent is the only person who can say
    # which of the two answers was wrong, and they are looking at one of them now.
    bad = rules.blocking(st["code"], dict(st["answers"], **{q["id"]: val}), q["id"])
    if bad:
        return await update.message.reply_text(f"⚠️ {bad['message']}\n\nPlease send a corrected value, or press ⬅️ Back "
            f"to change your earlier answer.")

    ok, message = check_format(q, val)
    if not ok:
        # Rejected, and the respondent stays on the question rather than being
        # advanced with a value that follow-up cannot use.
        return await update.message.reply_text(f"⚠️ {message}\n\nPlease try again, or press ⬅️ Back to change your answer.")

    st["answers"][q["id"]] = val
    await advance(ctx, st)


# The command menu respondents see next to the message box. Registered with
# Telegram on every start rather than set by hand in @BotFather, so the menu
# cannot drift from the handlers actually installed below -- a command listed in
# the menu but not handled is a dead end the respondent blames themselves for.
COMMANDS = [
    ("start", "Begin, or carry on where you left off"),
    ("progress", "How far you have got, and how long is left"),
    ("invite", "Get a link to pass on to someone else"),
    ("restart", "Start over from the beginning"),
    ("privacy", "How your answers are handled"),
    ("help", "What this bot is for"),
]

# A file touched on a timer, for container health checks. A bot with a rejected
# token, or one wedged behind a network failure, keeps its process alive and its
# container "running" -- which is the silent failure this whole stack is built to
# avoid. An mtime is the cheapest honest liveness signal: it is only fresh if the
# event loop is actually turning.
LIVENESS = Path(os.environ.get("AIMAP_LIVENESS", "/tmp/aimap-bot-alive"))
LIVENESS_SECONDS = 30


async def _keep_alive():
    import asyncio
    while True:
        try:
            LIVENESS.write_text(datetime.now(timezone.utc).isoformat())
        except OSError:
            log.warning("could not write the liveness file %s", LIVENESS)
        await asyncio.sleep(LIVENESS_SECONDS)


async def post_init(app):
    """Runs once the token has been accepted by Telegram.

    Reaching here at all is the proof that the token works, so this is where the
    bot says who it is -- the username matters operationally because it is what
    invitation deep links are built from.
    """
    import asyncio
    me = await app.bot.get_me()
    log.info("authenticated with Telegram as @%s (id %s)", me.username, me.id)
    log.info("invitation links will look like https://t.me/%s?start=ref_ABC123", me.username)
    await app.bot.set_my_commands(COMMANDS)
    app.bot_data["keepalive"] = asyncio.create_task(_keep_alive())


async def post_shutdown(app):
    task = app.bot_data.get("keepalive")
    if task:
        task.cancel()
    LIVENESS.unlink(missing_ok=True)      # an old mtime must never read as healthy


def main():
    if not TOKEN:
        # Exit ZERO. No token is a configuration choice -- the web questionnaire
        # and dashboard run perfectly well without a Telegram channel -- not a
        # failure, and a container orchestrator told otherwise will restart this
        # process every two seconds forever, scrolling the same message past
        # nobody. Exiting cleanly leaves it visibly stopped instead.
        log.warning("AIMAP_BOT_TOKEN is not set, so the Telegram channel is not running.\n"
            "The web questionnaire and dashboard are unaffected.\n"
            "To enable it, get a token from @BotFather on Telegram (/newbot), then:\n"
            "  export AIMAP_BOT_TOKEN='123456:ABC...'   for ./run-all.sh\n"
            "  set AIMAP_BOT_TOKEN in .env              for docker compose")
        return 0
    path = db.init()
    log.info("shared database: %s", path)
    log.info("the collection server must report this same path, or you have two datasets")
    app = (Application.builder().token(TOKEN)
           .post_init(post_init).post_shutdown(post_shutdown).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("invite", cmd_invite))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("AI-MAP bot running: one questionnaire, routed by R1 into organization, "
              "practitioner and citizen branches")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except InvalidToken:
        # A rejected token is fatal and will not fix itself, but the process is
        # under a restart policy that cannot know that. Pausing before exiting
        # turns a two-second scroll into a readable log line every half minute,
        # which is the difference between an operator seeing the problem and
        # scrolling past it.
        log.error("Telegram rejected AIMAP_BOT_TOKEN. Check it against @BotFather "
                  "(/mybots -> API Token). Retrying is pointless until it changes.")
        time.sleep(30)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
