#!/usr/bin/env python3
"""
Fill a throwaway database with synthetic responses.

Two uses, both real: exercising the dashboard against something other than an
empty table, and training enumerators on the field tools without touching
collected data.

The generated answers are drawn from the schema's own option lists, so a
question added to `tools/schema/*.json` is exercised without editing this file.
Some structure is imposed on top of the randomness -- a maturity gap, an arm
difference, a panel-versus-booster gap, a fast enumerator -- because a dashboard
tested only against uniform noise shows nothing and proves nothing.

    python tools/scripts/seed_demo.py --db /tmp/demo.db --n 300

It REFUSES to write to the default database. Demo data in a collection database
is indistinguishable from field data three months later, and that is not a
mistake anyone gets to make twice.
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import aimap_db as db                                    # noqa: E402


def options(code, q):
    """Option values for a question, following `options_ref`.

    The question's own instrument is searched first. Ids are unique only within
    an instrument -- "C1" exists in all three -- so a global search silently
    answers one instrument's question with another's option list.
    """
    if q.get("options"):
        return [o["value"] for o in q["options"]]
    ref = q.get("options_ref")
    if not ref:
        return []
    src_code, qid = ref.split(":", 1) if ":" in ref else (code, ref)
    for c in [src_code] + [x for x in db.INSTRUMENTS if x != src_code]:
        if c not in db.INSTRUMENTS:
            continue
        for sec in db.INSTRUMENTS[c]["sections"]:
            for src in sec["questions"]:
                if src["id"] == qid:
                    return (options(c, src)
                            or [r["value"] for r in src.get("row_options", [])]
                            or [r["value"] for r in src.get("rows", [])])
    return []


def answer(code, q, rng):
    """A plausible answer for one question, from the schema's own options."""
    t = q["type"]
    if t == "consent":
        return True
    if t == "info":
        return None
    if t in ("single", "checklist"):
        opts = options(code, q)
        return rng.choice(opts) if opts else None
    if t == "multi":
        opts = [o for o in options(code, q) if o != "none"]
        if not opts:
            return []
        k = min(len(opts), rng.randint(1, q.get("max_select") or 4))
        return rng.sample(opts, k)
    if t == "likert_grid":
        scale = [s["value"] for s in q.get("scale", [])]
        return {r["value"]: rng.choice(scale) for r in q.get("rows", [])} if scale else {}
    if t == "matrix":
        cols = [c["value"] for c in q.get("col_options", [])]
        # Weighted toward the low end: an unweighted draw would put a fifth of
        # every sector in production, which is the opposite of what this study exists to test.
        weights = [8, 5, 3, 2, 1][:len(cols)] or [1]
        return {r["value"]: rng.choices(cols, weights=weights)[0] for r in q.get("row_options", [])}
    if t == "scale":
        sc = q.get("scale", {})
        return str(rng.randint(sc.get("min", 1), sc.get("max", 5)))
    if t == "number":
        return rng.randint(0, 40)
    if t in ("text", "longtext"):
        return rng.choice(["", "", "Cost and skills are the main problem.",
                           "We have a pilot but no budget line."])
    if t == "email":
        return ""
    if t == "repeatable":
        return []
    return None


def show(cond, answers):
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
        return isinstance(v, dict) and any(
            str(x).replace(".", "").isdigit() and float(x) >= float(cond["value"])
            for x in v.values())
    return True


def build(code, rng, form):
    answers, path = {}, []
    for sec in db.INSTRUMENTS[code]["sections"]:
        if not show(sec.get("show_if"), answers):
            continue
        for q in sec["questions"]:
            if q.get("hidden") or (q.get("flags") and "honeypot" in q["flags"]):
                continue
            if form == "short" and not q.get("core"):
                continue
            if not show(q.get("show_if"), answers):
                continue
            v = answer(code, q, rng)
            if v is not None:
                answers[q["id"]] = v
            path.append((sec["id"], q["id"]))
    return answers, path


def skew(code, answers, rng):
    """Impose the patterns the dashboard exists to detect."""
    if code == "ORG":
        # Self-rating above what the behavioural checklist supports, most of the time.
        chk = answers.get("D5")
        if isinstance(chk, list):
            real = len([c for c in chk if c != "none"])
            answers["D4"] = str(min(5, max(0, real // 2 + rng.choice([1, 1, 2, 0, 2]))))
    if code == "IND":
        grid = answers.get("U1")
        if isinstance(grid, dict):
            # Facilitating conditions weakest, performance expectancy strongest --
            # the pattern the MWAIS study reports for Sub-Saharan Africa.
            for k in ("fc1", "fc2"):
                if k in grid:
                    grid[k] = str(rng.choice([1, 2, 2, 3]))
            for k in ("pe1", "pe2"):
                if k in grid:
                    grid[k] = str(rng.choice([4, 4, 5, 3]))
    return answers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to a THROWAWAY database file")
    ap.add_argument("--n", type=int, default=300, help="responses to generate")
    ap.add_argument("--days", type=int, default=45, help="spread submissions over this many days")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    target = Path(args.db).resolve()
    if target == Path(db.DEFAULT_DB).resolve() or target == Path(db.DB_PATH).resolve():
        raise SystemExit(
            f"refusing to seed {target}: that is the collection database.\n"
            "Demo responses are indistinguishable from field responses once they are in. "
            "Pass --db /tmp/demo.db and point AIMAP_DB at it to view the result.")

    rng = random.Random(args.seed)
    db.init(target)

    mix = [("ORG", 0.22), ("IND", 0.38), ("CIT", 0.40)]
    enumerators = ["ENUM-01", "ENUM-02", "ENUM-03", "ENUM-04"]
    codes = {}
    made = 0

    instruments = [c for c, _ in mix]
    weights = [w for _, w in mix]
    for _ in range(args.n):
        code = rng.choices(instruments, weights=weights)[0]
        if code == "ORG":
            mode = rng.choice(["web", "enumerator", "enumerator"])
            arm = "list"
            form = "full"
        elif code == "IND":
            mode = rng.choice(["web", "telegram"])
            arm = rng.choices(["list", "referral", "open"], weights=[5, 4, 1])[0]
            form = rng.choices(["full", "short"], weights=[7, 3])[0]
        else:
            mode = rng.choices(["telegram", "enumerator", "web"], weights=[6, 3, 1])[0]
            arm = "booster" if mode == "enumerator" else rng.choices(["open", "referral"], weights=[7, 3])[0]
            form = rng.choices(["full", "short"], weights=[5, 5])[0]

        answers, path = build(code, rng, form)
        answers = skew(code, answers, rng)

        # The panel over-reports AI use relative to the booster. Imposed, so the
        # panel/booster comparison in the dashboard has something to find.
        if code == "CIT" and "C3" in answers:
            if arm == "booster":
                answers["C3"] = rng.choices(["0", "1", "2", "3"], weights=[6, 3, 2, 1])[0]
            else:
                answers["C3"] = rng.choices(["0", "1", "2", "3"], weights=[2, 3, 4, 3])[0]

        enumerator = rng.choice(enumerators) if mode == "enumerator" else None
        base = {"ORG": 1500, "IND": 700, "CIT": 320}[code] * (0.55 if form == "short" else 1.0)
        dur = max(45, int(rng.gauss(base, base * 0.3)))
        if enumerator == "ENUM-03":
            dur = int(dur * 0.45)                 # the supervisor should see this one

        submitted = datetime.now(timezone.utc) - timedelta(
            days=rng.uniform(0, args.days), hours=rng.uniform(0, 24))
        started = submitted - timedelta(seconds=dur)
        rid = str(uuid.uuid4())

        referrer = None
        if arm == "referral" and codes.get(code):
            referrer = rng.choice(codes[code])

        db.save_partial({"response_id": rid, "instrument": code, "mode": mode, "form": form,
                         "recruit_arm": arm, "last_qid": path[-1][1] if path else None,
                         "section_id": path[-1][0] if path else None,
                         "answered": len(answers), "total": len(path),
                         "pct": 100, "started_at": started.isoformat()}, target)

        db.save_response({
            "response_id": rid, "instrument": code, "language": "en", "mode": mode,
            "form": form, "recruit_arm": arm, "referrer": referrer, "enumerator": enumerator,
            "started_at": started.isoformat(), "submitted_at": submitted.isoformat(),
            "answers": answers,
            "scores": {"duration_seconds": dur, "flag_speeder": dur < 60},
        }, target)
        made += 1

        if arm in ("list", "referral") and rng.random() < 0.35:
            codes.setdefault(code, []).append(
                db.issue_referral(db.hash_ref("demo", rid), code, target))

    # Abandoned starts, so drop-off is measurable rather than reading as zero.
    abandoned = 0
    for i in range(int(args.n * 0.45)):
        code = rng.choices(["CIT", "IND", "ORG"], weights=[6, 3, 1])[0]
        mode = "telegram" if code != "ORG" else "web"
        form = rng.choices(["full", "short"], weights=[6, 4])[0]
        _, path = build(code, rng, form)
        if not path:
            continue
        stop = rng.choices(range(len(path)), weights=[max(1, len(path) - i) for i in range(len(path))])[0]
        started = datetime.now(timezone.utc) - timedelta(days=rng.uniform(0, args.days))
        db.save_partial({"response_id": str(uuid.uuid4()), "instrument": code, "mode": mode,
                         "form": form, "recruit_arm": "open",
                         "last_qid": path[stop][1], "section_id": path[stop][0],
                         "answered": stop, "total": len(path),
                         "pct": round(100 * stop / len(path)),
                         "started_at": started.isoformat()}, target)
        abandoned += 1

    print(f"seeded {made} responses and {abandoned} abandoned starts into {target}")
    print(f"view it with:  AIMAP_DB={target} python tools/aimap_dashboard.py --report")


if __name__ == "__main__":
    main()
