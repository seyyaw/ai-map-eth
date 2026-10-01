#!/usr/bin/env python3
"""
AI-MAP Ethiopia: analysis layer behind the surveyor's dashboard.

`aimap_db` stores responses; this module answers questions about them. The split
is deliberate: storage has to be boringly correct and is written to by three
channels, whereas everything here is a reporting decision that will be argued
about and changed.

Everything is computed from the database on request. Nothing is cached and
nothing is precomputed on ingest, because a fieldwork dashboard that shows a
figure from an hour ago is worse than one that is slow: the daily quality review
(docs/study-design-decisions.md §4) acts on what it sees.

Three rules run through the whole module:

  * **Never report a rate without its denominator.** Every share is returned
    alongside the n it rests on, so a 60% computed over five responses cannot be
    rendered as a finding by a caller that did not think to check.
  * **Distinguish "no" from "we cannot tell".** The instrument asks, in several
    places, whether the respondent would even know. Those answers are counted
    separately rather than folded into the negative, because globally the blind
    share is the one that is growing.
  * **Suppress rather than qualify.** Where n is below the threshold in
    sampling.json, the figure is withheld and the reason given. A caveat under a
    number does not stop the number being quoted.

    python tools/aimap_dashboard.py            # the full payload as JSON
    python tools/aimap_dashboard.py --report   # the report draft as Markdown
"""

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import aimap_db as db                                   # noqa: E402

SCHEMA_DIR = BASE / "schema"
SAMPLING = json.loads((SCHEMA_DIR / "sampling.json").read_text(encoding="utf-8"))
THRESHOLDS = SAMPLING["quality_thresholds"]
MIN_N = THRESHOLDS["min_n_for_ranking"]

# ---------------------------------------------------------------------------
# Global comparators. Held here as data with their provenance attached, so that
# every Ethiopian figure the dashboard puts next to a world figure can be traced
# to the page it came from. A number without a source is not a comparison, it is
# a rumour, and these get quoted into a white paper.
# ---------------------------------------------------------------------------
BENCHMARKS = {
    "shadow_ai_blind": {
        "global": 0.21, "label": "Cannot tell whether staff use unapproved AI tools",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "lower_better",
    },
    "deployment_delayed": {
        "global": 0.88, "label": "AI deployment delayed by data or governance concerns",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "lower_better",
    },
    "deployment_delay_months": {
        "global": 5.9, "label": "Mean delay (months)", "unit": "months",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "lower_better",
    },
    "ai_incident": {
        "global": 0.88, "label": "At least one AI-related security incident in 12 months",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "lower_better",
    },
    "agentic_ai": {
        "global": 0.47, "label": "Using AI agents (production or pilot)",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "context",
    },
    "confidence_incident_paradox": {
        "global": 0.62, "label": "Confident in access control AND reporting an incident",
        "source": "AvePoint, The State of AI 2026 (n=750)", "direction": "lower_better",
    },
}

# Population diffusion comparators, for the citizen instrument. Microsoft's
# Q1 2026 diffusion figures are telemetry-derived and measure *individual use*,
# which is not what the ORG instrument measures -- so they sit only against CIT,
# never against organisational adoption. Conflating the two is the most likely
# misreading of this dashboard, so the two sets are kept in separate structures.
DIFFUSION = {
    "note": "Share of people aged 15-64 who used a generative AI tool in Q1 2026. "
            "Telemetry-derived, adjusted for device share, internet penetration and "
            "population. Comparable to CIT C3, not to ORG adoption.",
    "source": "Microsoft, Global AI Diffusion: Q1 2026, as reported by Ecofin Agency "
              "and TechCentral (sources/web-snapshots/)",
    "values": {
        "World": 0.178, "Developed countries": 0.275, "Developing countries": 0.154,
        "South Africa": 0.231, "Namibia": 0.151, "Egypt": 0.148, "Senegal": 0.139,
        "Nigeria": 0.101, "Kenya": 0.087, "Ethiopia (est.)": 0.068,
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _schema(code):
    return db.INSTRUMENTS[code]


def _questions(code):
    return {q["id"]: (sec, q) for sec in _schema(code)["sections"] for q in sec["questions"]}


def _resolve_options(code, q, seen=None):
    """Option list for a question, following `options_ref`.

    Several questions reuse another question's options rather than restating them
    (IND C5 offers training in the same areas C1 asked about) and the reference
    may name a question in a different instrument. Resolution has to prefer the
    question's OWN instrument: ids are unique only within an instrument, and
    "C1" exists in all three. Searching globally finds whichever instrument comes
    first in dictionary order, which is how a citizen awareness scale ends up
    labelling a practitioner training question.
    """
    if q.get("options"):
        return q["options"]
    ref = q.get("options_ref")
    if not ref:
        return q.get("row_options") or q.get("rows") or []
    seen = seen or set()
    if ref in seen:
        return []
    seen.add(ref)
    if ":" in ref:
        src_code, qid = ref.split(":", 1)
    else:
        src_code, qid = code, ref
    order = [src_code] + [c for c in db.INSTRUMENTS if c != src_code]
    for c in order:
        if c not in db.INSTRUMENTS:
            continue
        entry = _questions(c).get(qid)
        if entry:
            return list(_resolve_options(c, entry[1], seen)) + list(q.get("extra_options", []))
    return []


def _label_map(code, qid, which="options"):
    """value -> human label for one question, so the dashboard never shows a raw code."""
    entry = _questions(code).get(qid)
    if not entry:
        return {}
    q = entry[1]
    opts = q.get(which) if which != "options" else None
    if not opts:
        opts = _resolve_options(code, q)
    return {str(o["value"]): o.get("label", o["value"]) for o in opts}


def _share(numerator, denominator, nd=1):
    """A share and the n it rests on, or None when there is nothing to divide.

    Returns a dict rather than a float on purpose: every caller then has the
    denominator in hand, and a template cannot render a percentage without also
    having been given the number of responses behind it.
    """
    if not denominator:
        return {"pct": None, "n": 0, "of": 0}
    return {"pct": round(100 * numerator / denominator, nd), "n": numerator, "of": denominator}


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _quartiles(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    if len(xs) < 4:
        return {"min": xs[0], "median": _median(xs), "max": xs[-1], "n": len(xs)}
    q = statistics.quantiles(xs, n=4)
    return {"min": xs[0], "p25": round(q[0], 1), "median": round(q[1], 1),
            "p75": round(q[2], 1), "max": xs[-1], "n": len(xs)}


def _rows(path=None):
    """Every response, with answers and scores already parsed."""
    out = []
    for r in db.fetch(path=path):
        r = dict(r)
        r["answers"] = json.loads(r["answers"] or "{}")
        r["scores"] = json.loads(r["scores"] or "{}")
        r["client_scores"] = json.loads(r["client_scores"] or "{}")
        out.append(r)
    return out


def _day(ts):
    return (ts or "")[:10]


# ---------------------------------------------------------------------------
# 1. fieldwork: are we collecting what we said we would, and when will we finish?
# ---------------------------------------------------------------------------

def fieldwork(rows, days=60):
    by_inst = {}
    for code, target in db.TARGETS.items():
        mine = [r for r in rows if r["instrument"] == code]
        by_inst[code] = {
            "total": len(mine),
            "target": target,
            "pct": round(100 * len(mine) / target, 1) if target else None,
            "by_mode": dict(Counter(r["mode"] for r in mine)),
            "by_arm": dict(Counter(r.get("recruit_arm") or "open" for r in mine)),
            "by_form": dict(Counter(r.get("form") or "full" for r in mine)),
        }

    # Daily series over the last `days`, zero-filled. Zero-filling matters: a
    # sparse series drawn as a line silently joins across the days nobody
    # collected anything, which is exactly the pattern a field manager needs to see.
    today = datetime.now(timezone.utc).date()
    span = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    counts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        counts[_day(r["submitted_at"])][r["instrument"]] += 1
    series = [{"date": d, **{c: counts[d].get(c, 0) for c in db.TARGETS},
               "total": sum(counts[d].values())} for d in span]

    # Projection from the last 14 days of actual collection. Reported as a rate
    # and a date, with the window stated, because "on track" without a window is
    # an opinion.
    recent = series[-14:]
    per_day = sum(s["total"] for s in recent) / len(recent) if recent else 0
    remaining = sum(max(0, v["target"] - v["total"]) for v in by_inst.values())
    projection = {
        "window_days": len(recent),
        "responses_per_day": round(per_day, 1),
        "remaining": remaining,
        "days_to_target": round(remaining / per_day) if per_day > 0 else None,
        "projected_date": (today + timedelta(days=round(remaining / per_day))).isoformat()
                          if per_day > 0 and remaining else None,
    }
    return {"by_instrument": by_inst, "daily": series, "projection": projection,
            "total": len(rows)}


# ---------------------------------------------------------------------------
# 2. quotas: the question a total cannot answer
# ---------------------------------------------------------------------------

def quotas(rows):
    """Cell-level fill against sampling.json.

    A study that hits its total while leaving a region empty has not succeeded,
    and nothing in a running total shows that. Cells are returned sorted by how
    far behind they are, so the field team reads the list top-down.
    """
    out = {}

    org_cfg = SAMPLING["ORG"]
    labels = _label_map("ORG", org_cfg["variable"])
    got = Counter(r["answers"].get(org_cfg["variable"]) for r in rows if r["instrument"] == "ORG")
    cells = []
    for c in org_cfg["cells"]:
        n = got.get(c["value"], 0)
        cells.append({
            "value": c["value"], "label": c.get("label") or labels.get(c["value"], c["value"]),
            "n": n, "target": c["target"],
            "pct": round(100 * n / c["target"], 1) if c["target"] else None,
            "gap": max(0, c["target"] - n),
            "census": bool(c.get("census")),
        })
    out["ORG"] = {"variable": org_cfg["variable"], "note": org_cfg["note"],
                  "cells": sorted(cells, key=lambda c: c["pct"] if c["pct"] is not None else 0)}

    ind_cfg = SAMPLING["IND"]
    got = Counter((r.get("recruit_arm") or "open") for r in rows if r["instrument"] == "IND")
    cells = [{"value": c["value"], "label": c["label"], "n": got.get(c["value"], 0),
              "target": c["target"],
              "pct": round(100 * got.get(c["value"], 0) / c["target"], 1) if c["target"] else None,
              "gap": max(0, c["target"] - got.get(c["value"], 0)),
              "weightable": c.get("weightable", True)}
             for c in ind_cfg["cells"]]
    ind_rows = [r for r in rows if r["instrument"] == "IND"]
    watch = []
    for w in ind_cfg["secondary"]["watch"]:
        n = sum(1 for r in ind_rows if r["answers"].get(ind_cfg["secondary"]["variable"]) == w["value"])
        share = n / len(ind_rows) if ind_rows else 0
        watch.append({"label": w["label"], "share": round(share, 3), "n": n,
                      "of": len(ind_rows), "max_share": w["max_share"],
                      "breached": bool(ind_rows) and share > w["max_share"]})
    out["IND"] = {"variable": "recruit_arm", "note": ind_cfg["note"], "cells": cells,
                  "watch": watch, "watch_note": ind_cfg["secondary"]["note"]}

    cit_cfg = SAMPLING["CIT"]
    cit = [r for r in rows if r["instrument"] == "CIT"]
    got = Counter((r.get("recruit_arm") or "open") for r in cit)
    arms = [{"value": a["value"], "label": a["label"], "n": got.get(a["value"], 0),
             "target": a["target"],
             "pct": round(100 * got.get(a["value"], 0) / a["target"], 1) if a["target"] else None,
             "gap": max(0, a["target"] - got.get(a["value"], 0)),
             "weightable": a.get("weightable", True)}
            for a in cit_cfg["arms"]]

    # The booster quota is the part that actually needs watching, and it is a
    # region x settlement grid rather than a list: a region can be on target in
    # total while every response in it came from the regional capital.
    bq = cit_cfg["booster_quota"]
    booster = [r for r in cit if (r.get("recruit_arm") or "open") == bq["arm"]]
    grid = []
    for c in bq["cells"]:
        row = {"value": c["value"], "label": c["label"], "cells": []}
        for settlement in ("urban", "periurban", "rural"):
            target = c.get(settlement, 0)
            n = sum(1 for r in booster
                    if r["answers"].get(bq["variable"]) == c["value"]
                    and r["answers"].get(bq["cross"]) == settlement)
            row["cells"].append({
                "settlement": settlement, "n": n, "target": target,
                "pct": round(100 * n / target, 1) if target else None,
                "gap": max(0, target - n),
            })
        row["n"] = sum(x["n"] for x in row["cells"])
        row["target"] = sum(x["target"] for x in row["cells"])
        grid.append(row)
    out["CIT"] = {"note": cit_cfg["note"], "arms": arms,
                  "booster_quota": {"note": bq["note"], "grid": grid},
                  "calibration": cit_cfg["calibration"]}
    return out


# ---------------------------------------------------------------------------
# 3. funnel and drop-off, who starts, who finishes, and where the rest stop
# ---------------------------------------------------------------------------

def funnel(path=None):
    """Starts against completions, from the `partials` table.

    This is the measure the pilot gate in §4 is written against, and it cannot be
    recovered from the responses table: an abandoned questionnaire leaves no
    response behind, so without a position heartbeat the drop-out rate is
    structurally unmeasurable and quietly reads as zero.
    """
    with db.connect(path) as con:
        parts = [dict(r) for r in con.execute("SELECT * FROM partials")]

    by = {}
    for code in db.TARGETS:
        mine = [p for p in parts if p["instrument"] == code]
        done = [p for p in mine if p["completed"]]
        aband = [p for p in mine if not p["completed"]]
        by[code] = {
            "starts": len(mine),
            "completions": len(done),
            "abandoned": len(aband),
            "completion_rate": _share(len(done), len(mine)),
            "median_pct_at_abandonment": _median([p["pct"] for p in aband]),
            "by_mode": {},
        }
        for mode in sorted({p["mode"] for p in mine}):
            m = [p for p in mine if p["mode"] == mode]
            by[code]["by_mode"][mode] = {
                "starts": len(m),
                "completion_rate": _share(sum(1 for p in m if p["completed"]), len(m)),
            }

    # Where they stop. Reported with the question text, because a list of ids is
    # not actionable by the person who has to rewrite the question.
    stops = defaultdict(lambda: defaultdict(int))
    for p in parts:
        if not p["completed"] and p["last_qid"]:
            stops[p["instrument"]][p["last_qid"]] += 1

    worst = {}
    for code, counter in stops.items():
        qs = _questions(code)
        starts = max(1, sum(1 for p in parts if p["instrument"] == code))
        items = []
        for qid, n in counter.items():
            entry = qs.get(qid)
            items.append({
                "qid": qid,
                "section": entry[0]["id"] if entry else None,
                "text": (entry[1].get("text") if entry else None) or "(unknown question)",
                "n": n,
                "share_of_starts": round(n / starts, 3),
                "over_threshold": (n / starts) > THRESHOLDS["question_dropoff_max"],
            })
        worst[code] = sorted(items, key=lambda x: -x["n"])[:15]

    return {"by_instrument": by, "worst_questions": worst,
            "threshold": THRESHOLDS["question_dropoff_max"],
            "measurable": bool(parts)}


# ---------------------------------------------------------------------------
# 4. durations
# ---------------------------------------------------------------------------

def durations(rows):
    out = {}
    for code in db.TARGETS:
        mine = [r for r in rows if r["instrument"] == code]
        mins = [r["scores"].get("duration_seconds", 0) / 60 for r in mine
                if r["scores"].get("duration_seconds")]
        entry = {"overall": _quartiles(mins), "by_mode": {}, "by_form": {}}
        for key, field in (("by_mode", "mode"), ("by_form", "form")):
            groups = defaultdict(list)
            for r in mine:
                if r["scores"].get("duration_seconds"):
                    groups[r.get(field) or "full"].append(r["scores"]["duration_seconds"] / 60)
            entry[key] = {g: _quartiles(v) for g, v in sorted(groups.items())}
        out[code] = entry
    cit_median = (out.get("CIT", {}).get("overall") or {}).get("median")
    out["cit_gate"] = {
        "median_minutes": cit_median,
        "max": THRESHOLDS["cit_median_minutes_max"],
        "passes": cit_median is not None and cit_median <= THRESHOLDS["cit_median_minutes_max"],
    }
    return out


# ---------------------------------------------------------------------------
# 5. quality
# ---------------------------------------------------------------------------

def quality(rows, path=None):
    base = db.quality(path=path)
    for code, d in base.items():
        n = d["n"] or 1
        # Cross-field violations that reached storage. Both renderers block these
        # before submission, so a non-zero count here means the response did not
        # come through a renderer -- an enumerator import, a keyed-in paper form,
        # or a stale client. Which rule fired is kept, because "IT staff exceeds
        # headcount" and "founded in the future" call for different conversations
        # with the field team.
        mine = [r for r in rows if r["instrument"] == code]
        inconsistent = [r for r in mine if r["scores"].get("flag_inconsistent")]
        d["inconsistent"] = len(inconsistent)
        d["inconsistent_rate"] = round(len(inconsistent) / n, 3)
        broken = Counter(rule for r in inconsistent
                         for rule in (r["scores"].get("inconsistencies") or []))
        d["inconsistent_rules"] = dict(broken.most_common())
        flagged = sum(1 for r in rows
                      if r["instrument"] == code
                      and any(r["scores"].get(k) for k in
                              ("flag_planted", "flag_definition", "flag_attention",
                               "flag_honeypot", "flag_speeder")))
        d["any_flag"] = flagged
        d["flag_rate"] = round(flagged / n, 3)
        d["over_threshold"] = d["flag_rate"] > THRESHOLDS["flag_rate_max"]
    base["_threshold"] = THRESHOLDS["flag_rate_max"]
    return base


def enumerators(rows):
    """Per-enumerator workload, speed and flag rate.

    Interviewer effects are the largest uncontrolled source of error in
    enumerator-assisted collection, and they are detectable during fielding, which is the only time anything can be done about them. Speed is expressed
    as a ratio to the team median rather than in minutes: the absolute number
    depends on the instrument and tells a supervisor nothing on its own.
    """
    field = [r for r in rows if r.get("enumerator")]
    if not field:
        return {"enumerators": [], "team_median_minutes": None,
                "note": "No responses carry an enumerator id yet."}

    all_mins = [r["scores"]["duration_seconds"] / 60 for r in field
                if r["scores"].get("duration_seconds")]
    team = _median(all_mins)
    out = []
    for name in sorted({r["enumerator"] for r in field}):
        mine = [r for r in field if r["enumerator"] == name]
        mins = [r["scores"]["duration_seconds"] / 60 for r in mine
                if r["scores"].get("duration_seconds")]
        med = _median(mins)
        flagged = sum(1 for r in mine
                      if any(r["scores"].get(k) for k in
                             ("flag_planted", "flag_definition", "flag_attention", "flag_speeder")))
        ratio = round(med / team, 2) if med and team else None
        out.append({
            "enumerator": name, "n": len(mine),
            "median_minutes": med,
            "ratio_to_team": ratio,
            "too_fast": ratio is not None and ratio < THRESHOLDS["enumerator_duration_min_ratio"],
            "flag_rate": round(flagged / len(mine), 3),
            "flags": flagged,
            "instruments": dict(Counter(r["instrument"] for r in mine)),
            "last_submission": max(r["submitted_at"] for r in mine),
        })
    return {"enumerators": sorted(out, key=lambda e: -e["n"]),
            "team_median_minutes": team,
            "min_ratio": THRESHOLDS["enumerator_duration_min_ratio"]}


# ---------------------------------------------------------------------------
# 6. substantive distributions
# ---------------------------------------------------------------------------

def org_distributions(rows):
    org = [r for r in rows if r["instrument"] == "ORG"]
    n = len(org)
    maturity = Counter(r["scores"].get("maturity_computed") for r in org
                       if r["scores"].get("maturity_computed") is not None)
    technical = Counter(r["scores"].get("technical_computed") for r in org
                        if r["scores"].get("technical_computed") is not None)
    bands = Counter(r["scores"].get("readiness_band") for r in org
                    if r["scores"].get("readiness_band"))
    gaps = [r["scores"]["maturity_gap"] for r in org if r["scores"].get("maturity_gap") is not None]

    ladder = {str(l["level"]): l["name"] for l in db.COMMON["maturity_ladder"]["levels"]}
    tech_ladder = {str(l["level"]): l["name"]
                   for l in db.COMMON.get("technical_ladder", {}).get("levels", [])}

    return {
        "n": n,
        "maturity": [{"level": lvl, "name": ladder.get(str(lvl), str(lvl)),
                      "n": maturity.get(lvl, 0),
                      "pct": round(100 * maturity.get(lvl, 0) / n, 1) if n else None}
                     for lvl in range(6)],
        "technical": [{"level": lvl, "name": tech_ladder.get(str(lvl), str(lvl)),
                       "n": technical.get(lvl, 0),
                       "pct": round(100 * technical.get(lvl, 0) / n, 1) if n else None}
                      for lvl in range(5)],
        "readiness_bands": dict(bands),
        # The headline the instrument was built to produce: the distance between
        # what organisations say their maturity is and what their own behavioural
        # checklist supports. Mean and share-overclaiming are both given; the mean
        # alone hides a bimodal split between the candid and the inflating.
        "overclaiming": {
            "mean_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
            "n": len(gaps),
            "over": _share(sum(1 for g in gaps if g > 0), len(gaps)),
            "over_by_two_or_more": _share(sum(1 for g in gaps if g >= 2), len(gaps)),
            "under": _share(sum(1 for g in gaps if g < 0), len(gaps)),
            "distribution": dict(sorted(Counter(gaps).items())),
        },
    }


def benchmarks(rows):
    """Ethiopian shares beside the global comparators, with n on every row."""
    org = [r for r in rows if r["instrument"] == "ORG"]
    out = []
    for key, meta in BENCHMARKS.items():
        if meta.get("unit") == "months":
            vals = [r["scores"][key] for r in org if r["scores"].get(key) is not None]
            local = round(sum(vals) / len(vals), 1) if vals else None
            out.append({"key": key, "label": meta["label"], "unit": "months",
                        "local": local, "n": len(vals), "global": meta["global"],
                        "source": meta["source"], "direction": meta["direction"],
                        "sufficient": len(vals) >= MIN_N})
            continue
        asked = [r for r in org if key in r["scores"]]
        yes = sum(1 for r in asked if r["scores"].get(key))
        share = _share(yes, len(asked))
        out.append({"key": key, "label": meta["label"],
                    "local": (share["pct"] / 100) if share["pct"] is not None else None,
                    "n": len(asked), "global": meta["global"],
                    "source": meta["source"], "direction": meta["direction"],
                    "sufficient": len(asked) >= MIN_N})
    # Reported separately from BENCHMARKS: "cannot tell" is not the negative of
    # the question, and merging the two would erase the distinction the items exist for.
    blind = []
    for key, label in (("shadow_ai_blind", "Cannot tell whether staff use unapproved tools"),
                       ("incident_blind", "Would not necessarily know about an AI incident")):
        asked = [r for r in org if key in r["scores"]]
        blind.append({"key": key, "label": label,
                      **_share(sum(1 for r in asked if r["scores"].get(key)), len(asked))})
    return {"rows": out, "blind_spots": blind, "min_n": MIN_N}


def ind_distributions(rows):
    ind = [r for r in rows if r["instrument"] == "IND"]
    cfg = db.COMMON.get("utaut", {})
    constructs = list((cfg.get("constructs") or {}).keys())

    def construct_means(subset):
        out = {}
        for c in constructs:
            vals = [r["scores"][f"utaut_{c}"] for r in subset
                    if r["scores"].get(f"utaut_{c}") is not None]
            out[c] = {"mean": round(sum(vals) / len(vals), 2) if vals else None,
                      "n": len(vals), "sufficient": len(vals) >= MIN_N}
        return out

    # By arm, because the difference between the list arm and the referral arm is
    # not noise to be averaged away -- it is the estimate of who list-based
    # research in Ethiopia misses, which is the reason for running both.
    by_arm = {}
    for arm in sorted({(r.get("recruit_arm") or "open") for r in ind}):
        subset = [r for r in ind if (r.get("recruit_arm") or "open") == arm]
        by_arm[arm] = {"n": len(subset), "constructs": construct_means(subset)}

    freq = Counter(str(r["answers"].get("B1")) for r in ind if r["answers"].get("B1") is not None)
    gaps = [r["scores"]["intention_behaviour_gap"] for r in ind
            if r["scores"].get("intention_behaviour_gap") is not None]

    return {
        "n": len(ind),
        "constructs": construct_means(ind),
        "by_arm": by_arm,
        "scale_points": cfg.get("scale_points", 5),
        "aversion_note": cfg.get("note", ""),
        "use_frequency": {k: freq.get(k, 0) for k in ("0", "1", "2", "3", "4", "5")},
        "use_frequency_labels": _label_map("IND", "B1"),
        "intention_behaviour_gap": {
            "mean": round(sum(gaps) / len(gaps), 2) if gaps else None, "n": len(gaps),
            "wants_more_than_does": _share(sum(1 for g in gaps if g > 0), len(gaps)),
        },
        "blocked_by_payment": _share(sum(1 for r in ind if r["scores"].get("blocked_by_payment")),
                                     len(ind)),
        "language_penalty": _share(sum(1 for r in ind if r["scores"].get("language_penalty")),
                                   len(ind)),
        "emigration_intention": _quartiles([r["scores"].get("emigration_intention") for r in ind]),
        "skill_index": _quartiles([r["scores"].get("skill_index") for r in ind]),
    }


def cit_distributions(rows):
    """Citizen results, split by recruitment arm at every turn.

    The panel and the booster are never pooled into a single headline here. A
    combined 'national awareness' figure computed over a self-selected Telegram
    panel plus a probability booster is the single most misleading number this
    study could produce, and the surest way to stop it being quoted is not to
    compute it.
    """
    cit = [r for r in rows if r["instrument"] == "CIT"]

    def block(subset):
        n = len(subset)
        return {
            "n": n,
            "aware": _share(sum(1 for r in subset if r["scores"].get("aware_of_ai")), n),
            "uses": _share(sum(1 for r in subset if r["scores"].get("uses_ai")), n),
            "smartphone": _share(sum(1 for r in subset if r["scores"].get("smartphone")), n),
            "rural": _share(sum(1 for r in subset if r["scores"].get("rural")), n),
            "knows_how_to_complain": _share(sum(1 for r in subset if r["scores"].get("knows_how_to_complain")),
                sum(1 for r in subset if "knows_how_to_complain" in r["scores"])),
            "institutional_trust": _quartiles([r["scores"].get("institutional_trust") for r in subset]),
            "sufficient": n >= MIN_N,
        }

    by_arm = {arm: block([r for r in cit if (r.get("recruit_arm") or "open") == arm])
              for arm in sorted({(r.get("recruit_arm") or "open") for r in cit})}

    panel = [r for r in cit if (r.get("recruit_arm") or "open") in ("open", "referral")]
    booster = [r for r in cit if (r.get("recruit_arm") or "open") == "booster"]
    spread = None
    p, b = block(panel), block(booster)
    if p["uses"]["pct"] is not None and b["uses"]["pct"] is not None:
        spread = {
            "panel_pct": p["uses"]["pct"], "booster_pct": b["uses"]["pct"],
            "ratio": round(p["uses"]["pct"] / b["uses"]["pct"], 2) if b["uses"]["pct"] else None,
            "difference": round(p["uses"]["pct"] - b["uses"]["pct"], 1),
            "note": "The gap between an online panel and a probability booster on the same "
                    "question. Reported as a finding about online measurement in Ethiopia, "
                    "not corrected away.",
        }

    return {
        "n": len(cit), "by_arm": by_arm, "panel": p, "booster": b,
        "panel_booster_spread": spread,
        "region": dict(Counter(r["answers"].get("A1") for r in cit if r["answers"].get("A1"))),
        "region_labels": _label_map("CIT", "A1"),
        "settlement": dict(Counter(r["answers"].get("A2") for r in cit if r["answers"].get("A2"))),
        "settlement_labels": _label_map("CIT", "A2"),
        "diffusion_comparators": DIFFUSION,
    }


# ---------------------------------------------------------------------------
# 7. sectors and use cases
# ---------------------------------------------------------------------------

STATUS_MATRICES = {"YH": "YH3", "YF": "YF1", "YA": "YA1", "YG": "YG1"}
STATUS_LABELS = {"0": "Not relevant", "1": "Nothing done", "2": "Exploring",
                 "3": "Piloting", "4": "In production"}


def sectors(rows, path=None):
    table = db.by_sector(path=path)
    labels = _label_map("ORG", "S3")
    out = []
    for sector, row in table.items():
        row = dict(row)
        row["sector"] = sector
        row["label"] = labels.get(sector, sector)
        # Suppressed rather than qualified: a caveat under a number does not stop
        # the number being quoted, and by_sector() already knows whether n supports
        # a ranking. Values are blanked, and the reason travels with the row.
        if not row.get("sufficient_for_ranking"):
            row["suppressed"] = f"n={row['n']}: below the minimum of {MIN_N} for a ranking"
            for k in list(row):
                if k not in ("sector", "label", "n", "suppressed", "sufficient_for_ranking"):
                    row[k] = None
        out.append(row)
    return sorted(out, key=lambda r: (-(r.get("readiness_overall") or -1), -r["n"]))


def use_cases(rows):
    """The cross-sector use-case heatmap.

    Only the four modules that share the 0-4 status scale are pooled. The industry
    module (YI1) deliberately uses a different scale -- technology sophistication,
    for comparability with the 2022 Firm-level Adoption of Technology survey -- and
    is reported separately rather than silently rescaled into this grid.
    """
    org = [r for r in rows if r["instrument"] == "ORG"]
    out = {}
    for sec_id, qid in STATUS_MATRICES.items():
        rowlabels = _label_map("ORG", qid, "row_options")
        answered = [r["answers"][qid] for r in org if isinstance(r["answers"].get(qid), dict)]
        if not answered:
            continue
        cases = []
        for value, label in rowlabels.items():
            vals = [str(a.get(value)) for a in answered if a.get(value) not in (None, "")]
            if not vals:
                continue
            counts = Counter(vals)
            cases.append({
                "value": value, "label": label, "n": len(vals),
                "counts": {k: counts.get(k, 0) for k in STATUS_LABELS},
                "production": _share(counts.get("4", 0), len(vals)),
                "piloting_or_better": _share(counts.get("4", 0) + counts.get("3", 0), len(vals)),
                # Mean over the 0-4 status scale. An ordinal mean, used for ordering
                # the heatmap only -- never reported as a score.
                "mean_status": round(sum(int(v) for v in vals) / len(vals), 2),
            })
        out[sec_id] = {
            "question": qid,
            "n_responses": len(answered),
            "sufficient": len(answered) >= MIN_N,
            "cases": sorted(cases, key=lambda c: -c["mean_status"]),
        }

    # Industry, on its own scale, with the FAT baseline it was written against.
    yi = [r["answers"]["YI1"] for r in org if isinstance(r["answers"].get("YI1"), dict)]
    if yi:
        rowlabels = _label_map("ORG", "YI1", "row_options")
        funcs = []
        for value, label in rowlabels.items():
            vals = [int(a[value]) for a in yi if str(a.get(value, "")).isdigit()]
            if vals:
                funcs.append({"value": value, "label": label, "n": len(vals),
                              "mean_sophistication": round(sum(vals) / len(vals), 2),
                              "using_ai": _share(sum(1 for v in vals if v == 5), len(vals))})
        out["YI"] = {
            "question": "YI1", "n_responses": len(yi), "scale": "1-5 technology sophistication",
            "baseline": "Ethiopian Firm-level Adoption of Technology survey 2022: 0.0% using "
                        "AI or big-data analytics; mean function sophistication 1.3 (small) "
                        "to 1.8 (large firms).",
            "separate_scale": True,
            "functions": sorted(funcs, key=lambda f: -f["mean_sophistication"]),
        }
    return out


def barriers(rows):
    """What respondents say stops them, by instrument. Multi-select, so shares are
    over respondents who answered the item, not over selections."""
    out = {}
    for code, qid in (("ORG", "K1"), ("IND", "C5"), ("CIT", "E2")):
        mine = [r for r in rows if r["instrument"] == code]
        answered = [r["answers"][qid] for r in mine if isinstance(r["answers"].get(qid), list)]
        if not answered:
            continue
        labels = _label_map(code, qid)
        counts = Counter(v for a in answered for v in a)
        out[code] = {
            "question": qid,
            "text": (_questions(code).get(qid) or (None, {}))[1].get("text", ""),
            "n_respondents": len(answered),
            "items": sorted([{"value": v, "label": labels.get(v, v), "n": n,
                  **{"pct": round(100 * n / len(answered), 1)}}
                 for v, n in counts.items()],
                key=lambda x: -x["n"]),
        }
    return out


# ---------------------------------------------------------------------------
# 8. alerts: the daily review, computed
# ---------------------------------------------------------------------------

def alerts(payload):
    """The §4 triggers, evaluated. Each carries what to do, not only what is wrong.

    Severity is 'act' (a documented trigger has been crossed) or 'watch' (heading
    that way). Anything that cannot be evaluated yet is simply absent rather than
    reported as passing -- a green tick over an unmeasurable check is worse than
    no check.
    """
    out = []

    for code, q in payload["quality"].items():
        if code.startswith("_") or not isinstance(q, dict):
            continue
        if q.get("over_threshold"):
            out.append({"severity": "act", "area": "Data quality", "instrument": code,
                        "message": f"{code} flag rate {q['flag_rate']:.0%} is above the "
                                   f"{THRESHOLDS['flag_rate_max']:.0%} trigger ({q['any_flag']} of {q['n']}).",
                        "action": "Pause this channel and review the flagged responses before collecting more."})
        if q.get("client_divergence"):
            out.append({"severity": "act", "area": "Integrity", "instrument": code,
                        "message": f"{q['client_divergence']} {code} response(s) where the client's "
                                   f"scores disagree with the server's.",
                        "action": "Stale cached build or tampering. Investigate today; do not publish until resolved."})
        if q.get("inconsistent"):
            worst = ", ".join(f"{k} ({v})" for k, v in
                              list((q.get("inconsistent_rules") or {}).items())[:3])
            out.append({"severity": "act", "area": "Consistency", "instrument": code,
                        "message": f"{q['inconsistent']} {code} response(s) contradict themselves "
                                   f"across fields: {worst}.",
                        "action": "Both channels block these before submission, so these arrived "
                                  "another way: an enumerator import, a paper form, or a stale "
                                  "client. Check how they were collected before trusting them."})
        if q.get("scoring_errors"):
            out.append({"severity": "act", "area": "Integrity", "instrument": code,
                        "message": f"{q['scoring_errors']} {code} response(s) could not be scored.",
                        "action": "Fix scoring and re-score: python tools/scripts/scoring.py --rescore"})

    for code, f in payload["funnel"]["by_instrument"].items():
        rate = f["completion_rate"]["pct"]
        if rate is not None and f["starts"] >= 20 and (100 - rate) / 100 > THRESHOLDS["dropoff_rate_max"]:
            out.append({"severity": "act", "area": "Drop-off", "instrument": code,
                        "message": f"{code} drop-off is {100 - rate:.0f}% over {f['starts']} starts, "
                                   f"above the {THRESHOLDS['dropoff_rate_max']:.0%} gate.",
                        "action": "Cut the instrument further or switch this channel to the short form."})

    for code, items in payload["funnel"]["worst_questions"].items():
        for q in items[:3]:
            if q["over_threshold"]:
                out.append({"severity": "act", "area": "Question wording", "instrument": code,
                            "message": f"{q['share_of_starts']:.0%} of {code} starts stop at "
                                       f"{q['qid']}: “{str(q['text'])[:70]}”",
                            "action": "Rewrite or drop the question, and record the change with the date it took effect."})

    gate = payload["durations"].get("cit_gate") or {}
    if gate.get("median_minutes") is not None and not gate["passes"]:
        out.append({"severity": "act", "area": "Length", "instrument": "CIT",
                    "message": f"CIT median completion is {gate['median_minutes']} minutes "
                               f"against a gate of {gate['max']}.",
                    "action": "The Phase 2 gate is not met. Cut before the main wave."})

    for e in payload["enumerators"].get("enumerators", []):
        if e["too_fast"]:
            out.append({"severity": "act", "area": "Enumerator", "instrument": None,
                        "message": f"{e['enumerator']} completes in {e['ratio_to_team']}× the team "
                                   f"median over {e['n']} interviews.",
                        "action": "Re-brief and re-contact a sample of their respondents."})
        elif e["flag_rate"] > THRESHOLDS["flag_rate_max"] and e["n"] >= 10:
            out.append({"severity": "watch", "area": "Enumerator", "instrument": None,
                        "message": f"{e['enumerator']} has a {e['flag_rate']:.0%} flag rate over {e['n']} interviews.",
                        "action": "Observe one interview before the next batch."})

    for w in payload["quotas"]["IND"].get("watch", []):
        if w["breached"]:
            out.append({"severity": "watch", "area": "Composition", "instrument": "IND",
                        "message": f"{w['label']} is {w['share']:.0%} of IND responses, above the "
                                   f"{w['max_share']:.0%} watch level.",
                        "action": "Redirect recruitment. Do not impose a quota on the referral arm; it would break the RDS assumptions."})

    # Quota gaps at the halfway point. Only raised once fielding is genuinely
    # under way, or every cell is 'behind' on day one and the list is noise.
    for code, q in payload["quotas"].items():
        cells = q.get("cells") or q.get("arms") or []
        filled = sum(c["n"] for c in cells)
        target = sum(c["target"] for c in cells) or 1
        if filled / target >= 0.5:
            behind = [c for c in cells if (c.get("pct") or 0) < 50]
            if behind:
                names = ", ".join(c["label"] for c in behind[:4])
                out.append({"severity": "watch", "area": "Quota", "instrument": code,
                            "message": f"{code} is halfway overall but these cells are under 50%: {names}.",
                            "action": "Redirect field effort to these cells now; they will not catch up on their own."})

    order = {"act": 0, "watch": 1}
    return sorted(out, key=lambda a: order.get(a["severity"], 2))


# ---------------------------------------------------------------------------
# 9. insights and the report draft
# ---------------------------------------------------------------------------

def insights(payload):
    """Report-ready findings, each with its number, its n, and its caveat.

    The caveat is not decoration. Every one of these is written to be pasted into
    a document, and the fastest way for this study to be misquoted is for the
    dashboard to hand a surveyor a sentence with the qualification left off.
    Findings whose n is below the threshold are not produced at all.
    """
    out = []
    org, ind, cit = payload["org"], payload["ind"], payload["cit"]

    oc = org["overclaiming"]
    if oc["n"] >= MIN_N:
        out.append({
            "heading": "Self-assessment exceeds demonstrable adoption",
            "finding": f"Organisations rate their own AI maturity {oc['mean_gap']} levels higher, "
                       f"on average, than their own behavioural checklist supports. "
                       f"{oc['over']['pct']}% over-claim by at least one level and "
                       f"{oc['over_by_two_or_more']['pct']}% by two or more.",
            "n": oc["n"],
            "caveat": "Both figures come from the same respondent minutes apart, so the gap is "
                      "internal inconsistency, not disagreement between sources.",
            "section": "§4 Current state",
        })

    for row in payload["benchmarks"]["rows"]:
        if not row["sufficient"] or row["local"] is None:
            continue
        if row.get("unit") == "months":
            out.append({
                "heading": f"{row['label']} against the global figure",
                "finding": f"Ethiopian organisations report a mean delay of {row['local']} months, "
                           f"against {row['global']} months globally.",
                "n": row["n"],
                "caveat": f"Global figure: {row['source']}. Both are self-reported bands, so the "
                          f"comparison is of distributions, not of measured durations.",
                "section": "§3 Global context",
            })
        else:
            out.append({
                "heading": row["label"],
                "finding": f"{row['local']:.0%} of Ethiopian organisations, against {row['global']:.0%} globally.",
                "n": row["n"],
                "caveat": f"Global comparator: {row['source']}. Question wording was matched to that "
                          f"instrument deliberately so the two are comparable.",
                "section": "§3 Global context",
            })

    for b in payload["benchmarks"]["blind_spots"]:
        if b["of"] >= MIN_N and b["pct"]:
            out.append({
                "heading": f"Blind spot: {b['label'].lower().replace('ai ', 'AI ')}",
                "finding": f"{b['pct']}% of organisations answer that they would not know: "
                           f"“{b['label']}”.",
                "n": b["of"],
                "caveat": "Counted separately from the negative answer: not knowing is a different "
                          "state from having checked and found nothing. Visibility, not capability, "
                          "is what this measures.",
                "section": "§8 Challenges",
            })

    if ind["n"] >= MIN_N:
        cs = ind["constructs"]
        ranked = sorted([(k, v["mean"]) for k, v in cs.items() if v["mean"] is not None],
                        key=lambda x: x[1])
        if ranked:
            low, high = ranked[0], ranked[-1]
            out.append({
                "heading": "What drives and blocks practitioner adoption",
                "finding": f"On the 1–{ind['scale_points']} UTAUT scale the strongest construct is "
                           f"{high[0].replace('_', ' ')} ({high[1]}), and the weakest is "
                           f"{low[0].replace('_', ' ')} ({low[1]}).",
                "n": ind["n"],
                "caveat": "Algorithmic aversion is keyed toward aversion: a high score means more "
                          "aversion, not more trust. Constructs follow Venkatesh et al. (2003) as "
                          "extended by Ayeni et al. (MWAIS 2024).",
                "section": "§4 Current state",
            })
        gap = ind["intention_behaviour_gap"]
        if gap["n"] >= MIN_N and gap["wants_more_than_does"]["pct"]:
            out.append({
                "heading": "Intention outruns use",
                "finding": f"{gap['wants_more_than_does']['pct']}% of practitioners intend to use AI "
                           f"more than they currently do.",
                "n": gap["n"],
                "caveat": "A positive gap points at facilitating conditions: access, payment, "
                          "support, rather than at attitude.",
                "section": "§4 Current state",
            })
        if ind["blocked_by_payment"]["of"] >= MIN_N and ind["blocked_by_payment"]["pct"]:
            out.append({
                "heading": "Payment rails, not willingness, gate paid AI tools",
                "finding": f"{ind['blocked_by_payment']['pct']}% of practitioners say they would pay "
                           f"for an AI tool but cannot pay from Ethiopia.",
                "n": ind["blocked_by_payment"]["of"],
                "caveat": "Self-reported barrier; it does not establish that the payment would be made.",
                "section": "§8 Challenges",
            })
        # Only reported when the arms actually differ. An insight that fires on a
        # 0.02 difference trains the reader to ignore the ones that matter, and
        # this list is written to be pasted into a document unedited.
        arms = {a: v for a, v in ind["by_arm"].items() if v["n"] >= MIN_N}
        if len(arms) >= 2:
            spread_by_construct = {}
            for c in (cs or {}):
                means = [v["constructs"].get(c, {}).get("mean") for v in arms.values()]
                means = [m for m in means if m is not None]
                if len(means) >= 2:
                    spread_by_construct[c] = round(max(means) - min(means), 2)
            worst = max(spread_by_construct.items(), key=lambda kv: kv[1], default=None)
            if worst and worst[1] >= 0.3:
                detail = "; ".join(f"{a} {v['constructs'][worst[0]]['mean']} (n={v['n']})"
                    for a, v in arms.items() if v["constructs"].get(worst[0], {}).get("mean") is not None)
                out.append({
                    "heading": "The recruitment arms reach different people",
                    "finding": f"The arms differ most on {worst[0].replace('_', ' ')}: a spread of "
                               f"{worst[1]} points on the 1–{ind['scale_points']} scale: {detail}.",
                    "n": ind["n"],
                    "caveat": "The difference between arms is an estimate of who list-based research "
                              "in Ethiopia misses. It is a finding, not an inconsistency to average away.",
                    "section": "Annex A Methodology",
                })

    spread = cit.get("panel_booster_spread")
    if spread and cit["booster"]["n"] >= MIN_N:
        out.append({
            "heading": "An online panel overstates citizen AI use",
            "finding": f"{spread['panel_pct']}% of the online panel report using AI, against "
                       f"{spread['booster_pct']}% in the probability-sampled booster: a factor of "
                       f"{spread['ratio']}.",
            "n": cit["panel"]["n"] + cit["booster"]["n"],
            "caveat": "The two are never pooled into a single national figure. The spread is "
                      "reported as a finding about online measurement in Ethiopia.",
            "section": "§1.5 Limitations / Annex A",
        })

    if cit["booster"]["n"] >= MIN_N:
        b = cit["booster"]
        if b["uses"]["pct"] is not None:
            eth = DIFFUSION["values"]["Ethiopia (est.)"] * 100
            out.append({
                "heading": "Citizen AI use against the telemetry estimate",
                "finding": f"{b['uses']['pct']}% of booster respondents report using a generative AI "
                           f"tool, against a telemetry-derived estimate of about {eth:.1f}% for "
                           f"Ethiopia and {DIFFUSION['values']['Developing countries'] * 100:.1f}% "
                           f"across developing countries.",
                "n": b["uses"]["of"],
                "caveat": DIFFUSION["source"] + ". Telemetry counts devices and self-report counts "
                          "people; they will not agree exactly and are not expected to.",
                "section": "§3 Global context",
            })

    ranked_sectors = [s for s in payload["sectors"] if s.get("sufficient_for_ranking")]
    if len(ranked_sectors) >= 2:
        top, bottom = ranked_sectors[0], ranked_sectors[-1]
        out.append({
            "heading": "Readiness varies more between sectors than the national average suggests",
            "finding": f"{top['label']} leads on overall readiness ({top['readiness_overall']}, "
                       f"n={top['n']}); {bottom['label']} trails ({bottom['readiness_overall']}, "
                       f"n={bottom['n']}).",
            "n": sum(s["n"] for s in ranked_sectors),
            "caveat": f"Only sectors with n ≥ {MIN_N} are ranked; the rest are suppressed rather "
                      f"than shown with a caveat.",
            "section": "§4.2 Institutional concentration",
        })
        compensable = [s for s in ranked_sectors if (s.get("compensability_gap") or 0) >= 5]
        if compensable:
            s = max(compensable, key=lambda x: x["compensability_gap"])
            out.append({
                "heading": "Arithmetic averaging hides a missing dimension",
                "finding": f"In {s['label']} the arithmetic readiness mean ({s['readiness_overall']}) "
                           f"exceeds the geometric mean ({s['readiness_geometric']}) by "
                           f"{s['compensability_gap']} points.",
                "n": s["n"],
                "caveat": "A large gap means one dimension is near zero and is being masked by "
                          "strength elsewhere. The geometric figure is the one to quote.",
                "section": "§2 Framework",
            })

    for sec_id, block in payload["use_cases"].items():
        if sec_id == "YI" or not block.get("sufficient"):
            continue
        cases = block["cases"]
        if not cases:
            continue
        top = cases[0]
        if top["production"]["pct"] is not None:
            out.append({
                "heading": f"Most-deployed use case in the {sec_id} module",
                "finding": f"“{top['label']}” is in production at {top['production']['pct']}% of "
                           f"responding organisations; {top['piloting_or_better']['pct']}% are at "
                           f"least piloting it.",
                "n": top["n"],
                "caveat": "Status is self-reported against a five-point scale shared by every sector "
                          "module, which is what makes the modules comparable.",
                "section": "§5 Where AI should create value",
            })

    for code, block in payload["barriers"].items():
        if block["n_respondents"] >= MIN_N and block["items"]:
            top3 = block["items"][:3]
            out.append({
                "heading": f"Top reported barriers ({code})",
                "finding": "; ".join(f"{i['label']} ({i['pct']}%)" for i in top3),
                "n": block["n_respondents"],
                "caveat": "Multi-select: shares are over respondents, not over selections, so they "
                          "do not sum to 100%.",
                "section": "§8 Challenges",
            })

    return out


def report_markdown(payload):
    """A draft the surveyor edits, not a report the dashboard publishes.

    Written as Markdown rather than LaTeX so it can be pasted anywhere, and with
    every figure carrying its n inline, so a sentence lifted out of it arrives
    with its denominator attached.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fw = payload["fieldwork"]
    L = [f"# AI-MAP Ethiopia: findings draft", "",
         f"*Generated {now} from {fw['total']} responses. Instrument "
         f"{db.INSTRUMENT_VERSION}.*", "",
         "> Draft output. Every figure below is computed live from the collection "
         "database and will change as fielding continues. Nothing here has been "
         "weighted or calibrated unless the text says so.", "",
         "## 1. Fieldwork status", ""]

    L += ["| Instrument | Collected | Target | % | Channels |", "|---|---:|---:|---:|---|"]
    for code, v in fw["by_instrument"].items():
        modes = ", ".join(f"{k} {n}" for k, n in sorted(v["by_mode"].items())) or ": "
        L.append(f"| {code} | {v['total']} | {v['target']} | {v['pct']}% | {modes} |")
    p = fw["projection"]
    L += ["", f"Collection is running at **{p['responses_per_day']} responses/day** over the last "
              f"{p['window_days']} days. {p['remaining']} responses remain"
          + (f"; at that rate the targets are met on **{p['projected_date']}**."
             if p["projected_date"] else ", and the current rate does not support a projection."), ""]

    acts = [a for a in payload["alerts"] if a["severity"] == "act"]
    if acts:
        L += ["## 2. Issues requiring action", ""]
        for a in acts:
            L.append(f"- **{a['area']}**: {a['message']} *{a['action']}*")
        L.append("")

    L += ["## 3. Findings", ""]
    if not payload["insights"]:
        L += [f"Nothing yet meets the minimum of n ≥ {MIN_N} required to report a figure. "
              "This section fills in as collection continues.", ""]
    for i in payload["insights"]:
        L += [f"### {i['heading']}", "", i["finding"], "",
              f"*n = {i['n']}. {i['caveat']}*  \n`→ {i['section']}`", ""]

    L += ["## 4. Data quality", "",
          "| Instrument | n | Flag rate | Planted | Definition gate | Speeders | Client divergence |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for code, q in payload["quality"].items():
        if code.startswith("_") or not isinstance(q, dict):
            continue
        L.append(f"| {code} | {q['n']} | {q['flag_rate']:.1%} | {q['planted']} | "
                 f"{q['definition']} | {q['speeder']} | {q['client_divergence']} |")

    fn = payload["funnel"]
    L += ["", "## 5. Completion and drop-off", ""]
    if not fn["measurable"]:
        L += ["No progress heartbeats recorded yet, so drop-off cannot be measured. "
              "It is not zero; it is unmeasured.", ""]
    else:
        L += ["| Instrument | Starts | Completed | Completion rate | Median % reached when abandoning |",
              "|---|---:|---:|---:|---:|"]
        for code, f in fn["by_instrument"].items():
            L.append(f"| {code} | {f['starts']} | {f['completions']} | "
                     f"{f['completion_rate']['pct']}% | {f['median_pct_at_abandonment']}% |")
        L.append("")
        for code, items in fn["worst_questions"].items():
            if items:
                L.append(f"**{code}: questions people stop on:** " +
                         "; ".join(f"{q['qid']} ({q['n']})" for q in items[:5]))
        L.append("")

    L += ["## 6. Method notes to carry into the paper", "",
          "- Sector figures are suppressed below n = "
          f"{MIN_N}; suppressed rows show the reason rather than a caveated number.",
          "- The citizen panel and the enumerator booster are never pooled into one national figure.",
          "- Shares from multi-select questions are over respondents, not selections.",
          "- Global comparators are labelled with their source at every point of use.",
          "- Flagged responses are analysed in and out, and both are reported.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def dashboard(path=None):
    rows = _rows(path)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instrument_version": db.INSTRUMENT_VERSION,
        "min_n": MIN_N,
        "thresholds": THRESHOLDS,
        "fieldwork": fieldwork(rows),
        "quotas": quotas(rows),
        "funnel": funnel(path),
        "durations": durations(rows),
        "quality": quality(rows, path),
        "enumerators": enumerators(rows),
        "org": org_distributions(rows),
        "ind": ind_distributions(rows),
        "cit": cit_distributions(rows),
        "benchmarks": benchmarks(rows),
        "sectors": sectors(rows, path),
        "use_cases": use_cases(rows),
        "barriers": barriers(rows),
        "referral_chains": len(db.recruitment_chains(path=path)),
    }
    payload["alerts"] = alerts(payload)
    payload["insights"] = insights(payload)
    return payload


if __name__ == "__main__":
    data = dashboard()
    if "--report" in sys.argv:
        print(report_markdown(data))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
