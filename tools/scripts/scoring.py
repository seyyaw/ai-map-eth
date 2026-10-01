#!/usr/bin/env python3
"""
Reference scoring implementation for AI-MAP Ethiopia.

The web renderer (web/app.js) computes the same scores client-side so respondents
get immediate feedback and offline devices can score without a server. This module
is the authority: it re-scores every stored response during analysis, so a bug or a
tampered client cannot corrupt the published figures.

    python scoring.py --selftest
    python scoring.py --rescore path/to/export.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "schema"
COMMON = json.loads((SCHEMA / "common.json").read_text(encoding="utf-8"))
QUESTIONNAIRE = json.loads((SCHEMA / "questionnaire.json").read_text(encoding="utf-8"))


def reload():
    """Refresh COMMON/QUESTIONNAIRE in place after the schema editor publishes a
    change, in the SAME process (the collection server, which imports this module
    for ingest scoring). Mutated in place, not rebound, for the same reason
    aimap_db.reload_schema() is: anything that took `QUESTIONNAIRE` or `COMMON` as
    a local name at import time must see the update through the same object."""
    new_common = json.loads((SCHEMA / "common.json").read_text(encoding="utf-8"))
    new_q = json.loads((SCHEMA / "questionnaire.json").read_text(encoding="utf-8"))
    COMMON.clear(); COMMON.update(new_common)
    QUESTIONNAIRE.clear(); QUESTIONNAIRE.update(new_q)


def _org_question(qid):
    for sec in QUESTIONNAIRE["sections"]:
        for q in sec["questions"]:
            if q["id"] == qid:
                return q
    return None


D5 = _org_question("D5")
C2 = _org_question("C2")
D5_POINTS = {o["value"]: o.get("points", 0) for o in D5["options"]}
C2_CORRECT = [o["value"] for o in C2["options"] if o.get("correct")]
C2_WRONG = [o["value"] for o in C2["options"] if o.get("correct") is False]


def maturity(checklist):
    """Gated ladder: see common.json maturity_ladder.computed_rule.

    Deliberately NOT a point threshold: an additive score lets an organisation reach
    'deployed' on training and planning alone, which is the over-claiming this
    instrument exists to detect.
    """
    chk = set(checklist or [])
    has = chk.__contains__
    real = chk - {"none", "e14"}

    lvl = 0
    if real:
        lvl = 1
    if has("e3"):
        lvl = 2
    if has("e4"):
        lvl = 3
    if has("e4") and (has("e9") or (has("e6") and has("e7"))):
        lvl = 4
    if lvl == 4 and has("e13") and (has("e7") or has("e11")):
        lvl = 5
    return lvl


def maturity_points(checklist):
    """Continuous index retained for regression models; does not set the level."""
    return sum(D5_POINTS.get(v, 0) for v in (checklist or []))


def definition_accuracy(selected):
    """Net hit rate on the AI/not-AI gate: (true positives - false positives) / n_correct."""
    sel = set(selected or [])
    hit = len(sel & set(C2_CORRECT))
    fp = len(sel & set(C2_WRONG))
    return (hit - fp) / len(C2_CORRECT), fp >= 2


def score_org(answers):
    chk = answers.get("D5") or []
    lvl = maturity(chk)
    self_rated = answers.get("D4")
    self_rated = int(self_rated) if str(self_rated).isdigit() else None
    acc, def_fail = definition_accuracy(answers.get("C2"))
    return {
        "maturity_computed": lvl,
        "maturity_points": maturity_points(chk),
        "maturity_self": self_rated,
        "maturity_gap": (self_rated - lvl) if self_rated is not None else None,
        "definition_accuracy": round(acc, 3),
        "flag_definition": def_fail,
        "flag_planted": "e14" in chk,
        "digital_baseline_index": len([v for v in (answers.get("B1") or []) if v != "none"]),
        "data_governance_index": len([v for v in (answers.get("F3") or []) if v != "none"]),
        "pilot_conversion": (round(float(answers["D7b"]) / float(answers["D7"]), 3)
            if str(answers.get("D7", "")).replace(".", "").isdigit() and float(answers.get("D7") or 0) > 0
            and str(answers.get("D7b", "")).replace(".", "").isdigit()
            else None),
    }


# ---------------------------------------------------------------------------
#  Global-benchmark items (ORG D12-D15), worded to match AvePoint's The State of
#  AI 2026 (n=750), so an Ethiopian figure lands on a global distribution instead
#  of standing alone. Each is scored as a plain indicator: the analysis is a
#  share comparison, and anything cleverer here would make the comparison invalid.
#
#  `shadow_ai_blind` is deliberately its own indicator rather than folded into a
#  "no shadow AI" count. An organisation that cannot see whether staff use
#  unapproved tools is in a different state from one that has looked and found
#  none, and globally the blind share is the one that is growing.
# ---------------------------------------------------------------------------

def score_benchmarks(answers):
    out = {}
    d12 = str(answers.get("D12", ""))
    if d12:
        out["shadow_ai"] = d12 in ("3", "2")
        out["shadow_ai_blind"] = d12 == "0"
    d13 = str(answers.get("D13", ""))
    if d13 and d13 != "na":
        out["deployment_delayed"] = d13 != "0"
        # Midpoint of the answered band, in months. Reported as an estimate of the
        # mean delay, never as a measured duration -- the respondent gave a band.
        out["deployment_delay_months"] = {"0": 0, "1": 1.5, "2": 4.5, "3": 9, "4": 18}.get(d13)
    d14 = str(answers.get("D14", ""))
    if d14:
        out["ai_incident"] = d14 in ("3", "2")
        out["ai_incident_confirmed"] = d14 == "3"
        out["incident_blind"] = d14 == "0"
    d15 = str(answers.get("D15", ""))
    if d15:
        out["agentic_ai"] = d15 in ("4", "3")
        out["agentic_ai_production"] = d15 == "4"
    # The confidence-incident paradox: stated confidence in access control (D16)
    # alongside a reported incident (D14). Only computable when both were asked.
    conf = str(answers.get("D16", ""))
    if conf.isdigit() and out.get("ai_incident") is not None:
        out["confidence_incident_paradox"] = int(conf) >= 3 and out["ai_incident"]
    return out


# ===========================================================================
#  Technical depth: "are we building AI, or only adopting it?"
# ===========================================================================

TECH = COMMON["technical_ladder"]


def technical(checklist):
    """Gated ladder over ORG.T2, mirroring maturity(). Orthogonal to adoption:
    an organisation can be practically deep and technically shallow, or the
    reverse. Level 4 additionally requires level-3 evidence, because "trained
    from scratch" without any fine-tuning capability underneath it is far more
    likely to be a misread question than a real national capability."""
    chk = set(checklist or [])
    has = chk.__contains__
    lvl = 0
    if has("t1"):
        lvl = 1
    if has("t2") or has("t3"):
        lvl = 2
    if has("t4") or has("t5"):
        lvl = 3
    if has("t6") and (has("t4") or has("t5")):
        lvl = 4
    return lvl


def score_technical(answers):
    chk = set(answers.get("T2") or [])
    lvl = technical(chk)
    self_rated = answers.get("T1")
    self_rated = int(self_rated) if str(self_rated).isdigit() else None
    return {
        "technical_computed": lvl,
        "technical_self": self_rated,
        "technical_gap": (self_rated - lvl) if self_rated is not None else None,
        "trains_on_ethiopian_data": "t5" in chk,
        "contributes_back": "t7" in chk,
        # Vendor-hosted inference plus no in-house diagnosis = a purchased
        # service rather than a capability. Reported per sector.
        # "Trained from scratch" with no fine-tuning or integration beneath it
        # is almost always a misread question. Flagged, not silently dropped.
        "flag_scratch_unsupported": ("t6" in chk and not ({"t2", "t3", "t4", "t5"} & chk)),
        "capability_not_procurement": (str(answers.get("T5")) in ("2", "3") and answers.get("T4") != "vendor"),
    }


# ===========================================================================
#  Readiness index: five dimensions, scored identically for every sector
# ===========================================================================
#
# Every item is mapped to 0..1 by an explicit rule below. Nothing is normalised
# implicitly: a reader must be able to see exactly how an answer became a score.
# Equal weights within a dimension are a STATED CHOICE, not a finding; the
# sensitivity analysis reports how sector rankings move under alternatives.

def _ordinal(value, best):
    """Numeric-coded ordinal where `best` is the top code and 0 the bottom."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None                      # 'na' / unanswered -> excluded, not zero
    return max(0.0, min(1.0, v / best))


def _reverse(value, worst):
    """Ordinal where a HIGHER code is worse (e.g. recruitment difficulty)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, 1 - v / worst))


def _checklist(value, total, exclude=("none",)):
    if not isinstance(value, list):
        return None
    picked = [x for x in value if x not in exclude]
    return max(0.0, min(1.0, len(picked) / total))


def _checklist_bad(value, total, exclude=("none",)):
    """Checklist where every tick is a defect (e.g. F7 standardisation faults)."""
    v = _checklist(value, total, exclude)
    return None if v is None else 1 - v


def _has_any(value, wanted):
    if not isinstance(value, list):
        return None
    return 1.0 if any(w in value for w in wanted) else 0.0


def _categorical(value, mapping):
    return mapping.get(str(value))


def _grid_mean(value, best):
    if not isinstance(value, dict) or not value:
        return None
    vals = [float(v) for v in value.values() if str(v).replace(".", "").isdigit()]
    return (sum(vals) / len(vals)) / best if vals else None


def _count_band(value, full):
    """A raw count normalised against a 'well staffed' reference point."""
    try:
        return max(0.0, min(1.0, float(value) / full))
    except (TypeError, ValueError):
        return None


# item id -> (callable, note explaining the direction)
NORMALISE = {
    # ---- infrastructure -------------------------------------------------
    "G1": (lambda a: _checklist(a.get("G1"), 7), "compute resources available, of 7"),
    "G2": (lambda a: (1.0 if isinstance(a.get("G2"), list) and
                      any(r.get("model") for r in a["G2"]) else 0.0), "any accelerator at all"),
    "G3": (lambda a: _ordinal(a.get("G3"), 3), "willingness to federate spare capacity"),
    "G4": (lambda a: _categorical(a.get("G4"), {"none": 1.0, "cost": 0.5, "skills": 0.5,
                                                "compute": 0.0, "internet": 0.0, "power": 0.0,
                                                "storage": 0.25, "fx": 0.0}),
           "self-named binding infrastructure constraint"),
    "B3": (lambda a: _ordinal(a.get("B3"), 4), "connectivity quality"),
    "B4": (lambda a: _ordinal(a.get("B4"), 4), "power interruption frequency, reversed in coding"),
    "B5": (lambda a: _ordinal(a.get("B5"), 2), "backup power for servers"),
    # ---- data -----------------------------------------------------------
    "B1": (lambda a: _checklist(a.get("B1"), 8), "digital substrate present, of 8"),
    "B2": (lambda a: _ordinal(a.get("B2"), 4), "share of records held digitally"),
    "F1": (lambda a: _ordinal(a.get("F1"), 3), "datasets usable for training/evaluation"),
    "F2": (lambda a: (1.0 if isinstance(a.get("F2"), list) and
                      any(r.get("name") for r in a["F2"]) else 0.0), "at least one nameable dataset"),
    "F3": (lambda a: _checklist(a.get("F3"), 9), "data management practices, of 9"),
    "F5": (lambda a: _categorical(a.get("F5"), {"success": 1.0, "partial": 0.6,
                                                "failed": 0.2, "no": 0.4}),
           "outcome of an inter-institutional data request; 'never tried' scores mid"),
    "F7": (lambda a: _checklist_bad(a.get("F7"), 8), "standardisation defects, reversed"),
    # ---- expertise ------------------------------------------------------
    "A4": (lambda a: _count_band(a.get("A4"), 20), "technical staff, capped at 20"),
    "H1": (lambda a: _grid_mean(a.get("H1"), 4), "staffing across seven technical roles"),
    "H2": (lambda a: _reverse(a.get("H2"), 4), "recruitment difficulty, reversed"),
    "H3": (lambda a: _reverse(a.get("H3"), 4), "technical staff lost abroad, reversed"),
    "H4": (lambda a: _ordinal(a.get("H4"), 3), "training provided in the last year"),
    "C3": (lambda a: _ordinal(int(a["C3"]) - 1 if str(a.get("C3")).isdigit() else None, 4),
           "leadership understanding, 1-5 rescaled"),
    "C4": (lambda a: _ordinal(int(a["C4"]) - 1 if str(a.get("C4")).isdigit() else None, 4),
           "technical staff understanding, 1-5 rescaled"),
    # ---- economic -------------------------------------------------------
    "A7": (lambda a: _ordinal(a.get("A7"), 3), "foreign exchange access"),
    "A8": (lambda a: _ordinal(int(a["A8"]) - 1 if str(a.get("A8")).isdigit() else None, 4),
           "operating budget band"),
    "J1": (lambda a: _categorical(a.get("J1"), {"yes": 1.0, "within_ict": 0.6, "no": 0.0}),
           "dedicated AI budget line"),
    "J2": (lambda a: _ordinal(int(a["J2"]) - 1 if str(a.get("J2")).isdigit() else None, 4),
           "size of that budget"),
    "J3": (lambda a: _has_any(a.get("J3"), ["internal", "gov", "donor", "loan", "angel",
                                            "vc_seed", "vc_series", "diaspora"]),
           "any identified funding source"),
    "J4": (lambda a: _categorical(a.get("J4"), {"success": 1.0, "pending": 0.7, "reject": 0.4,
                                                "no": 0.3, "unaware": 0.0}),
           "public funding applied for; 'unaware any existed' is the floor"),
    "J7": (lambda a: _ordinal(a.get("J7"), 3), "whether cost has already killed a project"),
    # ---- governance -----------------------------------------------------
    "E6": (lambda a: _ordinal(a.get("E6"), 3), "policy on staff use of general-purpose AI"),
    "F3g": (lambda a: _has_any(a.get("F3"), ["dpo", "consent", "audit"]),
            "data-protection roles and audit trail present"),
    "F4": (lambda a: _ordinal(a.get("F4"), 3), "awareness of and action on Proclamation 1321/2024"),
    "I1": (lambda a: _ordinal(a.get("I1"), 3), "awareness of the National AI Policy"),
    "I8": (lambda a: _ordinal(a.get("I8"), 2), "clarity on liability for AI harm"),
    "K3": (lambda a: _grid_mean(a.get("K3"), 5), "breadth of risk awareness"),
}

# governance reuses F3 through a different lens, so it is aliased
DIM_ITEMS = {d["id"]: list(d["items"]) for d in COMMON["readiness_index"]["dimensions"]}
DIM_ITEMS["governance"] = [("F3g" if i == "F3" else i) for i in DIM_ITEMS["governance"]]


def readiness(answers):
    """Five dimension scores on 0-100, plus per-dimension coverage.

    Unanswered or 'don't know' items are EXCLUDED from the mean rather than
    scored zero -- treating a non-answer as a failure would systematically
    punish respondents who are candid about not knowing. `coverage` reports how
    much of each dimension was actually answered so thin scores can be flagged.
    """
    out = {}
    for dim, items in DIM_ITEMS.items():
        vals = []
        for i in items:
            fn = NORMALISE.get(i)
            if not fn:
                continue
            try:
                v = fn[0](answers)
            except Exception:
                v = None
            if v is not None:
                vals.append(max(0.0, min(1.0, v)))
        out[f"readiness_{dim}"] = round(100 * sum(vals) / len(vals), 1) if vals else None
        out[f"coverage_{dim}"] = round(len(vals) / len(items), 2)
    scored = [out[f"readiness_{d}"] for d in DIM_ITEMS if out[f"readiness_{d}"] is not None]
    # Composite is reported only alongside the five components, never instead.
    out["readiness_overall"] = round(sum(scored) / len(scored), 1) if scored else None

    # Geometric mean as the robustness variant: it limits compensability, so a
    # sector cannot mask absent governance with strong infrastructure. If the
    # sector ranking differs between the two, that difference is the finding.
    if scored:
        prod = 1.0
        for v in scored:
            prod *= max(v, 1.0)          # floor at 1 so a single zero does not annihilate
        out["readiness_overall_geometric"] = round(prod ** (1 / len(scored)), 1)
        out["compensability_gap"] = round(out["readiness_overall"] - out["readiness_overall_geometric"], 1)
    else:
        out["readiness_overall_geometric"] = None
        out["compensability_gap"] = None

    out["readiness_band"] = band(out["readiness_overall"])
    return out


BANDS = COMMON["readiness_index"]["bands"]


def band(score):
    """Band label is the headline; the number is supporting detail. Reporting a
    three-point difference between sectors as a ranking is spurious precision."""
    if score is None:
        return None
    for b in BANDS:
        if score <= b["max"]:
            return b["label"]
    return BANDS[-1]["label"]

def _q(qid):
    for sec in QUESTIONNAIRE["sections"]:
        for q in sec["questions"]:
            if q["id"] == qid:
                return q
    return None


# UTAUT construct scoring. The construct definitions live in the schema
# (common.json -> "utaut"), not here, so adding or re-balancing an item is a data
# change. Reverse-coded rows are flipped BEFORE aggregation, which makes a high
# `utaut_algorithmic_aversion` mean high aversion -- the sign is the single thing
# most easily got wrong when these scales are re-used.
_UTAUT = COMMON.get("utaut") or {}


def utaut_constructs(answers):
    """Mean per construct on the 1-5 response scale, plus the count behind each."""
    cfg = _UTAUT.get("constructs") or {}
    if not cfg:
        return {}
    grid = answers.get(_UTAUT.get("item", "PU1"))
    out = {}
    if not isinstance(grid, dict):
        return out
    points = _UTAUT.get("scale_points", 5)
    for name, spec in cfg.items():
        vals = []
        for row in spec["rows"]:
            v = grid.get(row)
            if v is None or str(v) == "":
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            vals.append((points + 1 - x) if spec.get("reverse") else x)
        if vals:
            out[f"utaut_{name}"] = round(sum(vals) / len(vals), 2)
            out[f"utaut_{name}_n"] = len(vals)
    answered = sum(v for k, v in out.items() if k.endswith("_n"))
    total = sum(len(s["rows"]) for s in cfg.values())
    out["utaut_coverage"] = round(answered / total, 2) if total else 0.0
    # Reported alongside the constructs rather than derived later: the gap between
    # what someone intends and what they already do is where facilitating
    # conditions become visible, and it is the point of asking U2 separately.
    intent = answers.get(_UTAUT.get("outcome", "PU2"))
    freq = answers.get("PB1")
    if str(intent).isdigit() and str(freq).isdigit():
        out["intention_behaviour_gap"] = int(intent) - min(int(freq), 4)
    return out


def score_individual(answers):
    """Practitioner branch. The emigration scale is the substantive measure;
    the rest are data-quality flags."""
    out = {}
    aq = _q("PG5")
    if aq and answers.get("PG5") is not None:
        out["flag_attention"] = str(answers["PG5"]) != str(aq.get("expected"))

    f3 = answers.get("PF3")
    if isinstance(f3, dict):
        vals = [float(f3[k]) for k in ("intent1", "intent2", "intent3")
                if str(f3.get(k, "")).replace(".", "").isdigit()]
        if vals:
            out["emigration_intention"] = round(sum(vals) / len(vals), 2)
            out["emigration_items_answered"] = len(vals)

    # Self-assessed technical ability across the ten areas of PC1.
    c1 = answers.get("PC1")
    if isinstance(c1, dict):
        vals = [float(v) for v in c1.values() if str(v).replace(".", "").isdigit()]
        if vals:
            out["skill_index"] = round(100 * (sum(vals) / len(vals)) / 4, 1)

    out.update(utaut_constructs(answers))

    out["remote_for_foreign_employer"] = answers.get("PF1") == "remote"
    out["blocked_by_payment"] = answers.get("PB3") == "want"
    out["language_penalty"] = str(answers.get("PD4")) in ("2", "3")
    out["diaspora"] = answers.get("PA3") == "diaspora"
    return out


def score_citizen(answers):
    """Citizen branch. Deliberately thin: the analytical work is done by weighting
    and disaggregation, not by scoring individual responses."""
    out = {}
    out["uses_ai"] = str(answers.get("ZC3")) in ("2", "3", "4")
    out["aware_of_ai"] = str(answers.get("ZC1")) in ("1", "2", "3")
    # Contestability: can this person challenge an automated decision?
    if answers.get("ZD3") is not None:
        out["knows_how_to_complain"] = str(answers.get("ZD3")) == "2"
    # Ethiopian-language performance, the lower-bound measure (see limitations).
    if answers.get("ZC6") is not None and str(answers.get("ZC6")) != "":
        out["language_worked_well"] = str(answers.get("ZC6")) == "3"
    d1 = answers.get("ZD1")
    if isinstance(d1, dict):
        vals = [float(v) for v in d1.values() if str(v).replace(".", "").isdigit()]
        if vals:
            out["institutional_trust"] = round(100 * ((sum(vals) / len(vals)) - 1) / 3, 1)
    out["smartphone"] = answers.get("ZB1") == "smart"
    out["rural"] = answers.get("ZA2") == "rural"
    return out


def score_all(answers):
    """Everything computed for one ORG response."""
    out = score_org(answers)
    out.update(score_technical(answers))
    out.update(readiness(answers))
    out.update(score_benchmarks(answers))
    return out


def _selftest():
    cases = [
        ("nothing ticked",                       [],                                          0),
        ("only the planted item (evidences nothing real)", ["e14"],                           0),
        ("training + written assessment",        ["e1", "e2"],                                1),
        ("REGRESSION: training+plan+budget+monitoring, nothing live",
                                                 ["e1", "e2", "e6", "e7", "e10", "e11"],      1),
        ("pilot run, nothing live",              ["e1", "e2", "e3"],                          2),
        ("REGRESSION: pilot + budget + monitoring + policy, nothing live",
                                                 ["e1", "e2", "e3", "e6", "e7", "e11", "e12"], 2),
        ("one system live",                      ["e3", "e4", "e5"],                          3),
        ("live but only one dept, no budget",    ["e3", "e4", "e5", "e7"],                    3),
        ("live in 2+ depts",                     ["e3", "e4", "e9"],                          4),
        ("live + budget line + monitoring",      ["e3", "e4", "e6", "e7"],                    4),
        ("scaled + critical + monitored",        ["e3", "e4", "e9", "e7", "e13"],             5),
        ("scaled + critical + written policy",   ["e3", "e4", "e9", "e11", "e13"],            5),
        ("critical but not scaled",              ["e3", "e4", "e13", "e7"],                   3),
    ]
    print("Maturity gate self-test\n" + "=" * 74)
    fails = 0
    for name, chk, expect in cases:
        got = maturity(chk)
        ok = got == expect
        fails += not ok
        print(f"  {'✓' if ok else '✗'}  L{got} (want L{expect})  {name}")
    print()

    print("Self-vs-computed gap (the study's headline measure)")
    over = {"D4": "4", "D5": ["e1", "e2", "e6", "e7", "e11"], "C2": ["ml_forecast", "dashboard", "rules_wf"]}
    s = score_org(over)
    print(f"  a respondent self-rating 'Scaled' with nothing in production scores "
          f"L{s['maturity_computed']} → gap +{s['maturity_gap']}")
    print(f"  definition_accuracy {s['definition_accuracy']}  flag_definition {s['flag_definition']}")
    assert s["maturity_gap"] == 3, "expected a +3 over-claim gap"

    honest = {"D4": "3", "D5": ["e3", "e4", "e5"], "C2": ["ml_forecast", "asr", "llm", "cv"]}
    h = score_org(honest)
    print(f"  an accurate respondent: self L{h['maturity_self']} computed L{h['maturity_computed']} "
          f"→ gap {h['maturity_gap']}, definition_accuracy {h['definition_accuracy']}")
    assert h["maturity_gap"] == 0 and h["definition_accuracy"] == 1.0

    # ---- technical ladder ------------------------------------------------
    print("\nTechnical depth gates ('building or adopting?')")
    tcases = [
        ("nothing",                              [],                          0),
        ("off-the-shelf only",                   ["t1"],                      1),
        ("integrated via API",                   ["t1", "t2"],                2),
        ("retrieval over own documents",         ["t1", "t3"],                2),
        ("fine-tuned on own data",               ["t1", "t2", "t4"],          3),
        ("fine-tuned on Ethiopian-language data",["t1", "t5"],                3),
        ("REGRESSION: 'from scratch' claimed with nothing beneath it",
                                                 ["t1", "t6"],                1),
        ("trained from scratch, with fine-tuning capability",
                                                 ["t1", "t2", "t4", "t6"],    4),
    ]
    for name, chk, expect in tcases:
        got = technical(chk)
        ok = got == expect
        fails += not ok
        print(f"  {'✓' if ok else '✗'}  L{got} (want L{expect})  {name}")

    # ---- readiness -------------------------------------------------------
    print("\nReadiness index")
    strong = {
        "G1": ["servers", "gpu", "cloud_intl", "colo"], "G2": [{"model": "A100", "count": "4"}],
        "G3": "3", "G4": "none", "B3": "4", "B4": "4", "B5": "2",
        "B1": ["website", "email", "mis", "db", "api", "cloud", "bi", "digital_svc"],
        "B2": "4", "F1": "3", "F2": [{"name": "core ledger"}],
        "F3": ["dict", "quality", "steward", "retention", "backup", "meta", "consent", "dpo", "audit"],
        "F5": "success", "F7": ["none"],
        "A4": 25, "H1": {"dev": "4", "data_sci": "3"}, "H2": "2", "H3": "0", "H4": "3",
        "C3": "5", "C4": "5",
        "A7": "3", "A8": "5", "J1": "yes", "J2": "5", "J3": ["internal", "gov"], "J4": "success", "J7": "3",
        "E6": "3", "F4": "3", "I1": "3", "I8": "2", "K3": {"privacy": "5", "bias": "4"},
    }
    weak = {"G1": ["none"], "G3": "0", "G4": "compute", "B3": "1", "B4": "0", "B5": "0",
            "B1": ["none"], "B2": "0", "F1": "0", "F3": ["none"], "F5": "failed",
            "F7": ["ethiopic", "calendar", "names", "address", "ids", "codes", "dupes", "missing"],
            "A4": 0, "H2": "4", "H3": "4", "H4": "0", "C3": "1", "C4": "1",
            "A7": "0", "A8": "1", "J1": "no", "J3": ["none"], "J4": "unaware", "J7": "0",
            "E6": "0", "F4": "0", "I1": "0", "I8": "0"}
    for label, ans in (("well resourced", strong), ("poorly resourced", weak)):
        r = readiness(ans)
        dims = " ".join(f"{d[:5]}={r['readiness_'+d]}" for d in DIM_ITEMS)
        print(f"  {label:17} {dims}  overall={r['readiness_overall']}")
    hi, lo = readiness(strong)["readiness_overall"], readiness(weak)["readiness_overall"]
    ok = hi is not None and lo is not None and hi > lo + 30
    fails += not ok
    print(f"  {'✓' if ok else '✗'}  well-resourced scores well above poorly-resourced")

    # 'don't know' must not be scored as failure
    partial = readiness({"G1": ["servers"], "A7": "na", "J1": "na"})
    ok = partial["coverage_economic"] < 1.0
    fails += not ok
    print(f"  {'✓' if ok else '✗'}  unanswered items excluded, not zeroed "
          f"(economic coverage {partial['coverage_economic']})")

    print(f"\n{'✓ all gates behave as specified' if not fails else f'✗ {fails} gate failure(s)'}")
    return 1 if fails else 0


def _rescore(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    changed = 0
    for r in rows:
        if r.get("instrument") != "ORG":
            continue
        answers = {}
        for k, v in r.items():
            if not k.startswith("a_"):
                continue
            try:
                answers[k[2:]] = json.loads(v) if v and v[0] in "[{" else v
            except json.JSONDecodeError:
                answers[k[2:]] = v
        fresh = score_org(answers)
        if str(fresh["maturity_computed"]) != str(r.get("s_maturity_computed", "")):
            changed += 1
        r.update({f"s_{k}": v for k, v in fresh.items()})
    print(f"re-scored {len(rows)} rows; {changed} client-side score(s) disagreed with the reference")
    if rows:
        out = Path(path).with_suffix(".rescored.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("wrote", out)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rescore")
    a = ap.parse_args()
    if a.rescore:
        sys.exit(_rescore(a.rescore))
    sys.exit(_selftest())


