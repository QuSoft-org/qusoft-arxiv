# Make the site readable for AI systems and other crawlers (light version)

## Context

The site is one page that builds everything with JavaScript from `site/data/*.json`, with sections as `#papers`, `#theses` etc. Crawlers that don't run JavaScript (most AI crawlers: GPTBot, ClaudeBot, PerplexityBot, Common Crawl) get only the navigation and "Loading papers…", and crawlers ignore everything after `#`, so the whole site is one URL. There is no sitemap, no structured data, no link previews, no `llms.txt`. `robots.txt` would have to live at `qusoft-org.github.io/robots.txt`, outside this repository.

What only this site has is the collection: which papers come from QuSoft, the plain-language summaries, the research lines and topics, and the theses. Decided with the user: **static index pages, no page per paper or thesis**; **AI-written summaries included, clearly labelled**.

## Approach

Generate plain HTML and text at build time in `qusoft/site_build.py`, from the same data `build()` and `build_theses()` already produce. The interactive app is unchanged.

1. **Static index pages** (new `build_static()` called at the end of `build()`)
   - `site/archive/papers-<year>.html`, one per year (one page for all 493 would be ~1.5 MB): each paper with title, authors (QuSoft people marked), date, abstract, the two plain-language summaries labelled "Plain-language summary written with AI; not checked by the authors", topics, link to the paper (arXiv/ePrint/…).
   - `site/archive/theses.html`: every thesis with author, year, promotors, abstract, both summaries (labelled), links to PDF and repository page, cover image.
   - `site/archive/research.html`: the five research lines and their topics with descriptions (from `data/topics.json`), group level only.
   - `site/archive/index.html`: what the site is, links to all of the above and to the data files.
   - Each page: `<title>`, meta description, canonical, Open Graph, and JSON-LD (`ItemList` of `ScholarlyArticle` / `Thesis` items whose `url` is the paper or thesis itself; authors as `Person`, QuSoft as `ResearchOrganization`). Minimal styling reusing the tokens in `site/style.css`, readable at phone width; a link back to the interactive site.
   - Stdlib only (`html.escape`, `json`); no new dependency.
2. **Home page `site/index.html`**
   - Meta description (exists), canonical, Open Graph + Twitter card (image: QuSoft logo or a first-page thumbnail), JSON-LD `WebSite` + `ResearchOrganization` + `Dataset` (pointing at `data/papers.json`, `data/theses.json`, `data/topics.json`).
   - `<noscript>` with a short description and links to the archive pages; footer link "Plain archive and data" so crawlers on the home page find them.
3. **Machine-readable entry points**
   - `site/sitemap.xml`: home page and archive pages, with `lastmod` from the build date.
   - `site/llms.txt`: what the site is, how it's made (and that summaries are AI-written), links to archive pages and JSON. `site/llms-full.txt`: all papers and theses as Markdown (title, authors, year, link, plain summary labelled).
4. **README**: short section on the archive pages, sitemap and llms files; mention submitting `sitemap.xml` once in Google Search Console and Bing Webmaster Tools (no root `robots.txt` to point at it). The nightly Action already runs `site_build` and commits `site/`, so it needs no change.

Project rules kept: group-level only, no per-person counts or rankings anywhere (no author lists with totals).

## Files

- `qusoft/site_build.py` — `build_static()` and small template helpers; called from `build()`.
- `site/index.html` — meta tags, JSON-LD, `<noscript>`, footer link.
- `site/archive/archive.css` (or inline in each page), `README.md`.

## Verification

- `python scripts/update.py --no-search --no-other-servers`; check `git status` only shows the intended files (revert timestamp-only changes if needed).
- `python -m http.server -d site`; `curl` home page and archive pages: paper titles, abstracts and labelled summaries present without JavaScript; `sitemap.xml`, `llms.txt`, `llms-full.txt` served.
- Validate one page's JSON-LD (schema.org validator) and the Open Graph preview after deploy.
- Look at an archive page in Chrome at desktop and phone width; check the app's tabs and deep links still work.
- Commit and push (the user has been asking for commit + push after changes; confirm before pushing).
