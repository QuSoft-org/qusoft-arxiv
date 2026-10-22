/* QuSoft papers: list, network, print. Data comes from data/*.json, built by scripts/update.py. */
(() => {
  "use strict";

  // ---------- helpers ----------

  const $ = (sel) => document.querySelector(sel);

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(c));
    }
    return node;
  }

  const fold = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });
  const formatDate = (iso) => dateFmt.format(new Date(iso + "T12:00:00"));
  const daysAgo = (iso) => (Date.now() - new Date(iso + "T12:00:00")) / 864e5;
  const today = () => new Date().toISOString().slice(0, 10);

  // LaTeX in titles and abstracts, typeset by MathJax once it has loaded (see index.html).
  const hasMath = (text) => /\$|\\\(/.test(text || "");
  function typeset(nodes) {
    const todo = [...nodes].filter((n) => n && n.isConnected && hasMath(n.textContent));
    if (!todo.length) return;
    const mj = window.MathJax;
    if (window.mathQueue !== null && !(mj && mj.typesetPromise)) {
      (window.mathQueue = window.mathQueue || []).push(...todo);
      return;
    }
    mj.startup.promise.then(() => mj.typesetPromise(todo)).catch(() => {});
  }
  // LaTeX text commands outside maths: \emph{..} and {\bf ..} become emphasis, \cite{..} is
  // dropped, and \ce{..} or \postBQP get wrapped in $..$ so MathJax renders them.
  const LATEX_TEXT = new RegExp([
    /(\$\$[\s\S]*?\$\$|\$[^$]*\$|\\\([\s\S]*?\\\))/.source,         // 1: maths, left alone
    /~?\\cite[pt]?\{[^}]*\}/.source,                                 // citation
    /\\(emph|textit|textbf)\{((?:[^{}$]|\$[^$]*\$)*)\}/.source,      // 2, 3
    /\{\\(bf|it|em)\s+([^{}]*)\}/.source,                            // 4, 5
    /(\\ce\{[^{}]*\}|\\postBQP\b)/.source,                           // 6
  ].join("|"), "g");
  function latexText(text) {
    const out = [];
    let last = 0, m;
    text = text || "";
    while ((m = LATEX_TEXT.exec(text))) {
      out.push(text.slice(last, m.index));
      if (m[1]) out.push(m[1]);
      else if (m[2]) out.push(el(m[2] === "textbf" ? "strong" : "em", {}, m[3]));
      else if (m[4]) out.push(el(m[4] === "bf" ? "strong" : "em", {}, m[5]));
      else if (m[6]) out.push(`$${m[6]}$`);
      last = LATEX_TEXT.lastIndex;
    }
    out.push(text.slice(last));
    return out.filter((x) => x !== "");
  }
  function untypeset(container) {
    const mj = window.MathJax;
    if (mj && mj.typesetClear) mj.typesetClear([container]);
  }

  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: fine */ }
    },
  };

  const SUBJECTS = {
    "quant-ph": "quantum physics", "cs.CR": "cryptography and security", "cs.CC": "computational complexity",
    "cs.DS": "data structures and algorithms", "cs.IT": "information theory", "math.IT": "information theory",
    "math-ph": "mathematical physics", "math.MP": "mathematical physics", "cs.LG": "machine learning",
    "stat.ML": "machine learning", "cs.ET": "emerging technologies", "cs.CY": "computers and society",
    "math.CO": "combinatorics", "physics.soc-ph": "physics and society", "cs.DM": "discrete mathematics",
    "math.OA": "operator algebras", "math.QA": "quantum algebra", "cs.LO": "logic in computer science",
    "cs.PL": "programming languages", "math.PR": "probability", "cs.DC": "distributed computing",
    "cs.NI": "networking", "math.OC": "optimization", "cs.AI": "artificial intelligence",
    "hep-th": "high-energy theory", "math.RT": "representation theory", "math.AG": "algebraic geometry",
    "math.NA": "numerical analysis", "cs.FL": "formal languages", "cs.GT": "game theory",
    "math.FA": "functional analysis", "cond-mat.str-el": "condensed matter", "cond-mat.stat-mech": "statistical mechanics",
    "cond-mat.quant-gas": "quantum gases", "physics.atom-ph": "atomic physics", "physics.optics": "optics",
    "physics.chem-ph": "chemical physics", "physics.comp-ph": "computational physics", "math.ST": "statistics",
    "cs.SE": "software engineering", "cs.AR": "hardware architecture", "math.GR": "group theory", "math.NT": "number theory",
  };
  const subject = (cats) => SUBJECTS[cats[0]] || cats[0] || "";

  const ROLE = { "PhD Students": "PhD student", "Postdocs": "postdoc", "Senior Researchers": "senior researcher", "Support Team": "support team", "Visitor": "visitor" };

  // ---------- data ----------

  let papers = [], people = {}, stats = {};

  async function load() {
    const get = (f) => fetch(`data/${f}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${f}: ${r.status}`);
      return r.json();
    });
    [papers, people, stats] = await Promise.all([get("papers.json"), get("people.json"), get("stats.json")]);
    for (const p of papers) {
      p.year = p.date.slice(0, 4);
      p.qusoft = p.authors.filter(([, person]) => person).map(([, person]) => person);
      p.haystack = fold([p.title, p.authors.map((a) => a[0]).join(" "), p.abstract, subject(p.categories)].join(" "));
    }
  }

  // ---------- routing ----------

  const views = ["papers", "people", "print"];
  const rendered = {};

  function route() {
    const [view, query] = (location.hash.slice(1) || "papers").split("?");
    const name = views.includes(view) ? view : "papers";
    for (const v of views) $(`#view-${v}`).hidden = v !== name;
    document.querySelectorAll("nav a").forEach((a) => {
      if (a.dataset.view === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const params = new URLSearchParams(query || "");
    if (name === "papers") showPapers(params);
    if (name === "people" && !rendered.people) { renderNetwork(); renderNumbers(); rendered.people = true; }
    if (name === "print" && !rendered.print) { renderPrint(); rendered.print = true; }
  }

  // ---------- papers ----------

  const filter = { q: "", year: "", who: "", person: "" };

  const initials = (name) => name.split(/\s+/).filter((w) => /^[A-ZÀ-Ž]/.test(w)).map((w) => w[0]).slice(0, 2).join("");

  function authorLine(p) {
    const parts = [];
    p.authors.forEach(([name, person], i) => {
      if (i) parts.push(", ");
      const info = person && people[person];
      if (!info) { parts.push(name); return; }
      // A small portrait before the name (decorative: the name follows), initials when there's no photo.
      const head = info.portrait
        ? el("img", { class: "head", src: info.portrait, alt: "", loading: "lazy", width: 20, height: 20 })
        : el("span", { class: "head initials", "aria-hidden": "true" }, initials(person));
      const link = { href: `#papers?person=${encodeURIComponent(person)}`, title: `Show only papers with ${person}` };
      if (info.alumni) {
        parts.push(el("a", { class: "who alumni", ...link }, head,
          el("span", { class: "alum", title: info.years ? `QuSoft ${info.years}` : "QuSoft alumni" }, name)));
        if (info.years) parts.push(el("span", { class: "years" }, info.years));
      } else {
        parts.push(el("a", { class: "who", ...link }, head, el("span", { class: "q" }, name)));
      }
    });
    return el("p", { class: "authors" }, parts);
  }

  function paperItem(p) {
    const abstract = el("p", { class: "abstract", hidden: true }, latexText(p.abstract));
    const toggle = el("button", {
      type: "button", class: "link-button", "aria-expanded": "false",
      onclick: (e) => {
        const open = abstract.hidden;
        abstract.hidden = !open;
        if (open) typeset([abstract]);
        e.currentTarget.setAttribute("aria-expanded", String(open));
        e.currentTarget.textContent = open ? "Hide abstract" : "Abstract";
      },
    }, "Abstract");
    const isNew = daysAgo(p.added) <= 7;
    return el("li", { class: "paper" },
      el("h3", { class: "paper-title" }, el("a", { href: p.link }, p.title)),
      authorLine(p),
      el("p", { class: "meta" },
        isNew ? el("span", { class: "new" }, "Added this week") : null,
        el("span", {}, [formatDate(p.date), subject(p.categories)].filter(Boolean).join(", ")),
        el("a", { href: p.link }, "arXiv"),
        p.page ? el("a", { href: `firstpages/${p.id}.pdf` }, "First page") : null,
        p.abstract ? toggle : null),
      abstract);
  }

  function renderIntro() {
    const recent = papers.filter((p) => daysAgo(p.added) <= 7).length;
    const lede = $("#papers-lede");
    lede.replaceChildren(
      `${papers.length} papers since ${stats.first_year}, by ${stats.people} current and former members of QuSoft, the research center for quantum software in Amsterdam. `,
      recent ? `${recent === 1 ? "One paper" : `${recent} papers`} added this week.` : "");

    // The newest first pages, overlapping like sheets on the message board.
    const latest = papers.filter((p) => p.page).slice(0, 5);
    const caption = $("#board-caption");
    const describe = (p, i) => {
      untypeset(caption);
      caption.replaceChildren(el("span", { class: "board-when" }, i === 0 ? "Newest" : formatDate(p.date)), " ", p.title);
      typeset([caption]);
    };
    const tilts = [-1.5, 2, -2.5, 1.2, -1];
    $("#latest").replaceChildren(...latest.map((p, i) => {
      const sheet = el("a", {
        class: "sheet", href: `firstpages/${p.id}.pdf`,
        style: `--i:${i};--r:${tilts[i]}deg`,
        "aria-label": `First page of ${p.title}`,
        onmouseenter: () => describe(p, i), onfocus: () => describe(p, i),
      }, el("img", { src: `thumbs/${p.id}.webp`, alt: "", width: 420, height: 543, loading: i ? "lazy" : "eager" }));
      return sheet;
    }));
    $("#latest").addEventListener("mouseleave", () => latest.length && describe(latest[0], 0));
    if (latest.length) describe(latest[0], 0);

    const years = [...new Set(papers.map((p) => p.year))];
    $("#year").append(...years.map((y) => el("option", { value: y }, y)));
  }

  function matches(p) {
    if (filter.year && p.year !== filter.year) return false;
    if (filter.person && !p.qusoft.includes(filter.person)) return false;
    if (filter.who === "alumni" && !p.qusoft.some((n) => people[n]?.alumni)) return false;
    if (filter.who === "current" && !p.qusoft.some((n) => people[n] && !people[n].alumni)) return false;
    if (filter.q) return fold(filter.q).split(/\s+/).every((w) => p.haystack.includes(w));
    return true;
  }

  function renderList() {
    const shown = papers.filter(matches);
    const groups = new Map();
    for (const p of shown) (groups.get(p.year) || groups.set(p.year, []).get(p.year)).push(p);

    const count = $("#result-count");
    const total = shown.length === papers.length ? `All ${papers.length} papers` : `${shown.length} of ${papers.length} papers`;
    count.replaceChildren(filter.person ? `${total} with ${filter.person}` : total);
    if (filter.person) {
      count.append(el("button", { type: "button", class: "link-button", onclick: () => { location.hash = "papers"; } }, "Show everyone's papers"));
    }

    const list = $("#paper-list");
    untypeset(list);
    if (!shown.length) {
      list.replaceChildren(el("p", { class: "empty" }, "No papers match. Try fewer words, or set the year to all years."));
      return;
    }
    list.replaceChildren(...[...groups].map(([year, ps]) => el("section", { class: "year-group", "aria-label": year },
      el("h2", { class: "year-label" }, year),
      el("ol", { class: "papers", reversed: true }, ps.map(paperItem)))));
    typeset(list.querySelectorAll(".paper-title"));
  }

  function showPapers(params) {
    if (!rendered.papers) {
      renderIntro();
      $("#q").addEventListener("input", (e) => { filter.q = e.target.value.trim(); renderList(); });
      $("#year").addEventListener("change", (e) => { filter.year = e.target.value; renderList(); });
      document.querySelectorAll('input[name="who"]').forEach((r) =>
        r.addEventListener("change", (e) => { filter.who = e.target.value; renderList(); }));
      rendered.papers = true;
    }
    filter.person = params.get("person") || "";
    renderList();
    if (filter.person) $("#result-count").scrollIntoView({ block: "start" });
  }

  // ---------- people: co-authorship network ----------

  function renderNetwork() {
    const names = Object.keys(people);
    const alumni = names.filter((n) => people[n].alumni).length;
    $("#people-lede").textContent =
      `${names.length} people have written QuSoft papers since ${stats.first_year}, ${alumni} of them now alumni. ` +
      "A line joins two people who have written a paper together. Move the slider to see how the group grew.";

    const svg = d3.select("#network");
    const box = svg.node().getBoundingClientRect();
    const W = box.width, H = box.height, R = Math.max(14, Math.min(20, W / 44));
    svg.attr("viewBox", [0, 0, W, H]);

    // The year each person, and each pair, first appears on a QuSoft paper.
    const firstYear = new Map(), pairYear = new Map();
    const pairKey = (a, b) => (a < b ? `${a}\n${b}` : `${b}\n${a}`);
    for (const p of papers) {
      const y = +p.date.slice(0, 4);
      const q = [...new Set(p.authors.map(([, person]) => person).filter(Boolean))];
      for (const n of q) if (!(firstYear.get(n) <= y)) firstYear.set(n, y);
      for (let i = 0; i < q.length; i++) for (let j = i + 1; j < q.length; j++) {
        const k = pairKey(q[i], q[j]);
        if (!(pairYear.get(k) <= y)) pairYear.set(k, y);
      }
    }
    const lastYear = d3.max(papers, (p) => +p.date.slice(0, 4));
    // The year someone left: the last year in "2018–2022", "until 2022" or "2026".
    const leftIn = (d) => (d.alumni ? +((d.years || "").match(/\d{4}(?!.*\d{4})/) || [lastYear])[0] : Infinity);

    const nodes = names.map((n) => ({ id: n, ...people[n], since: firstYear.get(n) ?? stats.first_year }));
    const links = stats.edges.map(([a, b]) => ({ source: a, target: b, since: pairYear.get(pairKey(a, b)) ?? stats.first_year }));

    const defs = svg.append("defs");
    defs.append("clipPath").attr("id", "clip-circle").attr("clipPathUnits", "objectBoundingBox")
      .append("circle").attr("cx", 0.5).attr("cy", 0.5).attr("r", 0.5);

    const edge = svg.append("g").selectAll("line").data(links).join("line").attr("class", "edge");
    const node = svg.append("g").selectAll("g").data(nodes).join("g")
      .attr("class", "node")
      .attr("role", "button");
    node.append("circle").attr("class", "ring").attr("r", R);
    node.filter((d) => !d.portrait).append("text").attr("class", "initials")
      .text((d) => initials(d.id));
    node.filter((d) => d.portrait).append("image")
      .attr("href", (d) => d.portrait)
      .attr("x", -R + 2).attr("y", -R + 2).attr("width", 2 * R - 4).attr("height", 2 * R - 4)
      .attr("clip-path", "url(#clip-circle)")
      .attr("preserveAspectRatio", "xMidYMid slice");
    const label = svg.append("text").attr("class", "label");

    const sim = d3.forceSimulation()
      .force("link", d3.forceLink().id((d) => d.id).distance(R * 4).strength(0.35))
      .force("charge", d3.forceManyBody().strength(-R * 9))
      .force("collide", d3.forceCollide(R + 3))
      .force("x", d3.forceX(W / 2).strength(0.05))
      .force("y", d3.forceY(H / 2).strength(0.07))
      .stop();

    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    function draw() {
      for (const d of sim.nodes()) { d.x = clamp(d.x, R + 2, W - R - 2); d.y = clamp(d.y, R + 2, H - R - 2); }
      edge.filter((d) => d.shown)
        .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      node.filter((d) => d.shown).attr("transform", (d) => `translate(${d.x},${d.y})`);
    }
    sim.on("tick", draw);
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let drawn = false;
    let year = lastYear, neighbours = new Map();
    const end = (e) => e.id ?? e; // a link end is a name until the simulation has seen the link
    function showYear(y) {
      year = y;
      const byId = new Map(nodes.map((d) => [d.id, d]));
      for (const d of nodes) {
        const was = d.shown;
        d.shown = d.since <= y;
        d.alumNow = leftIn(d) <= y;
        if (d.shown && !was) {
          // Newcomers start next to someone they wrote with, so the group grows outwards.
          const near = links.filter((l) => l.since <= y && (end(l.source) === d.id || end(l.target) === d.id))
            .map((l) => byId.get(end(l.source) === d.id ? end(l.target) : end(l.source)))
            .find((n) => n.shown && n.x != null && n.since < y);
          const a = Math.random() * 2 * Math.PI;
          d.x = (near ? near.x : W / 2) + Math.cos(a) * R * 2;
          d.y = (near ? near.y : H / 2) + Math.sin(a) * R * 2;
          d.vx = d.vy = 0;
        }
      }
      const shownLinks = links.filter((l) => l.since <= y);
      for (const l of links) l.shown = l.since <= y;
      neighbours = new Map(nodes.map((d) => [d.id, new Set()]));
      for (const l of shownLinks) {
        const a = end(l.source), b = end(l.target);
        neighbours.get(a).add(b); neighbours.get(b).add(a);
      }

      node.attr("display", (d) => (d.shown ? null : "none"))
        .attr("tabindex", (d) => (d.shown ? 0 : -1))
        .classed("alumni", (d) => d.alumNow)
        .attr("aria-label", (d) => `${d.id}${d.alumNow ? `, alumni${d.years ? ` ${d.years}` : ""}` : ""}`);
      edge.attr("display", (d) => (d.shown ? null : "none"));

      sim.nodes(nodes.filter((d) => d.shown));
      sim.force("link").links(shownLinks);
      if (still) { sim.alpha(1); for (let i = 0; i < 300; i++) sim.tick(); draw(); }
      else sim.alpha(year === lastYear && !drawn ? 1 : 0.5).restart();
      drawn = true;

      const shownPeople = nodes.filter((d) => d.shown).length;
      $("#network-year-out").textContent = y;
      $("#network-count").textContent = y === lastYear
        ? `All ${shownPeople} people, with ${shownLinks.length} pairs who have written together.`
        : `By the end of ${y}: ${shownPeople} people, with ${shownLinks.length} pairs who have written together.`;
      if (focused && !focused.shown) clear(); else if (focused) focus(focused);
    }
    let focused = null;
    function showLabel(d) {
      const right = d.x < W - 200;
      label.attr("x", d.x + (right ? R + 6 : -R - 6)).attr("y", d.y + 4)
        .attr("text-anchor", right ? "start" : "end").text(d.id);
    }
    function focus(d) {
      focused = d;
      const near = neighbours.get(d.id);
      svg.classed("focused", true);
      node.classed("on", (n) => n.id === d.id || near.has(n.id));
      edge.classed("on", (l) => l.shown && (l.source.id === d.id || l.target.id === d.id));
      showLabel(d);
      const role = ROLE[d.role] || "";
      const who = d.alumNow ? `alumni${d.years ? `, at QuSoft ${d.years}` : ""}` : role;
      const together = [...near].sort();
      $("#network-caption").replaceChildren(
        el("strong", {}, d.id), who ? `, ${who}. ` : ". ",
        together.length ? `${year === lastYear ? "Has written" : `By ${year} had written`} with ${together.join(", ")}. ` : "",
        el("a", { href: `#papers?person=${encodeURIComponent(d.id)}` }, `See papers with ${d.id}`));
    }
    function clear() {
      focused = null;
      svg.classed("focused", false);
      node.classed("on", false); edge.classed("on", false);
      label.text("");
      $("#network-caption").textContent = "Pick someone to see their co-authors and papers.";
    }
    node.on("click", (e, d) => { e.stopPropagation(); focused === d ? clear() : focus(d); })
      .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focus(d); } if (e.key === "Escape") clear(); })
      .on("mouseenter focus", (e, d) => { if (!focused) showLabel(d); })
      .on("mouseleave blur", () => { if (!focused) label.text(""); else showLabel(focused); });
    svg.on("click", clear);

    // Year slider, and a play button that runs through the years.
    const slider = $("#network-year"), play = $("#play");
    slider.min = stats.first_year; slider.max = lastYear; slider.value = lastYear;
    let timer = null;
    function stop() { clearInterval(timer); timer = null; play.textContent = "Play"; }
    slider.addEventListener("input", () => { stop(); showYear(+slider.value); });
    play.addEventListener("click", () => {
      if (timer) return stop();
      if (year >= lastYear) { slider.value = stats.first_year; showYear(stats.first_year); }
      play.textContent = "Pause";
      timer = setInterval(() => {
        if (year >= lastYear) return stop();
        slider.value = year + 1; showYear(year + 1);
      }, 1100);
    });
    showYear(lastYear);
  }

  // ---------- people: year-by-year numbers (group level only) ----------

  function barChart(rows, value, format) {
    const w = 320, h = 120, pad = { t: 16, b: 18 };
    const x = d3.scaleBand().domain(rows.map((r) => r.year)).range([0, w]).padding(0.18);
    const y = d3.scaleLinear().domain([0, d3.max(rows, value) || 1]).range([h - pad.b, pad.t]);
    const svg = d3.create("svg").attr("viewBox", [0, 0, w, h]).attr("role", "img");
    const thisYear = new Date().getFullYear();
    svg.append("g").selectAll("rect").data(rows).join("rect")
      .attr("class", (r) => `bar${r.year === thisYear ? " last" : ""}`)
      .attr("x", (r) => x(r.year)).attr("width", x.bandwidth())
      .attr("y", (r) => y(value(r))).attr("height", (r) => y(0) - y(value(r)))
      .append("title").text((r) => `${r.year}: ${format(value(r))}`);
    const ends = [rows[0], rows[rows.length - 1]];
    svg.append("g").attr("class", "axis").selectAll("text").data(ends).join("text")
      .attr("x", (r) => x(r.year) + x.bandwidth() / 2).attr("y", h - 4).attr("text-anchor", "middle").text((r) => r.year);
    const peak = rows.reduce((a, b) => (value(b) > value(a) ? b : a));
    svg.append("text").attr("class", "value").attr("x", x(peak.year) + x.bandwidth() / 2).attr("y", y(value(peak)) - 4)
      .attr("text-anchor", "middle").text(format(value(peak)));
    svg.attr("aria-label", rows.map((r) => `${r.year}: ${format(value(r))}`).join(", "));
    return svg.node();
  }

  function renderNumbers() {
    const rows = stats.by_year;
    const pct = (r) => (r.papers ? (100 * r.together) / r.papers : 0);
    const thisYear = new Date().getFullYear();
    const sofar = rows.some((r) => r.year === thisYear) ? ` ${thisYear} so far in red.` : "";
    const charts = [
      ["Papers", "Papers with a QuSoft affiliation, per year." + sofar, (r) => r.papers, (v) => String(v)],
      ["People publishing", "Current and former members on at least one paper that year.", (r) => r.contributors, (v) => String(v)],
      ["Written together", "Share of papers with two or more QuSoft authors.", pct, (v) => `${Math.round(v)}%`],
      ["With alumni", "Papers with at least one QuSoft alum among the authors.", (r) => r.with_alumni, (v) => String(v)],
    ];
    $("#numbers").replaceChildren(...charts.map(([title, note, value, format]) =>
      el("div", { class: "chart" }, el("h3", {}, title), el("p", {}, note), barChart(rows, value, format))));
  }

  // ---------- print ----------

  const PRINTED = "qusoft-printed";

  function renderPrint() {
    const saved = store.get(PRINTED, { ids: [], last: null });
    const printed = new Set(saved.ids);
    const since = saved.last || new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10);
    const all = papers.filter((p) => p.page).sort((a, b) => (b.added + b.date).localeCompare(a.added + a.date));
    const unprinted = (p) => !printed.has(p.id) && p.added >= since;
    const ticked = new Set(all.filter(unprinted).map((p) => p.id));
    let limit = Math.max(24, all.filter((p) => daysAgo(p.added) <= 90).length);

    const grid = $("#print-grid");
    function card(p) {
      const box = el("input", { type: "checkbox", value: p.id, "aria-label": p.title });
      box.checked = ticked.has(p.id);
      box.addEventListener("change", () => { box.checked ? ticked.add(p.id) : ticked.delete(p.id); update(); });
      return el("label", { class: "pick" }, box,
        el("img", { src: `thumbs/${p.id}.webp`, alt: "", loading: "lazy", width: 420, height: 543 }),
        el("span", { class: "cap" }, p.title),
        el("span", { class: "when" }, formatDate(p.date), printed.has(p.id) ? el("span", { class: "printed" }, ", printed") : null));
    }
    function draw() {
      untypeset(grid);
      grid.replaceChildren(...all.slice(0, limit).map(card));
      typeset(grid.querySelectorAll(".cap"));
      $("#print-more").hidden = limit >= all.length;
      $("#print-empty").hidden = ticked.size > 0 || all.some(unprinted);
    }
    function update() {
      const n = ticked.size;
      const pages = n === 1 ? "1 page" : `${n} pages`;
      $("#print-status").textContent = n ? `${n === 1 ? "1 paper" : `${n} papers`} ticked` : "No papers ticked";
      $("#download").textContent = n ? `Download ${pages} for printing` : "Download for printing";
      $("#mark-printed").textContent = n ? `Mark ${n} as printed` : "Mark as printed";
      $("#download").disabled = $("#mark-printed").disabled = !n;
    }

    $("#print-more").addEventListener("click", () => { limit += 48; draw(); });
    $("#select-none").addEventListener("click", () => { ticked.clear(); draw(); update(); });
    $("#select-unprinted").addEventListener("click", () => {
      ticked.clear(); all.filter(unprinted).forEach((p) => ticked.add(p.id)); draw(); update();
    });

    $("#download").addEventListener("click", async () => {
      const ids = all.filter((p) => ticked.has(p.id)).map((p) => p.id);
      const status = $("#print-status");
      $("#download").disabled = true;
      status.textContent = `Making the PDF (${ids.length} pages)…`;
      try {
        const out = await PDFLib.PDFDocument.create();
        for (const id of ids) {
          const bytes = await fetch(`firstpages/${id}.pdf`).then((r) => {
            if (!r.ok) throw new Error(`first page of ${id} is missing`);
            return r.arrayBuffer();
          });
          const src = await PDFLib.PDFDocument.load(bytes);
          const [page] = await out.copyPages(src, [0]);
          out.addPage(page);
        }
        const blob = new Blob([await out.save()], { type: "application/pdf" });
        const name = `qusoft-papers-${today()}.pdf`;
        const a = el("a", { href: URL.createObjectURL(blob), download: name });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 10000);
        status.textContent = `Downloaded ${name}. After printing, mark these papers as printed.`;
      } catch (err) {
        status.textContent = `Couldn't make the PDF: ${err.message}. Reload the page and try again.`;
      } finally {
        $("#download").disabled = false;
      }
    });

    $("#mark-printed").addEventListener("click", () => {
      const n = ticked.size;
      ticked.forEach((id) => printed.add(id));
      store.set(PRINTED, { ids: [...printed], last: today() });
      ticked.clear();
      draw(); update();
      $("#print-status").textContent = `Marked ${n === 1 ? "1 paper" : `${n} papers`} as printed.`;
    });

    draw(); update();
  }

  // ---------- start ----------

  load().then(() => {
    $("#updated").textContent = formatDate(stats.updated.slice(0, 10));
    window.addEventListener("hashchange", route);
    route();
  }).catch((err) => {
    $("#papers-lede").textContent = `The paper list didn't load (${err.message}). Reload the page to try again.`;
  });
})();
