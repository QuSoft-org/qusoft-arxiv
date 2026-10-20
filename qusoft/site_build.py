"""Write the data files the website reads, and small web versions of the portraits.

site/data/papers.json   every paper, newest first
site/data/people.json   QuSoft people who appear on a paper: status, alumni years, portrait
site/data/stats.json    numbers per year and the co-authorship network

Statistics are about the group, never per person: no rankings, no paper counts per author.
"""

from collections import Counter
from datetime import datetime
from itertools import combinations

from PIL import Image, ImageOps

from .common import CONFIG, ROOT, find_portrait, is_alumnus, name_key, paper_date, path, save_json, tenure

SITE = path("paths", "site_dir")
PORTRAIT_PX = 192


def page_files(paper):
    return SITE / "firstpages" / f"{paper['id']}.pdf", SITE / "thumbs" / f"{paper['id']}.webp"


def _web_portrait(person):
    src = find_portrait(person)
    if not src:
        return None
    slug = name_key(person).replace(" ", "-")
    out = SITE / "portraits" / f"{slug}.webp"
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        img = ImageOps.fit(Image.open(src).convert("RGB"), (PORTRAIT_PX, PORTRAIT_PX), Image.LANCZOS)
        img.save(out, "WEBP", quality=78, method=6)
    return out.relative_to(SITE).as_posix()


def build(papers, people):
    papers = sorted(papers, key=lambda p: p["submitted"], reverse=True)

    site_papers = []
    for p in papers:
        pdf, thumb = page_files(p)
        site_papers.append({
            "id": p["id"],
            "link": p["link"],
            "title": p["title"],
            "authors": [[a["name"], a["person"]] for a in p["authors"]],
            "date": p["submitted"][:10],
            "added": p.get("added", p["submitted"][:10]),
            "categories": p.get("categories", []),
            "abstract": p.get("abstract", ""),
            "page": pdf.exists() and thumb.exists(),
        })

    on_papers = {name for p in papers for name in p["qusoft_authors"]}
    site_people = {}
    for name in sorted(on_papers):
        info = people.get(name, {})
        site_people[name] = {
            "role": info.get("role", ""),
            "alumni": is_alumnus(info),
            "years": tenure(info),
            "portrait": _web_portrait(name),
        }

    # Group-level numbers per year.
    years = {}
    for p in papers:
        y = paper_date(p).year
        row = years.setdefault(y, {"year": y, "papers": 0, "contributors": set(), "together": 0, "with_alumni": 0})
        q = p["qusoft_authors"]
        row["papers"] += 1
        row["contributors"].update(q)
        row["together"] += len(q) >= 2
        row["with_alumni"] += any(is_alumnus(people.get(n, {})) for n in q)
    by_year = [{**r, "contributors": len(r["contributors"])} for _, r in sorted(years.items())]

    # Co-authorship network: who has written with whom. Edges only, no per-person totals.
    pairs = Counter()
    for p in papers:
        for a, b in combinations(sorted(set(p["qusoft_authors"])), 2):
            pairs[(a, b)] += 1
    edges = [[a, b, n] for (a, b), n in sorted(pairs.items())]

    stats = {
        "updated": datetime.now().isoformat(timespec="minutes"),
        "papers": len(papers),
        "people": len(on_papers),
        "alumni": sum(site_people[n]["alumni"] for n in site_people),
        "first_year": by_year[0]["year"] if by_year else None,
        "by_year": by_year,
        "edges": edges,
    }

    save_json(SITE / "data" / "papers.json", site_papers)
    save_json(SITE / "data" / "people.json", site_people)
    save_json(SITE / "data" / "stats.json", stats)
    print(f"Site data: {len(site_papers)} papers, {len(site_people)} people, {len(edges)} collaborations")
