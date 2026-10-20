# QuSoft papers

Finds every arXiv paper by current and former QuSoft members that mentions QuSoft on its first page, and publishes them at **https://cschaffner.github.io/qusoft-arxiv/**.

The site has three parts:
- **Papers**: every paper, searchable. QuSoft authors are in bold, and alumni are underlined in gold with their QuSoft years.
- **People**: who has written with whom, plus a few numbers per year. These are group-level only: no rankings or per-person counts.
- **Print**: tick papers and download their annotated first pages as one PDF for the message board. Each page has portraits, highlighted affiliations and a QR code.

## How it updates

A GitHub Action (`.github/workflows/update.yml`) runs every night:

1. It searches arXiv for each person in `people.csv`, but only for papers since that person's last search.
2. It downloads new candidates and keeps those with "QuSoft" on the first page. Papers without it are remembered in `data/rejected_ids.json` and are not checked again.
3. It makes the annotated first page (`site/firstpages/`) and a thumbnail (`site/thumbs/`) for each new paper.
4. It rebuilds `site/data/`, commits the changes and deploys `site/` to GitHub Pages.

To run it now, go to **Actions → Daily update → Run workflow**.

## Adding or updating people

`people.csv` is the list the search uses. It holds only what's fine to publish:

```
name,role,status,start_year,end_year
Yfke Dulek,PhD Students,alumni,2016,2022
```

`status` is `active` or `alumni`. The site shows years only for alumni. You can edit the file directly on GitHub; pushing a change rebuilds the site. The person's papers are found on the next nightly run.

Or regenerate it from the private spreadsheet (people with *Featured on Page = Yes*):

```bash
python scripts/excel_to_people_csv.py
```

A portrait goes in `qusofters/portraits/` as `firstname_lastname.jpg`. `scripts/download_portraits.py` fetches missing ones from qusoft.org.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/update.py                       # same as the nightly run
python scripts/update.py --authors "Name"      # search only some people
python scripts/update.py --no-search           # rebuild missing first pages and site data
python scripts/update.py --redo-pages          # remake all first pages (after changing their layout)

python scripts/make_booklet.py --year 2025     # one PDF of first pages → output/
python scripts/export_excel.py --year 2025     # Excel list → output/

python -m http.server -d site                  # preview the site at http://localhost:8000
```

Settings such as portrait sizes, the QIP checkbox and search depth are in `config.yaml`.

## Files

| Path | What it is |
|---|---|
| `people.csv` | QuSoft people searched for (public) |
| `data/papers_database.json` | all QuSoft papers found |
| `data/search_state.json` | per person: last search date and the query that finds them |
| `data/rejected_ids.json` | papers checked without QuSoft on the first page |
| `qusoft/` | shared code: search, first pages, site data |
| `scripts/` | command-line tools above |
| `site/` | the website (HTML, CSS, JS, generated data and pages) |
| `cache/`, `output/`, `archive/` | local only, not in git |

## One-time GitHub setup

In the repository **Settings → Pages**, set *Source* to **GitHub Actions**. The first run searches every name variant for everyone once, which takes up to an hour. After that, each run takes a few minutes.
