/* QuSoft papers: list, numbers, print. Data comes from data/*.json, built by scripts/update.py. */
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
  // A paper is news only if the site found it soon after it appeared. Papers found later (the launch
  // import, other servers, rule changes) keep their real date but don't count as new.
  const foundWithin = (p, days) => daysAgo(p.date) - daysAgo(p.added) <= days;
  const isFresh = (p, days) => daysAgo(p.added) <= days && foundWithin(p, 14);

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

  const SOURCE = { arxiv: "arXiv", eccc: "ECCC", eprint: "IACR ePrint", ssrn: "SSRN", chemrxiv: "ChemRxiv" };
  const ROLE = { "PhD Students": "PhD student", "Postdocs": "postdoc", "Senior Researchers": "senior researcher", "Support Team": "support team", "Visitor": "visitor", "Turing Chair": "Turing chair" };

  // ---------- data ----------

  let papers = [], people = {}, stats = {}, taxonomy = { lines: [] };
  const lineById = {}, topicById = {};

  async function load() {
    const get = (f) => fetch(`data/${f}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${f}: ${r.status}`);
      return r.json();
    });
    [papers, people, stats, taxonomy] = await Promise.all([get("papers.json"), get("people.json"), get("stats.json"),
      get("topics.json").catch(() => ({ lines: [] }))]);
    for (const l of taxonomy.lines) {
      lineById[l.id] = l;
      for (const t of l.topics) topicById[t.id] = { ...t, line: l.id };
    }
    for (const p of papers) {
      p.year = p.date.slice(0, 4);
      p.qusoft = p.authors.filter(([, person]) => person).map(([, person]) => person);
      p.haystack = fold([p.title, p.authors.map((a) => a[0]).join(" "), p.abstract, subject(p.categories)].join(" "));
    }
  }

  // ---------- routing ----------

  const views = ["papers", "research", "people", "theses", "print"];
  const rendered = {};

  function route() {
    const [view, query] = (location.hash.slice(1) || "papers").split("?");
    const old = { numbers: "research" }; // earlier tab
    const name = old[view] || (views.includes(view) ? view : "papers");
    for (const v of views) $(`#view-${v}`).hidden = v !== name;
    document.querySelectorAll("nav a").forEach((a) => {
      if (a.dataset.view === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const params = new URLSearchParams(query || "");
    if (name === "papers") showPapers(params);
    if (name === "research" && !rendered.research) { renderResearch(); renderNumbers(); rendered.research = true; }
    if (name === "people" && !rendered.people) { renderPeople(); rendered.people = true; }
    if (name === "theses") showTheses(params);
    if (name === "print" && !rendered.print) { renderPrint(); rendered.print = true; }
  }

  // ---------- papers ----------

  const filter = { q: "", year: "", who: "", person: "", topic: "", line: "" };

  const initials = (name) => name.split(/\s+/).filter((w) => /^[A-ZÀ-Ž]/.test(w)).map((w) => w[0]).slice(0, 2).join("");

  function authorLine(p) {
    const parts = [];
    p.authors.forEach(([name, person], i) => {
      if (i) parts.push(", ");
      const info = person && people[person];
      if (!info) { parts.push(name); return; }
      // A small portrait before the name (decorative: the name follows), initials when there's no photo.
      const head = info.portrait
        ? el("img", { class: "head", src: info.portrait, alt: "", loading: "lazy", width: 28, height: 28 })
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

  const LEVEL = "qusoft-abstract-level";
  let level = "technical";
  try { level = localStorage.getItem(LEVEL) || "technical"; } catch (err) { /* private mode */ }

  function summaryBlock(p) {
    if (level === "technical" || !p.summary) return null;
    return el("div", { class: "summary" },
      el("p", {}, latexText(p.summary[level])),
      el("p", { class: "ai-note" }, p.summary.checked
        ? "Plain-language summary, checked by the authors."
        : "Plain-language summary written with AI from the abstract; not checked by the authors."));
  }

  function topicLine(p) {
    const ts = (p.topics || []).filter((t) => topicById[t]);
    if (!ts.length) return null;
    const parts = [];
    ts.forEach((t, i) => {
      if (i) parts.push(", ");
      parts.push(el("a", { href: `#papers?topic=${t}` }, topicById[t].name));
    });
    return el("p", { class: "topics" },
      el("span", { class: "swatch", style: `--c: var(--line-${lineById[p.line]?.slot || 0})`, title: lineById[p.line]?.name || "" }),
      parts);
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
    const isNew = isFresh(p, 7);
    return el("li", { class: "paper" },
      el("h3", { class: "paper-title" }, el("a", { href: p.link }, p.title)),
      authorLine(p),
      el("p", { class: "meta" },
        isNew ? el("span", { class: "new" }, "Added this week") : null,
        el("span", {}, [formatDate(p.date), subject(p.categories)].filter(Boolean).join(", ")),
        el("a", { href: p.link }, SOURCE[p.source] || "arXiv"),
        p.page ? el("a", { href: `firstpages/${p.id}.pdf` }, "First page") : null,
        p.abstract ? toggle : null),
      topicLine(p),
      summaryBlock(p),
      abstract);
  }

  function renderIntro() {
    const recent = papers.filter((p) => isFresh(p, 7)).length;
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
    if (filter.topic && !(p.topics || []).includes(filter.topic)) return false;
    if (filter.line && p.line !== filter.line) return false;
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
    const about = filter.person ? ` with ${filter.person}`
      : filter.topic ? ` on ${topicById[filter.topic]?.name || filter.topic}`
      : filter.line ? ` in ${lineById[filter.line]?.name || filter.line}` : "";
    count.replaceChildren(total + about);
    if (filter.person || filter.topic || filter.line) {
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
      // Which abstract to show: the authors' technical one, or a plain-language version.
      const levels = document.querySelectorAll('input[name="level"]');
      levels.forEach((r) => { r.checked = r.value === level; });
      levels.forEach((r) => r.addEventListener("change", (e) => {
        level = e.target.value;
        try { localStorage.setItem(LEVEL, level); } catch (err) { /* private mode: not remembered */ }
        renderList();
      }));
      rendered.papers = true;
    }
    document.querySelectorAll('input[name="level"]').forEach((r) => { r.checked = r.value === level; });
    filter.person = params.get("person") || "";
    filter.topic = params.get("topic") || "";
    filter.line = params.get("line") || "";
    renderList();
    if (filter.person || filter.topic || filter.line) $("#result-count").scrollIntoView({ block: "start" });
  }

  // ---------- research: lines and topics (group level only) ----------

  const lineColor = (id) => `var(--line-${lineById[id]?.slot || 0})`;

  function tooltip() {
    let tip = $("#viz-tip");
    if (!tip) { tip = el("div", { id: "viz-tip", class: "viz-tip", role: "status", hidden: true }); document.body.append(tip); }
    return {
      show(e, html) {
        tip.replaceChildren(...html); tip.hidden = false;
        const r = tip.getBoundingClientRect();
        const x = Math.min(e.clientX + 14, innerWidth - r.width - 8), y = Math.max(8, e.clientY - r.height - 10);
        tip.style.left = `${x}px`; tip.style.top = `${y}px`;
      },
      hide() { tip.hidden = true; },
    };
  }

  function renderResearch() {
    const lines = taxonomy.lines;
    if (!lines.length) return;
    const tagged = papers.filter((p) => lineById[p.line]);
    const years = d3.range(d3.min(tagged, (p) => +p.year), d3.max(tagged, (p) => +p.year) + 1);
    const thisYear = new Date().getFullYear();
    const count = (pred) => years.map((y) => tagged.filter((p) => +p.year === y && pred(p)).length);
    const perLine = Object.fromEntries(lines.map((l) => [l.id, count((p) => p.line === l.id)]));
    const tip = tooltip();

    $("#research-lede").textContent = `${tagged.length} papers in five research lines, with ${Object.keys(topicById).length} topics ` +
      "within them, inferred from the titles and abstracts of the papers.";
    $("#topics-method").textContent = "How this was made: papers were grouped by the words in their titles and abstracts, " +
      "the groups were named as research lines and topics, and each paper was then read and tagged with AI, " +
      "checked against the groups and by hand on a sample. A paper has one main line and up to three topics.";

    // Legend: one entry per line, linking to its papers.
    $("#line-legend").replaceChildren(...lines.map((l) => el("li", {},
      el("a", { href: `#papers?line=${l.id}`, title: l.about },
        el("span", { class: "swatch", style: `--c: ${lineColor(l.id)}` }), l.name,
        el("span", { class: "n" }, String(d3.sum(perLine[l.id])))))));

    // Stacked columns: papers per year, by main research line.
    const W = 720, H = 300, m = { t: 12, r: 8, b: 26, l: 30 };
    const x = d3.scaleBand().domain(years).range([m.l, W - m.r]).paddingInner(0.22).paddingOuter(0.05);
    const totals = years.map((_, i) => d3.sum(lines, (l) => perLine[l.id][i]));
    const y = d3.scaleLinear().domain([0, d3.max(totals) || 1]).nice().range([H - m.b, m.t]);
    const svg = d3.create("svg").attr("viewBox", [0, 0, W, H]).attr("role", "img").attr("class", "stack")
      .attr("aria-label", "Papers per year by research line. A table version follows.");
    svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(5).slice(1)).join("line")
      .attr("x1", m.l).attr("x2", W - m.r).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
    svg.append("g").attr("class", "axis").selectAll("text").data(y.ticks(5)).join("text")
      .attr("x", m.l - 6).attr("y", (d) => y(d) + 4).attr("text-anchor", "end").text((d) => d);
    svg.append("g").attr("class", "axis").selectAll("text").data(years).join("text")
      .attr("x", (d) => x(d) + x.bandwidth() / 2).attr("y", H - 8).attr("text-anchor", "middle")
      .text((d) => (d === thisYear ? `${d}*` : x.bandwidth() > 30 || d % 2 === 0 ? d : ""));
    years.forEach((yr, i) => {
      let base = 0;
      lines.forEach((l, k) => {
        const v = perLine[l.id][i];
        if (!v) return;
        const y0 = y(base), y1 = y(base + v);
        const top = lines.slice(k + 1).every((o) => !perLine[o.id][i]);
        const h = Math.max(1, y0 - y1 - (base ? 2 : 0)); // 2px surface gap between stacked segments
        svg.append("rect").attr("class", "seg").attr("x", x(yr)).attr("width", x.bandwidth())
          .attr("y", y1).attr("height", h).attr("rx", top ? 3 : 0).attr("fill", lineColor(l.id)).attr("tabindex", -1)
          .on("mousemove", (e) => tip.show(e, [el("strong", {}, `${l.name}, ${yr}`), el("br"), `${v} papers of ${totals[i]}`]))
          .on("mouseleave", () => tip.hide())
          .on("click", () => { location.hash = `papers?line=${l.id}`; });
        base += v;
      });
    });
    $("#lines-chart").replaceChildren(svg.node());
    const peak = years[totals.indexOf(d3.max(totals))];
    $("#lines-caption").textContent = `Papers per year by main research line. ${thisYear}* is the year so far. ` +
      `The busiest year was ${peak}, with ${d3.max(totals)} papers.`;

    // Table version of the same numbers.
    const table = el("table", { class: "data-table" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Year"), lines.map((l) => el("th", { scope: "col" }, l.name)), el("th", { scope: "col" }, "All"))),
      el("tbody", {}, years.map((yr, i) => el("tr", {}, el("th", { scope: "row" }, yr),
        lines.map((l) => el("td", {}, perLine[l.id][i])), el("td", {}, totals[i])))));
    $("#lines-table").replaceChildren(table);
    const toggle = $("#lines-table-toggle");
    toggle.onclick = () => {
      const open = $("#lines-table").hidden;
      $("#lines-table").hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Hide the table" : "Show as a table";
    };

    renderTopicNetwork(tip);

    // Topics: per line, each topic with its papers per year on one shared scale.
    const perTopic = Object.fromEntries(Object.keys(topicById).map((t) => [t, count((p) => (p.topics || []).includes(t))]));
    const tmax = d3.max(Object.values(perTopic), (a) => d3.max(a)) || 1;
    const sw = 168, sh = 30;
    const sx = d3.scaleBand().domain(years).range([0, sw]).paddingInner(0.18);
    const sy = d3.scaleLinear().domain([0, tmax]).range([sh, 2]);
    const spark = (t, line) => {
      const s = d3.create("svg").attr("viewBox", [0, 0, sw, sh]).attr("class", "spark").attr("aria-hidden", "true");
      s.append("line").attr("class", "base").attr("x1", 0).attr("x2", sw).attr("y1", sh - 0.5).attr("y2", sh - 0.5);
      s.selectAll("rect").data(years.map((yr, i) => [yr, perTopic[t][i]]).filter((d) => d[1])).join("rect")
        .attr("x", (d) => sx(d[0])).attr("width", sx.bandwidth()).attr("y", (d) => sy(d[1])).attr("height", (d) => sh - sy(d[1]))
        .attr("rx", 1.5).attr("fill", lineColor(line))
        .on("mousemove", (e, d) => tip.show(e, [el("strong", {}, `${topicById[t].name}, ${d[0]}`), el("br"), `${d[1]} papers`]))
        .on("mouseleave", () => tip.hide());
      return s.node();
    };
    $("#topic-lines").replaceChildren(...lines.map((l) => {
      const ts = l.topics.map((t) => t.id).filter((t) => d3.sum(perTopic[t])).sort((a, b) => d3.sum(perTopic[b]) - d3.sum(perTopic[a]));
      return el("section", { class: "topic-line", "aria-labelledby": `tl-${l.id}` },
        el("h3", { id: `tl-${l.id}` }, el("span", { class: "swatch", style: `--c: ${lineColor(l.id)}` }), l.name),
        el("p", { class: "about" }, l.about),
        el("ol", { class: "topic-rows" }, ts.map((t) => el("li", {},
          el("a", { href: `#papers?topic=${t}`, title: topicById[t].about }, topicById[t].name),
          el("span", { class: "n" }, String(d3.sum(perTopic[t]))),
          spark(t, l.id)))));
    }));

    // People: how many QuSoft people publish in each line per year (no names).
    const peopleIn = (lid) => years.map((yr) => new Set(tagged.filter((p) => +p.year === yr && p.line === lid).flatMap((p) => p.qusoft)).size);
    const perPeople = Object.fromEntries(lines.map((l) => [l.id, peopleIn(l.id)]));
    const pmax = d3.max(Object.values(perPeople), (a) => d3.max(a)) || 1;
    const pw = 300, ph = 110, pm = { t: 14, b: 18 };
    const px = d3.scaleBand().domain(years).range([0, pw]).paddingInner(0.2);
    const py = d3.scaleLinear().domain([0, pmax]).range([ph - pm.b, pm.t]);
    $("#people-lines").replaceChildren(...lines.map((l) => {
      const s = d3.create("svg").attr("viewBox", [0, 0, pw, ph]).attr("role", "img")
        .attr("aria-label", `${l.name}: ` + years.map((yr, i) => `${yr} ${perPeople[l.id][i]}`).join(", "));
      s.append("line").attr("class", "base").attr("x1", 0).attr("x2", pw).attr("y1", ph - pm.b + 0.5).attr("y2", ph - pm.b + 0.5);
      s.selectAll("rect").data(years.map((yr, i) => [yr, perPeople[l.id][i]]).filter((d) => d[1])).join("rect")
        .attr("x", (d) => px(d[0])).attr("width", px.bandwidth()).attr("y", (d) => py(d[1])).attr("height", (d) => ph - pm.b - py(d[1]))
        .attr("rx", 2).attr("fill", lineColor(l.id))
        .on("mousemove", (e, d) => tip.show(e, [el("strong", {}, `${l.name}, ${d[0]}`), el("br"), `${d[1]} people`]))
        .on("mouseleave", () => tip.hide());
      const ends = [years[0], years[years.length - 1]];
      s.append("g").attr("class", "axis").selectAll("text").data(ends).join("text")
        .attr("x", (d) => px(d) + px.bandwidth() / 2).attr("y", ph - 3).attr("text-anchor", "middle").text((d) => d);
      const vals = perPeople[l.id], top = d3.max(vals), at = years[vals.lastIndexOf(top)];
      s.append("text").attr("class", "value").attr("x", px(at) + px.bandwidth() / 2).attr("y", py(top) - 4)
        .attr("text-anchor", "middle").text(top);
      return el("div", { class: "chart" }, el("h3", {}, el("span", { class: "swatch", style: `--c: ${lineColor(l.id)}` }), l.name), s.node());
    }));
  }


  // Topics as a network: circles sized by papers, links for papers shared between topics, with a year slider.
  function renderTopicNetwork(tip) {
    const svg = d3.select("#topic-net");
    const box = svg.node().getBoundingClientRect();
    const W = box.width || 800, H = box.height || 560;
    svg.attr("viewBox", [0, 0, W, H]);
    const tagged = papers.filter((p) => (p.topics || []).some((t) => topicById[t]));
    const first = d3.min(tagged, (p) => +p.year), last = d3.max(tagged, (p) => +p.year);
    const key = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);

    // Running totals per year: papers per topic, and papers shared by each pair of topics.
    const nodes = Object.values(topicById).map((t) => ({ ...t, short: t.short || t.name, byYear: {} }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const pairs = new Map();
    for (const p of tagged) {
      const ts = [...new Set(p.topics.filter((t) => topicById[t]))];
      for (const t of ts) byId.get(t).byYear[p.year] = (byId.get(t).byYear[p.year] || 0) + 1;
      for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
        const k = key(ts[i], ts[j]);
        if (!pairs.has(k)) pairs.set(k, { source: ts[i], target: ts[j], byYear: {} });
        pairs.get(k).byYear[p.year] = (pairs.get(k).byYear[p.year] || 0) + 1;
      }
    }
    const upTo = (byYear, y) => Object.entries(byYear).reduce((s, [yr, n]) => s + (+yr <= y ? n : 0), 0);
    const links = [...pairs.values()];
    const maxN = d3.max(nodes, (n) => upTo(n.byYear, last)) || 1;
    const maxL = d3.max(links, (l) => upTo(l.byYear, last)) || 1;
    const rScale = d3.scaleSqrt().domain([0, maxN]).range([0, Math.max(26, Math.min(46, W / 18))]);
    const wScale = d3.scaleLinear().domain([1, maxL]).range([1, 7]);

    // Each research line pulls its topics towards its own spot around the centre.
    const lines = taxonomy.lines;
    const anchor = Object.fromEntries(lines.map((l, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / lines.length;
      return [l.id, [W / 2 + Math.cos(a) * W * 0.24, H / 2 + Math.sin(a) * H * 0.26]];
    }));
    for (const n of nodes) { n.x = anchor[n.line][0] + (Math.random() - 0.5) * 40; n.y = anchor[n.line][1] + (Math.random() - 0.5) * 40; }

    const edge = svg.append("g").attr("class", "tn-edges").selectAll("line").data(links).join("line").attr("class", "tn-edge");
    const node = svg.append("g").selectAll("g").data(nodes).join("g").attr("class", "tn-node").attr("role", "button");
    node.append("circle").attr("fill", (d) => lineColor(d.line));
    node.append("text").attr("class", "tn-label").attr("text-anchor", "middle");

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink().id((d) => d.id).distance(90).strength((l) => Math.min(0.5, 0.06 * l.n)))
      .force("charge", d3.forceManyBody().strength(-160))
      .force("collide", d3.forceCollide((d) => d.r + 6))
      .force("x", d3.forceX((d) => anchor[d.line][0]).strength(0.08))
      .force("y", d3.forceY((d) => anchor[d.line][1]).strength(0.08))
      .stop();
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    // Names: biggest topics first; a name that would overlap one already placed is left out (it shows on hover).
    const fontPx = W < 640 ? 10.5 : 12;
    let pinned = new Set();
    function placeLabels() {
      const boxes = [];
      for (const d of [...nodes].filter((n) => n.n).sort((a, b) => b.r - a.r)) {
        const w = d.short.length * fontPx * 0.56, h = fontPx + 2;
        d.dx = clamp(d.x, w / 2 + 2, W - w / 2 - 2) - d.x; // keep names inside the picture
        const b = { x0: d.x + d.dx - w / 2, x1: d.x + d.dx + w / 2, y0: d.y + d.r + 3, y1: d.y + d.r + 3 + h };
        const free = !boxes.some((o) => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0);
        d.labelled = pinned.has(d.id) || (free && d.r >= (W < 640 ? 9 : 6));
        if (d.labelled) boxes.push(b);
      }
      node.select("text").attr("x", (d) => d.dx || 0).text((d) => (d.labelled ? d.short : ""));
    }
    function draw() {
      for (const d of nodes) { d.x = clamp(d.x, d.r + 4, W - d.r - 4); d.y = clamp(d.y, d.r + 4, H - d.r - 18); }
      placeLabels();
      edge.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    }
    sim.on("tick", draw);
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let year = last, focused = null, started = false;
    function show(y) {
      year = y;
      for (const n of nodes) { n.n = upTo(n.byYear, y); n.r = n.n ? Math.max(4, rScale(n.n)) : 0; }
      for (const l of links) l.n = upTo(l.byYear, y);
      const live = links.filter((l) => l.n > 0);
      node.attr("display", (d) => (d.n ? null : "none")).attr("tabindex", (d) => (d.n ? 0 : -1))
        .attr("aria-label", (d) => `${d.name}: ${d.n} papers`);
      node.select("circle").attr("r", (d) => d.r);
      // Name every topic that is big enough; small ones get their name on hover.
      node.select("text").attr("y", (d) => d.r + 3 + fontPx).style("font-size", `${fontPx}px`);
      edge.attr("display", (d) => (d.n ? null : "none")).attr("stroke-width", (d) => wScale(Math.max(1, d.n)));
      sim.force("link").links(live);
      sim.force("collide").radius((d) => d.r + 6);
      if (still) { sim.alpha(1); for (let i = 0; i < 300; i++) sim.tick(); draw(); }
      else sim.alpha(started ? 0.4 : 1).restart();
      started = true;
      const shown = nodes.filter((n) => n.n).length;
      const total = tagged.filter((p) => +p.year <= y).length;
      $("#topic-year-out").textContent = y;
      $("#topic-count").textContent = `${y === last ? "All" : `Up to ${y}:`} ${total} papers on ${shown} topics, ` +
        `with ${live.length} pairs of topics sharing papers.`;
      if (focused) (focused.n ? focus(focused) : clear());
    }
    function neighbours(d) {
      return links.filter((l) => l.n && (l.source.id === d.id || l.target.id === d.id))
        .map((l) => ({ t: l.source.id === d.id ? l.target : l.source, n: l.n })).sort((a, b) => b.n - a.n);
    }
    function focus(d) {
      focused = d;
      const near = neighbours(d);
      const ids = new Set([d.id, ...near.map((x) => x.t.id)]);
      svg.classed("focused", true);
      node.classed("on", (n) => ids.has(n.id));
      pinned = ids;
      placeLabels();
      edge.classed("on", (l) => l.source.id === d.id || l.target.id === d.id);
      $("#topic-net-caption").replaceChildren(
        el("strong", {}, d.name), `, ${lineById[d.line].name.toLowerCase()}: ${d.n} papers${year === last ? "" : ` up to ${year}`}. `,
        near.length ? `Shares papers with ${near.map((x) => `${x.t.name} (${x.n})`).join(", ")}. ` : "No shared papers yet. ",
        el("a", { href: `#papers?topic=${d.id}` }, `See the papers on ${d.name.toLowerCase()}`));
    }
    function clear() {
      focused = null;
      svg.classed("focused", false); node.classed("on", false); edge.classed("on", false);
      pinned = new Set();
      placeLabels();
      $("#topic-net-caption").textContent = "Pick a topic to see which topics it connects to.";
    }
    node.on("click", (e, d) => { e.stopPropagation(); focused === d ? clear() : focus(d); })
      .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focus(d); } if (e.key === "Escape") clear(); })
      .on("mousemove", (e, d) => tip.show(e, [el("strong", {}, d.name), el("br"), `${d.n} papers${year === last ? "" : ` up to ${year}`}`]))
      .on("mouseleave", () => tip.hide());
    edge.on("mousemove", (e, l) => tip.show(e, [el("strong", {}, `${l.source.name} and ${l.target.name}`), el("br"), `${l.n} shared papers`]))
      .on("mouseleave", () => tip.hide());
    svg.on("click", clear);

    const slider = $("#topic-year"), play = $("#topic-play");
    slider.min = first; slider.max = last; slider.value = last;
    let timer = null;
    const stop = () => { clearInterval(timer); timer = null; play.textContent = "Play"; };
    slider.addEventListener("input", () => { stop(); show(+slider.value); });
    play.addEventListener("click", () => {
      if (timer) return stop();
      if (year >= last) { slider.value = first; show(first); }
      play.textContent = "Pause";
      timer = setInterval(() => { if (year >= last) return stop(); slider.value = year + 1; show(year + 1); }, 1200);
    });
    show(last);
  }

  // ---------- people: research profiles, everyone with the same weight ----------

  let profiles = null;
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}) => {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const roleLabel = (p) => (p.alumni ? `alumni${p.years ? ` ${p.years}` : ""}` : ROLE[p.role] || "");

  function profileRing(p) {
    // The same size for everyone; the ring shows shares of research lines, starting at the top.
    const R = 45, C = 2 * Math.PI * R;
    const svg = svgEl("svg", { viewBox: "0 0 100 100", class: "ring", "aria-hidden": "true" });
    const id = `pc-${initials(p.name)}-${Math.random().toString(36).slice(2, 7)}`;
    const defs = svgEl("defs"), clip = svgEl("clipPath", { id });
    clip.append(svgEl("circle", { cx: 50, cy: 50, r: 37 })); defs.append(clip); svg.append(defs);
    const parts = taxonomy.lines.filter((l) => p.shares[l.id]);
    if (!parts.length) svg.append(svgEl("circle", { cx: 50, cy: 50, r: R, fill: "none", stroke: "var(--rule)", "stroke-width": 7 }));
    let at = 0;
    for (const l of parts) {
      const len = p.shares[l.id] * C;
      svg.append(svgEl("circle", { cx: 50, cy: 50, r: R, fill: "none", stroke: lineColor(l.id), "stroke-width": 7,
        "stroke-dasharray": `${Math.max(len - (parts.length > 1 ? 3 : 0), 0.5)} ${C}`, "stroke-dashoffset": -at, transform: "rotate(-90 50 50)" }));
      at += len;
    }
    if (p.portrait) {
      svg.append(svgEl("image", { href: p.portrait, x: 13, y: 13, width: 74, height: 74, "clip-path": `url(#${id})`, preserveAspectRatio: "xMidYMid slice" }));
    } else {
      svg.append(svgEl("circle", { cx: 50, cy: 50, r: 37, fill: "var(--rule)" }));
      const t = svgEl("text", { x: 50, y: 50, "text-anchor": "middle", "dominant-baseline": "central", class: "ring-initials" });
      t.textContent = initials(p.name); svg.append(t);
    }
    return svg;
  }

  function profileCard(p) {
    const parts = taxonomy.lines.filter((l) => p.shares[l.id]).sort((a, b) => p.shares[b.id] - p.shares[a.id]);
    const topicsOf = (list) => list.filter((t) => topicById[t]).map((t) => topicById[t].name);
    return el("li", { class: "profile-card", id: "profile-card" },
      el("h3", {}, p.name), el("p", { class: "muted" }, roleLabel(p)),
      parts.length ? [
        el("div", { class: "share-bar", "aria-hidden": "true" }, parts.map((l) => el("span", { style: `flex:${p.shares[l.id]}; background:${lineColor(l.id)}` }))),
        el("p", {}, "Mostly ", parts.map((l) => l.name.toLowerCase()).join(", then "), "."),
        el("ul", { class: "chips" }, topicsOf(p.topics.slice(0, 6)).map((t, i) => el("li", {}, el("a", { href: `#papers?topic=${p.topics[i]}` }, t)))),
        p.topics.length > 6 ? el("p", { class: "muted" }, "Also: ", topicsOf(p.topics.slice(6)).join(", "), ".") : null,
        el("p", {}, el("a", { href: `#papers?person=${encodeURIComponent(p.name)}` }, `Papers with ${p.name}`)),
      ] : el("p", { class: "muted" }, "No papers on this site yet."));
  }

  async function renderPeople() {
    if (!profiles) {
      try { profiles = await fetch("data/profiles.json", { cache: "no-cache" }).then((r) => r.json()); }
      catch (err) { $("#profile-grid").replaceChildren(el("li", { class: "empty" }, "The profiles could not be loaded. Reload the page to try again.")); return; }
      $("#people-legend").replaceChildren(...taxonomy.lines.map((l) => el("li", {},
        el("a", { href: `#papers?line=${l.id}` }, el("span", { class: "swatch", style: `--c: ${lineColor(l.id)}` }), l.name))));
      document.querySelectorAll('input[name="whom"]').forEach((r) => r.addEventListener("change", () => { openProfile = null; drawPeople(); }));
    }
    drawPeople();
  }

  let openProfile = null;
  function drawPeople() {
    const whom = document.querySelector('input[name="whom"]:checked')?.value || "current";
    const shown = profiles.filter((p) => whom === "all" || (whom === "alumni" ? p.alumni : !p.alumni));

    // Research profiles: a grid of equal faces; a picked face opens its card below its row.
    const items = [];
    let picked = null;
    for (const p of shown) {
      const btn = el("button", { type: "button", class: "profile", "aria-expanded": String(openProfile === p.name), "aria-controls": "profile-card",
        onclick: () => { openProfile = openProfile === p.name ? null : p.name; drawPeople(); } },
        profileRing(p), el("span", { class: "pname" }, p.name), el("span", { class: "prole" }, roleLabel(p)));
      const li = el("li", {}, btn);
      if (openProfile === p.name) picked = [li, p];
      items.push(li);
    }
    $("#profile-grid").replaceChildren(...items);
    if (picked) {
      let last = picked[0];
      while (last.nextElementSibling && last.nextElementSibling.offsetTop === picked[0].offsetTop) last = last.nextElementSibling;
      last.after(profileCard(picked[1]));
      picked[0].querySelector("button").focus({ preventScroll: true });
      $("#profile-card").scrollIntoView({ block: "nearest" });
    }

    // Who to talk to about...: every topic with its people, alphabetically, without counts.
    $("#talk-to").replaceChildren(...taxonomy.lines.map((l) => el("section", { class: "talk-line" },
      el("h3", {}, el("span", { class: "swatch", style: `--c: ${lineColor(l.id)}` }), l.name),
      l.topics.map((t) => {
        const who = shown.filter((p) => p.topics.includes(t.id));
        return el("div", { class: "talk-topic" },
          el("a", { class: "talk-name", href: `#papers?topic=${t.id}` }, t.name),
          who.length ? el("div", { class: "talk-faces" }, who.map((p) => el("a", {
            href: `#papers?person=${encodeURIComponent(p.name)}`, title: `${p.name}, ${roleLabel(p)}`, "aria-label": `${p.name}, ${roleLabel(p)}` },
            p.portrait ? el("img", { class: `talk-face${p.alumni ? " alum" : ""}`, src: p.portrait, alt: "", loading: "lazy", width: 44, height: 44 })
                       : el("span", { class: `talk-face initials${p.alumni ? " alum" : ""}` }, initials(p.name)))))
            : el("span", { class: "muted" }, whom === "current" ? "No current members yet." : "Nobody yet."));
      }))));
  }

  // ---------- theses: a wall of covers that turn over ----------

  let theses = null;
  const canHover = window.matchMedia("(hover: hover) and (pointer: fine)");
  const paragraphs = (text) => (text || "").split(/\n\s*\n/).filter(Boolean);

  // The text on the back of a cover, at the chosen level. Technical: the first paragraph.
  function thesisBlurb(t) {
    if (level !== "technical" && t.summary) return t.summary[level];
    return paragraphs(t.abstract)[0] || "";
  }

  function authorHead(t, size) {
    return t.portrait
      ? el("img", { class: "thesis-head", src: t.portrait, alt: "", loading: "lazy", width: size, height: size })
      : el("span", { class: "thesis-head initials", "aria-hidden": "true" }, initials(t.author));
  }

  function thesisCard(t) {
    const style = `--back: ${t.back}`;
    const front = t.cover
      ? el("img", { class: "cover-img", src: t.cover, alt: "", loading: "lazy", width: 480, height: 679 })
      : el("span", { class: "cover-plain", "aria-hidden": "true" },   // no cover image: a plain cloth binding
          el("span", { class: "plain-title" }, t.title), el("span", { class: "plain-author" }, t.author));
    const open = el("button", { type: "button", class: "thesis-open", "aria-haspopup": "dialog",
      onclick: (e) => { e.stopPropagation(); openThesis(t); } }, t.title);
    const card = el("article", { class: `thesis ink-${t.ink}`, style, "data-slug": t.slug },
      el("div", { class: "thesis-inner" },
        el("div", { class: "face front" }, front),
        el("div", { class: "face back" },
          el("p", { class: "thesis-by" }, authorHead(t, 36), el("span", {}, t.author)),
          el("h3", { class: "thesis-title" }, open),
          el("p", { class: "thesis-year" }, String(t.year)),
          el("p", { class: "thesis-blurb" }, latexText(thesisBlurb(t))),
          el("span", { class: "thesis-more", "aria-hidden": "true" }, "Read more"))));
    // With a mouse, hovering turns the cover and a click opens the thesis. On touch screens
    // the first tap turns the cover over, the second opens it.
    card.addEventListener("click", () => {
      if (canHover.matches || card.classList.contains("turned")) openThesis(t);
      else {
        document.querySelectorAll(".thesis.turned").forEach((c) => c.classList.remove("turned"));
        card.classList.add("turned");
      }
    });
    return card;
  }

  function drawWall() {
    const items = [];
    let year = null;
    for (const t of theses) {
      if (t.year !== year) {
        year = t.year;
        // A spine for each year, read bottom to top like the books on a European shelf.
        items.push(el("li", { class: "year-spine", "aria-hidden": "true" }, el("span", {}, String(year))));
      }
      items.push(el("li", { class: "wall-item" }, el("p", { class: "visually-hidden" }, String(t.year)), thesisCard(t)));
    }
    const wall = $("#thesis-wall");
    untypeset(wall);
    wall.replaceChildren(...items);
    typeset(wall.querySelectorAll(".thesis-title, .thesis-blurb"));
  }

  function openThesis(t, fromRoute = false) {
    const dlg = $("#thesis-dialog");
    const abstract = level !== "technical" && t.summary
      ? [el("p", {}, latexText(t.summary[level])),
         el("p", { class: "ai-note" }, t.summary.checked ? "Plain-language summary, checked by the author."
           : "Plain-language summary written with AI from the abstract; not checked by the author.")]
      : paragraphs(t.abstract).map((para) => el("p", {}, latexText(para)));
    const body = $("#thesis-dialog-body");
    untypeset(body);
    body.replaceChildren(
      t.cover ? el("img", { class: "dialog-cover", src: t.cover, alt: `Cover of ${t.title}`, width: 480, height: 679 })
              : el("div", { class: "dialog-cover cover-plain", style: `--back: ${t.back}` }, el("span", { class: "plain-title" }, t.title)),
      el("div", { class: "dialog-text" },
        el("p", { class: "thesis-by" }, authorHead(t, 44), el("span", {}, t.author)),
        el("h2", { id: "thesis-dialog-title" }, latexText(t.title)),
        el("p", { class: "dialog-meta" }, `PhD thesis, ${t.year}`,
          t.supervisors.length ? `. Supervised by ${t.supervisors.join(", ")}` : ""),
        el("div", { class: "dialog-abstract" }, abstract),
        el("p", { class: "dialog-links" },
          // Straight to the PDF where there is one; the repository page is for citing.
          t.pdf ? el("a", { href: t.pdf }, "Read the thesis (PDF)") : el("a", { href: t.link }, "Read the thesis"),
          t.pdf ? el("a", { class: "secondary", href: t.link }, "Repository page") : null,
          el("a", { href: `#papers?person=${encodeURIComponent(t.author)}` }, `Papers with ${t.author}`))));
    if (!dlg.open) dlg.showModal();
    body.scrollTop = 0;
    typeset(body.querySelectorAll("h2, .dialog-abstract p"));
    if (!fromRoute) history.replaceState(null, "", `#theses?thesis=${t.slug}`);
  }

  async function showTheses(params) {
    if (!theses) {
      try { theses = await fetch("data/theses.json", { cache: "no-cache" }).then((r) => r.json()); }
      catch (err) { $("#theses-lede").textContent = "The theses could not be loaded. Reload the page to try again."; return; }
      const first = Math.min(...theses.map((t) => t.year));
      $("#theses-lede").textContent = `Every PhD thesis written at QuSoft since ${first}, newest first: ${theses.length} so far. `
        + (canHover.matches ? "Point at a cover to turn it over; click it to read more." : "Tap a cover to turn it over; tap again to read more.");
      const levels = document.querySelectorAll('input[name="thesis-level"]');
      levels.forEach((r) => { r.checked = r.value === level; });
      levels.forEach((r) => r.addEventListener("change", (e) => {
        level = e.target.value;   // the same preference as on the papers page
        try { localStorage.setItem(LEVEL, level); } catch (err) { /* private mode: not remembered */ }
        if (rendered.papers) renderList();
        drawWall();
      }));
      const dlg = $("#thesis-dialog");
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });   // click outside closes
      dlg.addEventListener("close", () => {
        const slug = new URLSearchParams(location.hash.split("?")[1] || "").get("thesis");
        history.replaceState(null, "", "#theses");
        document.querySelector(`.thesis[data-slug="${slug}"] .thesis-open`)?.focus({ preventScroll: true });
      });
      drawWall();
    } else {
      document.querySelectorAll('input[name="thesis-level"]').forEach((r) => { r.checked = r.value === level; });
      drawWall();
    }
    const want = theses.find((t) => t.slug === params.get("thesis"));
    if (want) openThesis(want, true);
  }

  // ---------- numbers: year by year (group level only) ----------

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
    const all = papers.filter((p) => p.page).sort((a, b) => b.date.localeCompare(a.date));
    const unprinted = (p) => !printed.has(p.id) && p.added >= since && foundWithin(p, 30);
    const ticked = new Set(all.filter(unprinted).map((p) => p.id));
    let limit = Math.max(24, all.filter((p) => daysAgo(p.date) <= 90).length);

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
