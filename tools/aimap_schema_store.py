#!/usr/bin/env python3
"""
The admin editor's storage layer: drafts, publishing, and the build/conduct gate.

The design decision that keeps this simple: publishing writes straight to
tools/schema/questionnaire.json. There is no second, parallel "live" copy
anywhere. Every other tool in the project -- scoring, the constraint engine,
the CLI validator, the LaTeX generator, the channel-parity test -- already
reads that file directly and needs no changes at all to pick up a published
edit. The only thing this module owns is the WORKING STATE BEFORE publish:

    draft     a pending edit, held in the database, not yet live
    published a boolean flag: is the questionnaire open for real responses,
              or still being built?

A draft with no saved changes falls back to the current file content, so
opening the editor always starts from something real rather than a blank
document. Publishing validates the questionnaire's effective content, and
either writes the file and clears the draft, or writes nothing and returns
the errors.

The questionnaire used to be three separate files (org.json, ind.json,
cit.json), independently draftable through three editor tabs. They have
since been merged into one file, with organization-branch content keeping
its old ids, practitioner-branch content prefixed "P" and citizen-branch
content prefixed "Z" on every section and question id, plus a routing
section "R" that decides which branch a respondent sees. CODES below is
still a tuple for that history's sake, but it now holds exactly one code:
there is one document to draft and publish, not three.

This is a SAFETY NET, not the authoritative gate. The full pre-fieldwork check
remains `tools/scripts/validate_schema.py`, which checks routing order,
constraint reachability and reference resolution that this lighter validator
does not attempt -- see README "Before fielding". Publishing through the editor
without also running that script is publishing without the check the project's
own checklist calls for.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCHEMA_DIR = BASE / "schema"

import aimap_db as db                                     # noqa: E402

try:
    import sys as _sys
    _sys.path.insert(0, str(BASE / "scripts"))
    import scoring as _scoring
except Exception:                                          # pragma: no cover
    _scoring = None

try:
    import aimap_constraints as _constraints
except Exception:                                           # pragma: no cover
    _constraints = None

CODES = ("QUESTIONNAIRE",)
FILES = {"QUESTIONNAIRE": "questionnaire.json"}

VALID_TYPES = {"consent", "info", "single", "multi", "checklist", "scale", "likert_grid",
               "matrix", "repeatable", "text", "longtext", "number", "email", "phone"}


# --------------------------------------------------------------------- reads

def file_content(code):
    return json.loads((SCHEMA_DIR / FILES[code]).read_text(encoding="utf-8"))


def _get_doc(code, kind, path=None):
    with db.connect(path) as con:
        row = con.execute("SELECT content FROM schema_docs WHERE code=? AND kind=?",
                          (code, kind)).fetchone()
    return json.loads(row["content"]) if row else None


def draft(code, path=None):
    """The instrument as it currently stands for editing: a saved draft, or the
    file content if nothing has been changed yet."""
    return _get_doc(code, "draft", path) or file_content(code)


def has_draft(code, path=None):
    return _get_doc(code, "draft", path) is not None


def is_published(path=None):
    with db.connect(path) as con:
        row = con.execute("SELECT value FROM schema_settings WHERE key='published'").fetchone()
    return bool(row and row["value"] == "1")


def published_at(path=None):
    with db.connect(path) as con:
        row = con.execute("SELECT value FROM schema_settings WHERE key='published_at'").fetchone()
    return row["value"] if row else None


def effective(code, path=None):
    """What a respondent is actually answering right now.

    Once published, that is the file -- which is also exactly what the file
    already was the moment publishing wrote it, so this only differs from
    file_content() while UNPUBLISHED, when "conduct" mode is the admin testing
    their own draft before anyone else sees it.
    """
    if is_published(path):
        return file_content(code)
    return draft(code, path)


def state(path=None):
    code = CODES[0]
    doc = draft(code, path)
    return {
        "published": is_published(path),
        "published_at": published_at(path),
        "has_draft": has_draft(code, path),
        "sections": len(doc.get("sections", [])),
        "questions": sum(len(s.get("questions", [])) for s in doc.get("sections", [])),
    }


# -------------------------------------------------------------------- writes

def save_draft(code, content, updated_by=None, path=None):
    """Save a working copy. Deliberately unvalidated: a form mid-edit is
    routinely inconsistent (an option list with a blank label while someone is
    still typing it), and gating every keystroke on full validity is how a form
    builder becomes impossible to use. Publish is the gate, not this."""
    if not isinstance(content, dict) or not isinstance(content.get("sections"), list):
        raise ValueError("a schema document needs a top-level 'sections' list")
    now = datetime.now(timezone.utc).isoformat()
    with db.connect(path) as con:
        con.execute(
            "INSERT INTO schema_docs (code, kind, content, updated_at, updated_by) "
            "VALUES (?, 'draft', ?, ?, ?) "
            "ON CONFLICT(code, kind) DO UPDATE SET "
            " content=excluded.content, updated_at=excluded.updated_at, "
            " updated_by=excluded.updated_by",
            (code, json.dumps(content, ensure_ascii=False), now, updated_by),
        )


def discard_draft(code, path=None):
    """Drop unsaved changes: the draft reverts to whatever is on disk."""
    with db.connect(path) as con:
        con.execute("DELETE FROM schema_docs WHERE code=? AND kind='draft'", (code,))


def publish(updated_by=None, path=None):
    """Validate the questionnaire, then write questionnaire.json if it passes.

    Returns (ok, errors) where errors is a list of messages, empty on
    success. On success, the draft is cleared -- the file now IS the content
    that was being drafted, so there is nothing left pending. There is only
    one file now, so "all or nothing" is automatic: either this write happens
    or it does not, there is no partial case left to guard against.
    """
    code = CODES[0]
    doc = draft(code, path)
    errors = validate_light(doc)
    if errors:
        return False, errors

    now = datetime.now(timezone.utc).isoformat()
    (SCHEMA_DIR / FILES[code]).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with db.connect(path) as con:
        con.execute("DELETE FROM schema_docs WHERE code=? AND kind='draft'", (code,))
        for key, value in (("published", "1"), ("published_at", now)):
            con.execute(
                "INSERT INTO schema_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # Refresh every in-process copy in THIS process. The Telegram bot is a
    # separate process and picks this up on its own, via schema_mtime() -- see
    # bot.py's check on /start.
    db.reload_schema(path)
    if _scoring:
        _scoring.reload()
    if _constraints:
        _constraints.reload()
    return True, []


def unpublish(path=None):
    """Bring back the build/conduct chooser. The files are untouched -- they
    hold the last published content -- so this only changes what the picker
    screen offers, not what is saved."""
    with db.connect(path) as con:
        con.execute(
            "INSERT INTO schema_settings (key, value) VALUES ('published', '0') "
            "ON CONFLICT(key) DO UPDATE SET value='0'")


# ----------------------------------------------------------------- validation

def _walk_questions(doc):
    for sec in doc.get("sections", []):
        for q in sec.get("questions", []):
            yield sec, q


def _resolve_options(doc, q):
    """Find the option list a question uses, following options_ref if needed.

    Before the three schema files were merged, an options_ref could point
    into another instrument's file ("ORG:I10"), so resolving it meant looking
    across documents. Now everything lives in tools/schema/questionnaire.json,
    so a ref is just another question id in this same doc.
    """
    if q.get("options"):
        return q["options"]
    ref = q.get("options_ref")
    if not ref:
        return q.get("row_options") or q.get("rows") or []
    for _, sq in _walk_questions(doc):
        if sq["id"] == ref:
            return sq.get("options") or sq.get("row_options") or sq.get("rows") or []
    return None


def validate_light(doc):
    """A safety net for the live editor, not the authoritative check.

    Catches the mistakes that would make the questionnaire literally
    unrenderable (a choice question with no options, a grid with no scale, a
    duplicate id) or would silently corrupt scoring (removing a question id the
    reference implementation depends on). Does NOT check routing order,
    reachability, or every constraint rule -- that is
    `tools/scripts/validate_schema.py`, run by hand before real fieldwork.
    """
    errors = []

    if not isinstance(doc.get("sections"), list) or not doc["sections"]:
        return ["the instrument has no sections"]

    sec_ids, q_ids = [], []
    for sec in doc["sections"]:
        if not sec.get("id"):
            errors.append("a section is missing an id")
            continue
        sec_ids.append(sec["id"])
        for q in sec.get("questions", []):
            qid = q.get("id")
            if not qid:
                errors.append(f"{sec['id']}: a question is missing an id")
                continue
            if any(ch.isspace() for ch in qid):
                errors.append(f"{sec['id']}.{qid}: question ids cannot contain spaces")
            q_ids.append(qid)

            t = q.get("type")
            if t not in VALID_TYPES:
                errors.append(f"{sec['id']}.{qid}: '{t}' is not a known question type")
                continue
            if t not in ("consent", "info") and not q.get("text"):
                errors.append(f"{sec['id']}.{qid}: needs question text")
            if t in ("single", "multi", "checklist"):
                opts = _resolve_options(doc, q)
                if opts is None:
                    errors.append(f"{sec['id']}.{qid}: options_ref '{q.get('options_ref')}' "
                                  f"does not resolve to a question with options")
                elif not opts:
                    errors.append(f"{sec['id']}.{qid}: needs at least one option")
                else:
                    vals = [str(o.get("value")) for o in opts]
                    if len(vals) != len(set(vals)):
                        errors.append(f"{sec['id']}.{qid}: two options share the same value")
                    if any(not o.get("label") for o in opts):
                        errors.append(f"{sec['id']}.{qid}: every option needs a label")
            if t == "likert_grid" and not (q.get("rows") and q.get("scale")):
                errors.append(f"{sec['id']}.{qid}: needs both rows and a scale")
            if t == "matrix" and not (q.get("row_options") and q.get("col_options")):
                errors.append(f"{sec['id']}.{qid}: needs both row_options and col_options")
            if t == "scale":
                sc = q.get("scale") or {}
                if "min" not in sc or "max" not in sc:
                    errors.append(f"{sec['id']}.{qid}: a scale question needs min and max")

    if len(sec_ids) != len(set(sec_ids)):
        dupes = {x for x in sec_ids if sec_ids.count(x) > 1}
        errors.append(f"duplicate section id(s): {sorted(dupes)}")
    if len(q_ids) != len(set(q_ids)):
        dupes = {x for x in q_ids if q_ids.count(x) > 1}
        errors.append(f"duplicate question id(s): {sorted(dupes)}")

    # Best-effort reference check for routing and constraints: does the named
    # question exist SOMEWHERE in this instrument? Not whether it appears
    # earlier, which is the one check left to the full CLI validator.
    known = set(q_ids)
    for sec, q in _walk_questions(doc):
        for cond in (q.get("show_if"), sec.get("show_if")):
            if cond and cond.get("q") and cond["q"] not in known:
                errors.append(f"{sec['id']}.{q.get('id')}: show_if refers to unknown "
                              f"question '{cond['q']}'")
    for c in doc.get("constraints", []):
        for key in ("field", "band_field", "other"):
            ref = c.get(key)
            if not ref:
                continue
            base = ref.split(".", 1)[0]
            if base not in known:
                errors.append(f"constraint '{c.get('id')}': '{ref}' is not a question here")

    return errors


if __name__ == "__main__":
    import sys
    print("Schema editor state")
    print("=" * 40)
    for k, v in state().items():
        print(f"  {k}: {v}")
    if "--publish" in sys.argv:
        ok, errors = publish(updated_by="cli")
        print("\npublish:", "OK" if ok else "REJECTED")
        for m in errors:
            print(f"  - {m}")
        sys.exit(0 if ok else 1)
