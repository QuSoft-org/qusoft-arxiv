#!/usr/bin/env python3
"""Combine annotated first pages into one PDF booklet (e.g. all papers of a year).

The website's Print page does the same for a hand-picked set of papers.

    python scripts/make_booklet.py --year 2025
    python scripts/make_booklet.py --month 2025-10
    python scripts/make_booklet.py --start-date 2025-09-01 --authors "Stacey Jeffery"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz

from qusoft.common import filter_papers, load_papers, path
from qusoft.site_build import page_files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int)
    ap.add_argument("--month", help="YYYY-MM")
    ap.add_argument("--start-date", help="YYYY-MM-DD")
    ap.add_argument("--end-date", help="YYYY-MM-DD")
    ap.add_argument("--authors", nargs="+")
    ap.add_argument("--output", help="default: output/qusoft_firstpages_<filter>.pdf")
    args = ap.parse_args()

    papers = filter_papers(load_papers(), args.year, args.month, args.start_date, args.end_date, args.authors)
    label = str(args.year or args.month or args.start_date or "all")
    out = Path(args.output) if args.output else path("paths", "output_dir") / f"qusoft_firstpages_{label}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    booklet = fitz.open()
    missing = []
    for p in sorted(papers, key=lambda p: p["submitted"]):
        pdf, _ = page_files(p)
        if pdf.exists():
            with fitz.open(pdf) as page:
                booklet.insert_pdf(page)
        else:
            missing.append(p["id"])
    if not booklet.page_count:
        sys.exit("No first pages match these filters.")
    booklet.save(out, garbage=4, deflate=True)
    print(f"Saved {booklet.page_count} pages to {out}")
    if missing:
        print(f"No first page yet for {len(missing)} papers (run scripts/update.py --no-search): {missing}")


if __name__ == "__main__":
    main()
