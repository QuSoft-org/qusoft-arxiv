"""Config, people list, paper database and small helpers shared by all scripts."""

import csv
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()


def path(*keys):
    """Look up a path in config.yaml (e.g. path('paths', 'portraits_dir')), resolved from the repo root."""
    value = CONFIG
    for key in keys:
        value = value[key]
    return ROOT / value


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def normalize_name(name):
    """ASCII, lowercase, single spaces: 'Llorenç Escolà-Farràs' -> 'llorenc escola-farras'."""
    if not name:
        return ""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_name.lower().split())


def strip_parens(name):
    """'Junqiao (Randy) Lin' -> 'Junqiao Lin'."""
    return " ".join(re.sub(r"\([^)]*\)", " ", name).split())


def name_key(name):
    """Key for matching a person to an arXiv author name."""
    return normalize_name(strip_parens(name))


# ---------------------------------------------------------------------------
# People (people.csv)
# ---------------------------------------------------------------------------

PEOPLE_FIELDS = ["name", "role", "status", "start_year", "end_year"]


def load_people():
    """Return {name: {role, status, start_year, end_year}} from people.csv.

    status is 'active' or 'alumni'. Years are ints or None.
    """
    people = {}
    with open(path("database", "people_csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            if not name:
                continue
            people[name] = {
                "role": row["role"].strip() or "Unknown",
                "status": row["status"].strip().lower() or "active",
                "start_year": int(row["start_year"]) if row["start_year"].strip() else None,
                "end_year": int(row["end_year"]) if row["end_year"].strip() else None,
            }
    return people


def is_alumnus(info):
    return info.get("status") == "alumni"


def tenure(info):
    """'2018–2022' (or '2026' for a single year) for alumni, '' for current members or when years are unknown."""
    if not is_alumnus(info):
        return ""
    start, end = info.get("start_year"), info.get("end_year")
    if start and end:
        return str(end) if start == end else f"{start}–{end}"
    if end:
        return f"until {end}"
    return ""


def _tokens(name):
    """Name parts without initials: 'Alex B. Grilo' -> ['alex', 'grilo']."""
    return [t for t in name_key(name).replace("-", " ").split() if not (len(t) <= 2 and t.endswith("."))]


def is_same_person(a, b):
    """True if two spellings name the same person.

    Allows an extra trailing surname ('Garazi Muguruza' / 'Garazi Muguruza Lasa')
    and middle initials ('Alex B. Grilo' / 'Alex Grilo'), but needs at least a
    first name and one surname in common.
    """
    ta, tb = _tokens(a), _tokens(b)
    if ta == tb:
        return bool(ta)
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(shorter) >= 2 and longer[: len(shorter)] == shorter


class PersonMatcher:
    """Find which QuSoft person (if any) an arXiv author name belongs to."""

    def __init__(self, people):
        self.names = list(people)
        self.exact = {name_key(n): n for n in self.names}

    def __call__(self, author_name):
        hit = self.exact.get(name_key(author_name))
        if hit:
            return hit
        matches = [n for n in self.names if is_same_person(n, author_name)]
        return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# Portraits
# ---------------------------------------------------------------------------

def find_portrait(name):
    """Find a portrait file for a person, or None.

    Portraits are named like 'christian_schaffner.jpg'. An exact match wins over
    a partial one, so 'sebastian_verschoor' doesn't pick 'sebastian_r_verschoor'.
    """
    folder = path("paths", "portraits_dir")
    if not folder.exists():
        return None
    key = name_key(name).replace(" ", "_").replace(".", "")
    candidates = [p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    for p in candidates:
        if normalize_name(p.stem).replace(" ", "_") == key:
            return p
    for p in candidates:
        if key in normalize_name(p.stem):
            return p
    return None


# ---------------------------------------------------------------------------
# Paper database (data/papers_database.json)
# ---------------------------------------------------------------------------

def base_id(arxiv_id):
    """'2512.16974v1' -> '2512.16974'."""
    return re.sub(r"v\d+$", "", arxiv_id)


def load_json(file, default):
    try:
        with open(file, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(file, data):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    tmp.replace(file)


def load_papers():
    return load_json(path("database", "papers_db"), {"papers": []})["papers"]


def save_papers(papers):
    papers = sorted(papers, key=lambda p: p["submitted"], reverse=True)
    save_json(path("database", "papers_db"), {
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "total_papers": len(papers),
        "papers": papers,
    })


def paper_date(paper):
    return datetime.strptime(paper["submitted"][:10], "%Y-%m-%d").date()


def filter_papers(papers, year=None, month=None, start_date=None, end_date=None, authors=None):
    """Filter by submission date (year=2025, month='2025-10', ISO start/end dates) and QuSoft authors."""
    result = []
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    for p in papers:
        d = paper_date(p)
        if year and d.year != int(year):
            continue
        if month and d.strftime("%Y-%m") != month:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        if authors and not set(authors) & set(p.get("qusoft_authors", [])):
            continue
        result.append(p)
    return result
