/* wifitrx Android UI.
 *
 * Kotlin exposes `Native` (addJavascriptInterface):
 *   Native.listSpecs()            -> JSON string (sync, fast)
 *   Native.run(key, paramsJson)   -> starts foreground service; result is
 *                                    delivered via ui.onRunResult(json)
 *   Native.saveCalState()         -> JSON string (sync)
 *   Native.pickAndInspect()       -> file picker; ui.onInspectResult(json)
 *   Native.referenceData()        -> JSON string (sync)
 * A desktop-browser fallback stub lets the page be smoke-tested without
 * the app shell (open index.html, everything renders with canned data).
 */
"use strict";

const native = window.Native || {          // browser smoke-test stub
  listSpecs: () => JSON.stringify({ok: true, specs: []}),
  run: () => setTimeout(() => ui.onRunResult(
      JSON.stringify({ok: false, error: "no app shell"})), 0),
  saveCalState: () => JSON.stringify({ok: false, error: "no app shell"}),
  pickAndInspect: () => ui.onInspectResult(
      JSON.stringify({ok: false, error: "no app shell"})),
  referenceData: () => JSON.stringify({ok: true, entries: [], version: 0}),
  referenceVersion: () => JSON.stringify({ok: true, version: 0}),
  saveText: () => JSON.stringify({ok: false, error: "no app shell"}),
  selfCheck: () => setTimeout(() => ui.onSelfCheckResult(
      JSON.stringify({ok: false, error: "no app shell"})), 0),
};

const $ = id => document.getElementById(id);
const LONG_RUN_MHZ = 160;   // >= this: confirm before running (minutes+heat)

/* ---------------- tabs ---------------- */
document.querySelectorAll("nav button").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x =>
        x.classList.toggle("on", x === b));
    document.querySelectorAll("main section").forEach(s =>
        s.classList.toggle("on", s.id === "tab-" + b.dataset.tab));
    // The desktop re-renders Reference on every set_run_results; here the
    // page is cached, so compare the bridge's source version and reload
    // when a run or an inspected file has changed it.
    if (b.dataset.tab === "reference") {
      let v = -1;
      try { v = JSON.parse(native.referenceVersion()).version; } catch (e) { }
      if (ui.refVersion !== v) loadReference(v);
    }
  };
});

/* ---------------- analyses form ---------------- */
let SPECS = [];
function buildForm(spec) {
  $("a-title").textContent = spec.title;
  $("a-desc").textContent = spec.description;
  const form = $("a-form");
  form.innerHTML = "";
  for (const p of spec.params) {
    const row = document.createElement("div");
    row.className = "row";
    const lab = document.createElement("label");
    lab.textContent = p.label;
    if (p.tooltip) lab.title = p.tooltip;
    let w;
    if (p.kind === "bool") {
      w = document.createElement("input");
      w.type = "checkbox"; w.checked = !!p.default;
      w.value_get = () => w.checked;
    } else if (p.kind === "choice") {
      w = document.createElement("select");
      for (const c of p.choices) {
        const o = document.createElement("option");
        o.value = JSON.stringify(c); o.textContent = String(c);
        if (JSON.stringify(c) === JSON.stringify(p.default)) o.selected = true;
        w.appendChild(o);
      }
      w.value_get = () => JSON.parse(w.value);
    } else {                                   // int | float
      w = document.createElement("input");
      w.type = "number"; w.value = p.default;
      if (p.minimum != null) w.min = p.minimum;
      if (p.maximum != null) w.max = p.maximum;
      if (p.kind === "float") w.step = "any";
      w.value_get = () => p.kind === "int" ? parseInt(w.value, 10)
                                           : parseFloat(w.value);
    }
    w.dataset.name = p.name;
    row.appendChild(lab); row.appendChild(w); form.appendChild(row);
  }
}

function currentParams() {
  const out = {};
  for (const w of $("a-form").querySelectorAll("[data-name]"))
    out[w.dataset.name] = w.value_get();
  return out;
}

function init() {
  const r = JSON.parse(native.listSpecs());
  if (!r.ok) { setStatus(r.error, true); return; }
  SPECS = r.specs;
  const pick = $("a-pick");
  for (const s of SPECS) {
    const o = document.createElement("option");
    o.value = s.key; o.textContent = s.title; pick.appendChild(o);
  }
  pick.onchange = () => buildForm(SPECS[pick.selectedIndex]);
  if (SPECS.length) buildForm(SPECS[0]);
}

function setStatus(msg, err) {
  $("status").textContent = msg;
  $("status").className = err ? "err" : "";
}

/* Two-step confirm instead of window.confirm: a WebView without a
 * WebChromeClient suppresses JS dialogs and silently returns false. */
let armedLong = false;
function disarm() { armedLong = false; $("a-run").textContent = "Run"; }
$("a-pick").addEventListener("change", disarm);
$("a-form").addEventListener("change", disarm);

$("a-run").onclick = () => {
  const spec = SPECS[$("a-pick").selectedIndex];
  if (!spec) return;
  const params = currentParams();
  const bw = params.bw_mhz || 0;
  if (bw >= LONG_RUN_MHZ && !armedLong) {
    armedLong = true;
    $("a-run").textContent = "Confirm run (" + bw + " MHz)";
    setStatus(bw + " MHz on a phone SoC takes minutes and runs the CPU " +
              "hot. Tap again to confirm.");
    return;
  }
  disarm();
  $("a-run").disabled = true;
  $("a-out").hidden = true;
  setStatus("running… (screen may be turned off; a notification tracks " +
            "progress)");
  native.run(spec.key, JSON.stringify(params));
};

/* result callback from Kotlin */
const ui = {
  refVersion: null,
  onRunResult(json) {
    $("a-run").disabled = false;
    const r = JSON.parse(json);
    if (!r.ok) { setStatus(r.error, true); return; }
    setStatus("done");
    $("a-save").disabled = !r.has_cal_state;
    const mt = $("a-metrics");
    mt.innerHTML = "<tr><th>metric</th><th>value</th></tr>";
    for (const [k, v] of Object.entries(r.metrics)) {
      const tr = mt.insertRow();
      tr.insertCell().textContent = k;
      tr.insertCell().textContent =
          typeof v === "number" ? v.toFixed(2) : String(v);
    }
    $("a-text").textContent = r.text || "";
    $("a-text").hidden = !r.text;
    const pages = r.pages || [];
    const sel = $("a-page");
    sel.innerHTML = "";
    pages.forEach((p, i) => {
      const o = document.createElement("option");
      o.value = i; o.textContent = p.title; sel.appendChild(o);
    });
    sel.onchange = () => showPage(pages[sel.value]);
    sel.style.display = pages.length > 1 ? "" : "none";
    // unhide BEFORE laying out the SVG: showPage sizes the figure to
    // the container's clientWidth, which is 0 while #a-out is hidden —
    // the "analysis ran but no figure appears" bug on the first device
    if (pages.length) {                 // land on the last page (summary)
      $("a-out").hidden = false;
      sel.value = pages.length - 1;
      showPage(pages[pages.length - 1]);
    }
    $("a-out").hidden = false;
  },
  onSelfCheckResult(json) {
    $("sc-run").disabled = false;
    const r = JSON.parse(json);
    const out = $("sc-out");
    out.textContent = "";
    if (!r.ok) { $("sc-status").textContent = ""; out.textContent = r.error;
                 return; }
    const p = r.platform;
    $("sc-status").textContent =
        `${p.android_abi} · numpy ${p.numpy} · scipy ${p.scipy} · ` +
        `Python ${p.python} — tolerance ${r.tolerance_abs_db} dB abs ` +
        `or ${r.tolerance_rel} rel`;
    const banner = document.createElement("div");
    banner.className = "verdict " + (r.passed ? "pass" : "fail");
    banner.textContent = r.passed
        ? "PASS — this device reproduces the desktop physics"
        : "FAIL — metrics below are outside tolerance";
    out.appendChild(banner);
    for (const c of r.cases) {
      const h = document.createElement("h2");
      h.textContent = `${c.key} — ${c.passed ? "ok" : "FAIL"}`;
      out.appendChild(h);
      const t = makeTable(["metric", "desktop", "device", "delta",
                           "verdict"], c.rows);
      for (const tr of t.querySelectorAll("tr"))
        if (tr.lastChild && tr.lastChild.textContent === "FAIL")
          for (const td of tr.children) td.className = "bad";
      out.appendChild(t);
    }
  },
  onInspectResult(json) {
    const r = JSON.parse(json);
    const out = $("i-out");
    out.textContent = "";
    if (!r.ok) { out.textContent = r.error; return; }
    // findings first, then the same tables the desktop page shows
    const pre = document.createElement("pre");
    pre.className = "txt"; pre.textContent = r.text;
    out.appendChild(pre);
    for (const sec of r.sections || []) {
      const h = document.createElement("h2");
      h.textContent = sec.title; out.appendChild(h);
      out.appendChild(makeTable(sec.columns, sec.rows));
    }
  },
};
window.ui = ui;

$("a-save").onclick = () => {
  const r = JSON.parse(native.saveCalState());
  setStatus(r.ok ? "saved " + r.path + " (README beside it) — opening " +
                   "share sheet" : r.error, !r.ok);
};

/* ---------------- figure pan/zoom (toolbar equivalent) ------------- */
const view = { x: 0, y: 0, k: 1 };
function apply() {
  $("fig-inner").style.transform =
      `translate(${view.x}px,${view.y}px) scale(${view.k})`;
}
function resetView() { view.x = view.y = 0; view.k = 1; apply(); }
$("a-reset").onclick = resetView;

/* Export the figure as SVG — the toolbar's "save the current view" on the
 * desktop.  Vector, so it reopens at any zoom; the shell hands it to the
 * system share sheet rather than a file dialog (the Android idiom). */
function currentPageSvg() {
  const svg = $("fig-inner").querySelector("svg");
  return svg ? svg.outerHTML : null;
}
$("a-export").onclick = () => {
  const svg = currentPageSvg();
  if (!svg) return;
  const sel = $("a-page");
  const name = (sel.options[sel.value] || {}).textContent || "figure";
  const r = JSON.parse(native.saveText(
      name.replace(/[^A-Za-z0-9_.-]+/g, "_") + ".svg", svg));
  setStatus(r.ok ? "exported " + r.path : r.error, !r.ok);
};

function showPage(page) {
  $("fig-inner").innerHTML = page.svg;
  const svg = $("fig-inner").querySelector("svg");
  if (svg) {                     // scale to container width, keep vector
    // clientWidth can still be 0 in edge cases (mid-layout, rotation):
    // fall back to the viewport so the figure is never sized to nothing
    const w = $("fig").clientWidth ||
        (document.documentElement.clientWidth - 18);
    svg.style.width = w + "px"; svg.style.height = "auto";
    svg.removeAttribute("height");
  }
  resetView();
}

const fig = $("fig");
let touches = new Map(), lastDist = 0, lastTap = 0;
fig.addEventListener("pointerdown", e => {
  fig.setPointerCapture(e.pointerId);
  touches.set(e.pointerId, {x: e.clientX, y: e.clientY});
  const now = Date.now();                    // double-tap zoom
  if (touches.size === 1) {
    if (now - lastTap < 300) { view.k = view.k > 1 ? 1 : 2.5; apply(); }
    lastTap = now;
  }
});
fig.addEventListener("pointermove", e => {
  if (!touches.has(e.pointerId)) return;
  const prev = touches.get(e.pointerId);
  touches.set(e.pointerId, {x: e.clientX, y: e.clientY});
  const pts = [...touches.values()];
  if (pts.length === 1) {                    // pan
    view.x += e.clientX - prev.x; view.y += e.clientY - prev.y; apply();
  } else if (pts.length === 2) {             // pinch
    const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    if (lastDist > 0) {
      const c = {x: (pts[0].x + pts[1].x) / 2 - fig.offsetLeft,
                 y: (pts[0].y + pts[1].y) / 2 - fig.offsetTop};
      const s = d / lastDist;
      view.x = c.x - s * (c.x - view.x);
      view.y = c.y - s * (c.y - view.y);
      view.k = Math.min(40, Math.max(0.2, view.k * s));
      apply();
    }
    lastDist = d;
  }
});
["pointerup", "pointercancel"].forEach(ev => fig.addEventListener(ev, e => {
  touches.delete(e.pointerId);
  if (touches.size < 2) lastDist = 0;
}));
fig.addEventListener("wheel", e => {         // desktop smoke-test comfort
  e.preventDefault();
  const s = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  view.k = Math.min(40, Math.max(0.2, view.k * s)); apply();
}, {passive: false});

/* ---------------- inspector / reference ---------------- */
$("i-open").onclick = () => native.pickAndInspect();

$("sc-run").onclick = () => {
  $("sc-run").disabled = true;
  $("sc-out").textContent = "";
  $("sc-status").textContent = "replaying golden cases on this device… " +
      "(several minutes; a notification tracks progress)";
  native.selfCheck();
};

function makeTable(columns, rows) {
  const t = document.createElement("table");
  const hr = t.insertRow();
  for (const c of columns) {
    const th = document.createElement("th");
    th.textContent = c; hr.appendChild(th);
  }
  for (const row of rows) {
    const tr = t.insertRow();
    // rows are objects (inspector sections) or arrays (reference tables)
    const cells = Array.isArray(row) ? row : columns.map(c => row[c]);
    for (const c of cells) tr.insertCell().textContent = String(c ?? "");
  }
  const box = document.createElement("div");
  box.style.overflowX = "auto";       // wide tables scroll, page doesn't
  box.appendChild(t);
  return box;
}

function loadReference(version) {
  ui.refVersion = version;
  const r = JSON.parse(native.referenceData());
  if (r.version !== undefined) ui.refVersion = r.version;
  const body = $("r-body");
  if (!r.ok) { body.textContent = r.error; return; }
  body.innerHTML = ""; body.className = "";
  for (const e of r.entries) {
    const d = document.createElement("details");
    const s = document.createElement("summary");
    s.textContent = `${e.group} · ${e.title}`;
    d.appendChild(s);
    if (e.svg) {
      const div = document.createElement("div");
      div.innerHTML = e.svg;
      const svg = div.querySelector("svg");
      if (svg) { svg.style.maxWidth = "100%"; svg.style.height = "auto"; }
      d.appendChild(div);
      const btn = document.createElement("button");
      btn.className = "act"; btn.textContent = "Export SVG";
      btn.onclick = () => {
        const out = JSON.parse(native.saveText(e.key + ".svg", e.svg));
        btn.textContent = out.ok ? "Exported" : "Export failed";
      };
      d.appendChild(btn);
    } else {
      d.appendChild(makeTable(e.columns, e.rows));
    }
    if (e.note) {
      const p = document.createElement("p");
      p.className = "note"; p.textContent = e.note; d.appendChild(p);
    }
    body.appendChild(d);
  }
}

init();
