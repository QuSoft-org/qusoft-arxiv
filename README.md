# QuSoft papers

Finds every arXiv paper by current and former QuSoft members that names QuSoft (as an affiliation or supporter), and publishes them at **https://cschaffner.github.io/qusoft-arxiv/**.

The site has three parts:
- **Papers**: every paper, searchable. QuSoft authors are in bold with a small portrait (click one to see only their papers); alumni have a gold ring and their QuSoft years.
- **Research**: what QuSoft works on, in five research lines with 27 topics inferred from the papers (`data/topics.json`): papers per line per year, a network of how topics connect (with a year slider), papers per topic, and how many people publish in each line. Group-level only: no rankings or per-person counts.
- **Print**: tick papers and download their annotated first pages as one PDF for the message board. Each page has portraits, highlighted affiliations and a QR code.

## How it updates

A GitHub Action (`.github/workflows/update.yml`) runs every night:

1. It searches arXiv for each person in `people.csv`, but only for papers since that person's last search.
2. It downloads new candidates and keeps those that name QuSoft: anywhere on the first page, or on a later page as an affiliation, supporter or funder (many maths papers give the addresses after the references). A thank-you for discussions or hospitality doesn't count. Papers without it are remembered in `data/rejected_ids.json` and are not checked again; after changing this rule, run `python scripts/update.py --no-search --recheck-rejected`.
3. It also looks at other preprint servers: ECCC (complexity), IACR ePrint (cryptography), and SSRN and ChemRxiv (through Crossref). Papers there by QuSoft people, from their time at QuSoft, that aren't on arXiv are added when their PDF names QuSoft. ePrint, SSRN and ChemRxiv don't let scripts download PDFs, so those papers go on a list to check (`data/to_check.json`):

   ```bash
   python scripts/to_check.py                  # list the papers to check
   python scripts/to_check.py add eprint-2017-771
   python scripts/to_check.py reject eprint-2017-771
   ```

   Or save the PDF by hand as `cache/other_pdfs/<ID>.pdf` and run `python scripts/to_check.py pdfs`: it is then checked like an arXiv paper and used for the first page.
4. It makes the annotated first page (`site/firstpages/`) and a thumbnail (`site/thumbs/`) for each new paper.
5. It rebuilds `site/data/`, commits the changes and deploys `site/` to GitHub Pages.

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

A portrait goes in `qusofters/portraits/` as `firstname_lastname.jpg`. `scripts/download_portraits.py` fetches missing ones from the people page on qusoft.org and lists people whose photo there has changed; `--update` replaces those. Then run `python scripts/update.py --redo-pages` (or push, and let the nightly run pick it up for new papers only).

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
python scripts/internal_report.py              # management report → output/ (internal, not published)
python scripts/funding_report.py               # funding of PhD students and postdocs → output/ (internal)
python scripts/people_network.py               # co-author network as a local page → output/ (internal)
python scripts/people_lines.py                 # who works on what, per person → output/ (internal)
python scripts/topics.py discover|compare       # topic clusters; inferred vs. official research lines → output/ (internal)
python scripts/conference_talks.py             # QuSoft talks at QIP, QCrypt, TQC (from QuantumDB) → output/ (internal)

python -m http.server -d site                  # preview the site at http://localhost:8000
```

Settings such as portrait sizes, the QIP checkbox and search depth are in `config.yaml`.

## Files

| Path | What it is |
|---|---|
| `people.csv` | QuSoft people searched for (public) |
| `data/papers_database.json` | all QuSoft papers found |
| `data/search_state.json` | per person: last search date and the query that finds them |
| `data/to_check.json` | papers on other servers waiting to be checked, and the ones decided |
| `data/rejected_ids.json` | papers checked that don't name QuSoft |
| `qusoft/` | shared code: search, first pages, site data |
| `scripts/` | command-line tools above |
| `site/` | the website (HTML, CSS, JS, generated data and pages) |
| `cache/`, `output/`, `archive/` | local only, not in git |

## One-time GitHub setup

In the repository **Settings → Pages**, set *Source* to **GitHub Actions**. The first run searches every name variant for everyone once, which takes up to an hour. After that, each run takes a few minutes.
