#!/usr/bin/env python3
"""Local interactive HTML overview of the funding reports (internal, never published).

Reads the newest output/funding_landscape_<date>.json and output/centres_comparison_<date>.json
and writes output/funding_overview.html, a single file to open in a browser.

    python scripts/funding_landscape.py
    python scripts/compare_centres.py        # optional; the comparison tab says so when missing
    python scripts/funding_overview.py       # -> output/funding_overview.html
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
TEMPLATE = Path(__file__).resolve().parent / "templates" / "funding_overview.html"


def newest(prefix):
    files = sorted(OUT.glob(f"{prefix}_*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def as_js(data):
    # Safe inside <script>: no "</script>" or HTML comment openers in the JSON.
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def main():
    landscape = newest("funding_landscape")
    if not landscape:
        sys.exit("Run scripts/funding_landscape.py first.")
    comparison = newest("centres_comparison")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*LANDSCAPE*/null", as_js(landscape)).replace("/*COMPARISON*/null", as_js(comparison))
    out = OUT / "funding_overview.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}" + ("" if comparison else " (no comparison yet)"))


if __name__ == "__main__":
    main()
