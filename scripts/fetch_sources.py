#!/usr/bin/env python3
"""
Re-retrieve every external source in sources/README.md.

Publishers disagree about what counts as a robot, and the disagreement is not
guessable, so each source records the engine that actually works for it:

    plain     requests/curl is enough
    chromium  Playwright's bundled Chromium, headless
    firefox   Playwright Firefox -- Preprints.org sits behind an Akamai rule that
              rejects headless Chromium and real Chrome alike but passes Firefox
    download  the URL triggers a file download rather than a navigation, so the
              page must be driven and the download intercepted (AIS eLibrary)

Snapshot targets are HTML-only and are rendered to PDF, because the figures we
quote from them are edited in place without notice.

    pip install playwright pypdf && python -m playwright install chromium firefox
    python scripts/fetch_sources.py            # everything
    python scripts/fetch_sources.py --only avepoint
"""

import argparse
import sys
import time
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[1] / "sources"
SNAPS = SOURCES / "web-snapshots"

# name, url, engine, destination
DOCUMENTS = [
    ("avepoint", "https://cdn.avepoint.com/pdfs/en/shifthappens/AI-Report-eBook-2026.pdf",
     "plain", SOURCES / "avepoint-ai-report-2026.pdf"),
    ("asric", "https://asric.africa/sites/default/files/2025-07/NS%202023_Vol.%203%20Issue2_19.pdf",
     "plain", SOURCES / "asric-ai-landscape-ethiopia.pdf"),
    ("mwais", "https://aisel.aisnet.org/cgi/viewcontent.cgi?article=1030&context=mwais2024",
     "download", SOURCES / "mwais2024-genai-subsaharan-africa.pdf"),
    ("preprints", "https://www.preprints.org/manuscript/202503.0335/v1",
     "firefox", SOURCES / "preprints-ai-agriculture-review.pdf"),
]

SNAPSHOTS = [
    ("microsoft-ai-diffusion-q1-2026-africa", "https://www.ecofinagency.com/news/2205-55838-south-africa-tops-african-generative-ai-adoption-rankings-in-2026-microsoft-report"),
    ("techcentral-sa-leads-africa-ai-adoption", "https://techcentral.co.za/south-africa-leads-rest-of-africa-in-ai-adoption-microsoft/281427/"),
    ("hrrc-critical-gaps-ai-east-horn-africa", "https://www.humanrightsresearch.org/post/critical-gaps-in-artificial-intelligence-in-the-east-and-horn-of-africa-a-call-to-action-to-safegua"),
    ("ai-readiness-index-2026-rankings", "https://www.index.dev/blog/ai-readiness-index-statistics"),
    ("african-ai-adoption-trends-2025", "https://journal.neuravox.org/p/african-ai-adoption-trends-2025"),
    ("ai-regulation-africa-2026", "https://www.techinafrica.com/ai-regulation-africa-2026-new-laws-compliance-startup-opportunities/"),
    ("nigeria-genai-working-age-10pct", "https://technext24.com/2026/05/18/generative-ai-nigerias-working-age-use/"),
    ("togo-mid-tier-ai-adopters", "https://www.togofirst.com/en/itc/2505-19057-togo-joins-africa-s-mid-tier-ai-adopters-with-10-1-usage-rate"),
    ("ethiopia-first-ai-research-centre", "https://ethiopianbusinessreview.net/ethiopia-to-establish-its-first-ever-artificial-intelligence-research-centre/"),
]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")
BLOCKED = ("Just a moment", "Access Denied", "Access denied", "Attention Required")


def fetch_plain(url, dest):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read()
    if not body.startswith(b"%PDF"):
        return False, f"not a PDF ({len(body)} bytes)"
    dest.write_bytes(body)
    return True, f"{len(body)} bytes"


def fetch_download(url, dest):
    """The URL serves a PDF as an attachment; navigating to it starts a download."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(accept_downloads=True, user_agent=UA)
        page = ctx.new_page()
        try:
            with page.expect_download(timeout=120000) as info:
                try:
                    page.goto(url, timeout=90000)
                except Exception:
                    pass                      # "Download is starting" is the success path
            info.value.save_as(str(dest))
            return True, info.value.suggested_filename
        finally:
            b.close()


def fetch_firefox(url, dest):
    """Landing page passes in Firefox; the PDF link is in the markup, not a <a href>."""
    import re
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.firefox.launch(headless=True)
        ctx = b.new_context(accept_downloads=True, viewport={"width": 1400, "height": 1600})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="load", timeout=120000)
            time.sleep(8)
            if any(x in page.title() for x in BLOCKED):
                return False, f"blocked: {page.title()}"
            found = re.findall(r'["\'](/frontend/[^"\']+download[^"\']*)["\']', page.content())
            for href in dict.fromkeys(found):
                r = ctx.request.get("https://www.preprints.org" + href, timeout=90000)
                if "pdf" in r.headers.get("content-type", "") and len(r.body()) > 40000:
                    dest.write_bytes(r.body())
                    return True, f"{len(r.body())} bytes"
            return False, "no PDF link in page"
        finally:
            b.close()


def snapshot(pages):
    from playwright.sync_api import sync_playwright
    SNAPS.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 1600})
        for name, url in pages:
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                title = page.title()
                if any(x in title for x in BLOCKED):
                    results.append((name, False, f"blocked: {title[:40]}"))
                else:
                    page.emulate_media(media="screen")
                    page.pdf(path=str(SNAPS / f"{name}.pdf"), format="A4", print_background=True,
                             margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
                    results.append((name, True, title[:50]))
            except Exception as e:
                results.append((name, False, f"{type(e).__name__}: {e}"[:60]))
            page.close()
        b.close()
    return results


def extract_text(pdf):
    """Sidecar .txt next to each PDF. Grep-able evidence beats a binary."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(pdf)).pages)
    except Exception as e:
        return f"extract failed: {e}"
    pdf.with_suffix(".txt").write_text(text, encoding="utf-8")
    return f"{len(text)} chars"


ENGINES = {"plain": fetch_plain, "download": fetch_download, "firefox": fetch_firefox}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="fetch just this source by name")
    ap.add_argument("--skip-snapshots", action="store_true")
    args = ap.parse_args()

    SOURCES.mkdir(parents=True, exist_ok=True)
    failures = 0

    for name, url, engine, dest in DOCUMENTS:
        if args.only and args.only != name:
            continue
        print(f"[{engine:>8}] {name} … ", end="", flush=True)
        try:
            ok, detail = ENGINES[engine](url, dest)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"[:80]
        print(("ok (" if ok else "FAILED) ") + str(detail))
        failures += not ok
        if ok:
            note = extract_text(dest)
            if note:
                print(f"{'':>11} text: {note}")

    if not args.skip_snapshots and not args.only:
        print("\nSnapshots (HTML → PDF):")
        for name, ok, detail in snapshot(SNAPSHOTS):
            print(f"  {'ok      ' if ok else 'FAILED  '} {name}: {detail}")
            failures += not ok

    print(f"\n{failures} failure(s). Sources marked 'still to obtain' in sources/README.md "
          f"are not attempted here; they need an institutional session.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
