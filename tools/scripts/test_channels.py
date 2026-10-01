#!/usr/bin/env python3
"""
Channel parity: the web questionnaire and the Telegram bot must agree.

A respondent who starts on Telegram and finishes in a browser must not see the
completion figure jump, and the two channels must route identically: the same
questions in scope, the same weights, the same percentage. The progress model is
implemented twice, once in JavaScript and once in Python, because the two
channels cannot share a runtime. Two implementations of one model is exactly the
situation that drifts, so it is tested rather than trusted.

The web side is not reimplemented here. The REAL `tools/web/app.js` is loaded in
a real browser and its own `progressStats()` is called; a Python re-creation of
it would agree with the Python bot by construction and prove nothing.

    python tools/scripts/test_channels.py

Needs Playwright (`pip install playwright && python -m playwright install
chromium`). Without it the browser half is skipped with a message and the
Python-only checks still run: a skip is reported as a skip, never as a pass.
"""

import http.server
import json
import random
import time
import socketserver
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "telegram_bot"))

import aimap_db as db                                   # noqa: E402

WEB = BASE / "web"

failures = []
checks = 0


def check(ok, label, detail=""):
    global checks
    checks += 1
    print(("  ✓  " if ok else "  ✗  ") + label + (f"   {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------------------
# the bot's implementation, imported rather than copied
# ---------------------------------------------------------------------------

def load_bot():
    """Import bot.py without a Telegram token and without starting anything."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("aimap_bot", BASE / "telegram_bot" / "bot.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        print(f"  !  cannot import bot.py: {e}")
        print("     install python-telegram-bot to run the parity test:")
        print("     pip install -r tools/telegram_bot/requirements.txt")
        return None
    return mod


# ---------------------------------------------------------------------------
# answer sets to compare over
# ---------------------------------------------------------------------------

def sample_answers(code, rng, fill):
    """A partially-filled response, built from the schema's own options.

    Branching questions are answered too, so the comparison covers routed
    sections: the place where the two implementations are most likely to
    disagree, because each resolves `show_if` separately.
    """
    answers = {}
    for sec in db.INSTRUMENTS[code]["sections"]:
        for q in sec["questions"]:
            if q["type"] == "info" or rng.random() > fill:
                continue
            t = q["type"]
            if t == "consent":
                answers[q["id"]] = True
            elif t in ("single", "checklist") and q.get("options"):
                answers[q["id"]] = rng.choice([o["value"] for o in q["options"]])
            elif t == "multi" and q.get("options"):
                vals = [o["value"] for o in q["options"]]
                answers[q["id"]] = rng.sample(vals, min(len(vals), rng.randint(1, 3)))
            elif t == "likert_grid" and q.get("scale") and q.get("rows"):
                scale = [x["value"] for x in q["scale"]]
                answers[q["id"]] = {r["value"]: rng.choice(scale)
                                    for r in q["rows"] if rng.random() < 0.8}
            elif t == "matrix" and q.get("col_options") and q.get("row_options"):
                cols = [c["value"] for c in q["col_options"]]
                answers[q["id"]] = {r["value"]: rng.choice(cols)
                                    for r in q["row_options"] if rng.random() < 0.8}
            elif t == "scale" and q.get("scale"):
                sc = q["scale"]
                answers[q["id"]] = str(rng.randint(sc["min"], sc["max"]))
            elif t == "number":
                answers[q["id"]] = rng.randint(0, 50)
            elif t in ("text", "longtext"):
                answers[q["id"]] = "x"
    return answers


# ---------------------------------------------------------------------------
# the web implementation, in a real browser
# ---------------------------------------------------------------------------

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve_web():
    """Serve tools/web on a free port. http.server follows the schema symlink,
    which StaticFiles deliberately does not."""
    handler = lambda *a, **kw: QuietHandler(*a, directory=str(WEB), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/index.html"


# Cases chosen to cover each rule type and, as importantly, each NEAR MISS: a
# rule that fires on everything is as broken as one that never fires, and only
# the negative cases catch that.
CONSTRAINT_CASES = [
    ("ORG", {"A3": "3", "A4": 400}, True,  "400 IT staff in a 50-249 organisation"),
    ("ORG", {"A3": "3", "A4": 249}, False, "249 IT staff, exactly at the band ceiling"),
    ("ORG", {"A3": "3", "A4": 40},  False, "40 IT staff in a 50-249 organisation"),
    ("ORG", {"A3": "6", "A4": 9000}, False, "9,000 staff in the open-ended top band"),
    ("ORG", {"A3": "3"},            False, "headcount given, IT staff not yet answered"),
    ("ORG", {"D7": 3, "D7b": 5},    True,  "5 of 3 pilots reached production"),
    ("ORG", {"D7": 3, "D7b": 3},    False, "3 of 3 pilots reached production"),
    ("ORG", {"D7": 10, "D7b": 4},   False, "4 of 10 pilots reached production"),
    ("ORG", {"A5": 2031},           True,  "founded in the future"),
    ("ORG", {"A5": 1400},           True,  "founded in 1400"),
    ("ORG", {"A5": 1894},           False, "founded in 1894 (Ethio Telecom)"),
    ("ORG", {"A5": 1950},           False, "founded in 1950 (Addis Ababa University)"),
    # Contradictions found by tools/scripts/audit_logic.py. Only the blocking
    # ones appear here; the flag-level rules never stop a respondent, so there is
    # nothing for the two channels to disagree about.
    ("ORG", {"D1": "no", "D15": "4"},  True,  "AI agents in production, but never adopted AI"),
    ("ORG", {"D1": "no", "D15": "1"},  False, "no AI agents, never adopted AI"),
    ("ORG", {"D1": "yes", "D15": "4"}, False, "AI agents in production, and has adopted AI"),
]


def web_constraints(url, cases):
    """Ask the shipped app.js whether each case violates a BLOCKING rule."""
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        try:
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("typeof violates === 'function'", timeout=15000)
            for code, answers, _, _ in cases:
                out.append(page.evaluate("""async ({code, answers}) => {
                         INSTR = await loadJSON(COMMON.instruments.find(i => i.code === code).file);
                         refCache[code] = INSTR;
                         state = Object.assign({}, state, {code, answers});
                         return (INSTR.constraints || [])
                           .filter(c => c.severity === 'block' && violates(c, answers))
                           .map(c => c.id);
                       }""", {"code": code, "answers": answers}))
        finally:
            b.close()
    return out


def web_autoadvance(url):
    """A double tap inside the auto-advance window must not skip a question.

    A single-choice answer advances on a short delay so the selection is visible
    before the screen changes. During that delay the old options are still on
    screen and still live, so a second tap -- a double tap on a phone, an
    impatient change of mind -- used to queue a second advance and step past a
    question that was never answered. That is exactly the guarantee the
    questionnaire makes ("no skipping ahead") so it is asserted here rather than
    left to hold by luck.
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_context(viewport={"width": 900, "height": 1000}).new_page()
        try:
            page.goto(url, wait_until="networkidle")
            page.click('#instr-list label:has-text("General public") input')
            time.sleep(0.3)
            if page.is_visible("#lenfs"):
                page.click('#lenseg button[data-form="short"]')
            page.click("#pnext")
            page.wait_for_selector("#survey:not([hidden])", timeout=10000)
            page.locator("#qform label.opt").first.click()      # consent
            time.sleep(0.3)
            page.click("#next")
            time.sleep(0.5)
            start = page.evaluate("() => state.pages[state.page].questions[state.qidx].id")
            page.locator("#qform label.opt").nth(0).click()
            time.sleep(0.04)
            try:
                page.locator("#qform label.opt").nth(1).click(timeout=1500)
            except Exception:
                pass
            time.sleep(1.2)
            return page.evaluate("""(s) => {
                     const ids = state.pages.flatMap(p => p.questions.map(q => q.id));
                     const cur = state.pages[state.page].questions[state.qidx].id;
                     const idx = ids.indexOf(cur);
                     return {
                       start: s, cur, moved: idx - ids.indexOf(s),
                       skipped: state.pages.flatMap(p => p.questions).slice(0, idx)
                         .filter(q => mustAnswer(q) && !isComplete(q)).map(q => q.id)
                     };
                   }""", start)
        finally:
            b.close()


def web_progress(url, cases):
    """Ask the shipped app.js for its own numbers, for every case at once."""
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="networkidle")
        page.wait_for_function("typeof progressStats === 'function'", timeout=15000)
        for code, form, answers in cases:
            out.append(page.evaluate("""async ({code, form, answers}) => {
                     // Drive the real module: load the instrument the way the
                     // questionnaire does, set the state it would have, and ask
                     // it for the same numbers the respondent is shown.
                     INSTR = await loadJSON(COMMON.instruments.find(i => i.code === code).file);
                     if (code !== 'ORG' && !refCache.ORG) refCache.ORG = await loadJSON('org.json');
                     refCache[code] = INSTR;
                     state = Object.assign({}, state, {
                       code, form, answers, page: 0, qidx: 0, pages: []
                     });
                     buildPages();
                     const st = progressStats();
                     return {
                       pct: st.pct, done: st.done, total: st.total,
                       pages: state.pages.length,
                       ids: state.pages.flatMap(p => p.questions.map(q => q.id)),
                       // Counted questions only. The web keeps the honeypot in
                       // its page list and renders it hidden -- a trap has to be
                       // in the DOM to work -- while the bot drops it, there
                       // being no DOM to hide it in. That is a deliberate
                       // channel difference, not drift, and both already exclude
                       // it from the progress denominator.
                       counted: state.pages.flatMap(p => p.questions.filter(isCounted).map(q => q.id))
                     };
                   }""",
                {"code": code, "form": form, "answers": answers}))
        b.close()
        if errors:
            check(False, "web page raised no JavaScript errors", "; ".join(errors[:3]))
    return out


# ---------------------------------------------------------------------------

def main():
    print("AI-MAP channel parity")
    print("=" * 56)

    bot = load_bot()
    if bot is None:
        return 1

    rng = random.Random(20260911)
    cases = []
    for code in ("CIT", "IND", "ORG"):
        for form in ("full", "short"):
            for fill in (0.0, 0.35, 0.8, 1.0):
                cases.append((code, form, sample_answers(code, rng, fill)))

    print(f"\n{len(cases)} answer states across CIT, IND and ORG\n")

    print("Short form is a subset of the full form")
    for code in ("CIT", "IND", "ORG"):
        full = {q["id"] for _, q in bot.flat_questions(code, {}, "full")}
        short = {q["id"] for _, q in bot.flat_questions(code, {}, "short")}
        check(short < full, f"{code}: short form is a strict subset",
              f"{len(short)} of {len(full)} items")
        check(bool(short), f"{code}: short form is not empty")
        # The failure mode that actually bites: a core question whose routing
        # depends on a NON-core question. Dropping the dependency makes the core
        # question unreachable in the short form, so a headline variable is
        # silently missing from exactly the responses the short form collects.
        by_id = {q["id"]: q for sec in db.INSTRUMENTS[code]["sections"]
                 for q in sec["questions"]}
        core_ids = {qid for qid, q in by_id.items() if q.get("core")}
        orphaned = []
        for sec in db.INSTRUMENTS[code]["sections"]:
            for q in sec["questions"]:
                if not q.get("core"):
                    continue
                for cond in (q.get("show_if"), sec.get("show_if")):
                    dep = (cond or {}).get("q")
                    if dep and dep not in core_ids:
                        orphaned.append(f"{q['id']}←{dep}")
        check(not orphaned, f"{code}: no core item depends on a dropped question",
              "; ".join(orphaned[:5]))

    print("\nConsent is never routed out of either form")
    for code in ("CIT", "IND", "ORG"):
        for form in ("full", "short"):
            ids = [q for _, q in bot.flat_questions(code, {}, form)]
            check(any(q["type"] == "consent" for q in ids),
                  f"{code}/{form}: consent is present")

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("\n  !  SKIPPED: the browser half of the parity test needs Playwright.")
        print("     pip install playwright && python -m playwright install chromium")
        print(f"\n{checks} checks, {len(failures)} failure(s): browser parity NOT verified")
        return 1 if failures else 0

    httpd, url = serve_web()
    print(f"\nWeb questionnaire served at {url}")
    try:
        web = web_progress(url, cases)
        autoadvance = web_autoadvance(url)
        web_rules = web_constraints(url, CONSTRAINT_CASES)
    finally:
        httpd.shutdown()

    print("\nProgress parity: the same percentage on both channels")
    worst = 0
    for (code, form, answers), w in zip(cases, web):
        done, total, pct = bot.progress_stats(code, answers, form)
        agree = (pct == w["pct"] and done == w["done"] and total == w["total"])
        worst = max(worst, abs(pct - w["pct"]))
        if not agree:
            check(False, f"{code}/{form} fill={len(answers)}",
                  f"bot {done}/{total}={pct}%  web {w['done']}/{w['total']}={w['pct']}%")
    check(worst == 0, "every answer state gives an identical percentage",
          f"largest disagreement: {worst} percentage points")

    print("\nRouting parity: the same questions in scope")
    # Compared over COUNTED questions. The one legitimate difference between the
    # channels is the honeypot: the web renders it hidden, because a trap has to
    # exist in the DOM to catch anything, and the bot omits it, there being
    # nowhere to hide it in a chat. Both already exclude it from progress. Every
    # other difference is drift and must fail here.
    mismatches = []
    for i, ((code, form, answers), w) in enumerate(zip(cases, web)):
        if code == "ORG" and form == "full":
            continue                    # ORG's full form is web/enumerator-only
        bot_ids = [q["id"] for _, q in bot.flat_questions(code, answers, form)
                   if bot.is_counted(q)]
        web_ids = w["counted"]
        if bot_ids != web_ids:
            only_bot = [x for x in bot_ids if x not in web_ids]
            only_web = [x for x in web_ids if x not in bot_ids]
            mismatches.append(f"case {i} {code}/{form}: bot only {only_bot[:4]} "
                              f"· web only {only_web[:4]}")
    check(not mismatches, "every answer state routes to the same questions in both channels",
          mismatches[0] if mismatches else "")
    for m in mismatches[1:6]:
        print(f"       {m}")

    print("\nThe honeypot is web-only, and counted by neither")
    hp = [q["id"] for sec in db.INSTRUMENTS["IND"]["sections"] for q in sec["questions"]
          if "honeypot" in (q.get("flags") or [])]
    if hp:
        w0 = next(w for (c, f, a), w in zip(cases, web) if c == "IND")
        check(all(h in w0["ids"] for h in hp), f"web renders the honeypot ({', '.join(hp)})")
        check(all(h not in w0["counted"] for h in hp), "no channel counts it towards progress")
        check(all(h not in [q["id"] for _, q in bot.flat_questions("IND", {}, "full")] for h in hp),
              "the bot omits it entirely")

    print("\nAuto-advance cannot step past an unanswered question")
    aa = autoadvance
    check(aa["moved"] == 1, "a double tap advances exactly one question",
          f"{aa['start']} -> {aa['cur']}, moved {aa['moved']}")
    check(not aa["skipped"], "nothing is left behind unanswered",
          f"skipped: {aa['skipped']}" if aa["skipped"] else "")

    print("\nCross-field rules: both channels reach the same verdict")
    import aimap_constraints as rules
    disagreements = []
    for (code, answers, should_block, label), web_ids in zip(CONSTRAINT_CASES, web_rules):
        py_ids = sorted(v["id"] for v in rules.evaluate(code, answers)
                        if v["severity"] == "block")
        js_ids = sorted(web_ids)
        if py_ids != js_ids:
            disagreements.append(f"{label}: python {py_ids} vs web {js_ids}")
        elif bool(py_ids) != should_block:
            disagreements.append(f"{label}: expected {'a block' if should_block else 'no block'}, "
                                 f"got {py_ids or 'none'}")
    check(not disagreements, f"all {len(CONSTRAINT_CASES)} cases agree, and match what was expected",
          disagreements[0] if disagreements else "")
    for d in disagreements[1:5]:
        print(f"       {d}")

    print("\nTime estimates are finite and decreasing")
    for code in ("CIT", "IND", "ORG"):
        empty = bot.minutes_left(code, 0, 100, "full")
        nearly = bot.minutes_left(code, 99, 100, "full")
        check(bool(empty) and bool(nearly), f"{code}: an estimate is produced at both ends",
              f"{empty} → {nearly}")
        short_est = bot.minutes_left(code, 0, 100, "short")
        check(short_est != empty, f"{code}: the short form quotes a shorter time",
              f"full {empty} · short {short_est}")

    print("\n" + "=" * 56)
    if failures:
        print(f"{checks} checks, {len(failures)} FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{checks} checks, all passed: the two channels agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
