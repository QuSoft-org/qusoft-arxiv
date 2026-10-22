#!/usr/bin/env python3
"""The funding landscape of QuSoft researchers, for the management team (local only, never published).

Reads the acknowledgements of every paper by a QuSoft researcher (PhD student, postdoc or
senior), from before, during and after their QuSoft years, with or without QuSoft on the
paper. It pulls out projects (grant names and numbers, the funder, who is named with it),
looks them up in NWO's project database and in CORDIS (EU), and adds NWO projects of
these people that no paper thanks. For each project it shows where QuSoft is involved:

    QuSoft named           at least one of its papers has QuSoft as affiliation
    UvA/CWI, no QuSoft     held at UvA or CWI (NWO, CORDIS), or its papers have UvA/CWI but never QuSoft
    Elsewhere              neither: e.g. a grant from before or after someone's QuSoft years

    python scripts/funding_landscape.py   # -> output/funding_landscape_<date>.xlsx and .json

Run scripts/internal_report.py once first (it fetches the details and PDFs of papers that
don't mention QuSoft). NWO and CORDIS answers are cached in cache/funding/.
"""

import hashlib
import inspect
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook
from openpyxl.styles import Font

from qusoft.common import ROOT, base_id, is_alumnus, load_json, load_people, path, save_json
from qusoft.grants import (NWO, NWO_SKIP, Cordis, cordis_group, erc_type, looks_like_nwo, member_is, nwo_group)
from funding_report import (GROUPS, SOMEONE, acknowledgement_statements, grant_ids, groups_in, name_patterns,
                            people_match, spreadsheet)
from internal_report import (CWI_UVA, NONE, QUSOFT_LATER, QUSOFT_ON_FIRST_PAGE, UNREADABLE, _pdf, _sheet, collect,
                             membership)

RESEARCHERS = {"PhD Students": "PhD student", "Postdocs": "Postdoc", "Senior Researchers": "Senior", "Visitor": "Visitor"}
AFFIL = {QUSOFT_ON_FIRST_PAGE: "QuSoft", QUSOFT_LATER: "QuSoft", CWI_UVA: "UvA/CWI, no QuSoft", NONE: "Elsewhere",
         UNREADABLE: "Unreadable"}
VERDICTS = ["QuSoft named", "UvA/CWI, no QuSoft", "Elsewhere"]
HOME_ORG = re.compile(r"Universiteit van Amsterdam|University of Amsterdam|\bCWI\b|Centrum Wiskunde|CENTRUM WISKUNDE"
                      r"|UNIVERSITEIT VAN AMSTERDAM|STICHTING NEDERLANDSE WETENSCHAPPELIJK ONDERZOEK INSTITUTEN", re.I)
# Programmes thanked by name without a number: give them one key.
ALIASES = {GROUPS[0][0]: "024.003.037", GROUPS[2][0]: "024.002.003"}
OUT = Path(__file__).resolve().parent.parent / "output"
STATEMENT_CACHE = ROOT / "cache" / "funding" / "statements.json"


def short(group):
    return group.split(" (")[0]


# ---------------------------------------------------------------------------
# Papers and statements
# ---------------------------------------------------------------------------

def statements_for(rows):
    """{paper id: [funding statements]} from the cached PDFs, cached until funding_report.py changes."""
    import funding_report
    version = hashlib.sha1(inspect.getsource(funding_report).encode()).hexdigest()[:10]
    cache = load_json(STATEMENT_CACHE, {})
    if cache.get("version") != version:
        cache = {"version": version, "papers": {}}
    todo = [r for r in rows if base_id(r["id"]) not in cache["papers"]]
    if todo:
        print(f"Reading acknowledgements in {len(todo)} PDFs")
    for n, r in enumerate(todo, 1):
        pdf = _pdf(r["id"])
        cache["papers"][base_id(r["id"])] = acknowledgement_statements(pdf) if pdf else None
        if n % 200 == 0:
            print(f"  {n}/{len(todo)}")
            save_json(STATEMENT_CACHE, cache)
    save_json(STATEMENT_CACHE, cache)
    return cache["papers"]


def timing(span, day, alumnus):
    start, end = span
    if start and day < start:
        return "before"
    if alumnus and end and day > end:
        return "after"
    return "during" if start or alumnus else "during (no start date)"


NWO_LIKE = {GROUPS[i][0] for i in (0, 1, 2, 3, 6, 7)}
EU_LIKE = {GROUPS[4][0], GROUPS[5][0]}


def group_for_id(statement, gid, gs):
    """The funder named closest before a grant number in a statement (NWO-style numbers go to an NWO funder)."""
    if looks_like_nwo(gid) and NWO_LIKE & set(gs):
        gs = [g for g in gs if g in NWO_LIKE]
    elif re.fullmatch(r"\d{6,9}", gid) and EU_LIKE & set(gs):
        gs = [g for g in gs if g in EU_LIKE]
    if len(gs) == 1:
        return gs[0]
    pos = statement.find(gid)
    if pos < 0:
        return gs[0] if gs else ""
    best, best_pos = "", -1
    for g, rx in [(g, re.compile(p)) for g, p in GROUPS]:
        if g not in gs:
            continue
        for m in rx.finditer(statement[: pos + len(gid)]):
            if m.start() > best_pos:
                best, best_pos = g, m.start()
    return best or (gs[0] if gs else "")


def normalise_ids(keys):
    """Map short forms to the long form seen elsewhere: '192.109' -> 'VI.Vidi.192.109'."""
    canon = {}
    for k in keys:
        longer = [o for o in keys if o != k and o.lower().endswith("." + k.lower()) and re.fullmatch(r"[\d.]+", k)
                  and k.count(".") >= 1]
        canon[k] = max(longer, key=len) if longer else k
    return canon


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    people = load_people()
    researchers = {n: i for n, i in people.items() if i["role"] in RESEARCHERS}
    spans, span_source = membership(people)
    sheet_funding, supervisors = spreadsheet()

    rows, _ = collect(people, any_date=True)
    rows = [r for r in rows if any(m in researchers and m not in r["unsure"] for m in r["members"])]
    statements = statements_for(rows)

    name_to_number = {}       # grant name -> grant number seen with it
    mentions = []             # one per (statement, project or funder group) about QuSoft people or nobody in particular
    papers = {}               # id -> paper summary
    collaborator_only = Counter()  # group -> statements that name only non-QuSoft co-authors
    per_person = defaultdict(lambda: Counter())  # name -> affiliation -> papers
    for r in rows:
        pid = base_id(r["id"])
        who = [m for m in r["members"] if m in researchers and m not in r["unsure"]]
        affil = AFFIL.get(r["kind"], "Unreadable")
        stmts = statements.get(pid)
        papers[pid] = {"id": pid, "date": r["date"].isoformat(), "title": r["title"], "affil": affil,
                       "members": who, "timing": {m: timing(spans[m], r["date"], is_alumnus(people[m])) for m in who},
                       "readable": stmts is not None, "groups": set()}
        for m in who:
            per_person[m][affil] += 1
        if not stmts:
            continue
        pats = {a: name_patterns(a) for a in r["authors"]}
        member_name = {m: next((a for a in r["authors"] if people_match(a, m)), m) for m in who}
        for s in stmts:
            subjects = {a for a, ps in pats.items() if any(p.search(s) for p in ps)}
            named = [m for m in who if member_name[m] in subjects]
            gs = groups_in(s)
            if subjects and not named:
                for g in gs:
                    collaborator_only[g] += 1
                continue  # a co-author's grant, not QuSoft's
            anonymous = not subjects and bool(SOMEONE.search(s))
            papers[pid]["groups"].update(gs)
            used = set()
            ids = [(gid, group_for_id(s, gid, gs)) for gid in grant_ids(s)]
            for gid, g in ids:
                used.add(g)
                same = [i for i, h in ids if h == g and re.search(r"\d", i)
                        and abs(s.find(i) - s.find(gid)) < 60]
                if not re.search(r"\d", gid) and len(same) == 1:
                    name_to_number[gid] = same[0]  # "ERC grant QPROGRESS (No. 615307)", quoted title + number
                mentions.append({"key": gid, "group": g, "paper": pid, "named": named, "anonymous": anonymous,
                                 "statement": s})
            for g in gs:
                if g in used:
                    continue
                if g in ALIASES:
                    mentions.append({"key": ALIASES[g], "group": g, "paper": pid, "named": named,
                                     "anonymous": anonymous, "statement": s})
                elif named:
                    for m in named:  # "AB is supported by an NWO Veni grant": one project per person and funder
                        mentions.append({"key": f"{short(g)} | {m}", "group": g, "paper": pid, "named": [m],
                                         "anonymous": False, "statement": s, "unnumbered": True})
                else:
                    mentions.append({"key": None, "group": g, "paper": pid, "named": [], "anonymous": anonymous,
                                     "statement": s})

    # Projects ----------------------------------------------------------------
    canon = normalise_ids({m["key"] for m in mentions if m["key"] and not m.get("unnumbered")})
    for name, number in name_to_number.items():
        canon[name] = canon.get(number, number)
    projects = {}
    for m in mentions:
        if not m["key"]:
            continue
        key = canon.get(m["key"], m["key"])
        p = projects.setdefault(key, {"key": key, "groups": Counter(), "papers": set(), "named": Counter(),
                                      "unnumbered": m.get("unnumbered", False), "sources": {"papers"},
                                      "lookup_people": {}, "orgs": [], "title": "", "scheme": "", "start": "",
                                      "end": "", "home_ec": 0.0, "nl_ec": [], "statements": []})
        p["groups"][m["group"]] += 1
        p["papers"].add(m["paper"])
        p["named"].update(m["named"])
        if len(p["statements"]) < 3 and m["statement"] not in p["statements"]:
            p["statements"].append(m["statement"])

    print("Looking up grants in NWO and CORDIS")
    nwo, cordis = NWO(), Cordis()
    not_found = []
    for key, p in projects.items():
        if p["unnumbered"]:
            continue
        rec = None
        if looks_like_nwo(key):
            rec = nwo.project(key)
            if rec:
                _apply_nwo(p, rec, researchers)
        if not rec and (re.fullmatch(r"\d{6,9}", key) or re.fullmatch(r"[A-Z][A-Za-z0-9-]{3,}", key)):
            rec = cordis.get(key)
            if rec:
                _apply_cordis(p, rec)
        if not rec and key not in ALIASES.values():
            not_found.append([key, short(p["groups"].most_common(1)[0][0]), len(p["papers"]), p["statements"][0][:300]])

    # NWO projects of these people that no paper thanks.
    for n in sorted(researchers):
        for rec, roles in nwo.by_member(n):
            if NWO_SKIP.search(rec["scheme"]) or (rec["start"] and rec["start"] < "2008"):
                continue
            key = rec["id"]
            if key in projects:
                continue
            p = projects.setdefault(key, {"key": key, "groups": Counter(), "papers": set(), "named": Counter(),
                                          "unnumbered": False, "sources": set(), "lookup_people": {}, "orgs": [],
                                          "title": "", "scheme": "", "start": "", "end": "", "home_ec": 0.0,
                                          "nl_ec": [], "statements": []})
            _apply_nwo(p, rec, researchers)
    nwo.save()
    _merge_unnumbered(projects)

    # Verdicts ----------------------------------------------------------------
    project_rows = []
    for key, p in projects.items():
        group = p.get("lookup_group") or (p["groups"].most_common(1)[0][0] if p["groups"] else "")
        p["group"] = group
        affils = Counter(papers[x]["affil"] for x in p["papers"])
        held_home = any(HOME_ORG.search(o) for o in p["orgs"])
        if affils["QuSoft"]:
            verdict = "QuSoft named"
        elif held_home or affils["UvA/CWI, no QuSoft"]:
            verdict = "UvA/CWI, no QuSoft"
        else:
            verdict = "Elsewhere"
        p["verdict"] = verdict
        years = sorted(papers[x]["date"][:4] for x in p["papers"])
        guess = ""
        if not p["named"] and not p["lookup_people"] and p["papers"]:
            # Nobody named: the senior QuSoft author on most of its papers, else the most frequent one.
            c = Counter(m for x in p["papers"] for m in papers[x]["members"])
            seniors = [m for m, _ in c.most_common() if researchers[m]["role"] == "Senior Researchers"]
            guess = seniors[0] if seniors else c.most_common(1)[0][0]
        p["guess"] = guess
        named = ", ".join(n for n, _ in p["named"].most_common())
        looked = ", ".join(f"{n} ({r})" for n, r in p["lookup_people"].items())
        timings = Counter(t for x in p["papers"] for t in papers[x]["timing"].values())
        project_rows.append([
            key, short(group), p["title"], p["scheme"], p["start"], p["end"], verdict,
            len(p["papers"]), affils["QuSoft"], affils["UvA/CWI, no QuSoft"], affils["Elsewhere"],
            f"{years[0]}–{years[-1]}" if years else "", named, looked, guess,
            ", ".join(sorted(set(p["orgs"])))[:300], round(p["home_ec"]) or None,
            "; ".join(f"{o}: €{round(e):,}" for o, e in p["nl_ec"])[:300] or None,
            ", ".join(f"{k} {v}" for k, v in timings.most_common()),
            " + ".join(sorted(p["sources"])) or "",
            " | ".join(f"https://arxiv.org/abs/{x}" for x in sorted(p["papers"], reverse=True)[:5]),
            (p["statements"][0][:400] if p["statements"] else ""),
        ])
    order = {short(g): i for i, (g, _) in enumerate(GROUPS)}
    project_rows.sort(key=lambda r: (order.get(r[1], 99), VERDICTS.index(r[6]), -r[7], r[0]))

    # Overview per funder group ----------------------------------------------
    overview = []
    for g, _ in GROUPS:
        ps = [p for p in projects.values() if p["group"] == g]
        thanked = [x for x in papers.values() if g in x["groups"]]
        with_q = sum(1 for x in thanked if x["affil"] == "QuSoft")
        people_g = {n for p in ps for n in list(p["named"]) + list(p["lookup_people"])}
        overview.append([short(g), len(ps), *[sum(p["verdict"] == v for p in ps) for v in VERDICTS],
                         sum(1 for p in ps if "papers" not in p["sources"]),
                         len(thanked), with_q, round(100 * with_q / len(thanked)) if thanked else None,
                         len(people_g), round(sum(p["home_ec"] for p in ps)) or None, collaborator_only[g]])

    # Papers by members, during their QuSoft years, without QuSoft but thanking a funder.
    reminders = []
    for x in sorted(papers.values(), key=lambda x: x["date"], reverse=True):
        if x["affil"] in ("UvA/CWI, no QuSoft", "Elsewhere") and x["groups"]:
            during = [m for m in x["members"] if x["timing"][m].startswith("during")]
            if during:
                reminders.append([x["date"], f"https://arxiv.org/abs/{x['id']}", x["title"], x["affil"],
                                  ", ".join(during), "; ".join(short(g) for g in sorted(x["groups"]))])

    # Per researcher -----------------------------------------------------------
    person_rows = []
    for n, info in sorted(researchers.items(), key=lambda kv: (list(RESEARCHERS).index(kv[1]["role"]), kv[0])):
        mine = [p for p in projects.values() if n in p["named"] or n in p["lookup_people"] or p["guess"] == n]
        by_v = {v: sorted({f"{short(p['group'])}: {p['title'] or p['key']}"[:80] for p in mine if p["verdict"] == v})
                for v in VERDICTS}
        start, end = spans.get(n, (None, None))
        person_rows.append([n, RESEARCHERS[info["role"]], "alumni" if is_alumnus(info) else "current",
                            start.isoformat() if start else "", end.isoformat() if end else "",
                            ", ".join(supervisors.get(n, [])), sheet_funding.get(n, ""),
                            sum(per_person[n].values()), per_person[n]["QuSoft"], per_person[n]["UvA/CWI, no QuSoft"],
                            per_person[n]["Elsewhere"], *["; ".join(by_v[v]) for v in VERDICTS]])

    evidence = []
    for m in mentions:
        x = papers[m["paper"]]
        evidence.append([x["date"], f"https://arxiv.org/abs/{m['paper']}", x["affil"], short(m["group"]),
                         canon.get(m["key"], m["key"]) or "", ", ".join(m["named"]) or ("one author, unclear who" if m["anonymous"] else "nobody"),
                         ", ".join(x["members"]), m["statement"][:600]])

    # Write -------------------------------------------------------------------
    n_papers = len(papers)
    n_read = sum(1 for x in papers.values() if x["readable"])
    aff = Counter(x["affil"] for x in papers.values())
    caveat = ("Acknowledgements count mentions, not money. Only arXiv papers found by the site's search (since 2015). "
              "Computer-science papers often thank nobody. NWO's database has no amounts. CORDIS lists the university "
              "or NWO-I (CWI's legal body, also other NWO institutes), not QuSoft.")
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Overview", ["Funding source", "Projects", *VERDICTS, "Of these, only in NWO database",
                            "Papers thanking it", "…with QuSoft affiliation", "% with QuSoft", "QuSoft people involved",
                            "EU € to UvA/CWI (CORDIS)", "Statements naming only non-QuSoft co-authors (left out)"],
           overview, [40, 10, 13, 16, 11, 14, 12, 14, 10, 12, 14, 18],
           f"{len(researchers)} researchers in people.csv (PhD students, postdocs, seniors). {n_papers} papers: "
           f"{aff['QuSoft']} with QuSoft, {aff['UvA/CWI, no QuSoft']} UvA/CWI without QuSoft, {aff['Elsewhere']} elsewhere; "
           f"{n_read} readable. Generated {date.today()}. {caveat}")
    ws = _sheet(wb, "Projects", ["Project / grant", "Funding source", "Title (NWO / CORDIS)", "Scheme", "Start", "End",
                                 "QuSoft involved?", "Papers", "…with QuSoft", "…UvA/CWI, no QuSoft", "…elsewhere",
                                 "Paper years", "QuSoft people named in papers", "QuSoft people in NWO record (role)",
                                 "Nobody named: likely holder (guess)", "Organisations (NWO / CORDIS, NL)",
                                 "EU € to UvA/CWI", "EU € to Dutch participants", "Paper timing vs. QuSoft years",
                                 "Found in", "Papers (up to 5)", "Example statement"],
                project_rows, [22, 24, 40, 30, 11, 11, 18, 7, 9, 10, 9, 11, 30, 34, 22, 40, 12, 40, 26, 16, 50, 80],
                "One line per grant. Numbered grants are looked up in NWO and CORDIS; 'Veni | name' style keys are "
                "grants thanked without a number. 'Found in: NWO' alone means no paper thanks it.")
    for row in ws.iter_rows(min_row=4, min_col=21, max_col=21):
        for cell in row:
            if cell.value:
                cell.hyperlink = cell.value.split(" | ")[0]
                cell.font = Font(color="921317", underline="single")
    _sheet(wb, "Per researcher", ["Name", "Role", "Now", "Start", "End", "Supervisors", "Spreadsheet funding",
                                  "Papers", "…with QuSoft", "…UvA/CWI, no QuSoft", "…elsewhere",
                                  "Projects: QuSoft named", "Projects: UvA/CWI, no QuSoft", "Projects: elsewhere"],
           person_rows, [24, 11, 8, 11, 11, 30, 30, 7, 9, 10, 9, 60, 60, 60],
           f"Projects a researcher is named with, listed with in NWO, or guessed as holder. Membership dates: {span_source}.")
    _sheet(wb, "Affiliation reminders", ["Date", "Paper", "Title", "Affiliation", "Members at the time", "Funders thanked"],
           reminders, [11, 32, 60, 18, 34, 50],
           "Papers written during someone's QuSoft years that thank a funder but don't name QuSoft. "
           "Worth a look for QSC/QDNL reporting.")
    _sheet(wb, "Evidence", ["Date", "Paper", "Affiliation", "Funding source", "Project / grant", "Names",
                            "QuSoft authors", "Statement"],
           evidence, [11, 32, 18, 24, 22, 28, 30, 120], "Every funding statement used, for checking.")
    _sheet(wb, "Not found in NWO or CORDIS", ["Grant", "Funding source (from text)", "Papers", "Statement"],
           not_found, [26, 26, 8, 120], "Numbers that aren't NWO or EU grants (or were misread). Most are funders abroad.")
    OUT.mkdir(exist_ok=True)
    out = OUT / f"funding_landscape_{date.today()}.xlsx"
    wb.save(out)

    # Data for the HTML overview.
    export = {
        "generated": date.today().isoformat(), "caveat": caveat,
        "counts": {"researchers": len(researchers), "papers": n_papers, "readable": n_read, **aff},
        "groups": [short(g) for g, _ in GROUPS], "verdicts": VERDICTS,
        "overview": overview,
        "projects": [dict(zip(["key", "group", "title", "scheme", "start", "end", "verdict", "papers", "with_qusoft",
                               "uva_cwi", "elsewhere", "years", "named", "nwo_people", "guess", "orgs", "home_ec",
                               "nl_ec", "timing", "sources", "links", "statement"], r)) for r in project_rows],
        "papers_by_year": _papers_by_year(papers),
    }
    save_json(OUT / f"funding_landscape_{date.today()}.json", export)

    print(f"Wrote {out}")
    print(f"  {len(researchers)} researchers, {n_papers} papers ({n_read} readable): {dict(aff)}")
    print(f"  {len(projects)} projects; {len(not_found)} numbers not found in NWO/CORDIS")
    for row in overview:
        print(f"  {row[0][:34]:34s} {row[1]:4d} projects  ({row[2]} QuSoft, {row[3]} UvA/CWI, {row[4]} elsewhere)"
              f"  papers {row[6]}, {row[8]}% with QuSoft")


def _merge_unnumbered(projects):
    for key in [k for k, p in projects.items() if p["unnumbered"]]:
        p = projects[key]
        group = p["groups"].most_common(1)[0][0]
        person = key.split(" | ", 1)[1]
        targets = [q for q in projects.values() if not q["unnumbered"]
                   and (q.get("lookup_group") or (q["groups"].most_common(1)[0][0] if q["groups"] else "")) == group
                   and (person in q["named"] or person in q["lookup_people"])]
        if len(targets) != 1:
            continue
        t = targets[0]
        t["papers"] |= p["papers"]
        t["named"].update(p["named"])
        t["groups"].update(p["groups"])
        t["statements"] = (t["statements"] + [x for x in p["statements"] if x not in t["statements"]])[:3]
        del projects[key]


def _papers_by_year(papers):
    out = defaultdict(lambda: defaultdict(Counter))
    for x in papers.values():
        for g in x["groups"]:
            out[x["date"][:4]][short(g)][x["affil"]] += 1
    return {y: {g: dict(c) for g, c in v.items()} for y, v in sorted(out.items())}


def _apply_nwo(p, rec, researchers):
    p["sources"].add("NWO")
    p["title"], p["scheme"], p["start"], p["end"] = rec["title"], rec["scheme"], rec["start"], rec["end"]
    p["lookup_group"] = nwo_group(rec)
    for m in rec["members"]:
        p["orgs"].append(m["org"].split("||")[0] + (" / " + m["org"].split("||")[1] if "CWI" in m["org"] else ""))
        for n in researchers:
            if member_is(m, n):
                role = m["role"]
                p["lookup_people"][n] = role if n not in p["lookup_people"] else p["lookup_people"][n]
    p["orgs"] = list(dict.fromkeys(p["orgs"]))


def _apply_cordis(p, rec):
    p["sources"].add("CORDIS")
    kind = erc_type(rec)
    p["title"] = f"{rec['acronym']}: {rec['title']}"
    p["scheme"] = (kind + " · " if kind else "") + rec["scheme"]
    p["start"], p["end"] = rec["start"], rec["end"]
    p["lookup_group"] = cordis_group(rec)
    p["orgs"] = [o["name"].title() for o in rec["orgs"]] + ([f"coordinator {rec['coordinator']}"] if rec["coordinator"] else [])
    p["nl_ec"] = [(o["name"].title(), o["ec"]) for o in rec["orgs"]]
    p["home_ec"] = sum(o["ec"] for o in rec["orgs"] if HOME_ORG.search(o["name"]))


if __name__ == "__main__":
    main()
