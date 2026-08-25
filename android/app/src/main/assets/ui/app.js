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
  saveBinary: () => JSON.stringify({ok: false, error: "no app shell"}),
  pageSeries: () => JSON.stringify({ok: true, series: []}),
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
  pages: [],            // pristine bridge SVGs, what export saves from
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
    ui.pages = pages;
    for (const k of Object.keys(seriesCache)) delete seriesCache[k];
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
  /* the shell reporting a failure that happened after it had already
     answered — sharing is dispatched asynchronously, so its throw has no
     return value left to travel in */
  onShellError(msg) { setStatus(msg, true); },
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

/* ---------------- figure viewer: the matplotlib toolbar ------------- */

/* Mirrors NavigationToolbar2 on the desktop canvas — Home, Back, Forward,
 * Pan, Zoom-to-rectangle and the data-coordinate readout.  Qt gets all of
 * that from matplotlib itself; a WebView showing an SVG has to provide
 * it, so this is the one capability the two front-ends implement
 * separately (recorded in android/README.md's comparison table).
 *
 * The data readout is the part the SVG cannot supply on its own: the
 * bridge sends each page's axes rectangles and limits alongside it. */
const view = {x: 0, y: 0, k: 1};
const MIN_K = 0.2, MAX_K = 40;
let figAxes = [];               // axes metadata for the page on screen
let figSize = {w: 0, h: 0};     // the SVG's untransformed layout size
let mode = "pan";

function apply() {
  $("fig-inner").style.transform =
      `translate(${view.x}px,${view.y}px) scale(${view.k})`;
  if (cursors.length) drawCursors();   // markers hold data, not pixels
}
function setView(v) { view.x = v.x; view.y = v.y; view.k = v.k; apply(); }

/* view history, walked by Back/Forward exactly like the desktop toolbar */
let history = [], histAt = -1;
function pushView() {
  const v = {x: view.x, y: view.y, k: view.k}, top = history[histAt];
  if (top && top.x === v.x && top.y === v.y && top.k === v.k) return;
  history = history.slice(0, histAt + 1);
  history.push(v); histAt = history.length - 1;
  syncNav();
}
function syncNav() {
  $("a-back").disabled = histAt <= 0;
  $("a-fwd").disabled = histAt >= history.length - 1;
}
$("a-back").onclick = () => {
  if (histAt > 0) { setView(history[--histAt]); syncNav(); }
};
$("a-fwd").onclick = () => {
  if (histAt < history.length - 1) { setView(history[++histAt]); syncNav(); }
};
$("a-reset").onclick = () => { setView({x: 0, y: 0, k: 1}); pushView(); };

function setMode(m) {
  mode = m;
  $("a-pan").classList.toggle("on", m === "pan");
  $("a-zoom").classList.toggle("on", m === "zoom");
  $("a-cursor").classList.toggle("on", m === "cursor");
  setCursorMode(m === "cursor");
}
$("a-pan").onclick = () => setMode("pan");
$("a-zoom").onclick = () => setMode(mode === "zoom" ? "pan" : "zoom");

/* ----- data coordinates under a point (what the toolbar reports) ---- */

function axisValue(lim, t, scale) {
  if (scale === "log" && lim[0] > 0 && lim[1] > 0) {
    const a = Math.log10(lim[0]), b = Math.log10(lim[1]);
    return Math.pow(10, a + t * (b - a));
  }
  return lim[0] + t * (lim[1] - lim[0]);
}

/* Pure so the on-device test can check the mapping without a real run:
 * container point -> data coordinates, or null when off every axes.
 * Figure fractions measure y from the bottom (Axes.get_position), the
 * container measures it from the top — hence the flip. */
function dataAtPoint(axes, size, v, px, py) {
  if (!size.w || !size.h) return null;
  const figX = ((px - v.x) / v.k) / size.w;
  const figY = 1 - ((py - v.y) / v.k) / size.h;
  for (let i = axes.length - 1; i >= 0; i--) {      // topmost axes wins
    const a = axes[i];
    if (figX < a.x0 || figX > a.x1 || figY < a.y0 || figY > a.y1) continue;
    return {ai: i,
            x: axisValue(a.xlim, (figX - a.x0) / (a.x1 - a.x0), a.xscale),
            y: axisValue(a.ylim, (figY - a.y0) / (a.y1 - a.y0), a.yscale),
            xlabel: a.xlabel, ylabel: a.ylabel};
  }
  return null;
}

/* The inverse: a data point's place in the container.  Cursors are held
 * in data coordinates, so they stay on their point through pan and zoom
 * and only their screen position is recomputed. */
function axisFrac(lim, v, scale) {
  if (scale === "log" && lim[0] > 0 && lim[1] > 0 && v > 0) {
    const a = Math.log10(lim[0]), b = Math.log10(lim[1]);
    return (Math.log10(v) - a) / (b - a);
  }
  return (v - lim[0]) / (lim[1] - lim[0]);
}
function pointAtData(size, v, a, x, y) {
  const figX = a.x0 + axisFrac(a.xlim, x, a.xscale) * (a.x1 - a.x0);
  const figY = a.y0 + axisFrac(a.ylim, y, a.yscale) * (a.y1 - a.y0);
  return {px: v.x + v.k * figX * size.w,
          py: v.y + v.k * (1 - figY) * size.h};
}
window.pointAtData = pointAtData;      // reached by the on-device test
window.dataAtPoint = dataAtPoint;      // reached by the on-device test
// what the viewer currently holds, so a test can map a figure fraction to
// a container point the same way a finger would land on one
window.figState = () => ({axes: figAxes, size: figSize, view: view});

function fmtCoord(v) {
  if (!isFinite(v)) return "?";
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e5)) return v.toExponential(3);
  return v.toFixed(a >= 100 ? 1 : a >= 1 ? 3 : 4);
}
function showCoord(px, py) {
  if (mode === "cursor") return;           // the cursors own the readout
  const d = dataAtPoint(figAxes, figSize, view, px, py);
  $("fig-coord").textContent =
      d ? `x = ${fmtCoord(d.x)}   y = ${fmtCoord(d.y)}` : "";
}

/* ---------------- cursors: two markers and their delta -------------- */

/* The instrument idiom rather than a crosshair: each marker rides the
 * plotted data, and the pair reports the difference.  Markers are held in
 * data coordinates and re-projected on every view change, so panning and
 * zooming moves the picture under them, never the reading.
 *
 * The samples come from bridge.page_series(), fetched for one page at a
 * time and only once a cursor is armed — full_cal_steps carries ~106k
 * points across its pages, which has no business travelling on every run.
 */
let cursors = [];               // up to two {ai, x, y, name, snapped}
let dragging = -1;
const seriesCache = {};         // page index -> series[] (per run)
const GRAB_PX = 44;             // finger-sized: grab vs. place a marker

function curPage() { return Number($("a-page").value) || 0; }

function pageSeries() {
  const i = curPage();
  if (!(i in seriesCache)) {
    const r = nativeJson(() => native.pageSeries(i));
    seriesCache[i] = r.ok ? (r.series || []) : [];
    if (!r.ok) setStatus(r.error, true);
  }
  return seriesCache[i];
}

/* Nearest plotted point to a container position, within the axes under
 * it.  No radius limit: on an instrument a marker rides the trace, and a
 * finger cannot be placed to the pixel.  Where the axes has nothing
 * snappable — a constellation's scatter cloud — the marker stays where it
 * was put and says so, instead of pretending to sit on a sample. */
function nearestPoint(px, py) {
  const hit = dataAtPoint(figAxes, figSize, view, px, py);
  if (!hit) return null;
  const a = figAxes[hit.ai];
  let best = null;
  for (const s of pageSeries()) {
    if (s.axes !== hit.ai || !s.snap) continue;
    for (let i = 0; i < s.x.length; i++) {
      // null is a masked sample — real data, but nothing to snap to
      if (s.x[i] === null || s.y[i] === null) continue;
      const p = pointAtData(figSize, view, a, s.x[i], s.y[i]);
      const d = (p.px - px) * (p.px - px) + (p.py - py) * (p.py - py);
      if (best === null || d < best.d)
        best = {d: d, x: s.x[i], y: s.y[i], name: s.name};
    }
  }
  if (best) return {ai: hit.ai, x: best.x, y: best.y, name: best.name,
                    snapped: true};
  return {ai: hit.ai, x: hit.x, y: hit.y, name: "", snapped: false};
}

function cursorAt(px, py) {                 // which marker is under here?
  let best = -1, bestD = GRAB_PX * GRAB_PX;
  cursors.forEach((c, i) => {
    const p = pointAtData(figSize, view, figAxes[c.ai], c.x, c.y);
    const d = (p.px - px) * (p.px - px) + (p.py - py) * (p.py - py);
    if (d <= bestD) { bestD = d; best = i; }
  });
  return best;
}

function placeCursor(px, py) {
  const c = nearestPoint(px, py);
  if (!c) return;
  if (dragging < 0) dragging = cursors.length < 2 ? cursors.length : 0;
  cursors[dragging] = c;
  drawCursors();
}

function drawCursors() {
  const svg = $("fig-cursors");
  svg.hidden = cursors.length === 0;
  svg.setAttribute("width", fig.clientWidth);
  svg.setAttribute("height", fig.clientHeight);
  let out = "";
  cursors.forEach((c, i) => {
    const p = pointAtData(figSize, view, figAxes[c.ai], c.x, c.y);
    const col = i === 0 ? "#0a5bd3" : "#b3261e";
    out += `<line x1="${p.px}" y1="0" x2="${p.px}" y2="100%"
                  stroke="${col}" stroke-width="1"
                  stroke-dasharray="4 3"/>
            <line x1="0" y1="${p.py}" x2="100%" y2="${p.py}"
                  stroke="${col}" stroke-width="1"
                  stroke-dasharray="4 3"/>
            <circle cx="${p.px}" cy="${p.py}" r="5" fill="none"
                    stroke="${col}" stroke-width="2"/>
            <text x="${p.px + 7}" y="${p.py - 7}" fill="${col}"
                  font-size="12" font-weight="600">${i + 1}</text>`;
  });
  svg.innerHTML = out;
  showCursorReadout();
}

function showCursorReadout() {
  if (!cursors.length) {
    $("fig-coord").textContent = "tap the plot to place marker 1";
    return;
  }
  const lines = cursors.map((c, i) => {
    const tag = c.snapped ? c.name : "free — no curve on these axes";
    return `C${i + 1}  x = ${fmtCoord(c.x)}   y = ${fmtCoord(c.y)}` +
           (tag ? `   ${tag}` : "");
  });
  if (cursors.length === 2) {
    lines.push(cursors[0].ai === cursors[1].ai
        ? `Δ   x = ${fmtCoord(cursors[1].x - cursors[0].x)}` +
          `   y = ${fmtCoord(cursors[1].y - cursors[0].y)}`
        : "Δ   markers are on different axes");
  }
  $("fig-coord").textContent = lines.join("\n");
}

function setCursorMode(on) {
  if (on) {
    pageSeries();                 // fetch before the first tap, not during
    showCursorReadout();
  } else {
    $("fig-coord").textContent = "";
  }
}
$("a-cursor").onclick = () => setMode(mode === "cursor" ? "pan" : "cursor");
$("a-cursor-clear").onclick = () => {
  cursors = []; dragging = -1; drawCursors();
};

/* ---------------- export (the desktop toolbar's save) --------------- */

/* Never parse a bridge return value unguarded: a shell-side throw comes
 * back as something other than JSON, and an uncaught exception in a click
 * handler is invisible — the button silently does nothing. */
function nativeJson(call) {
  try {
    return JSON.parse(call());
  } catch (e) {
    return {ok: false, error: String(e)};
  }
}

/* Rasterize SVG text to base64 PNG using the WebView's own renderer.
 *
 * PNG, not SVG, is the default export: Android has no SVG decoder in the
 * platform, so an exported .svg reaches the recipient intact and
 * unopenable — gallery, file manager and chat previews all decline it.
 * The desktop toolbar defaults to PNG for the same reason.
 *
 * Rasterizing at a fixed width rather than the on-screen size keeps the
 * export sharp no matter how the figure happened to be zoomed. */
const PNG_WIDTH = 2000;
function rasterizePng(svgText) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      try {
        const w = PNG_WIDTH;
        const h = Math.max(1, Math.round(w * img.height / img.width));
        const c = document.createElement("canvas");
        c.width = w; c.height = h;
        const ctx = c.getContext("2d");
        // matplotlib writes a transparent background; PNG viewers show
        // that as black on dark themes, so paint white underneath first
        ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        resolve(c.toDataURL("image/png").split(",")[1]);
      } catch (e) { reject(e); }
    };
    img.onerror = () => reject(new Error("the renderer could not read " +
                                         "this SVG"));
    img.src = "data:image/svg+xml;charset=utf-8," +
              encodeURIComponent(svgText);
  });
}
window.rasterizePng = rasterizePng;      // reached by the on-device test

function safeName(name, ext) {
  return String(name || "figure").replace(/[^A-Za-z0-9_.-]+/g, "_") + ext;
}

/* Export the pristine SVG the bridge sent, NOT the one in the DOM:
 * showPage() sizes the displayed copy in px and drops its height
 * attribute, which leaves the saved file without an intrinsic size. */
function exportFigure(svgText, name, asPng, report) {
  if (!svgText) { report("no figure to export", true); return; }
  if (!asPng) {
    const r = nativeJson(() => native.saveText(safeName(name, ".svg"),
                                               svgText));
    report(r.ok ? "exported " + r.path : r.error, !r.ok);
    return;
  }
  report("rendering PNG…");
  rasterizePng(svgText).then(b64 => {
    const r = nativeJson(() => native.saveBinary(
        safeName(name, ".png"), b64, "image/png"));
    report(r.ok ? "exported " + r.path : r.error, !r.ok);
  }).catch(e => report("PNG export failed: " + e.message, true));
}

function currentPage() {
  const sel = $("a-page");
  return (ui.pages || [])[Number(sel.value)] || null;
}
function exportCurrent(asPng) {
  const page = currentPage();
  exportFigure(page && page.svg, page && page.title, asPng, setStatus);
}
$("a-export").onclick = () => exportCurrent(true);
$("a-export-svg").onclick = () => exportCurrent(false);

function showPage(page) {
  $("fig-inner").innerHTML = page.svg;
  figAxes = page.axes || [];
  cursors = []; dragging = -1;          // markers belong to one page
  const svg = $("fig-inner").querySelector("svg");
  if (svg) {                     // scale to container width, keep vector
    // clientWidth can still be 0 in edge cases (mid-layout, rotation):
    // fall back to the viewport so the figure is never sized to nothing
    const w = $("fig").clientWidth ||
        (document.documentElement.clientWidth - 18);
    svg.style.width = w + "px"; svg.style.height = "auto";
    svg.removeAttribute("height");
  }
  history = []; histAt = -1;
  setView({x: 0, y: 0, k: 1});
  // measure with the view at identity, so this is the layout size the
  // coordinate mapping divides by
  const box = svg ? svg.getBoundingClientRect() : null;
  figSize = box ? {w: box.width, h: box.height} : {w: 0, h: 0};
  // fit the viewport to the figure: the fixed CSS height left a phone
  // screen of dead space under a wide, short plot.  Zoomed content
  // simply overflows it, the way a canvas does.
  if (box && box.height) $("fig").style.height = Math.round(box.height) + "px";
  pushView();
  $("fig-coord").textContent = "";
}

const fig = $("fig");
let touches = new Map(), lastDist = 0, lastTap = 0, band = null;

function figPoint(e) {
  const r = fig.getBoundingClientRect();
  return {x: e.clientX - r.left, y: e.clientY - r.top};
}
function drawBand() {
  const b = $("fig-band");
  if (!band) { b.hidden = true; return; }
  b.hidden = false;
  b.style.left = Math.min(band.x0, band.x1) + "px";
  b.style.top = Math.min(band.y0, band.y1) + "px";
  b.style.width = Math.abs(band.x1 - band.x0) + "px";
  b.style.height = Math.abs(band.y1 - band.y0) + "px";
}
/* Zoom so the dragged rectangle fills the viewer — the toolbar's zoom. */
function zoomToBand() {
  const W = fig.clientWidth, H = fig.clientHeight;
  const x0 = Math.min(band.x0, band.x1), x1 = Math.max(band.x0, band.x1);
  const y0 = Math.min(band.y0, band.y1), y1 = Math.max(band.y0, band.y1);
  if (x1 - x0 < 12 || y1 - y0 < 12) return;    // a tap, not a drag
  const c0x = (x0 - view.x) / view.k, c0y = (y0 - view.y) / view.k;
  const c1x = (x1 - view.x) / view.k, c1y = (y1 - view.y) / view.k;
  const k = Math.min(MAX_K, Math.max(MIN_K,
      Math.min(W / (c1x - c0x), H / (c1y - c0y))));
  setView({k: k,
           x: -k * c0x + (W - k * (c1x - c0x)) / 2,
           y: -k * c0y + (H - k * (c1y - c0y)) / 2});
  pushView();
}

fig.addEventListener("pointerdown", e => {
  fig.setPointerCapture(e.pointerId);
  touches.set(e.pointerId, {x: e.clientX, y: e.clientY});
  const p = figPoint(e);
  showCoord(p.x, p.y);
  if (touches.size === 1) {
    if (mode === "cursor") {
      dragging = cursorAt(p.x, p.y);      // grab a marker, or place one
      placeCursor(p.x, p.y);
    }
    if (mode === "zoom") { band = {x0: p.x, y0: p.y, x1: p.x, y1: p.y}; }
    const now = Date.now();                  // double-tap zoom
    if (now - lastTap < 300) {
      view.k = view.k > 1 ? 1 : 2.5; apply(); pushView();
    }
    lastTap = now;
  } else {
    band = null; drawBand();                 // a second finger ends a drag
  }
});
fig.addEventListener("pointermove", e => {
  const p = figPoint(e);
  showCoord(p.x, p.y);
  if (!touches.has(e.pointerId)) return;
  const prev = touches.get(e.pointerId);
  touches.set(e.pointerId, {x: e.clientX, y: e.clientY});
  const pts = [...touches.values()];
  if (pts.length === 1 && mode === "cursor") {
    placeCursor(p.x, p.y);                    // drag the grabbed marker
  } else if (pts.length === 1 && band) {      // rubber band
    band.x1 = p.x; band.y1 = p.y; drawBand();
  } else if (pts.length === 1) {              // pan
    view.x += e.clientX - prev.x; view.y += e.clientY - prev.y; apply();
  } else if (pts.length === 2) {              // pinch, in either mode
    const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    if (lastDist > 0) {
      const r = fig.getBoundingClientRect();
      const c = {x: (pts[0].x + pts[1].x) / 2 - r.left,
                 y: (pts[0].y + pts[1].y) / 2 - r.top};
      const s = d / lastDist;
      view.x = c.x - s * (c.x - view.x);
      view.y = c.y - s * (c.y - view.y);
      view.k = Math.min(MAX_K, Math.max(MIN_K, view.k * s));
      apply();
    }
    lastDist = d;
  }
});
["pointerup", "pointercancel"].forEach(ev => fig.addEventListener(ev, e => {
  touches.delete(e.pointerId);
  if (touches.size < 2) lastDist = 0;
  if (touches.size === 0) dragging = -1;
  if (band && touches.size === 0) { zoomToBand(); band = null; drawBand(); }
  else if (touches.size === 0 && mode !== "cursor") pushView();
}));
fig.addEventListener("wheel", e => {         // desktop smoke-test comfort
  e.preventDefault();
  const s = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  view.k = Math.min(MAX_K, Math.max(MIN_K, view.k * s)); apply();
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
      const note = document.createElement("p");
      note.className = "note";
      for (const [label, asPng] of [["Export PNG", true],
                                    ["Export SVG", false]]) {
        const btn = document.createElement("button");
        btn.className = "act"; btn.textContent = label;
        // report through the note element: the old code collapsed every
        // failure into the button label and threw the real message away
        btn.onclick = () => exportFigure(
            e.svg, e.key, asPng,
            (msg, err) => { note.textContent = msg;
                            note.className = err ? "err" : "note"; });
        d.appendChild(btn);
      }
      d.appendChild(note);
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

/* Paint the shell before the first bridge call.
 *
 * list_specs() pays the import of the whole analysis stack — numpy, scipy
 * and matplotlib — plus, on a phone, byte-compiling every module the first
 * time (the APK ships no .pyc for this interpreter).  Measured cold on a
 * desktop: 14 s.  Called straight from page load it leaves an empty form
 * on screen with nothing to say why, which reads as a hung app.
 */
setStatus("starting Python — first launch imports numpy/scipy/matplotlib " +
          "and can take a while");
requestAnimationFrame(() => setTimeout(() => {
  init();
  if ($("status").textContent.startsWith("starting Python")) setStatus("");
}, 0));
