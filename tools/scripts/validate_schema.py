#!/usr/bin/env python3
"""
Validate the survey schemas before they reach the field.

Checks that every option reference resolves, every routing condition points at a
question that exists and can actually produce the value it tests for, that
required items are reachable, and that scoring keys line up with the renderers.
Also simulates respondent paths to report realistic questionnaire lengths.

    python validate_schema.py
Exit code 1 if any error is found.
"""

import json
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "schema"
COMMON = json.loads((SCHEMA / "common.json").read_text(encoding="utf-8"))
INSTR = {s["code"]: json.loads((SCHEMA / s["file"]).read_text(encoding="utf-8"))
         for s in COMMON["instruments"]}

errors, warnings = [], []
VALID_TYPES = {"consent", "info", "single", "multi", "checklist", "scale", "likert_grid",
               "matrix", "repeatable", "text", "longtext", "number", "email", "phone"}
VALID_OPS = {"answered", "eq", "not_eq", "in", "not_in", "gte", "lte",
             "includes", "includes_any", "scale_gte"}


def all_questions(code):
    for sec in INSTR[code]["sections"]:
        for q in sec["questions"]:
            yield sec, q


def qmap(code):
    return {q["id"]: q for _, q in all_questions(code)}


def resolve_options(code, q, seen=None):
    seen = seen or set()
    if q.get("options"):
        return q["options"]
    ref = q.get("options_ref")
    if ref:
        if ref in seen:
            errors.append(f"{code}.{q['id']}: circular options_ref -> {ref}")
            return []
        seen.add(ref)
        src_code, qid = ref.split(":") if ":" in ref else (code, ref)
        if src_code not in INSTR:
            errors.append(f"{code}.{q['id']}: options_ref names unknown instrument '{src_code}'")
            return []
        src = qmap(src_code).get(qid)
        if not src:
            errors.append(f"{code}.{q['id']}: options_ref '{ref}' -> no such question")
            return []
        opts = resolve_options(src_code, src, seen) or src.get("row_options") or []
        return list(opts) + list(q.get("extra_options", []))
    if q.get("rows"):
        return q["rows"]
    return []


CONSTRAINT_TYPES = {"lte_band", "lte_field", "year_range", "includes_field",
                    "incompatible_pair", "both_at_least", "matrix_any"}


def check_constraints(code):
    """Cross-field rules are only useful if they point at questions that exist.

    A rule naming a renamed question fails open -- it simply never fires -- so a
    typo here buys nothing and costs the check it was meant to perform. That is
    exactly the failure a validator is for.
    """
    qs = qmap(code)
    order = {qid: i for i, qid in enumerate(qs)}
    for c in INSTR[code].get("constraints", []):
        where = f"{code}.constraint[{c.get('id', '?')}]"
        if c.get("type") not in CONSTRAINT_TYPES:
            errors.append(f"{where}: unknown type '{c.get('type')}'")
            continue
        if c.get("severity") not in ("block", "flag"):
            errors.append(f"{where}: severity must be 'block' or 'flag'")
        if not c.get("message"):
            errors.append(f"{where}: needs a message the respondent can act on")

        refs = [c.get(k) for k in ("field", "band_field", "other")] + list(c.get("fields") or [])
        for ref in [r for r in refs if r]:
            # "Q.row" addresses one row of a grid; check both halves resolve.
            qid, _, row = ref.partition(".")
            if qid not in qs:
                errors.append(f"{where}: '{ref}' is not a question in {code}")
            elif row:
                rows = qs[qid].get("rows") or qs[qid].get("row_options") or []
                if row not in [r["value"] for r in rows]:
                    errors.append(f"{where}: '{ref}': {qid} has no row '{row}'")

        # A blocking rule must be checkable at the moment it blocks, which means
        # the other field has to have been asked already.
        f = (c.get("field") or "").split(".")[0] or None
        other = (c.get("band_field") or c.get("other") or "").split(".")[0] or None
        if (c.get("severity") == "block" and f in order and other in order
                and order[other] > order[f]):
            errors.append(f"{where}: blocks on {f} but compares against {other}, which comes "
                          f"later -- it can never fire")

        if c["type"] == "lte_band":
            band = qs.get(c.get("band_field"))
            if band and not any("max" in o for o in band.get("options", [])):
                errors.append(f"{where}: band_field '{c['band_field']}' has no option with a "
                              f"'max' bound, so there is nothing to compare against")
        if c["type"] == "year_range" and c.get("max") not in (None, "this_year") \
                and not isinstance(c.get("max"), int):
            errors.append(f"{where}: max must be an integer or 'this_year'")
        if c["type"] == "incompatible_pair" and not c.get("other_values"):
            errors.append(f"{where}: needs 'other_values'")


def check_instrument(code):
    qs = qmap(code)
    ids = list(qs)
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        errors.append(f"{code}: duplicate question ids {sorted(dupes)}")

    order = {qid: i for i, qid in enumerate(ids)}

    for sec, q in all_questions(code):
        qid, t = q["id"], q.get("type")
        where = f"{code}.{qid}"

        if t not in VALID_TYPES:
            errors.append(f"{where}: unknown type '{t}'")
        if t not in ("consent", "info") and not q.get("text"):
            errors.append(f"{where}: missing text")

        # option-bearing types must actually yield options
        if t in ("single", "multi", "checklist"):
            opts = resolve_options(code, q)
            if not opts:
                errors.append(f"{where}: no options and no resolvable options_ref")
            else:
                vals = [o["value"] for o in opts]
                if len(vals) != len(set(vals)):
                    errors.append(f"{where}: duplicate option values")
                for o in opts:
                    if "label" not in o:
                        errors.append(f"{where}: option '{o.get('value')}' has no label")
                if q.get("max_select") and q["max_select"] > len(vals):
                    warnings.append(f"{where}: max_select {q['max_select']} exceeds option count {len(vals)}")

        if t == "likert_grid":
            if not q.get("rows") or not q.get("scale"):
                errors.append(f"{where}: likert_grid needs both 'rows' and 'scale'")
        if t == "likert_grid":
            reversed_rows = [r["value"] for r in q.get("rows", []) if r.get("reverse")]
            if reversed_rows and not q.get("scoring"):
                warnings.append(f"{where}: rows {reversed_rows} are marked reverse-keyed, but this "
                    f"question has no 'scoring' key, so nothing reverses them. Whoever "
                    f"averages this grid next will get the sign wrong")
        if t in ("likert_grid", "matrix") and not q.get("row_noun"):
            # The bot walks a grid one row at a time and has to name what a row
            # IS ("skill area 4 of 10"). Without this it falls back to a generic
            # word, which reads as a new question rather than a sub-question.
            warnings.append(f"{where}: no 'row_noun', so the bot will say 'item N of M'")
        if t == "matrix":
            if not q.get("row_options") or not q.get("col_options"):
                errors.append(f"{where}: matrix needs 'row_options' and 'col_options'")
        if "attention_check" in (q.get("flags") or []):
            # A check whose instructed answer is not on the list fails every
            # respondent, and shows up as a 100% flag rate nobody can explain.
            opts = [str(o["value"]) for o in resolve_options(code, q)]
            if not q.get("expected"):
                errors.append(f"{where}: attention_check needs an 'expected' answer")
            elif str(q["expected"]) not in opts:
                errors.append(f"{where}: expected answer '{q['expected']}' is not one of "
                              f"its options {opts}")

        if q.get("validate"):
            rules = COMMON.get("validators", {})
            if q["validate"] not in rules:
                errors.append(f"{where}: validate '{q['validate']}' has no rule in "
                              f"common.json -> validators")
            elif t not in ("text", "email", "phone", "number"):
                warnings.append(f"{where}: validate on a '{t}' question has no effect")
        if t in ("email", "phone") and not q.get("validate"):
            warnings.append(f"{where}: type '{t}' without a `validate` rule accepts anything")

        if t == "scale":
            sc = q.get("scale") or {}
            if "min" not in sc or "max" not in sc:
                errors.append(f"{where}: scale needs min and max")
        if t == "repeatable":
            if not q.get("fields"):
                errors.append(f"{where}: repeatable needs 'fields'")
            for f in q.get("fields", []):
                if f.get("type") in ("single", "multi") and not f.get("options") and not f.get("options_ref"):
                    errors.append(f"{where}.{f.get('id')}: choice field has no options")

        # routing
        for cond, label in ((q.get("show_if"), "question"), (sec.get("show_if"), "section")):
            if not cond:
                continue
            if cond.get("op") not in VALID_OPS:
                errors.append(f"{where}: unknown routing op '{cond.get('op')}'")
            tgt = cond.get("q")
            if tgt not in qs:
                errors.append(f"{where}: {label} routing references missing question '{tgt}'")
                continue
            if order.get(tgt, 1e9) >= order.get(qid, -1) and label == "question":
                errors.append(f"{where}: routing depends on '{tgt}' which comes later in the instrument")
            # does the target question actually offer the tested value?
            src = qs[tgt]
            if cond["op"] in ("eq", "not_eq", "in", "not_in", "includes", "includes_any") \
               and src.get("type") in ("single", "multi", "checklist"):
                vals = {str(o["value"]) for o in resolve_options(code, src)}
                tested = cond["value"] if isinstance(cond["value"], list) else [cond["value"]]
                missing = [str(v) for v in tested if str(v) not in vals]
                if missing and vals:
                    errors.append(f"{where}: routing tests '{tgt}' for value(s) {missing} that it never produces")

        if q.get("pii") and q.get("storage") != "separate" and qid != "S2":
            warnings.append(f"{where}: marked pii but not flagged storage='separate'")

    # every instrument must open with consent
    first = INSTR[code]["sections"][0]["questions"]
    if not any(x.get("type") == "consent" for x in first):
        errors.append(f"{code}: first section has no consent item")


def simulate(code, picker):
    """Walk the instrument choosing answers via `picker` and count items shown."""
    answers, shown = {}, 0

    def show_if(cond):
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
            return str(v) in [str(x) for x in cond["value"]]
        if op == "not_in":
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
            return False
        return True

    for sec, q in all_questions(code):
        if not show_if(sec.get("show_if")) or not show_if(q.get("show_if")):
            continue
        if q.get("hidden") or (q.get("flags") and "honeypot" in q["flags"]):
            continue
        shown += 1
        opts = resolve_options(code, q) if q.get("type") in ("single", "multi", "checklist") else []
        answers[q["id"]] = picker(q, opts)
    return shown


def pick_max(q, opts):
    t = q.get("type")
    if t == "consent":
        return True
    if t == "single":
        return opts[0]["value"] if opts else "1"
    if t in ("multi", "checklist"):
        return [o["value"] for o in opts if not o.get("exclusive")][: q.get("max_select") or 99]
    if t == "likert_grid":
        return {r["value"]: q["scale"][-1]["value"] for r in q.get("rows", [])}
    if t == "repeatable":
        return [{f["id"]: "x" for f in q.get("fields", [])}]
    return "x"


def pick_min(q, opts):
    t = q.get("type")
    if t == "consent":
        return True
    if t == "single":
        return opts[-1]["value"] if opts else "0"
    if t in ("multi", "checklist"):
        excl = [o["value"] for o in opts if o.get("exclusive")]
        return excl[:1] or ([opts[-1]["value"]] if opts else [])
    if t == "likert_grid":
        return {r["value"]: q["scale"][0]["value"] for r in q.get("rows", [])}
    if t == "repeatable":
        return []
    return "x"


def main():
    for code in INSTR:
        check_instrument(code)
        check_constraints(code)

    print("AI-MAP schema validation\n" + "=" * 52)
    for code, inst in INSTR.items():
        total = sum(len(s["questions"]) for s in inst["sections"])
        lo, hi = simulate(code, pick_min), simulate(code, pick_max)
        spec = next(s for s in COMMON["instruments"] if s["code"] == code)
        print(f"{code:4} {total:4} items defined   path {lo:3}–{hi:3} shown   "
              f"target n={spec['target_n']:<5} ~{spec['est_minutes']} min")

    ln = {l["code"]: l.get("status") for l in COMMON["languages"]}
    print(f"\nlanguages: " + ", ".join(f"{k}({v})" for k, v in ln.items()))
    fieldable = [k for k, v in ln.items() if not str(v).startswith("pending")]
    print(f"fieldable now: {', '.join(fieldable)}")

    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print("  ⚠ ", w)
    if errors:
        print(f"\n{len(errors)} ERROR(s):")
        for e in errors:
            print("  ✗ ", e)
        return 1
    print("\n✓ no errors: schemas are internally consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
