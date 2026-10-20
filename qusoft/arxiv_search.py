"""Search arXiv for papers by QuSoft people.

Names with accents or parentheses are hard to find through the arXiv API, so
each person gets a list of query variants (see generate_search_queries). The
first variant that returns a paper by that person is remembered in the search
state, so daily runs need only one query per person.
"""

import time
from datetime import date, timedelta

import arxiv

from .common import CONFIG, base_id, is_same_person, normalize_name, strip_parens


def generate_search_queries(person):
    """Query variants for one person, most specific first."""
    plain = strip_parens(person)
    queries = []
    for variant in dict.fromkeys([plain, person]):  # without parentheses first
        queries += [f'au:"{variant}"', f"au:{variant}"]

    # Accent-free combinations of the distinctive name parts, for names the API mangles.
    parts = [normalize_name(p).title() for p in plain.replace("-", " ").split() if len(p) > 3]
    if len(parts) >= 2:
        first = parts[0]
        for other in parts[1:]:
            queries.append(f"{first} AND {other[:5]}")
            queries.append(f'au:"{first} {other}"')
    return list(dict.fromkeys(queries))


def make_entry(result, match_person):
    """Turn an arxiv.Result into a paper entry. match_person is a common.PersonMatcher."""
    authors, qusoft_authors = [], []
    for author in result.authors:
        person = match_person(author.name)
        if person and person not in qusoft_authors:
            qusoft_authors.append(person)
        authors.append({"name": author.name, "person": person})
    arxiv_id = result.entry_id.split("/")[-1]
    return {
        "id": arxiv_id,
        "link": f"https://arxiv.org/abs/{base_id(arxiv_id)}",
        "title": " ".join(result.title.split()),
        "authors": authors,
        "qusoft_authors": qusoft_authors,
        "submitted": str(result.published.replace(tzinfo=None)),
        "revision": str(result.updated.replace(tzinfo=None)),
        "categories": result.categories,
        "abstract": " ".join(result.summary.split()),
        "pdf_url": result.pdf_url,
    }


class Searcher:
    def __init__(self):
        self.client = arxiv.Client(page_size=CONFIG["search"]["max_results"], delay_seconds=CONFIG["search"]["rate_limit_delay"])
        self.delay = CONFIG["search"]["rate_limit_delay"]

    def _run(self, query, since, until):
        window = f"submittedDate:[{since:%Y%m%d}0000 TO {until:%Y%m%d}2359]"
        search = arxiv.Search(
            query=f"({query}) AND {window}",
            max_results=CONFIG["search"]["max_results"],
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        try:
            return list(self.client.results(search))
        finally:
            time.sleep(self.delay)

    def search_person(self, person, state):
        """Search one person's new papers. Updates `state` (that person's entry) in place.

        Returns a list of arxiv.Result written by this person.
        """
        today = date.today()
        if state.get("last_checked"):
            since = date.fromisoformat(state["last_checked"]) - timedelta(days=CONFIG["search"]["overlap_days"])
        else:
            since = today - timedelta(days=365 * CONFIG["search"]["years_back"])

        known = state.get("query")
        queries = generate_search_queries(person)
        if known:
            queries = [known]
        elif state.get("all_variants_tried") and today - date.fromisoformat(state["all_variants_tried"]) < timedelta(days=7):
            # Nothing found with any variant recently: only the main query daily, all variants weekly.
            queries = queries[:1]
        else:
            state["all_variants_tried"] = today.isoformat()
        found = []
        for query in queries:
            try:
                results = self._run(query, since, today)
            except Exception as e:  # network hiccups shouldn't stop the whole run
                print(f"    query failed ({query}): {e}")
                return None
            found = [r for r in results if any(is_same_person(person, a.name) for a in r.authors)]
            if found:
                state["query"] = query
                break
        state["last_checked"] = today.isoformat()
        return found


def fetch_by_ids(ids):
    """Metadata for specific arXiv ids."""
    client = arxiv.Client()
    return list(client.results(arxiv.Search(id_list=[base_id(i) for i in ids])))
