#!/usr/bin/env python3
"""Funding of QuSoft PhD students and postdocs, for the management team (local only, never published).

Two sources:
  1. the Funding column of the private QuSoft spreadsheet, where it is filled in;
  2. the acknowledgements of the papers people wrote while at QuSoft (the cached PDFs).

An acknowledgement statement that names someone ("AK is funded through the Groeifonds
QDNL Cat-1 Program") counts for that person. A statement that names nobody ("This work
was supported by ...") counts only as weak evidence for every QuSoft author of that paper.
Funders are put into groups (QSC, QDNL, ERC, ...); see GROUPS below.

    python scripts/funding_report.py        # -> output/funding_report_<date>.xlsx

Run scripts/internal_report.py once first: it fetches the details and PDFs of the
members' papers that don't mention QuSoft, and this report reads those too.
"""

import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
from openpyxl import Workbook, load_workbook

from qusoft.common import is_alumnus, load_people, path
from internal_report import (CWI_UVA, QUSOFT_LATER, QUSOFT_ON_FIRST_PAGE, _pdf, _sheet, collect, membership,
                             was_member)

JUNIOR = {"PhD Students": "PhD student", "Postdocs": "Postdoc"}

# Funder groups, most specific first. Each statement can match several groups.
GROUPS = [
    ("QSC (NWO Gravitation Quantum Software Consortium)",
     r"Quantum\s+Software\s+Consortium|024\.003\.037|\bQSC\b"),
    ("QDNL (Quantum Delta NL, National Growth Fund)",
     r"Quantum\s*Delta|\bQDNL\b|Groeifonds|Growth\s+Fund|\bNGF\b|\b[CK]AT[- ]?[12]\b|Startimpuls"),
    ("NETWORKS (NWO Gravitation)", r"\bNETWORKS\b|024\.002\.003"),
    ("NWO Veni / Vidi / Vici", r"(?i:\bV(?:eni|idi|ici)\b)|Talent\s+(?:Programme|Program|Scheme)|\b639\.0[0-9]{2}\.\d"),
    ("ERC", r"\bERC\b|European\s+Research\s+Council"),
    ("EU projects (Horizon, Flagship, MSCA, doctoral networks)",
     r"Horizon\s*(?:2020|Europe)|European\s+Union|\bEU\b|Quantum\s+(?:Technologies\s+)?Flagship|Quantum\s+Internet\s+Alliance"
     r"|\bQIA\b|Marie\s+Sk|Marie\s+Curie|\bMSCA\b|Doctoral\s+(?:Training\s+)?Network|Quantum-Safe\s+Internet|\bQSI\b"),
    ("Other NWO / NWA projects",
     r"\bNWO\b|Dutch\s+Research\s+Council|Netherlands\s+Organi[sz]ation\s+for\s+Scientific\s+Research|\bNWA\b"
     r"|National\s+Research\s+Agenda|Wetenschapsagenda|\bQISS\b|Societal\s+Security|\bKLEIN\b|Open\s+Competition|Zwaartekracht"
     r"|Gravitation|Divide\s*(?:&|and)\s*Quantum|\bFOM\b|Foundation\s+for\s+Fundamental\s+Research\s+on\s+Matter|\bSTW\b"
     r"|Stichting\s+voor\s+de\s+Technische|Applied\s+and\s+Engineering\s+Sciences|\bTTW\b"),
    ("QuantERA (European co-fund)", r"QuantERA"),
    ("Dutch government and public-private (TKI, ministries, TNO)",
     r"\bTKI\b|Top\s*sector|Topconsortium|\bPPP\b|Holland\s+High\s+Tech|Ministry\s+of\s+(?:Economic|Education|Defen[cs]e)"
     r"|\bEZK\b|\bOCW\b|\bTNO\b|\bRVO\b|Rijksdienst"),
    ("Industry", r"\bIBM\b|Toyota|Google|Microsoft|Amazon|\bAWS\b|Fujitsu|\bIntel\b|Quantinuum|Huawei|\bING\b|Rabobank"
     r"|ABN\s*AMRO|Capgemini|Thales|Airbus|\bSAP\b|Shell|Bosch(?!\s+Stiftung)|Volkswagen"
     r"|Qblox|QphoX|Orange\s+Quantum|Delft\s+Circuits|QuantWare|Fermioniq|Single\s+Quantum|Quix|Q\*Bird|Alice\s*&\s*Bob"),
    ("CWI / UvA own funds", r"start-?up\s+package|\bCWI\b|Centrum\s+Wiskunde|University\s+of\s+Amsterdam|\bUvA\b|\bIvI\b|group\s+budget"),
    ("Funders abroad",
     r"\bDFG\b|Deutsche\s+Forschungsgemeinschaft|\bBMBF\b|Federal\s+Ministry|National\s+Science\s+Foundation|\bNSF\b|\bDOE\b"
     r"|Department\s+of\s+Energy|\bARO\b|AFOSR|DARPA|IARPA|EPSRC|UKRI|Royal\s+Society|Leverhulme|\bANR\b|Agence\s+Nationale"
     r"|\bSNSF\b|Swiss\s+National|\bNCCR\b|Villum|Novo\s+Nordisk|Carlsberg|\bJSPS\b|\bJST\b|NSERC|Simons\s+Foundation"
     r"|Sloan|Humboldt|Australian\s+Research\s+Council|Israel\s+Science\s+Foundation|NSFC|Natural\s+Science\s+Foundation\s+of\s+China"
     r"|\bFWO\b|FNRS|Wallenberg|Knut|Stiftung|Bochum|MICINN|Generalitat|\bFCT\b|Klaus\s+Tschira|\bQuSol\b|Excellence\s+Strategy"
     r"|Templeton|FQXi|Moore\s+Foundation|Army\s+Research\s+Office|Office\s+of\s+Naval\s+Research|\bONR\b"),
]
GROUP_RE = [(g, re.compile(p)) for g, p in GROUPS]
GROUP_RE_ANYCASE = [(g, re.compile(p, re.I)) for g, p in GROUPS]  # for the spreadsheet: "Cat-1", "Networks"
SPECIFIC_NWO = {GROUPS[0][0], GROUPS[1][0], GROUPS[2][0], GROUPS[3][0]}  # QSC, QDNL (NGF grants run via NWO), NETWORKS, Veni/Vidi/Vici
OTHER_NWO, EU = GROUPS[6][0], GROUPS[5][0]
FUNDING_WORDS = re.compile(r"support|fund|grant|financ|fellowship|scholarship|sponsor|project", re.I)
# A person is the subject of a statement when their name is followed by one of these words.
SUBJECT_NEXT = (r"(?=[\s,]*(?:and\b|&|,|\(|is\b|was\b|are\b|were\b|has\b|have\b|had\b|acknowledges?\b|acknowledged\b|thanks?\b"
                r"|gratefully\b|also\b|would\b|wishes\b|wants\b|received?\b|receives\b|holds\b|held\b|did\b|does\b|appreciates?\b"
                r"|completed\b|carried\b|performed\b|’s|'s))")
# A statement about some author we can't tell apart: "The fourth author is supported by ...".
SOMEONE = re.compile(r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|sixth|last|corresponding)\s+author\b", re.I)


def groups_in(text, rules=GROUP_RE):
    found = [g for g, rx in rules if rx.search(text)]
    if OTHER_NWO in found and SPECIFIC_NWO & set(found) and not re.search(r"\bNWA\b|QISS|KLEIN|Divide", text):
        found.remove(OTHER_NWO)  # "NWO Veni", "NWO Gravitation QSC": already in a specific group
    if EU in found and GROUPS[4][0] in found and not re.search(r"Horizon|Flagship|Marie|MSCA|QuantERA|Doctoral|QIA|Alliance", text):
        found.remove(EU)  # "ERC grant from the European Union"
    gov = GROUPS[8][0]
    if gov in found and set(found) & (SPECIFIC_NWO | {OTHER_NWO}):
        rest = re.sub(r"\bOCW\b|\bEZK\b|Ministry\s+of\s+(?:Economic\s+Affairs(?:\s+and\s+Climate(?:\s+Policy)?)?"
                      r"|Education,?\s+Culture\s+and\s+Science)|\bRVO\b|Rijksdienst\s+voor\s+Ondernemend\s+Nederland", "", text)
        if not re.search(GROUPS[8][1], rest):
            found.remove(gov)  # "Dutch Research Council (NWO/OCW)": the ministry funds NWO or QDNL
    return found


# ---------------------------------------------------------------------------
# Acknowledgements
# ---------------------------------------------------------------------------

ACK_HEADING = re.compile(r"(?im)^[\s\d.IVX]*(?:acknowledge?ments?|funding(?:\s+information)?)\b[.:]?")
ACK_END = re.compile(r"(?im)^[\s\d.IVX]*(?:references|bibliography|appendix|appendices|author\s+contributions"
                     r"|data\s+availability|competing\s+interests|code\s+availability|ai\s+disclosure)\b|^\s*\[1\]")
SENTENCE = re.compile(r"(?:(?<=[a-z0-9\)\]”\"])|(?<=[A-Z]{2}))\.\s+(?=[A-Z])")
FIRST_PAGE_FUNDING = re.compile(r"support|funded|funding|acknowledg|fellowship|scholarship|\bgrants?\b(?!\s+[A-Z][a-z]+\d)", re.I)
AFFIL_MARK = re.compile(r"[a-z\u00C0-\u017F][\d∗†‡*]+(?:,\s?[\d∗†‡*]+)*(?=[\s,])")  # "Cade†1, Niesen1": names with affiliation marks
DISCLAIMER = re.compile(r"views\s+and\s+opinions|do\s+not\s+necessarily\s+reflect|neither\s+the\s+European", re.I)


def _plain(text):
    text = unicodedata.normalize("NFKC", text)  # ligatures: "Scientiﬁc" -> "Scientific"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text)


def acknowledgement_statements(pdf):
    """Funding-related statements from the acknowledgements and the first page's footnotes."""
    try:
        with fitz.open(pdf) as doc:
            pages = [pg.get_text() for pg in doc]
    except Exception:
        return None
    full = "\n".join(pages)
    parts = []
    heads = list(ACK_HEADING.finditer(full))
    for h in heads[-2:]:  # e.g. "Acknowledgements" followed by a separate "Funding" section
        end = ACK_END.search(full, h.end())
        parts.append(full[h.end(): min(end.start() if end else len(full), h.end() + 5000)])
    if not heads:  # no heading: funding sentences anywhere before the references
        end = ACK_END.search(full)
        parts.append(full[: end.start() if end else len(full)])
    parts.append(pages[0] if pages else "")  # footnotes such as "∗Supported by ..."
    out = []
    for i, part in enumerate(parts):
        first_page = i == len(parts) - 1
        for s in SENTENCE.split(_plain(part)):
            s = s.strip()
            if first_page and (not FIRST_PAGE_FUNDING.search(s) or len(AFFIL_MARK.findall(s)) >= 2):
                continue
            if FUNDING_WORDS.search(s) and not DISCLAIMER.search(s) and groups_in(s) and s not in out and len(s) < 1500:
                out.append(s)
    return out


def _ascii(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def name_patterns(author):
    """Ways an author is named in acknowledgements: full name, 'A. Name', last name, initials."""
    words = [w for w in re.split(r"[\s]+", author.strip()) if w]
    if len(words) < 2:
        return []
    particles = {"van", "de", "der", "den", "von", "da", "di", "le", "la", "du", "ter", "te"}
    last_start = next((i for i, w in enumerate(words[1:], 1) if w.lower() in particles), len(words) - 1)
    first, last = words[0], " ".join(words[last_start:])
    letters = []
    for w in words:
        for piece in w.split("-"):
            if piece:
                letters.append(piece[0] if piece.lower() not in particles else piece[0].lower())
    variants = {"".join(letters), letters[0] + "".join(l for l in letters[1:] if l.isupper())}
    if len(letters) > 2:
        variants.add(letters[0] + letters[-1])
    pats = []
    for v in variants:
        if len(v) < 2:
            continue
        dotted = r"\.?\s?".join(map(re.escape, v)) + r"\.?"
        pats.append(r"(?<![A-Za-z])" + dotted + r"(?![A-Za-z])" + SUBJECT_NEXT)
    for full in {author, _ascii(author)}:
        pats.append(re.escape(full))
    for l in {last, _ascii(last)}:
        pats.append(r"(?<![A-Za-z])" + re.escape(first[0]) + r"\.\s?(?:[A-Z]\.\s?)*" + re.escape(l) + r"\b")
        pats.append(r"(?<![A-Za-z])" + re.escape(l) + r"\b" + SUBJECT_NEXT)
    return [re.compile(p) for p in pats]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _cell(value):
    text = " ".join(str(value or "").split())
    return "" if text.upper() in ("", "NA", "N/A", "-", "NONE") else text


def spreadsheet():
    """({name: funding text}, {name: [supervisors]}) from the private spreadsheet."""
    excel = path("database", "excel_file")
    funding, supervisors = {}, {}
    if not excel.exists():
        return funding, supervisors
    wb = load_workbook(excel, read_only=True, data_only=True)
    # Main sheet: name A, supervisors H-J, funding W. Alumni sheet: name A, supervisors F-H.
    for sheet, first_row, sup_cols, fund_col in (("QuSoft People Database", 3, (7, 8, 9), 22),
                                                 ("Alumni & On Hold", 2, (5, 6, 7), None)):
        if sheet not in wb.sheetnames:
            continue
        for row in wb[sheet].iter_rows(min_row=first_row, values_only=True):
            name = _cell(row[0] if row else None)
            if not name:
                continue
            sups = [re.sub(r"\s*\(.*?\)", "", _cell(row[c])) for c in sup_cols if c < len(row) and _cell(row[c])]
            if sups and not supervisors.get(name):
                supervisors[name] = sups
            if fund_col is not None and fund_col < len(row) and _cell(row[fund_col]) and name not in funding:
                funding[name] = _cell(row[fund_col])
    return funding, supervisors


# Grant names and numbers, as written in acknowledgements: "VI.Vidi.192.109", "NGF.1623.23.025",
# "OCENW.KLEIN.267", "024.003.037", "101040907", "ERC Consolidator Grant QPROGRESS".
GRANT_IDS = [
    re.compile(r"\b(?:[A-Z][A-Za-z]*\.)+[A-Za-z]*\.?\d+(?:\.\d+)+\b"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}\b"),
    re.compile(r"(?:agreement|grant|project)\s*(?:No\.?|number|nr\.?)?\s*[:#]?\s*(\d{6,9})\b", re.I),
    # EU numbers after the acronym: "ERC Consolidator Grant QPROGRESS 615307", "SYMOPTIC, 101040907"
    re.compile(r"(?:ERC|European|Horizon|Marie|MSCA)[^.;]{0,80}?(?<![\d./-])(\d{6,9})(?![\d./])"),
    re.compile(r"ERC[A-Za-z\s-]{0,30}?Grant\s+[“\"(]?([A-Z][A-Za-z0-9-]{2,}[A-Z0-9][A-Za-z0-9-]*)\b"),
    re.compile(r"ERC\s+(?:grant\s+)?[“\"(]?([A-Z][A-Z0-9-]{3,})\b"),
    re.compile(r"(?:grant|project|programme|program)[^“\"]{0,40}[“\"]([^”\"]{4,70})[”\"]", re.I),
]


def grant_ids(statement):
    found = []
    for rx in GRANT_IDS:
        for m in rx.finditer(statement):
            g = re.sub(r"^(?:No|Nr)\.?\s*", "", (m.group(1) if m.groups() else m.group(0)).strip(" .,;()“”\""))
            if g and g not in found and g.upper() not in ("ERC", "NWO", "EU", "QSC", "QDNL", "NO"):
                found.append(g)
    return found


def mentions(statement, person, author_names):
    """Does a statement mention this person (as author initials, or by name, e.g. "de Wolf's ERC grant")?"""
    on_paper = next((a for a in author_names if people_match(a, person)), None)
    pats = name_patterns(on_paper or person)
    last = person.split()[-1] if " " in person else person
    for w in person.split()[1:]:
        if w[:1].islower():  # "de Wolf", "van de Wetering"
            last = person[person.index(w):]
            break
    return any(p.search(statement) for p in pats) or re.search(r"(?<![A-Za-z])" + re.escape(last) + r"\b", statement)


def spreadsheet_groups(text):
    return groups_in(text, GROUP_RE_ANYCASE) or ["Other"]


def main():
    people = load_people()
    juniors = {n: i for n, i in people.items() if i["role"] in JUNIOR}
    spans, source = membership(people)
    sheet, supervisors = spreadsheet()

    rows, _ = collect(people)
    named = defaultdict(Counter)       # person -> group -> papers naming them with that funder
    grants = defaultdict(lambda: defaultdict(Counter))  # person -> group -> grant name/number -> papers
    pi_named = defaultdict(lambda: defaultdict(Counter))  # person -> group -> supervisor named alongside
    paperwide = defaultdict(Counter)   # person -> group -> papers with an unnamed statement
    checked = Counter()                # person -> papers read
    evidence = []
    unreadable = 0
    for r in rows:
        if r["kind"] not in (QUSOFT_ON_FIRST_PAGE, QUSOFT_LATER, CWI_UVA):
            continue  # no QuSoft, CWI or UvA on the paper: outside work, or a namesake
        who = [m for m in r["members"] if m in juniors and m not in r["unsure"]
               and was_member(spans[m], r["date"], is_alumnus(people[m]))]
        if not who:
            continue
        pdf = _pdf(r["id"])
        statements = acknowledgement_statements(pdf) if pdf else None
        if statements is None:
            unreadable += 1
            continue
        # Patterns for every author, so a statement about a co-author isn't read as unnamed.
        on_paper = {}
        for a in r["authors"]:
            on_paper[a] = name_patterns(a)
        member_name = {m: next((a for a in r["authors"] if people_match(a, m)), m) for m in who}
        for m in who:
            checked[m] += 1
        named_here, wide_here = defaultdict(set), set()
        for s in statements:
            subjects = {a for a, pats in on_paper.items() if any(p.search(s) for p in pats)}
            gs = groups_in(s)
            if not subjects and SOMEONE.search(s):
                continue  # about one author, but not which one
            if subjects:
                for m in who:
                    if member_name[m] in subjects:
                        named_here[m].update(gs)
                        ids = grant_ids(s)
                        sups = [p for p in supervisors.get(m, []) if mentions(s, p, r["authors"])]
                        for g in gs:
                            # With several funders in one statement, a grant id can't be tied to one of them.
                            if len(gs) == 1:
                                grants[m][g].update(set(ids))
                            pi_named[m][g].update(set(sups))
                        evidence.append([m, r["date"].isoformat(), f"https://arxiv.org/abs/{r['id']}", "; ".join(gs),
                                         "names them", s[:600]])
            else:
                wide_here.update(gs)
                for m in who:
                    evidence.append([m, r["date"].isoformat(), f"https://arxiv.org/abs/{r['id']}", "; ".join(gs),
                                     "names nobody", s[:600]])
        for m in who:
            named[m].update(named_here[m])
            paperwide[m].update(wide_here)

    # Per person: the spreadsheet where filled in, otherwise statements that name them,
    # otherwise the funder in most of their papers' unnamed statements (weak).
    per_person, by_group = [], defaultdict(lambda: {"PhD student": [], "Postdoc": []})
    pi_rows = []
    agree = disagree = 0
    for n, info in sorted(juniors.items()):
        role = JUNIOR[info["role"]]
        start, end = spans.get(n, (None, None))
        fmt = lambda c: ", ".join(f"{g.split(' (')[0]} ×{k}" for g, k in c.most_common())
        strong = named.get(n, Counter())
        weak = paperwide.get(n, Counter())
        papers = checked.get(n, 0)
        weak_main = [g for g, k in weak.most_common() if papers >= 2 and k >= 2 and k / papers >= 0.5]
        if n in sheet:
            used, basis = spreadsheet_groups(sheet[n]), "spreadsheet"
            if strong:
                if set(used) & set(strong):
                    agree += 1
                else:
                    disagree += 1
        elif strong:
            top = strong.most_common(1)[0][1]
            used, basis = [g for g, k in strong.most_common() if k >= max(1, top / 2)], "papers name them"
        elif weak_main:
            used, basis = weak_main[:2], "papers, not naming them (weak)"
        else:
            used, basis = ["Unknown"], "no information" if not papers else "papers say nothing usable"
        for g in used:
            by_group[g][role].append(n)
        sups = supervisors.get(n, [])
        per_person.append([n, role, ", ".join(sups), "alumni" if is_alumnus(info) else "current",
                           start.isoformat() if start else "", end.isoformat() if end else "",
                           sheet.get(n, ""), fmt(strong), fmt(weak), papers, "; ".join(used), basis])

        # Whose project: a supervisor named with the grant, or named in the spreadsheet's
        # funding text ("Florian's startup package"), otherwise the first supervisor.
        for g in used:
            named_pis = pi_named[n][g].most_common()
            text = sheet.get(n, "")
            in_text = [p for p in sups if re.search(r"\b(?:%s)\b" % "|".join(map(re.escape, p.split()[::max(1, len(p.split()) - 1)])), text)]
            if in_text and basis == "spreadsheet":
                pi, why = in_text[0], "named in the spreadsheet"
            elif named_pis:
                pi, why = named_pis[0][0], "named with the grant in a paper"
            elif in_text:
                pi, why = in_text[0], "named in the spreadsheet"
            elif sups:
                pi, why = sups[0], "first supervisor"
            else:
                pi, why = "(no supervisor in spreadsheet)", ""
            if basis == "spreadsheet":
                # "ERC, CAT-2": give each part to its own funding source.
                parts = [x.strip() for x in re.split(r"[,;]", text) if x.strip()]
                project = ", ".join(x for x in parts if g in spreadsheet_groups(x)) if len(used) > 1 else text
            else:
                ids = [k for k, _ in grants[n][g].most_common(3)]
                project = ", ".join(ids)
            pi_rows.append([pi, g.split(" (")[0], project, n, role,
                            start.isoformat() if start else "", end.isoformat() if end else "",
                            ", ".join(x for x in sups if x != pi), basis, why])
    pi_rows.sort(key=lambda r: (r[0].startswith("("), r[0], r[1], r[5] or "9999", r[3]))

    # One line per PI and funding source.
    summary = defaultdict(lambda: {"PhD student": [], "Postdoc": [], "projects": Counter(), "from": [], "to": []})
    for pi, g, project, n, role, frm, to, *_ in pi_rows:
        e = summary[(pi, g)]
        e[role].append(n)
        if project and basis_of(project):
            for item in re.split(r";\s*|,\s+", project):
                if item and item.upper() not in (g.split(" ")[0].upper(),):
                    e["projects"][item] += 1
        if frm:
            e["from"].append(frm)
        e["to"].append(to or "now")
    pi_summary = [[pi, g, ", ".join(p for p, _ in e["projects"].most_common()), len(e["PhD student"]), len(e["Postdoc"]),
                   min(e["from"])[:4] if e["from"] else "", "now" if "now" in e["to"] else max(e["to"])[:4],
                   ", ".join(e["PhD student"]), ", ".join(e["Postdoc"])]
                  for (pi, g), e in summary.items()]

    order = [g for g, _ in GROUPS] + ["Other", "Unknown"]
    per_group = []
    for g in order:
        if g in by_group:
            phd, pd = by_group[g]["PhD student"], by_group[g]["Postdoc"]
            per_group.append([g, len(phd), len(pd), ", ".join(phd), ", ".join(pd)])

    wb = Workbook()
    wb.remove(wb.active)
    note = (f"PhD students and postdocs in people.csv ({len(juniors)}). Funding from the spreadsheet where it is filled in "
            f"({sum(n in sheet for n in juniors)} people), otherwise inferred from the acknowledgements of their papers "
            f"written while at QuSoft. Someone funded from two sources counts in both. Generated {date.today()}.")
    _sheet(wb, "Per source", ["Funding source", "PhD students", "Postdocs", "PhD students (names)", "Postdocs (names)"],
           per_group, [48, 13, 10, 80, 80], note)
    _sheet(wb, "PI projects", ["PI", "Funding source", "Project or grant", "PhD students", "Postdocs", "From", "To",
                               "PhD students (names)", "Postdocs (names)"],
           pi_summary, [24, 30, 48, 13, 10, 8, 8, 60, 60],
           "Per PI and funding source: the PhD students and postdocs it paid for, and when. The PI is a supervisor named "
           "with the grant in a paper or in the spreadsheet, otherwise the first supervisor; see 'PI projects, people'.")
    _sheet(wb, "PI projects, people", ["PI", "Funding source", "Project or grant", "Person", "Role", "Start", "End",
                                       "Other supervisors", "Funding based on", "Why this PI"],
           pi_rows, [24, 30, 48, 24, 12, 11, 11, 34, 26, 30],
           "One line per person and funding source. Grant names and numbers come from the spreadsheet, "
           "or from acknowledgements that name the person.")
    _sheet(wb, "Per person", ["Name", "Role", "Supervisors", "Now", "Start", "End", "Spreadsheet says",
                              "Papers name them with (papers)", "Papers, not naming anyone (papers)", "Papers read",
                              "Funding source used", "Based on"],
           per_person, [24, 12, 34, 9, 11, 11, 34, 44, 50, 8, 44, 26],
           f"Membership dates: {source}. 'Papers name them' is the strongest evidence from the papers; "
           "the column after it lists funders thanked for the whole paper, which may belong to a co-author or the supervisor.")
    _sheet(wb, "Acknowledgements", ["Person", "Date", "Paper", "Funding groups", "Statement", "Text"],
           evidence, [24, 11, 32, 40, 13, 120],
           "Every funding statement found in the papers of each PhD student and postdoc, for checking.")
    out = Path(__file__).resolve().parent.parent / "output" / f"funding_report_{date.today()}.xlsx"
    out.parent.mkdir(exist_ok=True)
    wb.save(out)

    print(f"Wrote {out}")
    print(f"  {len(juniors)} PhD students and postdocs; {sum(checked.values())} paper-person pairs read, {unreadable} papers unreadable")
    print(f"  spreadsheet vs. papers naming them: {agree} agree, {disagree} disagree")
    for g, phd, pd, *_ in per_group:
        print(f"  {phd:3d} PhD, {pd:3d} postdocs  {g}")


def basis_of(project):
    return bool(project.strip())


_match_cache = {}


def people_match(author, member):
    """Is this author name on the paper the QuSoft member? Uses the same matcher as the site."""
    from qusoft.common import PersonMatcher
    if "m" not in _match_cache:
        _match_cache["m"] = PersonMatcher(load_people())
    return _match_cache["m"](author) == member


if __name__ == "__main__":
    main()
