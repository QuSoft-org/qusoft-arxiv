#!/usr/bin/env python3
"""Map of QuSoft people by research similarity (internal draft, never published).

    python scripts/people_map.py       # -> output/people_map.html (open it in a browser)

Each person's research profile is the mix of topics over their QuSoft papers (a paper with
three topics gives each a third). People with similar mixes are placed close together
(t-SNE on Hellinger distances), all with faces of the same size and a ring showing their
research lines. Faint topic names mark where the people strongest in that topic are.
People without papers on the site can't be placed and are listed under the map.

Needs scikit-learn (local only: pip install scikit-learn).
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from people_profiles import ROLE, SITE_URL, portrait
from qusoft.common import is_alumnus, load_papers, load_people, tenure

ROOT = Path(__file__).resolve().parent.parent


def build():
    from sklearn.manifold import TSNE

    topics = json.loads((ROOT / "data" / "topics.json").read_text())
    lines = [{"id": l["id"], "name": l["name"], "slot": l["slot"],
              "topics": [{"id": t["id"], "name": t["name"], "short": t.get("short", t["name"])} for t in l["topics"]]}
             for l in topics["taxonomy"]["lines"]]
    tids = [t["id"] for l in lines for t in l["topics"]]
    people = load_people()
    weights, line_count = defaultdict(Counter), defaultdict(Counter)
    for p in load_papers():
        tag = topics["papers"].get(p["id"])
        if not tag or tag["line"] == "other" or not tag["topics"]:
            continue
        for q in set(p["qusoft_authors"]):
            for t in tag["topics"]:
                weights[q][t] += 1 / len(tag["topics"])
            line_count[q][tag["line"]] += 1

    names = sorted(weights, key=lambda n: (n.split()[-1].lower(), n))
    X = np.array([[weights[n][t] for t in tids] for n in names], dtype=float)
    X = np.sqrt(X / X.sum(axis=1, keepdims=True))  # Hellinger: similar mixes are close, volume doesn't matter
    Y = TSNE(n_components=2, perplexity=min(15, len(names) // 4), init="pca", random_state=1,
             metric="euclidean").fit_transform(X)
    Y = (Y - Y.min(axis=0)) / (Y.max(axis=0) - Y.min(axis=0))
    D = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)

    persons = []
    for i, n in enumerate(names):
        info = people.get(n, {})
        c = line_count[n]
        total = sum(c.values())
        persons.append({
            "name": n, "alumni": is_alumnus(info),
            "who": f"alumni {tenure(info)}".strip() if is_alumnus(info) else ROLE.get(info.get("role"), ""),
            "x": round(float(Y[i, 0]), 4), "y": round(float(Y[i, 1]), 4),
            "shares": {k: round(v / total, 3) for k, v in c.items()},
            "topics": [t for t, _ in weights[n].most_common()],
            "near": [names[j] for j in np.argsort(D[i])[1:6]],
            "portrait": portrait(n),
        })
    # Where each topic lives: the weighted centre of the people strongest in it.
    labels = []
    for k, t in enumerate(tids):
        w = X[:, k] ** 4
        if w.sum() > 0 and (X[:, k] > 0.5).sum() >= 2:
            labels.append({"id": t, "x": float((Y[:, 0] * w).sum() / w.sum()), "y": float((Y[:, 1] * w).sum() / w.sum())})
    unplaced = [{"name": n, "alumni": is_alumnus(i),
                 "who": f"alumni {tenure(i)}".strip() if is_alumnus(i) else ROLE.get(i.get("role"), "")}
                for n, i in sorted(people.items(), key=lambda kv: kv[0].split()[-1].lower()) if n not in weights]
    data = {"lines": lines, "people": persons, "labels": labels, "unplaced": unplaced,
            "site": SITE_URL, "made": date.today().isoformat()}
    out = ROOT / "output" / "people_map.html"
    out.write_text(PAGE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    return out, len(persons), len(unplaced)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuSoft people by research similarity (internal draft)</title>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600&family=STIX+Two+Text:wght@400;500&display=swap" rel="stylesheet">
<style>
:root { --paper:#F7F8F9; --surface:#FFFFFF; --ink:#2E353C; --slate:#626C75; --rule:#D5DADF; --gold:#C1AB47; --red:#C02127; --focus:#C02127;
  --line-1:#2a6fb0; --line-2:#c8721f; --line-3:#1f9a8a; --line-4:#8e4a9c; --line-5:#5d8f1f;
  --serif:"STIX Two Text",Georgia,serif; --sans:"Atkinson Hyperlegible Next",system-ui,sans-serif; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root { --paper:#1B2026; --surface:#232A31; --ink:#E6E9EC; --slate:#9AA4AE; --rule:#3A434C; --gold:#D4C26A;
  --red:#E25A5E; --focus:#F08A8D; --line-1:#4a8fd4; --line-2:#c8721f; --line-3:#22a090; --line-4:#9b62b5; --line-5:#6fa332; color-scheme:dark; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--serif); }
main { max-width:90rem; margin:0 auto; padding:2rem clamp(16px,4vw,3rem) 4rem; }
h1 { font-weight:500; font-size:2.2rem; margin:0 0 .5rem; }
.lede { font-size:1.1rem; line-height:1.5; max-width:70ch; margin:0 0 .5rem; }
.note { font-family:var(--sans); font-size:.85rem; color:var(--slate); max-width:76ch; margin:0 0 1rem; }
.controls { display:flex; flex-wrap:wrap; gap:.5rem 1.5rem; align-items:center; font-family:var(--sans); font-size:.9rem; margin:1rem 0 .5rem; }
.toggle { display:inline-flex; border:1px solid var(--rule); border-radius:3px; overflow:hidden; }
.toggle button { font:inherit; background:transparent; color:var(--ink); border:0; padding:.45rem .8rem; cursor:pointer; }
.toggle button[aria-pressed="true"] { background:var(--ink); color:var(--paper); }
.legend { display:flex; flex-wrap:wrap; gap:.3rem 1.1rem; font-size:.82rem; color:var(--slate); }
.sw { display:inline-block; width:.75rem; height:.75rem; border-radius:3px; margin-right:.35rem; vertical-align:-.05em; }
svg#map { width:100%; height:min(82vh,60rem); display:block; touch-action:none; }
.tlabel { font-family:var(--sans); font-size:13px; font-weight:600; fill:var(--slate); text-anchor:middle; pointer-events:none; paint-order:stroke; stroke:var(--paper); stroke-width:5px; stroke-opacity:.85; }
.focused .tlabel { opacity:.25; }
.p { cursor:pointer; }
.p:focus-visible { outline:none; } .p:focus-visible .bg { stroke:var(--focus); stroke-width:3; }
.focused .p { opacity:.2; } .focused .p.on { opacity:1; }
.link { stroke:var(--red); stroke-opacity:.5; stroke-width:1.5; }
.name { font-family:var(--sans); font-size:12px; fill:var(--ink); paint-order:stroke; stroke:var(--paper); stroke-width:4px; text-anchor:middle; pointer-events:none; }
#card { font-family:var(--sans); font-size:.9rem; min-height:4.5em; max-width:80ch; }
#card strong { font-family:var(--serif); font-weight:500; font-size:1.15rem; }
#card a { color:var(--red); }
.muted { color:var(--slate); }
.unplaced { font-family:var(--sans); font-size:.85rem; color:var(--slate); max-width:80ch; margin-top:2rem; }
</style>
</head>
<body>
<main>
  <h1>Who works on similar things</h1>
  <p class="lede">QuSoft people placed by the mix of topics in their papers: people close together work on similar things. Every face is the same size; the ring shows the person's research lines.</p>
  <p class="note"><strong>Internal draft</strong> for the QuSoft management team, made <span id="made"></span>. Topics are inferred with AI from the papers' titles and abstracts. Distances within a neighbourhood are meaningful; distances between far-apart groups are not (the layout method only keeps local neighbourhoods). Someone at the edge has an unusual mix of topics, which says nothing about how much they publish.</p>
  <div class="controls">
    <span class="toggle" role="group" aria-label="Show">
      <button type="button" data-show="current" aria-pressed="false">Current members</button>
      <button type="button" data-show="alumni" aria-pressed="false">Alumni</button>
      <button type="button" data-show="all" aria-pressed="true">Everyone</button>
    </span>
    <span class="legend" id="legend"></span>
  </div>
  <svg id="map" role="img" aria-label="Map of QuSoft people by research similarity"></svg>
  <p id="card">Pick a face to see that person's topics and the five people whose topic mix is closest.</p>
  <p class="unplaced" id="unplaced"></p>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<script>
const DATA = /*DATA*/;
const $ = (s) => document.querySelector(s);
const lineOf = Object.fromEntries(DATA.lines.map((l) => [l.id, l]));
const topic = Object.fromEntries(DATA.lines.flatMap((l) => l.topics.map((t) => [t.id, t])));
const color = (lid) => `var(--line-${lineOf[lid]?.slot || 0})`;
const initials = (n) => n.split(/\s+/).filter((w) => /^[A-ZÀ-Ž]/.test(w)).map((w) => w[0]).slice(0, 2).join("");
$("#made").textContent = DATA.made;
for (const l of DATA.lines) { const s = document.createElement("span"); s.innerHTML = `<span class="sw" style="background:${color(l.id)}"></span>`; s.append(l.name); $("#legend").append(s); }

const svg = d3.select("#map");
const box = svg.node().getBoundingClientRect();
const W = box.width, H = box.height, R = Math.max(13, Math.min(19, W / 60)), pad = R + 30;
svg.attr("viewBox", [0, 0, W, H]);
const sx = (v) => pad + v * (W - 2 * pad), sy = (v) => pad + v * (H - 2 * pad);

const linkG = svg.append("g");
const nodes = DATA.people.map((p) => ({ ...p, tx: sx(p.x), ty: sy(p.y), x: sx(p.x), y: sy(p.y) }));
const byName = new Map(nodes.map((n) => [n.name, n]));

const g = svg.append("g").selectAll("g").data(nodes).join("g").attr("class", "p").attr("tabindex", 0).attr("role", "button")
  .attr("aria-label", (d) => `${d.name}, ${d.who}`);
g.append("circle").attr("class", "bg").attr("r", R + 3.5).attr("fill", "var(--paper)").attr("stroke", "var(--rule)").attr("stroke-width", 1);
// The ring: research-line shares, same size for everyone.
g.each(function (d) {
  const C = 2 * Math.PI * (R + 2);
  let at = 0;
  const parts = DATA.lines.filter((l) => d.shares[l.id]);
  for (const l of parts) {
    const len = d.shares[l.id] * C;
    d3.select(this).append("circle").attr("r", R + 2).attr("fill", "none").attr("stroke", color(l.id)).attr("stroke-width", 3)
      .attr("stroke-dasharray", `${Math.max(len - (parts.length > 1 ? 1.5 : 0), 0.5)} ${C}`).attr("stroke-dashoffset", -at)
      .attr("transform", "rotate(-90)");
    at += len;
  }
});
svg.append("defs").append("clipPath").attr("id", "cl").attr("clipPathUnits", "objectBoundingBox")
  .append("circle").attr("cx", .5).attr("cy", .5).attr("r", .5);
g.filter((d) => d.portrait).append("image").attr("href", (d) => d.portrait).attr("x", -R + 1).attr("y", -R + 1)
  .attr("width", 2 * R - 2).attr("height", 2 * R - 2).attr("clip-path", "url(#cl)").attr("preserveAspectRatio", "xMidYMid slice");
g.filter((d) => !d.portrait).append("text").attr("text-anchor", "middle").attr("dominant-baseline", "central")
  .attr("font-family", "system-ui").attr("font-size", 10).attr("fill", "var(--slate)").text((d) => initials(d.name));
// Topic names on top of the faces, with a halo so they stay readable.
const tlabels = svg.append("g").selectAll("text").data(DATA.labels).join("text").attr("class", "tlabel")
  .attr("x", (d) => sx(d.x)).attr("y", (d) => sy(d.y)).text((d) => topic[d.id].short);
const label = svg.append("text").attr("class", "name");

// Faces are pushed apart so none overlap, staying as close as possible to their place on the map.
const sim = d3.forceSimulation(nodes).force("x", d3.forceX((d) => d.tx).strength(0.6)).force("y", d3.forceY((d) => d.ty).strength(0.6))
  .force("collide", d3.forceCollide(R + 4).iterations(3)).stop();
for (let i = 0; i < 300; i++) sim.tick();
g.attr("transform", (d) => `translate(${d.x},${d.y})`);

let show = "all", focused = null;
const visible = (d) => show === "all" || (show === "alumni" ? d.alumni : !d.alumni);
function focus(d) {
  focused = d;
  const near = d.near.map((n) => byName.get(n)).filter((n) => n && visible(n));
  svg.classed("focused", true);
  g.classed("on", (n) => n === d || near.includes(n));
  linkG.selectAll("line").data(near).join("line").attr("class", "link")
    .attr("x1", d.x).attr("y1", d.y).attr("x2", (n) => n.x).attr("y2", (n) => n.y);
  label.attr("x", d.x).attr("y", d.y + R + 16).text(d.name);
  const card = $("#card"); card.replaceChildren();
  const s = document.createElement("strong"); s.textContent = d.name;
  const a = document.createElement("a"); a.href = `${DATA.site}#papers?person=${encodeURIComponent(d.name)}`; a.textContent = "papers on the site";
  card.append(s, ` (${d.who}). Main topics: ${d.topics.slice(0, 5).map((t) => topic[t].name.toLowerCase()).join(", ")}. `,
    `Closest topic mix: ${near.map((n) => n.name).join(", ") || "nobody shown"}. See their `, a, ".");
}
function clear() {
  focused = null; svg.classed("focused", false); g.classed("on", false); linkG.selectAll("line").remove(); label.text("");
  $("#card").textContent = "Pick a face to see that person's topics and the five people whose topic mix is closest.";
}
g.on("click", (e, d) => { e.stopPropagation(); focused === d ? clear() : focus(d); })
  .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focus(d); } if (e.key === "Escape") clear(); })
  .on("mouseenter focus", (e, d) => { if (!focused) label.attr("x", d.x).attr("y", d.y + R + 16).text(d.name); })
  .on("mouseleave blur", () => { if (!focused) label.text(""); });
svg.on("click", clear);

function applyShow() {
  g.attr("display", (d) => (visible(d) ? null : "none"));
  if (focused && !visible(focused)) clear(); else if (focused) focus(focused);
  const un = DATA.unplaced.filter(visible);
  $("#unplaced").textContent = un.length
    ? `Not on the map yet, because they have no papers on the site: ${un.map((u) => `${u.name} (${u.who})`).join(", ")}.` : "";
}
document.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => {
  show = b.dataset.show;
  document.querySelectorAll("[data-show]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  applyShow();
}));
applyShow();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    out, n, u = build()
    print(f"Wrote {out}: {n} people on the map, {u} without papers listed below it")
