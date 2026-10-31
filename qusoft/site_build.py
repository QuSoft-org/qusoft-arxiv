"""Write the data files the website reads, and small web versions of the portraits.

site/data/papers.json   every paper, newest first
site/data/people.json   QuSoft people who appear on a paper: status, alumni years, portrait
site/data/stats.json    numbers per year and the co-authorship network
site/data/theses.json   PhD theses written at QuSoft, with covers (see scripts/theses.py)

Statistics are about the group, never per person: no rankings, no paper counts per author.
"""

import colorsys
import re
import unicodedata
from datetime import datetime

from collections import Counter

from PIL import Image, ImageOps

from .common import CONFIG, ROOT, find_portrait, load_json, open_portrait, is_alumnus, name_key, paper_date, path, save_json, tenure

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
        img = ImageOps.fit(open_portrait(src), (PORTRAIT_PX, PORTRAIT_PX), Image.LANCZOS)
        img.save(out, "WEBP", quality=78, method=6)
    return out.relative_to(SITE).as_posix()


def build(papers, people):
    papers = sorted(papers, key=lambda p: p["submitted"], reverse=True)

    summaries = load_json(ROOT / "data" / "summaries.json", {})  # plain-language abstracts
    topics = load_json(ROOT / "data" / "topics.json", {})  # research lines and topics, inferred from the papers
    tags = topics.get("papers", {})
    site_papers = []
    for p in papers:
        pdf, thumb = page_files(p)
        site_papers.append({
            "id": p["id"],
            "link": p["link"],
            "source": p.get("source", "arxiv"),
            "title": p["title"],
            "authors": [[a["name"], a["person"]] for a in p["authors"]],
            "date": p["submitted"][:10],
            "added": p.get("added", p["submitted"][:10]),
            "categories": p.get("categories", []),
            "abstract": p.get("abstract", ""),
            "line": tags.get(p["id"], {}).get("line"),
            "topics": tags.get(p["id"], {}).get("topics", []),
            "summary": ({"accessible": summaries[p["id"]]["accessible"], "simple": summaries[p["id"]]["simple"],
                         "checked": bool(summaries[p["id"]].get("checked_by"))} if p["id"] in summaries else None),
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

    stats = {
        "updated": datetime.now().isoformat(timespec="minutes"),
        "papers": len(papers),
        "people": len(on_papers),
        "alumni": sum(site_people[n]["alumni"] for n in site_people),
        "first_year": by_year[0]["year"] if by_year else None,
        "by_year": by_year,
    }

    save_json(SITE / "data" / "papers.json", site_papers)
    save_json(SITE / "data" / "people.json", site_people)

    # Research profiles for the People page: everyone in people.csv, also those without papers yet.
    # Shares of research lines and topics only, never counts.
    if topics:
        line_n, topic_n = {}, {}
        for p in papers:
            tag = tags.get(p["id"])
            if not tag or tag.get("line") in (None, "other"):
                continue
            for q in set(p["qusoft_authors"]):
                line_n.setdefault(q, Counter())[tag["line"]] += 1
                topic_n.setdefault(q, Counter()).update(tag.get("topics", []))
        profiles = []
        for name, info in sorted(people.items(), key=lambda kv: (kv[0].split()[-1].lower(), kv[0])):
            c = line_n.get(name, Counter())
            total = sum(c.values())
            profiles.append({
                "name": name, "role": info.get("role", ""), "alumni": is_alumnus(info), "years": tenure(info),
                "shares": {k: round(v / total, 3) for k, v in c.items()} if total else {},
                "topics": [t for t, _ in topic_n.get(name, Counter()).most_common()],
                "portrait": _web_portrait(name),
            })
        save_json(SITE / "data" / "profiles.json", profiles)
    save_json(SITE / "data" / "stats.json", stats)
    if topics:
        taxonomy = {"lines": [{"id": l["id"], "name": l["name"], "about": l["about"], "slot": l["slot"],
                               "topics": [{"id": t["id"], "name": t["name"], "short": t.get("short", t["name"]), "about": t["about"]} for t in l["topics"]]}
                              for l in topics["taxonomy"]["lines"]],
                    "method": topics.get("method", "")}
        save_json(SITE / "data" / "topics.json", taxonomy)
    n_theses = build_theses(people)
    print(f"Site data: {len(site_papers)} papers, {len(site_people)} people, {n_theses} theses")


# ---- PhD theses ----

def thesis_slug(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _luminance(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# Library cloth for theses without a cover image; all have AAA contrast with white text
CLOTH = ["#24453a", "#5a1f24", "#1f3550", "#4a3a1c", "#3b3350"]
LIGHT_INK, DARK_INK = (255, 255, 255), (34, 40, 46)


def back_cover(cover):
    """The colour of a thesis's back cover: the front's main colour, made dark (or light)
    enough that small text on it has AAA contrast. Returns (hex, 'light' | 'dark' ink)."""
    img = Image.open(cover).convert("RGB")
    img.thumbnail((60, 85))
    pal = img.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    counts = sorted(pal.getcolors(), reverse=True)
    palette = pal.getpalette()
    rgb = tuple(palette[counts[0][1] * 3: counts[0][1] * 3 + 3])
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    ink = DARK_INK if l > 0.62 else LIGHT_INK
    step = 0.02 if ink == DARK_INK else -0.02
    s = min(s, 0.75)  # tame neon covers a little; long text sits on this
    while True:
        out = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
        if _contrast(out, ink) >= 7 or not 0 < l < 1:
            break
        l = min(1, max(0, l + step))
    return "#%02x%02x%02x" % out, "dark" if ink == DARK_INK else "light"


def build_theses(people):
    theses = load_json(ROOT / "data" / "theses.json", [])
    out, plain = [], 0
    for t in theses:
        slug = thesis_slug(t["author"])
        cover = SITE / "covers" / f"{slug}.jpg"
        if not t.get("title") or not t.get("year"):
            continue
        if cover.exists():
            back, ink = back_cover(cover)
        else:  # no cover image: a plain cloth binding, the colours taken in turn
            back, ink = CLOTH[plain % len(CLOTH)], "light"
            plain += 1
        summary = t.get("summary") or {}
        out.append({
            "author": t["author"],
            "slug": slug,
            "title": t["title"],
            "year": t["year"],
            "before_qusoft": bool(t.get("before_qusoft")),  # from the groups that founded QuSoft in 2015
            "supervisors": t.get("supervisors", []),
            "abstract": t.get("abstract", ""),  # empty when the thesis has no English abstract
            "summary": {"accessible": summary["accessible"], "simple": summary["simple"],
                        "checked": bool(summary.get("checked_by"))} if summary.get("simple") else None,
            "link": t.get("page") or t["url"],
            # one PDF of the whole thesis; Leiden splits theses into chapters, so link its page instead
            "pdf": None if t.get("pdf_parts") else t.get("pdf_url"),
            "cover": cover.relative_to(SITE).as_posix() if cover.exists() else None,
            "back": back,
            "ink": ink,
            "portrait": _web_portrait(t["author"]),  # also for authors not in people.csv
        })
    out.sort(key=lambda t: (-t["year"], t["author"].split()[-1].lower()))
    save_json(SITE / "data" / "theses.json", out)
    return len(out)
