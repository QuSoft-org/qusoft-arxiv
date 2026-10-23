#!/usr/bin/env python3
"""QuSoft talks at QIP, QCrypt and TQC (internal, for the management team; never published).

Uses QuantumDB (https://quantumdb.iaqi.org), the IAQI's database of these conferences,
through its open data on GitHub (https://github.com/IAQI/QuantumDB, folder data/).
QuantumDB is still being filled in, so some years, talks and committees may be missing.

    python scripts/conference_talks.py     # -> output/conference_talks_<date>.xlsx

A talk counts for QuSoft when one of its authors is a QuSoft person who was at QuSoft that
year (by name, with the membership dates from the spreadsheet or people.csv). Talks are
linked to papers on the site by arXiv id or title, which also gives their research line.
Plenary, keynote and award talks are added to internal/highlights.yaml as suggestions.
"""

import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl import Workbook

from internal_report import _sheet, membership
from qusoft.common import PersonMatcher, base_id, is_alumnus, load_papers, load_people
from qusoft.other_servers import same_title

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "cache" / "quantumdb"
FIRST_YEAR = 2015

# Talk types in QuantumDB, grouped from most to least prominent.
KINDS = {"plenary": "Plenary", "plenary_long": "Plenary", "plenary_short": "Plenary", "keynote": "Keynote",
         "invited": "Invited", "tutorial": "Tutorial", "regular": "Contributed", "industry": "Contributed",
         "poster": "Poster"}
ORDER = ["Keynote", "Plenary", "Invited", "Tutorial", "Contributed", "Poster"]
csv.field_size_limit(10_000_000)


def update_data():
    """Fetch or refresh the data folder of the QuantumDB repository (a light, partial clone)."""
    if not (REPO / ".git").exists():
        REPO.parent.mkdir(exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
                        "https://github.com/IAQI/QuantumDB.git", str(REPO)], check=True)
        subprocess.run(["git", "-C", str(REPO), "sparse-checkout", "set", "data"], check=True)
    else:
        subprocess.run(["git", "-C", str(REPO), "pull", "-q", "--depth", "1"], check=False)


def rows(kind):
    for f in sorted((REPO / "data" / "conferences").glob(f"*/{kind}.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                yield f.parent.name, r


def split(cell):
    return [x.strip() for x in (cell or "").split(";") if x.strip()]


def main():
    update_data()
    people = load_people()
    match = PersonMatcher(people)
    spans, _ = membership(people)
    papers = load_papers()
    by_arxiv = {base_id(p["id"]): p for p in papers}
    topics = json.loads((ROOT / "data" / "topics.json").read_text()) if (ROOT / "data" / "topics.json").exists() else {}
    line_name = {l["id"]: l["name"] for l in topics.get("taxonomy", {}).get("lines", [])}
    line_of = {pid: line_name.get(t["line"], "") for pid, t in topics.get("papers", {}).items()}

    def at_qusoft(person, year):
        start, end = spans.get(person, (None, None))
        if start and year < start.year:
            return False
        return not (end and year > end.year and is_alumnus(people[person]))

    talks = []
    for kind in ("talks", "proceedings", "workshop", "posters"):
        for folder, r in rows(kind):
            try:
                year = int(r.get("year") or folder.split("_")[-1])
            except ValueError:
                continue
            if year < FIRST_YEAR:
                continue
            authors = split(r.get("authors")) or split(r.get("speakers") or r.get("speaker"))
            who = [p for p in dict.fromkeys(filter(None, map(match, authors))) if at_qusoft(p, year)]
            if not who:
                continue
            ptype = (r.get("paper_type") or "regular").strip().lower()
            kind_name = KINDS.get(ptype, "Contributed")
            if kind == "proceedings" and kind_name == "Contributed":
                kind_name = "Contributed"
            paper = next((by_arxiv[base_id(a)] for a in split(r.get("arxiv_ids")) if base_id(a) in by_arxiv), None)
            if not paper:
                paper = next((p for p in papers if same_title(p["title"], r.get("title", ""))), None)
            talks.append({
                "year": year, "venue": (r.get("venue") or folder.split("_")[0]).upper(), "kind": kind_name,
                "type": ptype, "title": " ".join((r.get("title") or "").split()), "award": (r.get("award") or "").strip(),
                "qusoft": who, "speakers": split(r.get("speakers")), "paper": paper["id"] if paper else "",
                "link": paper["link"] if paper else "", "line": line_of.get(paper["id"], "") if paper else "",
                "track": "proceedings" if kind == "proceedings" else ("poster" if kind == "posters" else "talk"),
            })
    # The same paper can appear twice (e.g. TQC proceedings and a merged QIP talk): keep both, they are separate talks.
    talks.sort(key=lambda t: (-t["year"], t["venue"], ORDER.index(t["kind"]), t["title"]))

    committees = []
    for folder, r in rows("committees"):
        try:
            year = int(r.get("year") or folder.split("_")[-1])
        except ValueError:
            continue
        name = r.get("name") or r.get("full_name") or r.get("member") or ""
        p = match(name) if name else None
        if year >= FIRST_YEAR and p and at_qusoft(p, year):
            committees.append([year, (r.get("venue") or folder.split("_")[0]).upper(),
                               r.get("committee_type") or r.get("committee") or "", r.get("position") or "", p])
    committees.sort(key=lambda c: (-c[0], c[1], c[2], c[4]))

    # Per year and venue: talks of each kind.
    years = sorted({t["year"] for t in talks}, reverse=True)
    per_year = []
    for y in years:
        for v in ("QIP", "QCRYPT", "TQC"):
            c = Counter(t["kind"] for t in talks if t["year"] == y and t["venue"] == v)
            if c:
                per_year.append([y, v, *[c[k] for k in ORDER], sum(1 for t in talks if t["year"] == y and t["venue"] == v and t["award"])])
    per_line = []
    for line in sorted({t["line"] for t in talks if t["line"]}):
        c = Counter(t["kind"] for t in talks if t["line"] == line)
        per_line.append([line, *[c[k] for k in ORDER]])
    unlinked = Counter(t["kind"] for t in talks if not t["line"])
    per_line.append(["(talk not linked to a paper on the site)", *[unlinked[k] for k in ORDER]])

    wb = Workbook()
    wb.remove(wb.active)
    note = (f"QuSoft talks at QIP, QCrypt and TQC since {FIRST_YEAR}, from QuantumDB (quantumdb.iaqi.org, data as of "
            f"{date.today()}). QuantumDB is still being completed: missing years or talks are gaps in its data, not "
            "necessarily in QuSoft's record. A talk counts when a QuSoft author was at QuSoft that year.")
    _sheet(wb, "Per year", ["Year", "Conference", *ORDER, "With award"], per_year, [8, 12, 10, 10, 10, 10, 12, 10, 11], note)
    _sheet(wb, "Per research line", ["Research line (inferred)", *ORDER], per_line, [44, 10, 10, 10, 10, 12, 10],
           "Research line of the paper behind the talk (data/topics.json), where the talk could be linked to a paper on the site.")
    _sheet(wb, "Talks", ["Year", "Conference", "Kind", "Award", "Title", "QuSoft people", "Speakers", "Research line", "Paper"],
           [[t["year"], t["venue"], t["kind"], t["award"], t["title"], ", ".join(t["qusoft"]), ", ".join(t["speakers"]),
             t["line"], t["link"]] for t in talks],
           [7, 10, 11, 18, 70, 34, 30, 30, 34])
    _sheet(wb, "Committees", ["Year", "Conference", "Committee", "Position", "QuSoft person"], committees, [7, 10, 22, 14, 26],
           "Programme and steering committee memberships of QuSoft people while at QuSoft.")
    out = ROOT / "output" / f"conference_talks_{date.today()}.xlsx"
    out.parent.mkdir(exist_ok=True)
    wb.save(out)

    # Suggest the most prominent talks as highlights for the MT to curate.
    hl = ROOT / "internal" / "highlights.yaml"
    existing = hl.read_text() if hl.exists() else ""
    new = []
    for t in talks:
        if t["kind"] in ("Plenary", "Keynote") or t["award"]:
            key = t["paper"] or f"{t['venue']}{t['year']}: {t['title']}"
            if key in existing:
                continue
            why = f"{t['kind']} talk at {t['venue']} {t['year']}" + (f"; {t['award']}" if t["award"] else "")
            new += [f"- id: {json.dumps(key)}", f"  title: {json.dumps(t['title'])}", f"  line: {json.dumps(t['line'])}",
                    f"  why: {json.dumps(why)}", "  status: suggested", ""]
    if new:
        hl.parent.mkdir(exist_ok=True)
        hl.write_text(existing.rstrip() + "\n\n" + "\n".join(new))

    print(f"Wrote {out}: {len(talks)} QuSoft talks, {len(committees)} committee seats")
    tot = Counter(t["kind"] for t in talks)
    print("  " + ", ".join(f"{k}: {tot[k]}" for k in ORDER))
    print(f"  {sum(1 for t in talks if t['award'])} with an award; {len(new) // 6} highlight suggestions added")


if __name__ == "__main__":
    main()
