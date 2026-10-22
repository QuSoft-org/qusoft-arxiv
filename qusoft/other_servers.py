"""QuSoft papers on preprint servers other than arXiv.

- ECCC (complexity): listing pages per year; PDFs are open, so papers are checked like arXiv ones.
- IACR ePrint (cryptography): the OAI-PMH metadata feed. ePrint asks crawlers not to fetch PDFs.
- SSRN (law, policy) and ChemRxiv (chemistry): found through Crossref. Both block scripts.

Papers by QuSoft people, from their time at QuSoft, that aren't on arXiv go on a list to check
(data/to_check.json). A paper is added to the site when its PDF names QuSoft (same rule as for
arXiv), or when someone confirms it with scripts/to_check.py. PDFs that scripts can't fetch can be
downloaded by hand into cache/other_pdfs/<id>.pdf.
"""

import difflib
import html
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests

from .common import CONFIG, ROOT, PersonMatcher

UA = {"User-Agent": "qusoft-arxiv (https://github.com/cschaffner/qusoft-arxiv)"}
OTHER_PDFS = ROOT / "cache" / "other_pdfs"
SOURCES = {"eccc": "ECCC", "eprint": "IACR ePrint", "ssrn": "SSRN", "chemrxiv": "ChemRxiv"}
CROSSREF_PREFIXES = {"10.2139": "ssrn", "10.26434": "chemrxiv"}
FIRST_YEAR = 2015


def _get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60, **kw)
            if r.status_code in (429, 503):
                time.sleep(30 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == 3:
                print(f"    could not fetch {url}: {e}")
                return None
            time.sleep(10)
    return None


def _clean(text):
    text = html.unescape(text or "")  # Crossref sometimes escapes the HTML twice
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in text if not unicodedata.combining(c)).lower()).strip()


def same_title(a, b):
    a, b = fold(a), fold(b)
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() > 0.92


# ---------------------------------------------------------------------------
# Sources. Each returns candidates: {id, source, title, authors, date, link, pdf, abstract}
# ---------------------------------------------------------------------------

def eccc(since_year):
    out = []
    for year in range(since_year, date.today().year + 1):
        r = _get(f"https://eccc.weizmann.ac.il/year/{year}/")
        time.sleep(3)
        if not r:
            continue
        for box in r.text.split('<div id="box">')[1:]:
            num = re.search(r"/report/(\d{4})/(\d+)", box)
            title = re.search(r"<h4>(.*?)</h4>", box, re.S)
            when = re.search(r"\|\s*(\d+)\w*\s+(\w+)\s+(\d{4})", box)
            small = re.search(r"</u></b><br\s*/?>(.*?)</small>", box, re.S)
            if not (num and title and small):
                continue
            y, n = num.groups()
            try:
                day = date(int(when.group(3)), _MONTHS[when.group(2)[:3].lower()], int(when.group(1))) if when else date(int(y), 1, 1)
            except (KeyError, ValueError):
                day = date(int(y), 1, 1)
            authors = [a for a in (_clean(x) for x in small.group(1).split(",")) if a]
            abstract = re.search(r"<p>(.*?)</p>", box, re.S)
            out.append({"id": f"eccc-{y}-{int(n)}", "source": "eccc", "title": _clean(title.group(1)), "authors": authors,
                        "date": day.isoformat(), "link": f"https://eccc.weizmann.ac.il/report/{y}/{int(n):03d}",
                        "pdf": f"https://eccc.weizmann.ac.il/report/{y}/{int(n):03d}/download/",
                        "abstract": _clean(abstract.group(1)) if abstract else ""})
    return out


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
OAI = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def eprint(since):
    """Records added or changed since `since` (a date), from ePrint's OAI-PMH feed."""
    out = []
    url = f"https://eprint.iacr.org/oai?verb=ListRecords&metadataPrefix=oai_dc&from={since:%Y-%m-%d}"
    while url:
        r = _get(url)
        time.sleep(3)
        if not r:
            break
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            break
        for rec in root.iter(f"{OAI}record"):
            md = rec.find(f"{OAI}metadata")
            if md is None:
                continue
            ident = next((e.text for e in md.iter(f"{DC}identifier") if e.text and "eprint.iacr.org/" in e.text), None)
            m = re.search(r"(\d{4})/(\d+)", ident or "")
            if not m:
                continue
            dates = sorted(e.text[:10] for e in md.iter(f"{DC}date") if e.text)
            out.append({"id": f"eprint-{m.group(1)}-{int(m.group(2))}", "source": "eprint",
                        "title": " ".join((md.findtext(f".//{DC}title") or "").split()),
                        "authors": [" ".join(e.text.split()) for e in md.iter(f"{DC}creator") if e.text],
                        "date": dates[0] if dates else f"{m.group(1)}-01-01",
                        "link": f"https://eprint.iacr.org/{m.group(1)}/{int(m.group(2))}",
                        "pdf": f"https://eprint.iacr.org/{m.group(1)}/{int(m.group(2))}.pdf",
                        "abstract": " ".join((md.findtext(f".//{DC}description") or "").split())})
        token = root.find(f".//{OAI}resumptionToken")
        url = (f"https://eprint.iacr.org/oai?verb=ListRecords&resumptionToken={requests.utils.quote(token.text)}"
               if token is not None and token.text else None)
    return out


def crossref(people, since):
    """SSRN and ChemRxiv preprints with a QuSoft person among the authors, posted since `since`."""
    out, seen = [], set()
    for name, info in people.items():
        if info.get("role") == "Support Team":
            continue
        r = _get("https://api.crossref.org/works", params={
            "filter": f"type:posted-content,from-posted-date:{since:%Y-%m-%d}",
            "query.author": name, "rows": 100,
            "select": "DOI,title,author,posted,abstract,resource,URL"})
        time.sleep(1.5)
        for w in (r.json()["message"]["items"] if r else []):
            prefix = w["DOI"].split("/")[0]
            source = CROSSREF_PREFIXES.get(prefix)
            if not source or w["DOI"] in seen:
                continue
            seen.add(w["DOI"])
            authors = [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in w.get("author", [])]
            parts = (w.get("posted") or {}).get("date-parts", [[None]])[0]
            day = date(parts[0], (parts[1:2] or [1])[0], (parts[2:3] or [1])[0]) if parts and parts[0] else date.today()
            suffix = re.sub(r"[^A-Za-z0-9]+", "-", w["DOI"].split("/", 1)[1]).strip("-")
            suffix = re.sub(r"-v\d+$", "", suffix.replace("ssrn-", "").replace("chemrxiv-", ""))
            out.append({"id": f"{source}-{suffix}", "source": source, "title": _clean((w.get("title") or [""])[0]),
                        "authors": authors, "date": day.isoformat(), "link": f"https://doi.org/{w['DOI']}",
                        "pdf": None, "abstract": _clean(w.get("abstract", ""))})
    return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def at_qusoft(info, day, first_paper=None):
    """Was this person at QuSoft on this day? Without a start year in people.csv, the year of
    their first QuSoft paper on arXiv stands in (or the last two years, without any papers)."""
    start, end = info.get("start_year"), info.get("end_year")
    start = start or first_paper or date.today().year - 2
    return day.year >= start and (not end or day.year <= end)


STOPWORDS = set("""about above after again against their there these those which while would could should within
    without between through under using based paper study shows results approach method methods model models analysis
    where whose other these such than then them they this that with from into over have been being were what when
    some many each very only both same""".split())


def words(text):
    return {w for w in fold(text).split() if len(w) > 4 and w not in STOPWORDS}


def history(papers):
    """Per QuSoft person: year of their first QuSoft paper, their co-authors, and the words they use."""
    first, coauthors, vocab = {}, {}, {}
    for p in papers:
        y = int(p["submitted"][:4])
        for q in p["qusoft_authors"]:
            first[q] = min(first.get(q, y), y)
            coauthors.setdefault(q, set()).update(fold(a["name"]) for a in p["authors"])
            vocab.setdefault(q, set()).update(words(p["title"] + " " + p.get("abstract", "")))
    return first, coauthors, vocab


def qusoft_people(cand, people, match, first):
    """QuSoft people among the authors who were at QuSoft when the paper appeared."""
    day = date.fromisoformat(cand["date"])
    found = []
    for a in cand["authors"]:
        p = match(a)
        if p and p not in found and at_qusoft(people[p], day, first.get(p)):
            found.append(p)
    return found


def maybe_someone_else(cand, who, coauthors, vocab):
    """A hint, not a decision: one QuSoft name, none of their known co-authors, nothing quantum,
    and few of the words the person uses in their QuSoft papers."""
    text = cand["title"] + " " + cand.get("abstract", "")
    if len(who) > 1 or "quantum" in fold(text):
        return False
    names = {fold(a) for a in cand["authors"]}
    if any(names & (coauthors.get(p, set()) - {fold(p)}) for p in who):
        return False
    w = words(text)
    return not any(len(w & vocab.get(p, set())) >= 0.3 * max(1, len(w)) for p in who)


def on_arxiv(title, authors):
    """Is there an arXiv paper with this title? Two searches: exact phrase, then words plus an author."""
    words = [w for w in fold(title).split() if len(w) > 3][:8]
    last = fold(authors[0]).split()[-1] if authors else ""
    queries = [f'ti:"{fold(title)}"'] + ([f"ti:({' AND '.join(words)}) AND au:{last}"] if words and last else [])
    for q in queries:
        r = _get("http://export.arxiv.org/api/query", params={"search_query": q, "max_results": 10})
        time.sleep(CONFIG["search"]["rate_limit_delay"])
        if r and any(same_title(title, t) for t in re.findall(r"<entry>.*?<title>(.*?)</title>", r.text, re.S)):
            return True
    return False


def local_pdf(item):
    f = OTHER_PDFS / f"{item['id']}.pdf"
    return f if f.exists() else None


def fetch_pdf(item, folder=OTHER_PDFS):
    """ECCC PDFs can be downloaded; the other servers don't allow scripts to."""
    if local_pdf(item):
        return local_pdf(item)
    if item["source"] != "eccc" or not item.get("pdf"):
        return None
    r = _get(item["pdf"])
    time.sleep(3)
    if r and r.content[:4] == b"%PDF":
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / f"{item['id']}.pdf"
        f.write_bytes(r.content)
        return f
    return None


def make_paper(item, people):
    match = PersonMatcher(people)
    authors = [{"name": a, "person": match(a)} for a in item["authors"]]
    return {
        "id": item["id"], "source": item["source"], "link": item["link"], "title": item["title"],
        "authors": authors, "qusoft_authors": list(dict.fromkeys(a["person"] for a in authors if a["person"])),
        "submitted": f"{item['date']}T00:00:00", "categories": [], "abstract": item.get("abstract", ""),
        "pdf_url": item.get("pdf"), "added": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Daily run
# ---------------------------------------------------------------------------

TO_CHECK, ADDED, NO_QUSOFT, ON_ARXIV, REJECTED = "to check", "added", "PDF doesn't name QuSoft", "on arXiv", "rejected"


def judge(item, papers, people, mentions_qusoft):
    """Decide a candidate with a PDF: added when the PDF names QuSoft. Returns the new paper or None."""
    pdf = fetch_pdf(item)
    if not pdf:
        item["status"] = TO_CHECK
        return None
    if mentions_qusoft(pdf):
        item["status"] = ADDED
        paper = make_paper(item, people)
        papers.append(paper)
        return paper
    item["status"] = NO_QUSOFT
    return None


def run(people, papers, state, to_check, mentions_qusoft):
    """Search the other servers. Updates papers, state and to_check in place; returns the new papers."""
    match = PersonMatcher(people)
    s = state.setdefault("__other_servers__", {})
    today = date.today()
    eprint_since = date.fromisoformat(s.get("eprint", f"{FIRST_YEAR}-01-01")) - timedelta(days=3)
    crossref_since = date.fromisoformat(s.get("crossref", f"{FIRST_YEAR}-01-01")) - timedelta(days=14)
    eccc_since = int(s.get("eccc", FIRST_YEAR))

    candidates = []
    for name, fetch in (("ECCC", lambda: eccc(eccc_since)), ("IACR ePrint", lambda: eprint(eprint_since)),
                        ("SSRN and ChemRxiv", lambda: crossref(people, crossref_since))):
        found = fetch()
        print(f"  {name}: {len(found)} records")
        candidates += found
    s.update({"eccc": str(today.year), "eprint": today.isoformat(), "crossref": today.isoformat()})

    known_titles = [p["title"] for p in papers]
    first, coauthors, vocab = history(papers)
    added = []
    for c in candidates:
        if c["id"] in to_check or any(p["id"] == c["id"] for p in papers):
            continue
        who = qusoft_people(c, people, match, first)
        if not who:
            continue
        hint = maybe_someone_else(c, who, coauthors, vocab)
        if hint and c["source"] in ("ssrn", "chemrxiv"):
            continue  # these cover every field, so the namesakes are many: keep only likely ones
        item = {**c, "people": who, "found": today.isoformat(), "status": TO_CHECK, "maybe_someone_else": hint}
        to_check[c["id"]] = item
        if any(same_title(c["title"], t) for t in known_titles) or on_arxiv(c["title"], c["authors"]):
            item["status"] = ON_ARXIV
            continue
        paper = judge(item, papers, people, mentions_qusoft)
        print(f"  {item['status']:24} {c['id']:22} {c['title'][:60]}")
        if paper:
            added.append(paper)

    # PDFs downloaded by hand since the last run.
    for item in to_check.values():
        if item["status"] == TO_CHECK and local_pdf(item):
            paper = judge(item, papers, people, mentions_qusoft)
            print(f"  {item['status']:24} {item['id']:22} {item['title'][:60]} (PDF added by hand)")
            if paper:
                added.append(paper)
    return added
