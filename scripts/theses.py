"""PhD theses written at QuSoft, for the thesis wall on the website.

data/theses.json is the list. Each thesis has the author, the repository page,
and what this script fills in from that page: title, year, supervisors, abstract
and the PDF. Plain-language abstracts ("summary": accessible and simple) are
written separately, like data/summaries.json for papers, and kept in the same file.

    python scripts/theses.py import               # add thesis links from the private spreadsheet
    python scripts/theses.py add "Name" URL       # add one thesis by hand
    python scripts/theses.py fetch                # fill in metadata, download PDFs, make covers
    python scripts/theses.py fetch --redo         # fetch everything again
    python scripts/theses.py covers --redo        # remake the cover images only
    python scripts/theses.py list                 # what is there, and what is missing

The cover is the first page of the PDF after the repository's front sheet. When
that page is a wraparound print cover, its right part (the front) is used.
"abstract_from": "thesis" marks an abstract copied from the thesis PDF, because the
repository's is shorter; fetch then leaves it alone.
"no_cover": true when the PDF has none (the site then shows a plain binding);
"cover_page" (1-based) and "cover_crop" ([left, right] or [left, top, right,
bottom], as fractions of the page) in data/theses.json override both guesses. Covers go to
site/covers/; PDFs are kept in cache/theses/ (not in git).
"""

import argparse
import html
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qusoft.common import CONFIG, ROOT, load_json, load_people, save_json  # noqa: E402
from qusoft.site_build import thesis_slug  # noqa: E402

THESES = ROOT / "data" / "theses.json"
PDF_DIR = ROOT / "cache" / "theses"
COVER_DIR = ROOT / "site" / "covers"
COVER_WIDTH = 480  # px; shown at about 200 px wide, sharp on high-density screens
UA = {"User-Agent": "QuSoft papers site (https://qusoft-org.github.io/qusoft-arxiv/)"}


slug = thesis_slug


def load():
    return load_json(THESES, [])


def save(theses):
    theses.sort(key=lambda t: (t.get("year") or 9999, t["author"]))
    save_json(THESES, theses)


# ---------------------------------------------------------------- import

def import_from_excel():
    """Thesis links of PhD students in the private spreadsheet."""
    import openpyxl
    people = set(load_people())
    wb = openpyxl.load_workbook(ROOT / CONFIG["database"]["excel_file"], read_only=True, data_only=True)
    ws = wb["QuSoft People Database"]
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() if h else "" for h in rows[1]]
    col = {h: i for i, h in enumerate(head)}
    theses = load()
    known = {t["author"] for t in theses}
    added = []
    for r in rows[2:]:
        name = (r[col["Name"]] or "").strip()
        link = (r[col["PhD thesis link"]] or "").strip() if isinstance(r[col["PhD thesis link"]], str) else ""
        if not name or not link.startswith("http") or name.startswith("http"):
            continue
        # Only theses written here: PhD students, and staff who did their PhD at QuSoft
        # (start date before the graduation date). Postdocs' earlier theses are left out.
        role = r[col["Role"]]
        if role == "Postdocs":
            continue
        if name in known:
            continue
        if people and name not in people:
            print(f"  not in people.csv, skipped: {name}")
            continue
        theses.append({"author": name, "url": link})
        known.add(name)
        added.append(name)
    save(theses)
    print(f"Added {len(added)}: {', '.join(added) or '-'}")


# ---------------------------------------------------------------- fetch

def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def abstract_text(box):
    """The abstract in a UvA-DARE field: all of it is in the page (the "Show more" button only
    unfolds it), with paragraphs split by <br> or <p>. The button's label is not part of it."""
    for b in box.find_all("button"):
        b.decompose()
    wrap = box.find(class_="text-wrapper") or box
    for br in wrap.find_all("br"):
        br.replace_with("\n\n")
    for p in wrap.find_all("p"):
        p.insert_after("\n\n")
    text = wrap.get_text()
    paras = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"\n\s*\n", text)]
    return "\n\n".join(x for x in paras if x)


def scrape(url):
    """Title, year, supervisors, abstract and PDF link from a repository page."""
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    if "application/pdf" in r.headers.get("content-type", ""):
        return {"pdf_url": r.url}, r.content
    soup = BeautifulSoup(r.text, "html.parser")
    # Some repositories escape entities twice ("&amp;amp;"), so unescape once more
    meta = lambda n: [html.unescape(m["content"]).strip() for m in soup.find_all("meta", attrs={"name": n}) if m.get("content")]
    info = {"page": r.url}
    # citation_* tags (UvA-DARE, Leiden, Pure), or eprints.* (the ILLC repository)
    title = meta("citation_title") or meta("eprints.title")
    if title:
        info["title"] = title[0]
    date = (meta("citation_publication_date") or meta("citation_date") or meta("eprints.date") or [""])[0]
    if re.match(r"\d{4}", date):
        info["year"] = int(date[:4])
    pdfs = meta("citation_pdf_url") or [u for u in meta("eprints.document_url") if u.lower().endswith(".pdf")]
    if pdfs:
        info["pdf_url"] = pdfs[0]
        if len(pdfs) > 1:
            info["pdf_parts"] = pdfs  # Leiden splits theses into chapters; the first holds the cover

    # UvA-DARE: labelled fields in definition-style blocks
    labels = {}
    for el in soup.find_all(string=re.compile(r"^\s*(Supervisors?|Co-supervisors?|Award date|Series|Abstract)\s*$")):
        label = el.strip()
        holder = el.parent
        box = holder.find_next_sibling() or holder.parent.find_next_sibling()
        if box is not None:
            labels[label] = box
    sup = []
    for key in ("Supervisor", "Supervisors", "Co-supervisor", "Co-supervisors"):
        if key in labels:
            items = labels[key].find_all(["li", "a", "span", "div"]) or [labels[key]]
            for it in items:
                t = _text(it)
                if t and t not in sup and len(t) < 60 and not it.find(["li", "a", "span", "div"]):
                    sup.append(t)
    if sup:
        info["supervisors"] = sup
    if "Award date" in labels:
        m = re.search(r"(19|20)\d\d", _text(labels["Award date"]))
        if m:
            info["year"] = int(m.group(0))
    if "Series" in labels:
        info["series"] = _text(labels["Series"])
    if "Abstract" in labels:
        info["abstract"] = abstract_text(labels["Abstract"])
    if "abstract" not in info:
        desc = meta("citation_abstract") or meta("eprints.abstract") or meta("DC.description") or meta("dc.description")
        if desc:
            info["abstract"] = desc[0]
    return info, None


def download_pdf(t, content=None):
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out = PDF_DIR / f"{slug(t['author'])}.pdf"
    if out.exists() and content is None:
        return out
    if content is None:
        url = (t.get("pdf_parts") or [t["pdf_url"]])[0]
        r = requests.get(url, headers=UA, timeout=180)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise RuntimeError(f"not a PDF: {url}")
        content = r.content
    out.write_bytes(content)
    return out


REPOSITORY_SHEET = re.compile(r"UvA-DARE|Digital Academic Repository|Downloaded from|hdl\.handle\.net/1887|Tilburg University", re.I)


def cover_page(doc, t):
    """0-based index of the cover: 'cover_page' if set, else the first page after the
    repository's own front sheet (UvA-DARE and Leiden add one)."""
    if t.get("cover_page"):
        return t["cover_page"] - 1
    first = doc[0].get_text()
    return 1 if len(doc) > 1 and REPOSITORY_SHEET.search(first) else 0


def make_cover(t, redo=False):
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    out = COVER_DIR / f"{slug(t['author'])}.jpg"
    if t.get("no_cover"):  # the PDF has no cover: the site shows a plain binding
        out.unlink(missing_ok=True)
        return None
    if out.exists() and not redo:
        return out
    src = PDF_DIR / f"{slug(t['author'])}.pdf"
    if not src.exists():
        return None
    with fitz.open(src) as doc:
        page = doc[cover_page(doc, t)]
        clip = page.rect
        # A wraparound print cover (back, spine, front side by side): keep the front.
        # "cover_crop" overrides the guess: [left, right] or [left, top, right, bottom],
        # as fractions of the page.
        crop = t.get("cover_crop")
        if crop is None and clip.width > 1.2 * clip.height:
            crop = [0.515, 1.0]
        if crop:
            l, top, r, b = crop if len(crop) == 4 else (crop[0], 0, crop[1], 1)
            w, h = clip.width, clip.height
            clip = fitz.Rect(clip.x0 + l * w, clip.y0 + top * h, clip.x0 + r * w, clip.y0 + b * h)
        zoom = COVER_WIDTH / clip.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out


def fetch(redo=False):
    theses = load()
    for t in theses:
        if t.get("title") and t.get("pdf_url") and not redo:
            make_cover(t)
            continue
        print(f"{t['author']}: {t['url']}")
        try:
            info, content = scrape(t["url"])
        except Exception as e:  # keep going; report at the end
            print(f"  failed: {e}")
            continue
        # Hand-made fields win over scraped ones. An abstract taken from the thesis itself
        # ("abstract_from": "thesis") is kept even with --redo: repositories often shorten it.
        for k, v in info.items():
            if k == "abstract" and t.get("abstract_from") == "thesis":
                continue
            if redo or not t.get(k):
                t[k] = v
        if t.get("pdf_url") or content:
            try:
                download_pdf(t, content)
                make_cover(t, redo=True)
            except Exception as e:
                print(f"  PDF failed: {e}")
        save(theses)
    listing()


def listing():
    theses = load()
    for t in theses:
        missing = [k for k in ("title", "year", "abstract") if not t.get(k)]
        missing += [k for k in ("accessible", "simple") if not (t.get("summary") or {}).get(k)]
        cover = (COVER_DIR / f"{slug(t['author'])}.jpg").exists()
        if not cover:
            missing.append("cover")
        print(f"{t.get('year', '????')}  {t['author']:<26} {t.get('title', '')[:60]:<60} "
              f"{'missing: ' + ', '.join(missing) if missing else ''}")
    print(f"{len(theses)} theses")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import")
    a = sub.add_parser("add")
    a.add_argument("author")
    a.add_argument("url")
    f = sub.add_parser("fetch")
    f.add_argument("--redo", action="store_true")
    c = sub.add_parser("covers")
    c.add_argument("--redo", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args()

    if args.cmd == "import":
        import_from_excel()
    elif args.cmd == "add":
        theses = load()
        if any(t["author"] == args.author for t in theses):
            sys.exit(f"{args.author} already has a thesis in the list")
        theses.append({"author": args.author, "url": args.url})
        save(theses)
        print(f"Added. Now run: python scripts/theses.py fetch")
    elif args.cmd == "fetch":
        fetch(args.redo)
    elif args.cmd == "covers":
        for t in load():
            make_cover(t, redo=args.redo)
        listing()
    elif args.cmd == "list":
        listing()


if __name__ == "__main__":
    main()
