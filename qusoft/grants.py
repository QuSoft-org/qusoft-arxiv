"""Grant lookups for the internal funding reports: NWO's project database and CORDIS (EU).

NWO: the open NWOpen API (projects, schemes, members and their organisations; no amounts).
     It also holds the National Growth Fund grants (QDNL, "NGF.…").
CORDIS: the EU's project dumps for FP7, Horizon 2020 and Horizon Europe, with € per participant.
     They are downloaded once into cache/funding/cordis/.

Everything is cached in cache/funding/, which is not in git.
"""

import csv
import io
import re
import time
import unicodedata
import zipfile
from pathlib import Path

import requests

from .common import ROOT, load_json, save_json

CACHE = ROOT / "cache" / "funding"
NWO_API = "https://nwopen-api.nwo.nl/NWOpen-API/api/Projects"
CORDIS_ZIPS = {
    "FP7": "https://cordis.europa.eu/data/cordis-fp7projects-csv.zip",
    "H2020": "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
    "HORIZON": "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip",
}
UA = {"User-Agent": "qusoft-arxiv internal funding report (https://github.com/cschaffner/qusoft-arxiv)"}
PARTICLES = {"van", "de", "der", "den", "von", "da", "di", "le", "la", "du", "ter", "te", "del", "dos", "das"}

# Small or non-research NWO schemes, left out of "projects".
NWO_SKIP = re.compile(r"open access|rekentijd|computing time|computer time|visitor|bezoekers|reisbeurs|travel|congres"
                      r"|conference|meeting|summer school|incentive fund|stimulerings|internationalisering", re.I)


def _ascii(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def core_last_name(name):
    """'Ronald de Wolf' -> 'wolf', 'Paola Gori-Giorgi' -> 'gori-giorgi'."""
    words = [w for w in re.sub(r"\(.*?\)", " ", name).split() if w]
    rest = [w for w in words[1:] if w.lower() not in PARTICLES]
    return _ascii(rest[-1] if rest else words[-1])


def first_name(name):
    return _ascii(name.split()[0]) if name.split() else ""


# ---------------------------------------------------------------------------
# NWO
# ---------------------------------------------------------------------------

class NWO:
    def __init__(self):
        self.file = CACHE / "nwo.json"
        self.data = load_json(self.file, {"projects": {}, "members": {}})
        self.dirty = 0

    def save(self):
        save_json(self.file, self.data)
        self.dirty = 0

    def _get(self, **params):
        out, page = [], 1
        while True:
            for attempt in range(4):
                try:
                    r = requests.get(NWO_API, params={**params, "per_page": 100, "page": page}, headers=UA, timeout=60)
                    if r.ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(5 * (attempt + 1))
            else:
                return None
            d = r.json()
            out += [_slim(p) for p in d.get("projects", [])]
            if page >= (d.get("meta", {}).get("pages") or 1):
                return out
            page += 1
            time.sleep(0.5)

    def project(self, pid):
        """The NWO project with this id (or None). Tries the id as written, then without spaces."""
        key = pid.strip()
        if key not in self.data["projects"]:
            found = self._get(project_id=key)
            if found is None:
                return None  # network trouble: try again next run
            self.data["projects"][key] = found[0] if found else None
            self.dirty += 1
            if self.dirty >= 20:
                self.save()
        return self.data["projects"][key]

    def by_member(self, name):
        """NWO projects that list this person (matched on core surname and first name or initial)."""
        last = core_last_name(name)
        if last not in self.data["members"]:
            found = self._get(member_last_name=last)
            if found is None:
                return []
            self.data["members"][last] = found
            self.dirty += 1
            if self.dirty >= 20:
                self.save()
        hits = []
        for p in self.data["members"][last]:
            roles = [m for m in p["members"] if member_is(m, name)]
            if roles:
                hits.append((p, roles))
        return hits


def _slim(p):
    members = [{"role": m.get("role", ""), "first": m.get("first_name") or "", "last": m.get("last_name") or "",
                "initials": m.get("initials") or "", "org": m.get("organisation") or ""}
               for m in p.get("project_members") or []]
    return {"id": p.get("project_id"), "title": p.get("title") or "", "scheme": p.get("funding_scheme") or "",
            "start": (p.get("start_date") or "")[:10], "end": (p.get("end_date") or "")[:10],
            "parent": p.get("parent_project_id") or "", "members": members}


def member_is(member, name):
    if _ascii(member["last"]).split()[-1:] != [core_last_name(name)] and _ascii(member["last"]) != core_last_name(name):
        return False
    first = first_name(name)
    if member["first"]:
        f = _ascii(member["first"])
        return f == first or f.split()[0] == first or (len(f) <= 2 and f[0] == first[0])
    return bool(member["initials"]) and _ascii(member["initials"])[:1] == first[:1]


def nwo_group(project):
    """Funder group (as in funding_report.GROUPS) for an NWO project."""
    pid, scheme = project["id"] or "", project["scheme"]
    if pid.startswith("024.003.037") or project.get("parent", "").startswith("024.003.037"):
        return "QSC (NWO Gravitation Quantum Software Consortium)"
    if pid.startswith("024.002.003") or project.get("parent", "").startswith("024.002.003"):
        return "NETWORKS (NWO Gravitation)"
    if re.search(r"\bNGF\b|Groeifonds|Quantum Delta", scheme) or pid.startswith("NGF"):
        return "QDNL (Quantum Delta NL, National Growth Fund)"
    if re.search(r"Veni|Vidi|Vici|Vernieuwingsimpuls|Talent", scheme, re.I) or re.match(r"VI\.", pid):
        return "NWO Veni / Vidi / Vici"
    if re.search(r"QuantERA", scheme, re.I):
        return "QuantERA (European co-fund)"
    return "Other NWO / NWA projects"


def looks_like_nwo(gid):
    return bool(re.fullmatch(r"(?:[A-Za-z][A-Za-z-]*\.)+[A-Za-z]*\.?\d+(?:\.\d+)+|\d{3}\.\d{3}\.\d{3}|\d{3}\.\d{2,3}\.\d{2,3}"
                             r"|\d{3}-\d{2}-\d{3}|\d{3}\.\d{3}", gid))


# ---------------------------------------------------------------------------
# CORDIS
# ---------------------------------------------------------------------------

def _download_cordis():
    folder = CACHE / "cordis"
    folder.mkdir(parents=True, exist_ok=True)
    for fp, url in CORDIS_ZIPS.items():
        z = folder / f"{fp}.zip"
        if not z.exists():
            print(f"  downloading CORDIS {fp}")
            r = requests.get(url, headers=UA, timeout=600)
            r.raise_for_status()
            z.write_bytes(r.content)
    return folder


def _euro(s):
    try:
        return float((s or "0").replace(",", "."))
    except ValueError:
        return 0.0


QUANTUM = re.compile(r"quantum|qubit", re.I)


class Cordis:
    """EU projects: id -> {acronym, title, start, end, scheme, programme, quantum, orgs: [Dutch participants]}."""

    def __init__(self):
        slim = CACHE / "cordis_slim.json"
        cached = load_json(slim, None)
        if cached:
            self.projects = cached
            self._index()
            return
        folder = _download_cordis()
        self.projects = {}
        for fp in CORDIS_ZIPS:
            with zipfile.ZipFile(folder / f"{fp}.zip") as z:
                with z.open("project.csv") as f:
                    for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";"):
                        text = " ".join([row.get("title", ""), row.get("keywords", ""), row.get("objective", "")[:3000]])
                        self.projects[row["id"]] = {
                            "id": row["id"], "acronym": row["acronym"], "title": row["title"],
                            "start": row["startDate"], "end": row["endDate"],
                            "scheme": f'{row["fundingScheme"]} {row["masterCall"]}'.strip(),
                            "programme": fp, "total_ec": _euro(row["ecMaxContribution"]),
                            "quantum": bool(QUANTUM.search(text)), "orgs": [], "coordinator": ""}
                with z.open("organization.csv") as f:
                    for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";"):
                        p = self.projects.get(row["projectID"])
                        if not p:
                            continue
                        if row["role"] == "coordinator":
                            p["coordinator"] = f'{row["name"]} ({row["country"]})'
                        if row["country"] == "NL":
                            p["orgs"].append({"name": row["name"], "role": row["role"],
                                              "ec": _euro(row["ecContribution"]) or _euro(row["netEcContribution"])})
        save_json(slim, self.projects)
        self._index()

    def _index(self):
        self.by_acronym = {}
        for p in self.projects.values():
            self.by_acronym.setdefault(p["acronym"].upper(), []).append(p["id"])

    def get(self, gid):
        if re.fullmatch(r"\d{6,9}", gid):
            return self.projects.get(gid)
        ids = self.by_acronym.get(gid.upper(), [])
        erc = [i for i in ids if "ERC" in self.projects[i]["scheme"]]
        return self.projects[erc[0]] if len(erc) == 1 else (self.projects[ids[0]] if len(ids) == 1 else None)


def cordis_group(project):
    if "ERC" in project["scheme"]:
        return "ERC"
    if "QUANTERA" in project["acronym"].upper():
        return "QuantERA (European co-fund)"
    return "EU projects (Horizon, Flagship, MSCA, doctoral networks)"


def erc_type(project):
    """'ERC StG' etc. from CORDIS funding schemes such as 'ERC-STG' or 'HORIZON-ERC'."""
    s = project["scheme"].upper()
    for code, label in (("STG", "Starting"), ("COG", "Consolidator"), ("ADG", "Advanced"), ("SYG", "Synergy"),
                        ("POC", "Proof of Concept")):
        if code in s:
            return f"ERC {label}"
    return "ERC" if "ERC" in s else ""
