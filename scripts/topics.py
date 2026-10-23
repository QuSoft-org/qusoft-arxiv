#!/usr/bin/env python3
"""What QuSoft writes about: topics inferred from the papers themselves.

    python scripts/topics.py discover [--k 24]   # clusters of similar papers -> output/topic_clusters.md
    python scripts/topics.py compare             # inferred lines vs. official research lines -> output/

'discover' groups papers by the words in their titles and abstracts (TF-IDF, reduced with SVD,
then agglomerative clustering). The clusters are a starting point for naming research lines
and topics by reading the papers; they are not the final taxonomy.

Needs scikit-learn (local only: pip install scikit-learn).
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from qusoft.common import load_papers

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

# Words every paper here uses; they say nothing about the topic.
COMMON = """quantum classical show shows shown result results paper work study new problem problems
approach method methods based using use used give gives given prove proves proved provide provides
also case cases first one two three number general known well terms present presents
introduce introduces consider considers find finds found main question questions""".split()


def text(p):
    t = f"{p['title']}. {p['title']}. {p.get('abstract', '')}"  # title counts double
    t = re.sub(r"\$[^$]*\$", " ", t)  # drop inline maths
    return re.sub(r"\\[a-zA-Z]+", " ", t)


def discover(k):
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from sklearn.preprocessing import normalize

    papers = sorted(load_papers(), key=lambda p: p["submitted"])
    docs = [text(p) for p in papers]
    vec = TfidfVectorizer(stop_words=list(ENGLISH_STOP_WORDS | set(COMMON)), ngram_range=(1, 2),
                          min_df=3, max_df=0.4, sublinear_tf=True, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z-]+\b")
    X = vec.fit_transform(docs)
    Z = normalize(TruncatedSVD(n_components=100, random_state=0).fit_transform(X))
    labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z)
    terms = np.array(vec.get_feature_names_out())

    lines = [f"# Clusters of QuSoft papers ({len(papers)} papers, k={k})", "",
             "Groups of papers with similar words in title and abstract. A starting point for naming topics.", ""]
    order = sorted(range(k), key=lambda c: -(labels == c).sum())
    for c in order:
        idx = np.where(labels == c)[0]
        centroid = np.asarray(X[idx].mean(axis=0)).ravel()
        top = ", ".join(terms[centroid.argsort()[::-1][:14]])
        years = Counter(papers[i]["submitted"][:4] for i in idx)
        span = f"{min(years)}–{max(years)}"
        zc = Z[idx].mean(axis=0)
        rep = idx[np.argsort(-(Z[idx] @ zc))][:10]
        lines += [f"## Cluster {c}: {len(idx)} papers ({span})", "", f"Terms: {top}", "",
                  "Per year: " + ", ".join(f"{y}: {years[y]}" for y in sorted(years)), ""]
        lines += [f"- {papers[i]['title']} ({papers[i]['submitted'][:4]})" for i in rep]
        lines.append("")
    OUT.mkdir(exist_ok=True)
    out = OUT / "topic_clusters.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


SELECTED = [("QIP", r"\\bQIP\\b"), ("STOC", r"\\bSTOC\\b|Symposium on Theory of Computing"),
            ("FOCS", r"\\bFOCS\\b|Foundations of Computer Science"), ("SODA", r"\\bSODA\\b"),
            ("CCC", r"\\bCCC\\b|Computational Complexity Conference"), ("ICALP", r"\\bICALP\\b"), ("ITCS", r"\\bITCS\\b"),
            ("CRYPTO", r"\\bCRYPTO\\b"), ("EUROCRYPT", r"EUROCRYPT|Eurocrypt"), ("ASIACRYPT", r"ASIACRYPT|Asiacrypt"),
            ("TCC", r"\\bTCC\\b"), ("Nature family", r"\\bNature\\b|Nat\\. ?(Phys|Commun)"), ("Science", r"^Science\\b"),
            ("PRL", r"Phys\\.? ?Rev\\.? ?Lett|Physical Review Letters|\\bPRL\\b"), ("PRX", r"\\bPRX\\b|Phys\\. Rev\\. X"),
            ("Quantum (journal)", r"^Quantum\\b|Quantum \\d+, \\d")]


def venues_and_citations(topics, names, papers):
    """Internal: selected venues and citations per line, from cache/venues.json (scripts/fetch_venues.py)."""
    import json
    import statistics
    from datetime import date
    from qusoft.common import base_id
    f = ROOT / "cache" / "venues.json"
    if not f.exists():
        return []
    V = json.loads(f.read_text())
    rows, top = {}, {}
    for pid, tag in topics["papers"].items():
        p, v = papers.get(pid), V.get(base_id(pid), {})
        if not p:
            continue
        text = " | ".join([v.get("journal_ref", ""), v.get("comment", ""), v.get("venue", "")])
        sel = [n for n, rx in SELECTED if re.search(rx, text)]
        age = max(0.5, (date.today() - date.fromisoformat(p["submitted"][:10])).days / 365)
        cpy = v["citations"] / age if v.get("citations") is not None else None
        rows.setdefault(tag["line"], []).append((cpy, sel))
        if cpy is not None:
            top.setdefault(tag["line"], []).append((cpy, v["citations"], p["title"], p["submitted"][:4], sel))
    out = ["", "## Venues and citations per line (internal)", "",
           "Venues from arXiv journal references and comments, and Semantic Scholar; selected venues: "
           + ", ".join(n for n, _ in SELECTED) + ". Citations per year since the paper appeared. "
           "Fields cite at very different rates, so compare lines with care.", "",
           "| Line | Papers | In a selected venue | Median citations per year | 20+ citations per year |", "|---|---:|---:|---:|---:|"]
    for l in sorted(rows, key=lambda l: -len(rows[l])):
        r = rows[l]
        c = [x for x, _ in r if x is not None]
        n = sum(1 for _, v in r if v)
        out.append(f"| {names.get(l, l)} | {len(r)} | {n} ({round(100 * n / len(r))}%) | "
                   f"{statistics.median(c):.1f} | {sum(1 for x in c if x >= 20)} |" if c else f"| {names.get(l, l)} | {len(r)} | | | |")
    out += ["", "### Most cited per year, per line (top 5)", ""]
    for l in sorted(top, key=lambda l: -len(rows[l])):
        out += [f"**{names.get(l, l)}**", ""]
        out += [f"- {t} ({y}): {c} citations, {x:.0f} per year{'; ' + ', '.join(s) if s else ''}"
                for x, c, t, y, s in sorted(top[l], reverse=True)[:5]]
        out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["discover", "compare"])
    ap.add_argument("--k", type=int, default=24, help="number of clusters for 'discover'")
    args = ap.parse_args()
    if args.action == "discover":
        discover(args.k)
    else:
        compare()


def official_lines():
    """{person: [official research lines]} from the private spreadsheet (columns P and Q)."""
    from openpyxl import load_workbook
    from qusoft.common import path
    out = {}
    excel = path("database", "excel_file")
    if not excel.exists():
        return out
    ws = load_workbook(excel, read_only=True, data_only=True)["QuSoft People Database"]
    for row in ws.iter_rows(min_row=3, values_only=True):
        name = " ".join(str(row[0] or "").split())
        lines = [str(x).strip() for x in row[15:17] if x and str(x).strip() not in ("NA", "-", "")]
        if name and lines:
            out[name] = lines
    return out


def compare():
    """Inferred research lines (data/topics.json) next to the official ones, written for the MT."""
    import json
    topics = json.loads((ROOT / "data" / "topics.json").read_text())
    names = {l["id"]: l["name"] for l in topics["taxonomy"]["lines"]}
    names["other"] = "Other"
    tnames = {t["id"]: t["name"] for l in topics["taxonomy"]["lines"] for t in l["topics"]}
    papers = {p["id"]: p for p in load_papers()}
    official = official_lines()
    off_names = sorted({l for ls in official.values() for l in ls})

    cross = {l: Counter() for l in names}
    per_year = {l: Counter() for l in names}
    no_official = Counter()
    for pid, tag in topics["papers"].items():
        p = papers.get(pid)
        if not p:
            continue
        line = tag["line"]
        per_year[line][p["submitted"][:4]] += 1
        offs = {o for a in p["qusoft_authors"] for o in official.get(a, [])}
        if not offs:
            no_official[line] += 1
        for o in offs:
            cross[line][o] += 1

    years = sorted({y for c in per_year.values() for y in c})
    out = ["# Research lines inferred from the papers, next to the official ones", "",
           f"{len(topics['papers'])} papers. Inferred lines come from reading titles and abstracts; "
           "official lines are those of the papers' QuSoft authors in the spreadsheet (a paper counts "
           "under every official line of its authors).", "",
           "## Papers per inferred line and official line", "",
           "| Inferred line | Papers | " + " | ".join(off_names) + " | No official line |",
           "|---|---:|" + "---:|" * (len(off_names) + 1)]
    for l in sorted(names, key=lambda l: -sum(per_year[l].values())):
        out.append(f"| {names[l]} | {sum(per_year[l].values())} | " +
                   " | ".join(str(cross[l][o] or "") for o in off_names) + f" | {no_official[l] or ''} |")
    out += ["", "## Papers per inferred line per year", "",
            "| Inferred line | " + " | ".join(years) + " |", "|---|" + "---:|" * len(years)]
    for l in sorted(names, key=lambda l: -sum(per_year[l].values())):
        out.append(f"| {names[l]} | " + " | ".join(str(per_year[l][y] or "") for y in years) + " |")
    tc = Counter(t for tag in topics["papers"].values() for t in tag["topics"])
    out += ["", "## Topics", "", "| Topic | Papers (as any of its 1-3 topics) |", "|---|---:|"]
    out += [f"| {tnames.get(t, t)} | {n} |" for t, n in tc.most_common()]
    out += venues_and_citations(topics, names, papers)
    OUT.mkdir(exist_ok=True)
    f = OUT / "research_lines_comparison.md"
    f.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {f}")


if __name__ == "__main__":
    main()
