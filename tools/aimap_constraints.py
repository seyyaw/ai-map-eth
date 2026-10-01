#!/usr/bin/env python3
"""
Cross-field consistency rules, evaluated.

Per-question validation catches an answer that is malformed on its own. It cannot
catch an answer that is only wrong in the light of another one: 400 IT staff in a
company with 50 employees, more pilots reaching production than were ever
started, an organisation founded next year. Each of those passes every check its
own field can make, and each of them ends up either dropped in cleaning or, worse,
published -- a pilot-conversion rate above 100% is a number this instrument can
currently produce.

The rules themselves live in the schema (`tools/schema/*.json` -> "constraints"),
not here, so adding one is a data change a methodologist can review rather than a
code change. This module only knows how to evaluate the five rule types.

Two severities, and the difference matters:

  block   The respondent is stopped and asked to fix it, because one of the two
          answers is definitely wrong and they are the only person who can say
          which.
  flag    The response is stored as given and recorded as a data-quality
          statistic. Used where the combination is unlikely but possible -- a
          holding company registered where it does not operate is a real
          arrangement, and a form that refuses it fabricates a correction rather
          than recording a fact.

This is implemented twice, here and in `tools/web/app.js`, because the two
channels cannot share a runtime. The parity test asserts the two agree.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def _load():
    common = json.loads((SCHEMA_DIR / "common.json").read_text(encoding="utf-8"))
    return {s["code"]: json.loads((SCHEMA_DIR / s["file"]).read_text(encoding="utf-8"))
            for s in common["instruments"]}


INSTRUMENTS = _load()


def reload():
    """Refresh INSTRUMENTS in place after the schema editor publishes a change,
    in the same process. Mutated, not rebound -- see aimap_db.reload_schema()."""
    fresh = _load()
    for code in list(INSTRUMENTS):
        if code not in fresh:
            del INSTRUMENTS[code]
    for code, doc in fresh.items():
        INSTRUMENTS.setdefault(code, {}).clear()
        INSTRUMENTS[code].update(doc)


def _num(value):
    """A number, or None. Blank is not zero: an unanswered count must not compare
    equal to a real one, or every empty form fails every rule."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve(answers, ref):
    """Read an answer, addressing a grid cell as "Q.row" where needed.

    A contradiction often lives between a whole question and one row of a grid --
    "rates themselves expert at machine learning" is C1.ml, not C1 -- and without
    a way to name the row, those rules cannot be written at all.
    """
    if ref and "." in ref:
        qid, row = ref.split(".", 1)
        cell = answers.get(qid)
        return cell.get(row) if isinstance(cell, dict) else None
    return answers.get(ref)


def _question(code, qid):
    for sec in INSTRUMENTS[code]["sections"]:
        for q in sec["questions"]:
            if q["id"] == qid:
                return q
    return None


def _band_max(code, qid, value):
    """Upper bound of the chosen band, or None if the band is open-ended.

    An open-ended top band ("5,000 or more") has no maximum by design, so nothing
    can exceed it and the rule correctly does not fire.
    """
    q = _question(code, qid)
    if not q:
        return None
    for o in q.get("options", []):
        if str(o["value"]) == str(value):
            return o.get("max")
    return None


def _base(ref):
    """The question a reference belongs to, so `only_field` still matches."""
    return ref.split(".", 1)[0] if ref else ref


def evaluate(code, answers, only_field=None):
    """Every violated rule for this answer set.

    `only_field` narrows evaluation to rules whose blocking field is the question
    on screen, which is what both renderers want: a respondent should be stopped
    by the question they are answering, never by one three screens back that they
    can no longer see.
    """
    out = []
    for c in INSTRUMENTS.get(code, {}).get("constraints", []):
        if only_field and _base(c.get("field")) != only_field:
            continue
        if _violates(code, c, answers):
            out.append({
                "id": c["id"], "field": c.get("field"), "severity": c.get("severity", "flag"),
                "message": c["message"],
            })
    return out


def _violates(code, c, answers):
    kind = c["type"]
    value = resolve(answers, c.get("field"))

    if kind == "lte_band":
        n = _num(value)
        if n is None:
            return False
        cap = _band_max(code, c["band_field"], answers.get(c["band_field"]))
        return cap is not None and n > cap

    if kind == "lte_field":
        a, b = _num(value), _num(resolve(answers, c["other"]))
        return a is not None and b is not None and a > b

    if kind == "both_at_least":
        # Two answers that cannot comfortably both be high. Used for the
        # reverse-keyed pairs inside an attitude grid, where agreeing strongly
        # with a statement and its opposite is the signal, not an error to fix.
        vals = [_num(resolve(answers, ref)) for ref in c["fields"]]
        if any(v is None for v in vals):
            return False
        return all(v >= c["min"] for v in vals)

    if kind == "year_range":
        n = _num(value)
        if n is None:
            return False
        lo = c.get("min")
        hi = c.get("max")
        # Computed at evaluation time, never stored: a hard-coded upper year
        # starts rejecting valid answers on the first of January.
        if hi == "this_year":
            hi = datetime.now(timezone.utc).year
        if lo is not None and n < lo:
            return True
        return hi is not None and n > hi

    if kind == "includes_field":
        chosen = value
        other = resolve(answers, c["other"])
        if not isinstance(chosen, list) or not chosen or other in (None, ""):
            return False           # nothing to be inconsistent with yet
        return str(other) not in [str(x) for x in chosen]

    if kind == "matrix_any":
        # Does any row of a WHOLE matrix/grid carry one of the "bad" values, paired
        # with another answer that asserts the opposite? Used for "we admit no
        # review process exists for a sensitive use (ET1), yet say current
        # safeguards are enough (ET4)" -- a contradiction that lives inside a grid
        # rather than at a single field, which the dotted "Q.row" addressing in
        # resolve() cannot express because it names one row, not "any row".
        grid = answers.get(c["field"])
        if not isinstance(grid, dict):
            return False
        bad = {str(x) for x in c["bad_values"]}
        if not any(str(v) in bad for v in grid.values()):
            return False
        other = resolve(answers, c["other"])
        return other is not None and str(other) in [str(x) for x in c["other_values"]]

    if kind == "incompatible_pair":
        if str(value) not in [str(x) for x in (c.get("values") or [c.get("value")])]:
            return False
        other = resolve(answers, c["other"])
        return other is not None and str(other) in [str(x) for x in c["other_values"]]

    return False


def blocking(code, answers, field):
    """The first blocking violation for the question on screen, or None."""
    for v in evaluate(code, answers, only_field=field):
        if v["severity"] == "block":
            return v
    return None


def flags(code, answers):
    """Everything a stored response violates, for the data-quality record.

    Includes blocking rules as well as flag-level ones: enumerator and paper
    imports never passed through a renderer, so a blocking rule can still be
    violated in the data, and silently dropping that would hide exactly the
    interviewer errors this is meant to surface.
    """
    return evaluate(code, answers)


if __name__ == "__main__":
    import sys
    cases = [
        ("ORG", {"A3": "3", "A4": 400}, "400 IT staff in a 50-249 organisation"),
        ("ORG", {"A3": "3", "A4": 40}, "40 IT staff in a 50-249 organisation"),
        ("ORG", {"A3": "6", "A4": 9000}, "9,000 IT staff in a 5,000+ organisation"),
        ("ORG", {"D7": 3, "D7b": 5}, "5 of 3 pilots reached production"),
        ("ORG", {"D7": 10, "D7b": 4}, "4 of 10 pilots reached production"),
        ("ORG", {"A5": 2031}, "established in 2031"),
        ("ORG", {"A5": 1400}, "established in 1400"),
        ("ORG", {"A5": 1894}, "established in 1894 (Ethio Telecom)"),
        ("ORG", {"A1": "tigray", "A2": ["addis", "amhara"]}, "head office in a region not operated in"),
        ("IND", {"A1": "1", "A7": "4"}, "under 20, more than ten years' experience"),
        ("IND", {"A1": "3", "A7": "4"}, "25-34, more than ten years' experience"),
    ]
    bad = 0
    for code, answers, label in cases:
        found = evaluate(code, answers)
        mark = "  ".join(f"[{v['severity']}] {v['id']}" for v in found) or "ok"
        print(f"  {label:<52} {mark}")
    sys.exit(0)
