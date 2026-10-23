#!/usr/bin/env python3
"""Where QuSoft papers appeared, and how often they are cited (internal, never published).

    python scripts/fetch_venues.py        # -> cache/venues.json

For arXiv papers: the journal reference and comments the authors gave on arXiv
(e.g. "QIP 2024 plenary talk", "Phys. Rev. Lett. 130, ..."), and from Semantic Scholar
the venue, citation count and influential citations. Kept in cache/ (git-ignored).
Used by the internal report; nothing of this goes on the site.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from qusoft.arxiv_search import fetch_by_ids
from qusoft.common import base_id, load_papers

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "venues.json"
UA = {"User-Agent": "qusoft-arxiv internal report (https://github.com/QuSoft-org/qusoft-arxiv)"}


def arxiv_meta(ids):
    out = {}
    for i in range(0, len(ids), 50):
        for attempt in range(4):
            try:
                for r in fetch_by_ids(ids[i:i + 50]):
                    out[base_id(r.get_short_id())] = {"journal_ref": r.journal_ref or "", "comment": r.comment or "",
                                                      "doi": r.doi or ""}
                break
            except Exception as e:
                print(f"  arXiv: {e}; waiting")
                time.sleep(30 * (attempt + 1))
        time.sleep(3)
    return out


def semantic_scholar(ids):
    out = {}
    fields = "citationCount,influentialCitationCount,venue,publicationVenue,year,externalIds,publicationTypes"
    for i in range(0, len(ids), 400):
        batch = [f"ARXIV:{x}" for x in ids[i:i + 400]]
        for attempt in range(5):
            r = requests.post("https://api.semanticscholar.org/graph/v1/paper/batch", params={"fields": fields},
                              json={"ids": batch}, headers=UA, timeout=120)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            for x, rec in zip(ids[i:i + 400], r.json()):
                if rec:
                    pv = rec.get("publicationVenue") or {}
                    out[x] = {"citations": rec.get("citationCount"), "influential": rec.get("influentialCitationCount"),
                              "venue": rec.get("venue") or pv.get("name") or "", "venue_type": pv.get("type") or ""}
            break
        time.sleep(5)
    return out


def main():
    papers = [p for p in load_papers() if p.get("source", "arxiv") == "arxiv"]
    ids = [base_id(p["id"]) for p in papers]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [i for i in ids if "journal_ref" not in cache.get(i, {})]
    if todo:
        print(f"arXiv details for {len(todo)} papers")
        for k, v in arxiv_meta(todo).items():
            cache.setdefault(k, {}).update(v)
    print(f"Semantic Scholar for {len(ids)} papers")
    for k, v in semantic_scholar(ids).items():
        cache.setdefault(k, {}).update(v, fetched=date.today().isoformat())
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    with_cites = sum(1 for v in cache.values() if v.get("citations") is not None)
    print(f"Wrote {CACHE}: {len(cache)} papers, {with_cites} with citation counts")


if __name__ == "__main__":
    main()
