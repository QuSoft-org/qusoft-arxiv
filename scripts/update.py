#!/usr/bin/env python3
"""Daily update: find new QuSoft papers on arXiv, make their first pages, rebuild the site data.

    python scripts/update.py                         # what the daily GitHub Action runs
    python scripts/update.py --authors "Yfke Dulek"  # search only these people
    python scripts/update.py --no-search             # only fill in missing first pages + site data
    python scripts/update.py --redo-pages            # remake every first page (e.g. after a layout change)

A paper counts when it names QuSoft: anywhere on the first page, or on a later page as an
affiliation, supporter or funder (maths papers often give addresses after the references).
Papers checked and found without it are remembered in data/rejected_ids.json.
"""

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qusoft import site_build
from qusoft.arxiv_search import Searcher, fetch_by_ids, make_entry
from qusoft.common import (PersonMatcher, base_id, find_portrait, load_json, load_papers, load_people,
                           path, save_json, save_papers, tenure)
from qusoft.firstpage import make_first_page, mentions_qusoft, save_first_page

PENDING = "__pending__"  # key in search_state for papers whose PDF couldn't be fetched yet


class PdfSource:
    """Full arXiv PDFs: from the local cache when there is one, otherwise downloaded to a temp folder."""

    def __init__(self):
        self.cache = path("paths", "local_pdf_cache")
        self.tmp = tempfile.TemporaryDirectory()

    def get(self, arxiv_id, result=None):
        cached = self.cache / f"{arxiv_id}.pdf"
        if cached.exists():
            return cached
        target = Path(self.tmp.name) / f"{arxiv_id}.pdf"
        if target.exists():
            return target
        try:
            result = result or fetch_by_ids([arxiv_id])[0]
            result.download_pdf(dirpath=self.tmp.name, filename=target.name)
            return target
        except Exception as e:
            print(f"    could not download {arxiv_id}: {e}")
            return None

    def done(self, path_):
        """Delete a downloaded PDF once used (keeps CI disk use small)."""
        if path_ and Path(self.tmp.name) in Path(path_).parents:
            Path(path_).unlink(missing_ok=True)


def make_page(paper, pdfs, people, result=None):
    pdf_out, thumb_out = site_build.page_files(paper)
    src = pdfs.get(paper["id"], result)
    if not src:
        return False
    try:
        save_first_page(make_first_page(paper, src, people), pdf_out, thumb_out)
        return True
    except Exception as e:
        print(f"    could not make first page for {paper['id']}: {e}")
        return False
    finally:
        pdfs.done(src)


def page_people(paper, people):
    """What a first page shows about its QuSoft authors. When this changes, the page is remade."""
    shown = []
    for name in paper["qusoft_authors"]:
        info = people.get(name, {})
        portrait = find_portrait(name)
        shown.append([name, info.get("role"), info.get("status"), tenure(info),
                      portrait.name if portrait else None, portrait.stat().st_size if portrait else None])
    return shown


def refresh_authors(papers, people):
    """Match every paper's authors to people.csv again, so people added later are linked
    to their older papers. Returns the papers whose first page shows different people now."""
    match = PersonMatcher(people)
    stale = []
    for p in papers:
        qusoft_authors = []
        for a in p["authors"]:
            a["person"] = match(a["name"])
            if a["person"] and a["person"] not in qusoft_authors:
                qusoft_authors.append(a["person"])
        p["qusoft_authors"] = qusoft_authors
        shown = page_people(p, people)
        if "page_people" in p and p["page_people"] != shown:
            stale.append(p)
        p["page_people"] = shown
    return stale


def search(people, papers, state, rejected, pdfs, only_authors):
    """Search arXiv and add new QuSoft papers to `papers`. Returns the new papers."""
    match = PersonMatcher(people)
    known = {base_id(p["id"]) for p in papers} | set(rejected)
    names = only_authors or list(people)
    candidates = {}
    searcher = Searcher()

    for i, name in enumerate(names, 1):
        person_state = state.setdefault(name, {})
        found = searcher.search_person(name, person_state) if name in people else None
        if found is None:
            continue
        new = [r for r in found if base_id(r.entry_id.split("/")[-1]) not in known | set(candidates)]
        print(f"[{i}/{len(names)}] {name}: {len(found)} found, {len(new)} new")
        for r in new:
            candidates[base_id(r.entry_id.split("/")[-1])] = r

    # Papers whose PDF failed last time get another try.
    retry = [i for i in state.get(PENDING, []) if i not in known and i not in candidates]
    if retry:
        for r in fetch_by_ids(retry):
            candidates[base_id(r.entry_id.split("/")[-1])] = r

    added, pending = [], []
    for bid, result in candidates.items():
        entry = make_entry(result, match)
        src = pdfs.get(entry["id"], result)
        if not src:
            pending.append(bid)
            continue
        if not mentions_qusoft(src):
            rejected.append(bid)
            pdfs.done(src)
            continue
        entry["added"] = date.today().isoformat()
        papers.append(entry)
        added.append(entry)
        print(f"  + {entry['id']} {entry['title'][:70]}")
        make_page(entry, pdfs, people, result)
    state[PENDING] = pending
    return added


def recheck_rejected(people, papers, rejected, pdfs):
    """Check earlier rejected papers again (after the QuSoft rule changed). Uses cached PDFs where present."""
    match = PersonMatcher(people)
    found = []
    for i, bid in enumerate(list(rejected), 1):
        cached = sorted(pdfs.cache.glob(f"{bid}v*.pdf"))
        src = cached[-1] if cached else pdfs.get(bid)
        if src and mentions_qusoft(src):
            found.append(bid)
        if i % 200 == 0:
            print(f"  checked {i}/{len(rejected)}")
    added = []
    for result in fetch_by_ids(found) if found else []:
        entry = make_entry(result, match)
        entry["added"] = date.today().isoformat()
        papers.append(entry)
        added.append(entry)
        rejected.remove(base_id(entry["id"]))
        print(f"  + {entry['id']} {entry['title'][:70]}")
    return added


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authors", nargs="+", help="search only these people (names as in people.csv)")
    ap.add_argument("--no-search", action="store_true", help="skip arXiv search")
    ap.add_argument("--redo-pages", action="store_true", help="remake all first pages")
    ap.add_argument("--recheck-rejected", action="store_true", help="check rejected papers again (after a rule change)")
    args = ap.parse_args()

    people = load_people()
    papers = load_papers()
    state = load_json(path("database", "search_state"), {})
    rejected = load_json(path("database", "rejected_ids"), [])
    pdfs = PdfSource()

    if args.authors:
        unknown = [a for a in args.authors if a not in people]
        if unknown:
            sys.exit(f"Not in people.csv: {', '.join(unknown)}")

    added = []
    if not args.no_search:
        try:
            added = search(people, papers, state, rejected, pdfs, args.authors)
        finally:
            save_papers(papers)
            save_json(path("database", "search_state"), state)
            save_json(path("database", "rejected_ids"), sorted(set(rejected)))

    if args.recheck_rejected:
        print(f"Checking {len(rejected)} rejected papers again")
        added += recheck_rejected(people, papers, rejected, pdfs)
        save_papers(papers)
        save_json(path("database", "rejected_ids"), sorted(set(rejected)))

    # People added to or changed in people.csv, and new portraits, show up on older papers too.
    stale = {p["id"] for p in refresh_authors(papers, people)}
    save_papers(papers)

    # Make any first pages that are missing or out of date (or all of them with --redo-pages).
    missing = [p for p in papers if args.redo_pages or p["id"] in stale
               or not all(f.exists() for f in site_build.page_files(p))]
    if missing:
        print(f"Making {len(missing)} first pages")
        for i, p in enumerate(missing, 1):
            ok = make_page(p, pdfs, people)
            print(f"  [{i}/{len(missing)}] {p['id']} {'ok' if ok else 'FAILED'}")

    site_build.build(papers, people)
    print(f"Done: {len(added)} new papers, {len(papers)} in total")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {len(added)} new QuSoft papers\n\n")
            f.writelines(f"- [{p['title']}]({p['link']})\n" for p in added)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"new_papers={len(added)}\n")


if __name__ == "__main__":
    main()
