#!/usr/bin/env python3
"""Compare the funding of Dutch quantum centres, for the QuSoft management team (local only).

The centres and their PIs are in centres.yaml. Three measures, the same for every centre:

  A. Papers: arXiv papers by the centre's PIs with the centre on the first page, and the
     funders their acknowledgements thank (share of papers per funder group).
  B. NWO: grants in NWO's project database that list a PI (Veni/Vidi/Vici, Growth Fund,
     NWA, Gravitation, ...), split by role (main applicant / project leader / co-applicant).
  C. EU: quantum projects in CORDIS (H2020, Horizon Europe) with the host organisation
     as participant, and the € it receives. CORDIS lists universities, not centres.

    python scripts/compare_centres.py --search      # find PIs' papers on arXiv (slow: hours the first time)
    python scripts/compare_centres.py               # -> output/centres_comparison_<date>.xlsx and .json

Searches, PDFs and lookups are cached in cache/, so later runs only fetch what is new.
"""

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import arxiv
import fitz
import yaml
from openpyxl import Workbook

from qusoft.arxiv_search import generate_search_queries
from qusoft.common import ROOT, base_id, is_same_person, load_json, load_people, save_json
from qusoft.grants import NWO, NWO_SKIP, Cordis, cordis_group, erc_type, member_is, nwo_group
from funding_report import GROUPS, acknowledgement_statements, groups_in, name_patterns
from internal_report import _pdf, _sheet

CONFIG_FILE = ROOT / "centres.yaml"
CACHE = ROOT / "cache" / "centres"
OUT = ROOT / "output"
# Own-institution funds, per centre (replaces the QuSoft-specific "CWI / UvA own funds" group).
OWN_GROUP = "CWI / UvA own funds"
HOST_GROUP = "Host institution funds"


def short(group):
    return group.split(" (")[0]


def load_centres():
    cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    people = load_people()
    for key, c in cfg["centres"].items():
        if c.get("pis") == "people.csv":
            c["pis"] = [n for n, i in people.items() if i["role"] == "Senior Researchers"]
        entries = [p if isinstance(p, dict) else {"name": p} for p in c["pis"]]
        c["pis"] = [e["name"] for e in entries]
        c["aliases"] = {e["name"]: e.get("aliases", []) for e in entries}
        c["categories"] = {e["name"]: e["categories"] for e in entries if e.get("categories")}
        c["affiliation_re"] = re.compile(c["affiliation"], re.I)
        c["own_re"] = re.compile(c["own_funds"]) if c.get("own_funds") else None
        c["key"] = key
    return cfg


# ---------------------------------------------------------------------------
# A. arXiv search and first-page check
# ---------------------------------------------------------------------------

def search(cfg, only=None):
    since = date.fromisoformat(str(cfg["since"]))
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=5)
    for key, c in cfg["centres"].items():
        if only and key not in only:
            continue
        state_file = CACHE / key / "search.json"
        state = load_json(state_file, {})
        for pi in c["pis"]:
            s = state.get(pi, {})
            aliases = c["aliases"].get(pi, [])
            if s.get("checked") == date.today().isoformat() and (not aliases or s.get("aliases_done")):
                continue
            start = date.fromisoformat(s["checked"]) if s.get("checked") and (not aliases or s.get("aliases_done")) else since
            names = [pi] + aliases
            cats = c["categories"].get(pi)
            window = f"submittedDate:[{start:%Y%m%d}0000 TO {date.today():%Y%m%d}2359]"

            def run(q):
                for attempt in range(4):
                    try:
                        res = list(client.results(arxiv.Search(query=f"({q}) AND {window}", max_results=1000,
                                                               sort_by=arxiv.SortCriterion.SubmittedDate)))
                        time.sleep(3)
                        return {base_id(r.get_short_id()): {
                            "id": r.get_short_id(), "title": " ".join(r.title.split()),
                            "date": r.published.date().isoformat(), "authors": [a.name for a in r.authors],
                            "categories": list(r.categories)}
                            for r in res if any(is_same_person(n, a.name) for n in names for a in r.authors)
                            and (not cats or any(x == k or x.startswith(k + ".") for x in r.categories for k in cats))}
                    except Exception as e:
                        print(f"    {pi}: {e}; retrying")
                        time.sleep(30 * (attempt + 1))
                return None

            # The first spelling that finds papers, plus every alias (people who sign with initials).
            found, res = {}, {}
            for q in [s["query"]] if s.get("query") else generate_search_queries(pi):
                res = run(q)
                if res is None:
                    break
                if res:
                    found.update(res)
                    s["query"] = q
                    break
            for a in aliases:
                if res is None:
                    break
                res = run(f'au:"{a}"')
                found.update(res or {})
            if aliases and res is not None:
                s["aliases_done"] = True
            if res is None:
                continue  # try again next run
            s.setdefault("papers", {}).update(found)
            s["checked"] = date.today().isoformat()
            state[pi] = s
            save_json(state_file, state)
            print(f"  {c['name']}: {pi}: {len(s['papers'])} papers")


def centre_papers(cfg, key):
    """Papers by the centre's PIs with the centre's affiliation on the first page (PDFs fetched as needed)."""
    c = cfg["centres"][key]
    since = str(cfg["since"])
    if key == "qusoft" and c.get("use_site_database"):
        return _qusoft_from_site(c, since)
    state = load_json(CACHE / key / "search.json", {})
    kinds_file = CACHE / key / "first_page.json"
    kinds = load_json(kinds_file, {})
    by_id = {}
    for pi, s in state.items():
        if pi not in c["pis"]:
            continue
        cats = c["categories"].get(pi)
        for pid, p in s.get("papers", {}).items():
            if cats and not any(x == k or x.startswith(k + ".") for x in p["categories"] for k in cats):
                continue
            if p["date"] >= since:
                by_id.setdefault(pid, {**p, "pis": []})["pis"].append(pi)
    todo = [pid for pid in by_id if pid not in kinds]
    if todo:
        print(f"  {c['name']}: checking first pages of {len(todo)} papers")
    for n, pid in enumerate(todo, 1):
        pdf = _pdf(by_id[pid]["id"])
        kinds[pid] = None
        if pdf:
            try:
                with fitz.open(pdf) as doc:
                    kinds[pid] = bool(c["affiliation_re"].search(doc[0].get_text()))
            except Exception:
                pass
        if n % 25 == 0:
            save_json(kinds_file, kinds)
            print(f"    {n}/{len(todo)}")
    save_json(kinds_file, kinds)
    return [p for pid, p in by_id.items() if kinds.get(pid)], sum(1 for pid in by_id if kinds.get(pid) is None), len(by_id)


def _qusoft_from_site(c, since):
    """QuSoft: the site's database already holds every paper with QuSoft on the first page."""
    from qusoft.common import load_papers
    out = []
    for p in load_papers():
        if p["submitted"][:10] < since:
            continue
        pis = [a for a in p["qusoft_authors"] if a in c["pis"]]
        if pis:
            out.append({"id": p["id"], "title": p["title"], "date": p["submitted"][:10],
                        "authors": [a["name"] for a in p["authors"]], "categories": p.get("categories", []), "pis": pis})
    return out, 0, len(out)


def funders_of(paper, c):
    """(funder groups, statements) thanked in a paper, or (None, []) without a PDF.

    Every statement counts, also those about co-authors from elsewhere: we can't tell the centre's
    juniors from collaborators. This is the same for every centre."""
    pdf = _pdf(paper["id"])
    stmts = acknowledgement_statements(pdf) if pdf else None
    if stmts is None:
        return None, []
    found = set()
    for s in stmts:
        gs = groups_in(s)
        gs = [g for g in gs if g != OWN_GROUP]
        if c["own_re"] and c["own_re"].search(s):
            gs.append(HOST_GROUP)
        found.update(gs)
    return found, stmts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", action="store_true", help="search arXiv for the PIs' papers first")
    ap.add_argument("--centres", nargs="*", help="only these centres (keys from centres.yaml)")
    args = ap.parse_args()
    cfg = load_centres()
    if args.search:
        search(cfg, args.centres)

    groups = [g for g, _ in GROUPS if g != OWN_GROUP] + [HOST_GROUP]
    years = list(range(int(str(cfg["since"])[:4]), date.today().year + 1))
    summary, per_group, per_year, nwo_rows, nwo_summary, eu_rows, eu_summary, pi_rows = [], [], [], [], [], [], [], []
    export = {"generated": date.today().isoformat(), "since": str(cfg["since"]), "groups": [short(g) for g in groups],
              "centres": {}}
    nwo, cordis = NWO(), Cordis()

    for key, c in cfg["centres"].items():
        print(f"{c['name']}")
        papers, unreadable, candidates = centre_papers(cfg, key)
        active = Counter(pi for p in papers for pi in p["pis"])
        g_count, g_year, n_read = Counter(), defaultdict(Counter), 0
        n_year = Counter()
        for p in papers:
            fs, _ = funders_of(p, c)
            n_year[p["date"][:4]] += 1
            if fs is None:
                continue
            n_read += 1
            g_count.update(fs)
            for g in fs:
                g_year[p["date"][:4]][g] += 1

        # B. NWO grants of the PIs.
        nwo_seen = {}
        for pi in c["pis"]:
            for rec, roles in nwo.by_member(pi):
                if NWO_SKIP.search(rec["scheme"]) or (rec["start"] or "9999") < str(cfg["since"]):
                    continue
                role = _best_role(roles)
                e = nwo_seen.setdefault(rec["id"], {"rec": rec, "pis": {}})
                e["pis"][pi] = role
        nwo_by_scheme = Counter()
        lead_by_scheme = Counter()
        for pid, e in nwo_seen.items():
            rec = e["rec"]
            kind = _nwo_kind(rec)
            nwo_by_scheme[kind] += 1
            lead = any(r in ("Main Applicant", "Project leader") for r in e["pis"].values())
            if lead:
                lead_by_scheme[kind] += 1
            nwo_rows.append([c["name"], pid, rec["title"], rec["scheme"], kind, rec["start"], rec["end"],
                             ", ".join(f"{n} ({r})" for n, r in e["pis"].items()), "yes" if lead else ""])
        nwo.save()

        # C. EU quantum projects with the host organisations.
        host = re.compile(c["cordis_orgs"], re.I)
        eu_by = defaultdict(lambda: [0, 0.0])
        eu_year = defaultdict(float)
        for p in cordis.projects.values():
            if not p["quantum"] or (p["start"] or "9999") < str(cfg["since"]):
                continue
            mine = [o for o in p["orgs"] if host.search(o["name"])]
            if not mine:
                continue
            kind = erc_type(p) or short(cordis_group(p))
            ec = sum(o["ec"] for o in mine)
            eu_by[kind][0] += 1
            eu_by[kind][1] += ec
            eu_year[p["start"][:4]] += ec
            eu_rows.append([c["name"], p["id"], p["acronym"], p["title"], kind, p["start"], p["end"],
                            "; ".join(f"{o['name'].title()} ({o['role']})" for o in mine), round(ec),
                            p["coordinator"]])

        n_pis = len(c["pis"])
        n_active = len(active)
        total_eu = sum(v[1] for v in eu_by.values())
        summary.append([c["name"], n_pis, n_active, len(papers), n_read, unreadable, candidates,
                        round(len(papers) / n_active, 1) if n_active else None,
                        len(nwo_seen), sum(lead_by_scheme.values()),
                        nwo_by_scheme["Veni"], nwo_by_scheme["Vidi"], nwo_by_scheme["Vici"],
                        nwo_by_scheme["Growth Fund (QDNL)"], nwo_by_scheme["Gravitation"], nwo_by_scheme["NWA"],
                        sum(v[0] for v in eu_by.values()), sum(v[0] for k, v in eu_by.items() if k.startswith("ERC")),
                        round(total_eu), round(total_eu / n_active) if n_active else None])
        for g in groups:
            per_group.append([c["name"], short(g), g_count[g], round(100 * g_count[g] / n_read, 1) if n_read else None])
        for y in years:
            per_year.append([c["name"], y, n_year[str(y)], round(eu_year.get(str(y), 0))])
        for kind, (n, ec) in sorted(eu_by.items()):
            eu_summary.append([c["name"], kind, n, round(ec)])
        for kind, n in sorted(nwo_by_scheme.items()):
            nwo_summary.append([c["name"], kind, n, lead_by_scheme[kind]])
        for pi in c["pis"]:
            pi_rows.append([c["name"], pi, active.get(pi, 0)])
        export["centres"][key] = {
            "name": c["name"], "pis": n_pis, "active_pis": n_active, "papers": len(papers), "readable": n_read,
            "share": {short(g): (round(100 * g_count[g] / n_read, 1) if n_read else 0) for g in groups},
            "papers_by_year": {str(y): n_year[str(y)] for y in years},
            "share_by_year": {str(y): {short(g): g_year[str(y)][g] for g in groups} for y in years},
            "nwo": dict(nwo_by_scheme), "nwo_lead": dict(lead_by_scheme),
            "eu": {k: {"projects": v[0], "ec": round(v[1])} for k, v in eu_by.items()},
            "eu_by_year": {str(y): round(eu_year.get(str(y), 0)) for y in years},
            "eu_orgs": c["cordis_orgs_label"],
        }
        print(f"  {n_active}/{n_pis} PIs with papers, {len(papers)} papers ({n_read} read); "
              f"{len(nwo_seen)} NWO grants; {sum(v[0] for v in eu_by.values())} EU quantum projects, €{total_eu:,.0f}")

    caveat = ("A: acknowledgements count mentions, not money, and also thank co-authors' funders. Only papers with a "
              "centre PI and the centre on the first page. B: NWO's database has no amounts and may miss recent grants. "
              "C: CORDIS lists the university (or NWO-I, TNO), not the centre, so it covers all quantum projects there. "
              "PI lists are hand-made from the centres' websites (centres.yaml).")
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Summary", ["Centre", "PIs listed", "PIs with papers", "Papers (A)", "…read", "…PDF missing",
                           "Candidates checked", "Papers per active PI", "NWO grants (B)", "…as main applicant/leader",
                           "Veni", "Vidi", "Vici", "Growth Fund", "Gravitation", "NWA", "EU quantum projects (C)",
                           "…ERC", "EU € to host", "EU € per active PI"],
           summary, [14, 8, 9, 9, 8, 8, 10, 9, 9, 11, 6, 6, 6, 8, 9, 6, 10, 6, 14, 12],
           f"Since {cfg['since']}. Generated {date.today()}. {caveat}")
    _sheet(wb, "A. Funders in papers", ["Centre", "Funding source", "Papers thanking it", "% of read papers"],
           per_group, [14, 44, 12, 12])
    _sheet(wb, "Per year", ["Centre", "Year", "Papers (A)", "EU € to host, by project start (C)"], per_year, [14, 8, 10, 18])
    _sheet(wb, "B. NWO per scheme", ["Centre", "Scheme", "Grants", "…as main applicant/leader"], nwo_summary, [14, 30, 8, 12])
    _sheet(wb, "B. NWO grants", ["Centre", "NWO id", "Title", "Scheme", "Kind", "Start", "End", "PIs (role)", "PI leads"],
           nwo_rows, [14, 20, 50, 40, 18, 11, 11, 40, 8])
    _sheet(wb, "C. EU per programme", ["Centre", "Programme", "Projects", "€ to host"], eu_summary, [14, 30, 9, 14])
    _sheet(wb, "C. EU projects", ["Centre", "CORDIS id", "Acronym", "Title", "Programme", "Start", "End",
                                  "Host participants (role)", "€ to host", "Coordinator"],
           eu_rows, [14, 11, 14, 50, 20, 11, 11, 40, 12, 40])
    _sheet(wb, "PIs", ["Centre", "PI", "Papers with the centre on the first page"], pi_rows, [14, 30, 12],
           "Check these lists: a PI with no papers may be spelled differently on arXiv, or not publish on arXiv.")
    OUT.mkdir(exist_ok=True)
    out = OUT / f"centres_comparison_{date.today()}.xlsx"
    wb.save(out)
    export["caveat"] = caveat
    save_json(OUT / f"centres_comparison_{date.today()}.json", export)
    print(f"Wrote {out}")


ROLE_ORDER = ["Main Applicant", "Project leader", "Co-applicant", "Researcher"]


def _best_role(roles):
    names = [r["role"] for r in roles]
    return next((r for r in ROLE_ORDER if r in names), names[0] if names else "")


def _nwo_kind(rec):
    s = rec["scheme"]
    for k in ("Veni", "Vidi", "Vici"):
        if re.search(k, s, re.I):
            return k
    g = nwo_group(rec)
    if g.startswith("QDNL"):
        return "Growth Fund (QDNL)"
    if g.startswith(("QSC", "NETWORKS")) or re.search(r"Zwaartekracht|Gravitation", s, re.I):
        return "Gravitation"
    if re.search(r"\bNWA\b", s):
        return "NWA"
    if re.search(r"KLEIN|Open Competit|ENW-M|ENW-XL|ENW XL|XS\b", s, re.I):
        return "Open Competition"
    if re.search(r"Perspectief|TTW|STW|Take-off|Demonstrator", s, re.I):
        return "Applied (TTW / Perspectief)"
    if re.search(r"FOM|Projectruimte|Programma", s, re.I):
        return "FOM / programmes"
    return "Other"


if __name__ == "__main__":
    main()
