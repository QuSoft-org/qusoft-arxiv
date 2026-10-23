#!/usr/bin/env python3
"""Research profiles of QuSoft people: an internal draft (never published as is).

    python scripts/people_profiles.py      # -> output/people_profiles.html (open it in a browser)

Two views, made to include everyone equally:
1. Fingerprints: every person's portrait with a ring of the same size, split by how their
   QuSoft papers spread over the five research lines. Shares, not counts; people without
   papers on the site get a plain ring and are listed all the same. Click a face for topics.
2. Who to talk to about...: every topic with the faces of the people who have written on it,
   alphabetically, without counts.

Lines and topics come from data/topics.json (inferred from titles and abstracts, with AI).
People should check their own profile before any of this is published.
"""

import base64
import io
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qusoft.common import find_portrait, is_alumnus, load_papers, load_people, name_key, open_portrait, tenure

ROOT = Path(__file__).resolve().parent.parent
SITE_URL = "https://qusoft-org.github.io/qusoft-arxiv/"
ROLE = {"PhD Students": "PhD student", "Postdocs": "postdoc", "Senior Researchers": "senior researcher",
        "Support Team": "support team", "Visitor": "visitor", "Turing Chair": "Turing chair"}


def portrait(name):
    """The small web portrait if there is one, else made from the original photo (black and white)."""
    f = ROOT / "site" / "portraits" / f"{name_key(name).replace(' ', '-')}.webp"
    if f.exists():
        return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()
    src = find_portrait(name)
    if not src or src.suffix.lower() == ".svg":
        return None
    from PIL import Image, ImageOps
    img = ImageOps.fit(open_portrait(src), (160, 160), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=78)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def build():
    topics = json.loads((ROOT / "data" / "topics.json").read_text())
    lines = [{"id": l["id"], "name": l["name"], "slot": l["slot"],
              "topics": [{"id": t["id"], "name": t["name"]} for t in l["topics"]]} for l in topics["taxonomy"]["lines"]]
    people = load_people()
    line_count, topic_set = {}, {}
    for p in load_papers():
        tag = topics["papers"].get(p["id"])
        if not tag or tag["line"] == "other":
            continue
        for q in set(p["qusoft_authors"]):
            line_count.setdefault(q, Counter())[tag["line"]] += 1
            topic_set.setdefault(q, Counter()).update(tag["topics"])
    persons = []
    for name, info in sorted(people.items(), key=lambda kv: (kv[0].split()[-1].lower(), kv[0])):
        c = line_count.get(name, Counter())
        total = sum(c.values())
        persons.append({
            "name": name,
            "alumni": is_alumnus(info),
            "who": f"alumni {tenure(info)}".strip() if is_alumnus(info) else ROLE.get(info.get("role"), ""),
            "shares": {k: round(v / total, 3) for k, v in c.items()} if total else {},
            # Topics in order of how central they are to the person, but shown without numbers.
            "topics": [t for t, _ in topic_set.get(name, Counter()).most_common()],
            "portrait": portrait(name),
        })
    data = {"lines": lines, "people": persons, "site": SITE_URL, "made": date.today().isoformat()}
    out = ROOT / "output" / "people_profiles.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(PAGE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    return out, len(persons), sum(1 for p in persons if p["shares"])


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuSoft research profiles (internal draft)</title>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600&family=STIX+Two+Text:wght@400;500&display=swap" rel="stylesheet">
<style>
:root { --paper:#F7F8F9; --surface:#FFFFFF; --ink:#2E353C; --slate:#626C75; --rule:#D5DADF; --gold:#C1AB47; --red:#C02127; --focus:#C02127;
  --line-1:#2a6fb0; --line-2:#c8721f; --line-3:#1f9a8a; --line-4:#8e4a9c; --line-5:#5d8f1f;
  --serif:"STIX Two Text",Georgia,serif; --sans:"Atkinson Hyperlegible Next",system-ui,sans-serif; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root { --paper:#1B2026; --surface:#232A31; --ink:#E6E9EC; --slate:#9AA4AE; --rule:#3A434C; --gold:#D4C26A;
  --red:#E25A5E; --focus:#F08A8D; --line-1:#4a8fd4; --line-2:#c8721f; --line-3:#22a090; --line-4:#9b62b5; --line-5:#6fa332; color-scheme:dark; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--serif); }
main { max-width:76rem; margin:0 auto; padding:2rem clamp(16px,4vw,3rem) 4rem; }
h1 { font-weight:500; font-size:2.2rem; margin:0 0 .5rem; }
h2 { font-weight:500; font-size:1.55rem; margin:3rem 0 .4rem; border-top:2px solid var(--ink); padding-top:1rem; }
.lede { font-size:1.12rem; line-height:1.5; max-width:66ch; margin:0 0 .6rem; }
.note { font-family:var(--sans); font-size:.85rem; color:var(--slate); max-width:72ch; margin:0 0 1rem; }
.controls { display:flex; flex-wrap:wrap; gap:.5rem 1.5rem; align-items:center; font-family:var(--sans); font-size:.9rem; margin:1rem 0 1.25rem; position:sticky; top:0; background:var(--paper); padding:.5rem 0; z-index:2; }
.toggle { display:inline-flex; border:1px solid var(--rule); border-radius:3px; overflow:hidden; }
.toggle button { font:inherit; background:transparent; color:var(--ink); border:0; padding:.45rem .8rem; cursor:pointer; }
.toggle button[aria-pressed="true"] { background:var(--ink); color:var(--paper); }
.toggle button:focus-visible { outline:2px solid var(--focus); outline-offset:-2px; }
.legend { display:flex; flex-wrap:wrap; gap:.3rem 1.1rem; font-size:.82rem; color:var(--slate); }
.sw { display:inline-block; width:.75rem; height:.75rem; border-radius:3px; margin-right:.35rem; vertical-align:-.05em; }
.grid { list-style:none; padding:0; margin:0; display:grid; grid-template-columns:repeat(auto-fill,minmax(7.2rem,1fr)); gap:1.4rem .8rem; }
.person { text-align:center; }
.person button { all:unset; cursor:pointer; display:block; width:100%; border-radius:6px; padding:.2rem 0; }
.person button:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.person button[aria-expanded="true"] .name { color:var(--red); }
.ring { width:5.6rem; height:5.6rem; display:block; margin:0 auto .35rem; }
.name { font-family:var(--sans); font-size:.85rem; line-height:1.25; display:block; }
.who { font-family:var(--sans); font-size:.75rem; color:var(--slate); display:block; }
.detail { grid-column:1/-1; background:var(--surface); border:1px solid var(--rule); border-radius:6px; padding:1rem 1.2rem; text-align:left; font-family:var(--sans); font-size:.9rem; }
.detail h3 { font-family:var(--serif); font-weight:500; font-size:1.25rem; margin:0 0 .2rem; }
.detail p { margin:.4rem 0; max-width:70ch; }
.detail .bar { display:flex; height:.6rem; border-radius:3px; overflow:hidden; gap:2px; max-width:24rem; margin:.5rem 0; }
.detail .bar span { display:block; }
.detail ul { list-style:none; padding:0; margin:.3rem 0; display:flex; flex-wrap:wrap; gap:.3rem .6rem; }
.detail li { border:1px solid var(--rule); border-radius:3px; padding:.1rem .45rem; font-size:.82rem; }
.detail a { color:var(--red); }
.muted { color:var(--slate); }
.topic-line { margin:1.8rem 0 0; }
.topic-line h3 { font-weight:500; font-size:1.2rem; margin:0 0 .5rem; display:flex; align-items:center; }
.topic { display:grid; grid-template-columns:minmax(10rem,16rem) 1fr; gap:.4rem 1rem; padding:.55rem 0; border-bottom:1px solid var(--rule); align-items:start; }
.topic .t { font-size:1rem; line-height:1.3; }
.faces { display:flex; flex-wrap:wrap; gap:.3rem; }
.face { width:2.1rem; height:2.1rem; border-radius:50%; object-fit:cover; display:block; border:1.5px solid var(--slate); background:var(--rule); }
.face.alum { border:2px solid var(--gold); }
.face.initials { display:grid; place-items:center; font-family:var(--sans); font-size:.7rem; color:var(--slate); }
.faces a { display:block; border-radius:50%; }
.faces a:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.tip { position:fixed; z-index:9; pointer-events:none; background:var(--surface); color:var(--ink); border:1px solid var(--rule); border-radius:4px; padding:.3rem .5rem; font-family:var(--sans); font-size:.8rem; }
@media (max-width:600px) { .topic { grid-template-columns:1fr; } .ring { width:4.6rem; height:4.6rem; } }
</style>
</head>
<body>
<main>
  <h1>Research profiles</h1>
  <p class="lede">What each QuSoft person works on, shown so that everyone carries the same weight: shares instead of counts, the same size for everyone, and people without papers on the site included.</p>
  <p class="note"><strong>Internal draft</strong> for the QuSoft management team, made <span id="made"></span>. Research lines and topics are inferred with AI from the titles and abstracts of papers on the site. Everyone should check their own profile before anything like this is published.</p>

  <div class="controls">
    <span class="toggle" role="group" aria-label="Show">
      <button type="button" data-show="current" aria-pressed="true">Current members</button>
      <button type="button" data-show="alumni" aria-pressed="false">Alumni</button>
      <button type="button" data-show="all" aria-pressed="false">Everyone</button>
    </span>
    <span class="legend" id="legend"></span>
  </div>

  <h2>Fingerprints</h2>
  <p class="note">The ring around each portrait shows how that person's papers spread over the five research lines: its share of the circle, not the number of papers. A plain grey ring means no papers on the site yet. Pick a face for the topics.</p>
  <ul class="grid" id="grid"></ul>

  <h2>Who to talk to about&hellip;</h2>
  <p class="note">Every topic with the people who have written about it, in alphabetical order. Someone who works on several topics appears under each of them.</p>
  <div id="topics"></div>
</main>
<script>
const DATA = /*DATA*/;
const $ = (s) => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const n = tag.startsWith("svg:") ? document.createElementNS("http://www.w3.org/2000/svg", tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) k.startsWith("on") ? n.addEventListener(k.slice(2), v) : n.setAttribute(k, v === true ? "" : v);
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) n.append(c instanceof Node ? c : document.createTextNode(c));
  return n;
};
const lineOf = Object.fromEntries(DATA.lines.map((l) => [l.id, l]));
const topicName = Object.fromEntries(DATA.lines.flatMap((l) => l.topics.map((t) => [t.id, t.name])));
const topicLine = Object.fromEntries(DATA.lines.flatMap((l) => l.topics.map((t) => [t.id, l.id])));
const color = (lid) => `var(--line-${lineOf[lid]?.slot || 0})`;
const initials = (n) => n.split(/\s+/).filter((w) => /^[A-ZÀ-Ž]/.test(w)).map((w) => w[0]).slice(0, 2).join("");
$("#made").textContent = DATA.made;
$("#legend").append(...DATA.lines.map((l) => el("span", {}, el("span", { class: "sw", style: `background:${color(l.id)}` }), l.name)));

let show = "current", open = null;
const visible = (p) => show === "all" || (show === "alumni" ? p.alumni : !p.alumni);

function ring(p) {
  // Same size for everyone; the ring shows shares, starting at the top, with a small gap between lines.
  const S = 100, R = 45, C = 2 * Math.PI * R;
  const svg = el("svg:svg", { viewBox: `0 0 ${S} ${S}`, class: "ring", "aria-hidden": "true" });
  const clip = `c-${Math.random().toString(36).slice(2)}`;
  svg.append(el("svg:defs", {}, el("svg:clipPath", { id: clip }, el("svg:circle", { cx: 50, cy: 50, r: 37 }))));
  const parts = DATA.lines.filter((l) => p.shares[l.id]);
  if (!parts.length) svg.append(el("svg:circle", { cx: 50, cy: 50, r: R, fill: "none", stroke: "var(--rule)", "stroke-width": 7 }));
  let at = 0;
  const gap = parts.length > 1 ? 3 : 0;
  for (const l of parts) {
    const len = p.shares[l.id] * C;
    svg.append(el("svg:circle", { cx: 50, cy: 50, r: R, fill: "none", stroke: color(l.id), "stroke-width": 7,
      "stroke-dasharray": `${Math.max(len - gap, 0.5)} ${C}`, "stroke-dashoffset": -at, transform: "rotate(-90 50 50)" }));
    at += len;
  }
  if (p.portrait) svg.append(el("svg:image", { href: p.portrait, x: 13, y: 13, width: 74, height: 74, "clip-path": `url(#${clip})`, preserveAspectRatio: "xMidYMid slice" }));
  else svg.append(el("svg:circle", { cx: 50, cy: 50, r: 37, fill: "var(--rule)" }),
    el("svg:text", { x: 50, y: 50, "text-anchor": "middle", "dominant-baseline": "central", "font-family": "system-ui", "font-size": 22, fill: "var(--slate)" }, initials(p.name)));
  return svg;
}

function detail(p) {
  const parts = DATA.lines.filter((l) => p.shares[l.id]).sort((a, b) => p.shares[b.id] - p.shares[a.id]);
  return el("li", { class: "detail", id: "detail" },
    el("h3", {}, p.name), el("span", { class: "muted" }, p.who),
    parts.length
      ? [el("div", { class: "bar", "aria-hidden": "true" }, parts.map((l) => el("span", { style: `flex:${p.shares[l.id]};background:${color(l.id)}` }))),
         el("p", {}, "Mostly ", parts.map((l) => l.name.toLowerCase()).join(", then "), "."),
         el("p", { class: "muted" }, "Main topics:"), el("ul", {}, p.topics.slice(0, 6).map((t) => el("li", {}, topicName[t]))),
         p.topics.length > 6 ? el("p", { class: "muted" }, "Also: ", p.topics.slice(6).map((t) => topicName[t]).join(", "), ".") : null,
         el("p", {}, el("a", { href: `${DATA.site}#papers?person=${encodeURIComponent(p.name)}` }, `Papers with ${p.name} on the site`))]
      : el("p", { class: "muted" }, "No papers on the site yet."));
}

function renderGrid() {
  const list = DATA.people.filter(visible);
  const items = [];
  let openItem = null;
  for (const p of list) {
    const btn = el("button", { type: "button", "aria-expanded": String(open === p.name), "aria-controls": "detail",
      onclick: () => { open = open === p.name ? null : p.name; renderGrid(); if (open) document.getElementById("detail").scrollIntoView({ block: "nearest" }); } },
      ring(p), el("span", { class: "name" }, p.name), el("span", { class: "who" }, p.who));
    const li = el("li", { class: "person" }, btn);
    if (open === p.name) openItem = [li, p];
    items.push(li);
  }
  $("#grid").replaceChildren(...items);
  if (openItem) {
    // Open the profile below the row the face is in, so the row stays whole.
    let lastInRow = openItem[0];
    while (lastInRow.nextElementSibling && lastInRow.nextElementSibling.offsetTop === openItem[0].offsetTop) lastInRow = lastInRow.nextElementSibling;
    lastInRow.after(detail(openItem[1]));
    openItem[0].querySelector("button").focus({ preventScroll: true });
  }
}

function renderTopics() {
  const list = DATA.people.filter(visible);
  $("#topics").replaceChildren(...DATA.lines.map((l) => el("section", { class: "topic-line" },
    el("h3", {}, el("span", { class: "sw", style: `background:${color(l.id)}` }), l.name),
    l.topics.map((t) => {
      const who = list.filter((p) => p.topics.includes(t.id));
      return el("div", { class: "topic" }, el("span", { class: "t" }, t.name),
        who.length ? el("div", { class: "faces" }, who.map((p) => el("a", { href: `${DATA.site}#papers?person=${encodeURIComponent(p.name)}`, title: `${p.name}, ${p.who}`, "aria-label": `${p.name}, ${p.who}` },
          p.portrait ? el("img", { class: `face${p.alumni ? " alum" : ""}`, src: p.portrait, alt: "" })
                     : el("span", { class: `face initials${p.alumni ? " alum" : ""}` }, initials(p.name)))))
          : el("span", { class: "muted" }, show === "current" ? "No current members yet." : "Nobody yet."));
    }))));
}

document.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => {
  show = b.dataset.show; open = null;
  document.querySelectorAll("[data-show]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  renderGrid(); renderTopics();
}));
renderGrid(); renderTopics();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    out, n, with_papers = build()
    print(f"Wrote {out}: {n} people, {with_papers} with papers on the site")
