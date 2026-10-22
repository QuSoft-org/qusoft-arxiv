#!/usr/bin/env python3
"""Papers on other preprint servers (IACR ePrint, SSRN, ChemRxiv) that need checking by hand.

The daily run finds papers there by QuSoft people, from their time at QuSoft, that aren't on
arXiv. When the PDF can't be fetched by a script, it can't check whether the paper names QuSoft,
so the paper waits here.

    python scripts/to_check.py                    # list the papers waiting
    python scripts/to_check.py --all              # also the ones already decided
    python scripts/to_check.py add ID [ID ...]    # it is a QuSoft paper: put it on the site
    python scripts/to_check.py reject ID [ID ...] # it isn't (no QuSoft affiliation, or a namesake)
    python scripts/to_check.py pdfs               # check PDFs saved in cache/other_pdfs/<ID>.pdf

A PDF saved as cache/other_pdfs/<ID>.pdf is checked automatically (same rule as for arXiv papers)
and is used for the annotated first page.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qusoft import other_servers as osv
from qusoft.common import load_json, load_papers, load_people, path, save_json, save_papers
from qusoft.firstpage import mentions_qusoft

ROOT = Path(__file__).resolve().parent.parent


def show(items):
    for c in sorted(items, key=lambda c: (bool(c.get("maybe_someone_else")), c["date"]), reverse=False):
        pdf = " (PDF saved)" if osv.local_pdf(c) else ""
        pdf += "; may be someone else with this name" if c.get("maybe_someone_else") and c["status"] == osv.TO_CHECK else ""
        print(f"{c['id']:24} {c['date']}  {osv.SOURCES[c['source']]:11}  {c['status']}{pdf}")
        print(f"    {c['title']}")
        print(f"    {', '.join(c['authors'][:8])}{' …' if len(c['authors']) > 8 else ''}")
        print(f"    QuSoft: {', '.join(c['people'])}    {c['link']}")


def rebuild():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update.py"), "--no-search"], check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", choices=["add", "reject", "pdfs"], help="what to do (default: list)")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true", help="list decided papers too")
    args = ap.parse_args()

    to_check = load_json(path("database", "to_check"), {})
    if not args.action:
        waiting = [c for c in to_check.values() if args.all or c["status"] == osv.TO_CHECK]
        show(waiting)
        print(f"\n{len(waiting)} papers{'' if args.all else ' to check'}. "
              "Add or reject them by ID; a PDF in cache/other_pdfs/<ID>.pdf is checked automatically (action 'pdfs').")
        return

    people, papers = load_people(), load_papers()
    changed = False
    if args.action == "pdfs":
        for c in to_check.values():
            if c["status"] in (osv.TO_CHECK, osv.REJECTED) and osv.local_pdf(c):
                paper = osv.judge(c, papers, people, mentions_qusoft)
                print(f"{c['status']:24} {c['id']:22} {c['title'][:60]}")
                changed |= bool(paper)
    for i in args.ids:
        c = to_check.get(i)
        if not c:
            sys.exit(f"Not on the list: {i}")
        if args.action == "add" and not any(p["id"] == i for p in papers):
            papers.append(osv.make_paper(c, people))
            c["status"], changed = osv.ADDED, True
            print(f"Added {i}: {c['title']}")
        elif args.action == "reject":
            if c["status"] == osv.ADDED:
                papers[:] = [p for p in papers if p["id"] != i]
                changed = True
            c["status"] = osv.REJECTED
            print(f"Rejected {i}: {c['title']}")
    save_json(path("database", "to_check"), to_check)
    if changed:
        save_papers(papers)
        rebuild()


if __name__ == "__main__":
    main()
