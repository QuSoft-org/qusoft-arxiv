#!/usr/bin/env python3
"""Who works on what: QuSoft people by research line and topic (internal, never published).

    python scripts/people_lines.py      # -> output/people_lines.html (open it in a browser)

For each person: how their QuSoft papers spread over the five research lines, and their
most frequent topics (from data/topics.json). People are grouped by the line most of their
papers are in. Per-person counts are for the management team only.
"""

import base64
import html
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qusoft.common import is_alumnus, load_papers, load_people, name_key, tenure

ROOT = Path(__file__).resolve().parent.parent
COLORS = {1: "#2a6fb0", 2: "#c8721f", 3: "#1f9a8a", 4: "#8e4a9c", 5: "#5d8f1f"}
ROLE = {"PhD Students": "PhD student", "Postdocs": "postdoc", "Senior Researchers": "senior researcher",
        "Support Team": "support team", "Visitor": "visitor", "Turing Chair": "Turing chair"}


def portrait(name):
    f = ROOT / "site" / "portraits" / f"{name_key(name).replace(' ', '-')}.webp"
    return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode() if f.exists() else None


def main():
    topics = json.loads((ROOT / "data" / "topics.json").read_text())
    lines = topics["taxonomy"]["lines"]
    tname = {t["id"]: t["name"] for l in lines for t in l["topics"]}
    people = load_people()
    per_line, per_topic = {}, {}
    for p in load_papers():
        tag = topics["papers"].get(p["id"])
        if not tag or tag["line"] == "other":
            continue
        for q in set(p["qusoft_authors"]):
            per_line.setdefault(q, Counter())[tag["line"]] += 1
            per_topic.setdefault(q, Counter()).update(tag["topics"])

    groups = {l["id"]: [] for l in lines}
    for q, c in per_line.items():
        groups[c.most_common(1)[0][0]].append(q)

    W = 220
    out = []
    for l in lines:
        members = sorted(groups[l["id"]], key=lambda q: (is_alumnus(people.get(q, {})), q.split()[-1]))
        if not members:
            continue
        out.append(f'<h2><span class="sw" style="background:{COLORS[l["slot"]]}"></span>{html.escape(l["name"])}'
                   f' <small>{len(members)} people whose papers are mostly in this line</small></h2><ol>')
        for q in members:
            c, total = per_line[q], sum(per_line[q].values())
            x, bars = 0, []
            for k in lines:
                v = c.get(k["id"], 0)
                if v:
                    w = W * v / total
                    bars.append(f'<rect x="{x:.1f}" width="{max(w - 2, 1):.1f}" height="12" rx="2" fill="{COLORS[k["slot"]]}">'
                                f'<title>{html.escape(k["name"])}: {v}</title></rect>')
                    x += w
            info = people.get(q, {})
            who = f"alumni {tenure(info)}".strip() if is_alumnus(info) else ROLE.get(info.get("role"), "")
            img = portrait(q)
            face = f'<img src="{img}" alt="">' if img else '<span class="noimg"></span>'
            tops = ", ".join(tname.get(t, t) for t, _ in per_topic[q].most_common(3))
            out.append(f'<li class="{"alum" if is_alumnus(info) else ""}">{face}<div><strong>{html.escape(q)}</strong> '
                       f'<span class="who">{html.escape(who)}</span><br><span class="tops">{html.escape(tops)}</span></div>'
                       f'<svg viewBox="0 0 {W} 12" width="{W}" height="12" role="img" aria-label="{total} papers">{"".join(bars)}</svg>'
                       f'<span class="n">{total}</span></li>')
        out.append("</ol>")

    legend = " ".join(f'<span><span class="sw" style="background:{COLORS[l["slot"]]}"></span>{html.escape(l["name"])}</span>'
                      for l in lines)
    page = PAGE.replace("<!--LEGEND-->", legend).replace("<!--BODY-->", "\n".join(out)).replace("<!--DATE-->", str(date.today()))
    f = ROOT / "output" / "people_lines.html"
    f.parent.mkdir(exist_ok=True)
    f.write_text(page, encoding="utf-8")
    print(f"Wrote {f}: {len(per_line)} people")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuSoft people by research line (internal)</title>
<style>
:root{--paper:#F7F8F9;--ink:#2E353C;--slate:#626C75;--rule:#D5DADF;--gold:#C1AB47}
@media (prefers-color-scheme:dark){:root{--paper:#1B2026;--ink:#E6E9EC;--slate:#9AA4AE;--rule:#3A434C;--gold:#D4C26A}}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.45 system-ui,sans-serif}
main{max-width:64rem;margin:0 auto;padding:2rem 16px 4rem}
h1{font-weight:500;margin:0 0 .4rem}
.note{color:var(--slate);font-size:.85rem;max-width:70ch}
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1.2rem;font-size:.85rem;margin:1rem 0 2rem}
.sw{display:inline-block;width:.75rem;height:.75rem;border-radius:3px;margin-right:.4rem;vertical-align:-.05em}
h2{font-weight:500;font-size:1.25rem;margin:2.5rem 0 .6rem;display:flex;align-items:center;gap:.2rem;flex-wrap:wrap}
h2 small{color:var(--slate);font-size:.8rem;font-weight:400;margin-left:.6rem}
ol{list-style:none;padding:0;margin:0}
li{display:grid;grid-template-columns:2.2rem 1fr 220px 2rem;gap:.75rem;align-items:center;padding:.4rem 0;border-bottom:1px solid var(--rule)}
li img,.noimg{width:2.2rem;height:2.2rem;border-radius:50%;object-fit:cover;border:1.5px solid var(--slate);display:block;box-sizing:border-box;background:var(--rule)}
li.alum img,li.alum .noimg{border:2px solid var(--gold)}
.who{color:var(--slate);font-size:.85rem}
.tops{color:var(--slate);font-size:.8rem}
.n{color:var(--slate);font-size:.85rem;text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:640px){li{grid-template-columns:2.2rem 1fr 2rem}li svg{grid-column:2/4}}
</style></head><body><main>
<h1>Who works on what</h1>
<p class="note">Internal to the QuSoft management team; not on the public site. Made <!--DATE--> from the papers on the site and their
research lines (inferred from titles and abstracts, tagged with AI). Each person is listed under the line most of their QuSoft papers
are in; the bar shows how their papers spread over the lines, the number is their papers on the site, and the grey text their most
frequent topics. Current members first, then alumni (gold ring).</p>
<p class="legend"><!--LEGEND--></p>
<!--BODY-->
</main></body></html>
"""


if __name__ == "__main__":
    main()
