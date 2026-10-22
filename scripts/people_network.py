#!/usr/bin/env python3
"""Co-author network of QuSoft people, as one local web page (internal, never published).

The network shows who has written with whom, with a year slider. Its separate clusters
single people out, so it is for the management team only, not for the public site.

    python scripts/people_network.py      # -> output/people_network.html (open it in a browser)

The page is self-contained (data and portraits inside); it loads d3 and fonts from the web.
"""

import base64
import json
import sys
from collections import Counter
from datetime import date
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qusoft.common import is_alumnus, load_papers, load_people, name_key, tenure

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://cschaffner.github.io/qusoft-arxiv/"


def portrait_uri(name):
    web = ROOT / "site" / "portraits" / f"{name_key(name).replace(' ', '-')}.webp"
    if not web.exists():
        return None
    return "data:image/webp;base64," + base64.b64encode(web.read_bytes()).decode()


def build():
    people, papers = load_people(), load_papers()
    on_papers = sorted({n for p in papers for n in p["qusoft_authors"]})
    nodes = {n: {"role": people.get(n, {}).get("role", ""), "alumni": is_alumnus(people.get(n, {})),
                 "years": tenure(people.get(n, {})), "portrait": portrait_uri(n)} for n in on_papers}
    pairs = Counter()
    for p in papers:
        for a, b in combinations(sorted(set(p["qusoft_authors"])), 2):
            pairs[(a, b)] += 1
    data = {
        "people": nodes,
        "papers": [[p["submitted"][:10], sorted(set(p["qusoft_authors"]))] for p in papers],
        "edges": [[a, b] for a, b in sorted(pairs)],
        "first_year": min(int(p["submitted"][:4]) for p in papers),
        "site": SITE_URL,
        "made": date.today().isoformat(),
    }
    out = ROOT / "output" / "people_network.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(PAGE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    return out, len(nodes), len(pairs)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuSoft co-authors (internal)</title>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600&family=STIX+Two+Text:wght@400;500&display=swap" rel="stylesheet">
<style>
:root { --paper:#F7F8F9; --ink:#2E353C; --slate:#626C75; --rule:#D5DADF; --red:#C02127; --gold:#C1AB47; --focus:#C02127;
  --serif:"STIX Two Text",Georgia,serif; --sans:"Atkinson Hyperlegible Next",system-ui,sans-serif; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root { --paper:#1B2026; --ink:#E6E9EC; --slate:#9AA4AE; --rule:#3A434C; --red:#E25A5E; --gold:#D4C26A; --focus:#F08A8D; color-scheme:dark; } }
body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--serif); }
main { padding:2rem clamp(16px,4vw,3rem) 3rem; max-width:90rem; margin:0 auto; }
h1 { font-weight:500; font-size:2.2rem; margin:0 0 .5rem; }
.lede { font-size:1.15rem; max-width:62ch; line-height:1.5; margin:0 0 .5rem; }
.note { font-family:var(--sans); font-size:.85rem; color:var(--slate); margin:0 0 1.5rem; }
.legend { font-family:var(--sans); font-size:.8rem; color:var(--slate); display:flex; gap:.4rem .5rem; align-items:center; flex-wrap:wrap; margin:0 0 1rem; }
.key { width:.9rem; height:.9rem; border-radius:50%; display:inline-block; border:2px solid var(--slate); }
.key-alumni { border:3px solid var(--gold); margin-left:1rem; }
.timeline { display:flex; flex-wrap:wrap; align-items:center; gap:.5rem 1rem; font-family:var(--sans); }
.timeline button { font:inherit; font-weight:600; background:transparent; color:var(--ink); border:1px solid var(--rule); border-radius:3px; padding:.55rem 1rem; min-width:5.5rem; cursor:pointer; }
.timeline button:hover { border-color:var(--ink); }
.timeline input { flex:1 1 16rem; max-width:32rem; accent-color:var(--red); }
#year { font-size:1.5rem; font-weight:600; min-width:3em; }
#count { flex-basis:100%; margin:0; font-size:.85rem; color:var(--slate); }
svg { width:100%; height:min(80vh,56rem); display:block; touch-action:none; }
.edge { stroke:var(--red); stroke-opacity:.28; stroke-width:1; }
.node { cursor:pointer; }
.node circle { fill:var(--paper); stroke:var(--slate); stroke-width:1.5; }
.node.alumni circle { stroke:var(--gold); stroke-width:3; }
.node text { font-family:var(--sans); font-size:10px; fill:var(--slate); text-anchor:middle; dominant-baseline:central; }
.focused .node { opacity:.25; } .focused .node.on { opacity:1; }
.focused .edge { stroke-opacity:.06; } .focused .edge.on { stroke-opacity:.9; stroke-width:1.5; }
.node:focus-visible { outline:none; } .node:focus-visible circle { stroke:var(--focus); stroke-width:3; }
.label { font-family:var(--sans); font-size:13px; fill:var(--ink); paint-order:stroke; stroke:var(--paper); stroke-width:4px; pointer-events:none; }
#caption { font-family:var(--sans); font-size:.9rem; color:var(--slate); min-height:3em; max-width:70ch; }
#caption strong { color:var(--ink); }
a { color:var(--red); }
.sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }
</style>
</head>
<body>
<main>
  <h1>Who writes with whom</h1>
  <p class="lede" id="lede"></p>
  <p class="note">Internal to the QuSoft management team; not on the public site. Made <span id="made"></span> from the papers on the site.</p>
  <p class="legend"><span class="key"></span> current member <span class="key key-alumni"></span> alumni</p>
  <div class="timeline">
    <button type="button" id="play">Play</button>
    <label class="sr" for="slider">Show the network up to the year</label>
    <input type="range" id="slider" step="1">
    <output id="year" for="slider"></output>
    <p id="count" aria-live="polite"></p>
  </div>
  <svg id="network" role="img" aria-label="Co-authorship network of QuSoft people"></svg>
  <p id="caption">Pick someone to see their co-authors.</p>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<script>
const DATA = /*DATA*/;
const $ = (s) => document.querySelector(s);
const ROLE = { "PhD Students": "PhD student", "Postdocs": "postdoc", "Senior Researchers": "senior researcher", "Support Team": "support team", "Visitor": "visitor", "Turing Chair": "Turing chair" };
const initials = (n) => n.split(/\s+/).filter((w) => /^[A-ZÀ-Ž]/.test(w)).map((w) => w[0]).slice(0, 2).join("");
const names = Object.keys(DATA.people);
$("#made").textContent = DATA.made;
$("#lede").textContent = `${names.length} people have written QuSoft papers since ${DATA.first_year}, ` +
  `${names.filter((n) => DATA.people[n].alumni).length} of them now alumni. A line joins two people who have written a paper together.`;

const svg = d3.select("#network");
const box = svg.node().getBoundingClientRect();
const W = box.width, H = box.height, R = Math.max(14, Math.min(20, W / 44));
svg.attr("viewBox", [0, 0, W, H]);

const firstYear = new Map(), pairYear = new Map();
const key = (a, b) => (a < b ? `${a}\n${b}` : `${b}\n${a}`);
for (const [d, q] of DATA.papers) {
  const y = +d.slice(0, 4);
  for (const n of q) if (!(firstYear.get(n) <= y)) firstYear.set(n, y);
  for (let i = 0; i < q.length; i++) for (let j = i + 1; j < q.length; j++) { const k = key(q[i], q[j]); if (!(pairYear.get(k) <= y)) pairYear.set(k, y); }
}
const lastYear = d3.max(DATA.papers, (p) => +p[0].slice(0, 4));
const leftIn = (d) => (d.alumni ? +((d.years || "").match(/\d{4}(?!.*\d{4})/) || [lastYear])[0] : Infinity);
const nodes = names.map((n) => ({ id: n, ...DATA.people[n], since: firstYear.get(n) ?? DATA.first_year }));
const links = DATA.edges.map(([a, b]) => ({ source: a, target: b, since: pairYear.get(key(a, b)) ?? DATA.first_year }));

svg.append("defs").append("clipPath").attr("id", "clip").attr("clipPathUnits", "objectBoundingBox")
  .append("circle").attr("cx", .5).attr("cy", .5).attr("r", .5);
const edge = svg.append("g").selectAll("line").data(links).join("line").attr("class", "edge");
const node = svg.append("g").selectAll("g").data(nodes).join("g").attr("class", "node").attr("role", "button");
node.append("circle").attr("r", R);
node.filter((d) => !d.portrait).append("text").text((d) => initials(d.id));
node.filter((d) => d.portrait).append("image").attr("href", (d) => d.portrait)
  .attr("x", -R + 2).attr("y", -R + 2).attr("width", 2 * R - 4).attr("height", 2 * R - 4)
  .attr("clip-path", "url(#clip)").attr("preserveAspectRatio", "xMidYMid slice");
const label = svg.append("text").attr("class", "label");

const sim = d3.forceSimulation()
  .force("link", d3.forceLink().id((d) => d.id).distance(R * 4).strength(.35))
  .force("charge", d3.forceManyBody().strength(-R * 9))
  .force("collide", d3.forceCollide(R + 3))
  .force("x", d3.forceX(W / 2).strength(.05))
  .force("y", d3.forceY(H / 2).strength(.07)).stop();
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
function draw() {
  for (const d of sim.nodes()) { d.x = clamp(d.x, R + 2, W - R - 2); d.y = clamp(d.y, R + 2, H - R - 2); }
  edge.filter((d) => d.shown).attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
  node.filter((d) => d.shown).attr("transform", (d) => `translate(${d.x},${d.y})`);
}
sim.on("tick", draw);
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const end = (e) => e.id ?? e;
let year = lastYear, neighbours = new Map(), drawn = false, focused = null;

function showYear(y) {
  year = y;
  const byId = new Map(nodes.map((d) => [d.id, d]));
  for (const d of nodes) {
    const was = d.shown;
    d.shown = d.since <= y; d.alumNow = leftIn(d) <= y;
    if (d.shown && !was) {
      const near = links.filter((l) => l.since <= y && (end(l.source) === d.id || end(l.target) === d.id))
        .map((l) => byId.get(end(l.source) === d.id ? end(l.target) : end(l.source))).find((n) => n.shown && n.x != null && n.since < y);
      const a = Math.random() * 2 * Math.PI;
      d.x = (near ? near.x : W / 2) + Math.cos(a) * R * 2; d.y = (near ? near.y : H / 2) + Math.sin(a) * R * 2; d.vx = d.vy = 0;
    }
  }
  const shown = links.filter((l) => l.since <= y);
  for (const l of links) l.shown = l.since <= y;
  neighbours = new Map(nodes.map((d) => [d.id, new Set()]));
  for (const l of shown) { neighbours.get(end(l.source)).add(end(l.target)); neighbours.get(end(l.target)).add(end(l.source)); }
  node.attr("display", (d) => (d.shown ? null : "none")).attr("tabindex", (d) => (d.shown ? 0 : -1)).classed("alumni", (d) => d.alumNow)
    .attr("aria-label", (d) => `${d.id}${d.alumNow ? `, alumni${d.years ? ` ${d.years}` : ""}` : ""}`);
  edge.attr("display", (d) => (d.shown ? null : "none"));
  sim.nodes(nodes.filter((d) => d.shown)); sim.force("link").links(shown);
  if (still) { sim.alpha(1); for (let i = 0; i < 300; i++) sim.tick(); draw(); } else sim.alpha(!drawn ? 1 : .5).restart();
  drawn = true;
  const n = nodes.filter((d) => d.shown).length;
  $("#year").textContent = y;
  $("#count").textContent = `${y === lastYear ? "All" : `By the end of ${y}:`} ${n} people, with ${shown.length} pairs who have written together.`;
  if (focused && !focused.shown) clear(); else if (focused) focus(focused);
}
function showLabel(d) {
  const right = d.x < W - 200;
  label.attr("x", d.x + (right ? R + 6 : -R - 6)).attr("y", d.y + 4).attr("text-anchor", right ? "start" : "end").text(d.id);
}
function focus(d) {
  focused = d;
  const near = neighbours.get(d.id);
  svg.classed("focused", true);
  node.classed("on", (n) => n.id === d.id || near.has(n.id));
  edge.classed("on", (l) => l.shown && (l.source.id === d.id || l.target.id === d.id));
  showLabel(d);
  const who = d.alumNow ? `alumni${d.years ? `, at QuSoft ${d.years}` : ""}` : ROLE[d.role] || "";
  const cap = $("#caption"); cap.replaceChildren();
  const s = document.createElement("strong"); s.textContent = d.id; cap.append(s, who ? `, ${who}. ` : ". ");
  const t = [...near].sort();
  if (t.length) cap.append(`${year === lastYear ? "Has written" : `By ${year} had written`} with ${t.join(", ")}. `);
  const a = document.createElement("a"); a.href = `${DATA.site}#papers?person=${encodeURIComponent(d.id)}`; a.textContent = `Papers with ${d.id}`; cap.append(a);
}
function clear() {
  focused = null; svg.classed("focused", false); node.classed("on", false); edge.classed("on", false); label.text("");
  $("#caption").textContent = "Pick someone to see their co-authors.";
}
node.on("click", (e, d) => { e.stopPropagation(); focused === d ? clear() : focus(d); })
  .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focus(d); } if (e.key === "Escape") clear(); })
  .on("mouseenter focus", (e, d) => { if (!focused) showLabel(d); })
  .on("mouseleave blur", () => { if (!focused) label.text(""); else showLabel(focused); });
svg.on("click", clear);

const slider = $("#slider"), play = $("#play");
slider.min = DATA.first_year; slider.max = lastYear; slider.value = lastYear;
let timer = null;
const stop = () => { clearInterval(timer); timer = null; play.textContent = "Play"; };
slider.addEventListener("input", () => { stop(); showYear(+slider.value); });
play.addEventListener("click", () => {
  if (timer) return stop();
  if (year >= lastYear) { slider.value = DATA.first_year; showYear(DATA.first_year); }
  play.textContent = "Pause";
  timer = setInterval(() => { if (year >= lastYear) return stop(); slider.value = year + 1; showYear(year + 1); }, 1100);
});
showYear(lastYear);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    out, n, e = build()
    print(f"Wrote {out}: {n} people, {e} pairs")
