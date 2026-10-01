#!/usr/bin/env python3
"""
Hunt for answer combinations that contradict each other.

Routing decides which questions a respondent SEES. It says nothing about whether
the answers they give can all be true at once. A respondent can report never
having used an AI tool and then say they will certainly keep using it; an
organisation can say it has never deployed AI and then tick a production system.
Nothing in the schema stops either, and nothing in analysis notices.

This enumerates candidate contradictions and, for each, reports which of three
states it is in:

    PREVENTED   Routing already makes the combination unreachable. Nothing to do.
    OPEN        Reachable, and nothing catches it. A decision is needed.
    HANDLED     Reachable, and a constraint in the schema catches it.

The verdict column is the point. Not every contradiction should be designed out:

  * Route it away where the second question is meaningless given the first.
  * Block it where both answers cannot be true and only the respondent can say
    which is wrong.
  * FLAG it where the contradiction is the measurement. Reverse-keyed items in an
    attitude scale exist precisely to be contradicted by careless respondents;
    branching them away would delete the detector and leave the scale unable to
    tell a considered answer from a straight line of taps.

    python tools/scripts/audit_logic.py
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import aimap_constraints as rules                        # noqa: E402

SCHEMA = BASE / "schema"
COMMON = json.loads((SCHEMA / "common.json").read_text(encoding="utf-8"))
INSTR = {s["code"]: json.loads((SCHEMA / s["file"]).read_text(encoding="utf-8"))
         for s in COMMON["instruments"]}


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
        return isinstance(v, dict) and any(str(x).replace(".", "").isdigit() and float(x) >= float(cond["value"])
            for x in v.values())
    return True


def in_scope(code, qid, answers):
    """Would this question be shown, given these answers?"""
    for sec in INSTR[code]["sections"]:
        if not show_if(sec.get("show_if"), answers):
            continue
        for q in sec["questions"]:
            if q["id"] == qid:
                return show_if(q.get("show_if"), answers)
    return False


# Each case: the two answers, what makes them contradictory, and the verdict
# taken. `expect` is what the audit should report once the decision is applied.
CASES = [
    # ---------------------------------------------------------------- ORG
    {
        "code": "ORG", "id": "never-adopted-but-production",
        "answers": {"D1": "no", "D5": ["e3"]},
        "pair": ("D1", "D5"),
        "why": "Says it has never used AI, then ticks a production system",
        "verdict": "flag",
    },
    {
        "code": "ORG", "id": "never-adopted-but-agentic",
        "answers": {"D1": "no", "D15": "4"},
        "pair": ("D1", "D15"),
        "why": "Says it has never used AI, then reports AI agents in production",
        "verdict": "blocked-already",
    },
    {
        "code": "ORG", "id": "no-automated-decisions-but-production",
        "answers": {"S3": "fed_gov", "S6": "no",
                    "YG5": "0", "YG1": {"casework": "4"}},
        "pair": ("YG5", "YG1"),
        "why": "Says it makes no automated decisions about citizens, then reports "
               "case triage in production",
        "verdict": "flag",
    },
    {
        "code": "ORG", "id": "pilots-without-pilot-evidence",
        "answers": {"D1": "yes", "D5": ["e3"], "D7": 0, "D7b": 3},
        "pair": ("D7", "D7b"),
        "why": "No pilots started, yet pilots reached production",
        "verdict": "blocked-already",
    },
    # ---------------------------------------------------------------- IND
    {
        "code": "IND", "id": "never-uses-but-certain-to-continue",
        "answers": {"S2": "data", "B1": "0", "U2": "4"},
        "pair": ("B1", "U2"),
        "why": "Never uses AI tools, but is certain they already do and will continue",
        "verdict": "reworded",
    },
    {
        "code": "IND", "id": "accepted-work-abroad-but-no-intent",
        "answers": {"S2": "data", "F5": "3", "F3": {"intent1": "1", "intent2": "1",
                                                    "intent3": "1", "stay1": "5"}},
        "pair": ("F5", "F3"),
        "why": "Has accepted AI work outside Ethiopia, but strongly denies any "
               "intention to leave",
        "verdict": "flag",
    },
    {
        "code": "IND", "id": "high-intent-and-high-stay",
        "answers": {"S2": "data", "F3": {"intent1": "5", "intent2": "5",
                                         "intent3": "5", "stay1": "5"}},
        "pair": ("F3", "F3"),
        "why": "Strongly intends to leave AND strongly agrees they can build the "
               "career they want without leaving: the reverse-keyed pair",
        "verdict": "flag-by-design",
    },
    {
        "code": "IND", "id": "expert-but-never-built",
        "answers": {"S2": "data", "B5": "0", "C1": {"ml": "4", "dl": "4"}},
        "pair": ("B5", "C1"),
        "why": "Rates own machine-learning ability as expert, but has never built "
               "or trained a model",
        "verdict": "flag",
    },
    # ---------------------------------------------------------------- CIT
    {
        "code": "CIT", "id": "unaware-but-uses",
        "answers": {"C1": "0", "C3": "3"},
        "pair": ("C1", "C3"),
        "why": "Has never heard of AI, but reports using it often",
        "verdict": "by-design",
    },
]


# Verdicts that mean "looked at, decided, nothing more to do". Kept distinct from
# OPEN so the summary line cannot quietly report a settled decision as an
# outstanding one -- which is how an audit stops being read.
SETTLED = {"reworded", "by-design"}


def classify(case):
    code, answers = case["code"], case["answers"]
    a, b = case["pair"]
    reachable = in_scope(code, a, answers) and in_scope(code, b, answers)
    if not reachable:
        return "PREVENTED", "routing makes it unreachable"
    caught = [v["id"] for v in rules.evaluate(code, answers)]
    if caught:
        return "HANDLED", f"caught by {', '.join(caught)}"
    if case["verdict"] in SETTLED:
        return "RESOLVED", "reachable, and deliberately left so"
    return "OPEN", "reachable, nothing catches it"


VERDICT_TEXT = {
    "route": "route the second question out",
    "flag": "flag; both could be true, or the respondent knows something the form does not",
    "flag-by-design": "FLAG, never route: the contradiction IS the measurement",
    "by-design": "leave: the definition is shown between the two questions",
    "blocked-already": "blocked by an existing constraint",
    "reword": "reword or route: the two items are asking past each other",
    "reworded": "reworded: the option no longer asserts current use",
}


def main():
    print("AI-MAP logical consistency audit")
    print("=" * 78)
    counts = {"PREVENTED": 0, "HANDLED": 0, "RESOLVED": 0, "OPEN": 0}
    open_cases = []
    for case in CASES:
        state, detail = classify(case)
        counts[state] += 1
        mark = {"PREVENTED": "·", "HANDLED": "✓", "RESOLVED": "○", "OPEN": "!"}[state]
        print(f"\n {mark} [{state}] {case['code']} {case['pair'][0]} × {case['pair'][1]}"
              f"  ({case['id']})")
        print(f"     {case['why']}")
        print(f"     {detail}")
        print(f"     verdict: {VERDICT_TEXT[case['verdict']]}")
        if state == "OPEN":
            open_cases.append(case)

    print("\n" + "=" * 78)
    print(f"{counts['PREVENTED']} prevented by routing · {counts['HANDLED']} caught by a "
          f"constraint · {counts['RESOLVED']} deliberately left · {counts['OPEN']} open")
    if open_cases:
        print("\nOpen cases still needing a decision:")
        for c in open_cases:
            print(f"  - {c['code']} {c['id']}: {VERDICT_TEXT[c['verdict']]}")
    return 1 if open_cases else 0


if __name__ == "__main__":
    sys.exit(main())
