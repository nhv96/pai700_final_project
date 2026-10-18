"use strict";

// Dashboard page: follows the replay feed's stream, keeps the readings in memory, draws the table and charts.
// The page owns its clock: pause = close the stream, play = open it again from the last hour received.

const TZ = "Etc/GMT-1";           // the data's fixed UTC+1 time, no DST
const DAY = 86400;
const $ = (id) => document.getElementById(id);

const timeFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, month: "short" });
const yearFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, year: "numeric" });
const num = (v, d = 0) => v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
const at = (t) => new Date(t * 1000);

const state = {
  info: null, t0: 0, t1: 0,
  data: new Map(),               // building id -> { t: [epoch s], heat: [kW], tout: [C] }
  lastT: null, lastTs: null, phase: null,
  es: null, playing: false, finished: false,
  selected: null, range: "all",
  charts: {},                    // scales of the last draw, used by the hover layer
};

// ---------- start-up ----------

async function init() {
  try {
    const r = await fetch("/api/buildings");
    if (!r.ok) throw new Error(r.status);
    state.info = await r.json();
  } catch (e) {
    message("Cannot reach the replay feed. Is it running?", true);
    return;
  }
  state.t0 = Date.parse(state.info.window.first) / 1000;
  state.t1 = Date.parse(state.info.window.last) / 1000;
  for (const b of state.info.buildings) state.data.set(b.building_id, { t: [], heat: [], tout: [] });
  state.selected = state.info.buildings[0]?.building_id ?? null;

  buildTable();
  $("play").addEventListener("click", () => (state.playing ? stop() : play()));
  $("reset").addEventListener("click", restart);
  $("speed").addEventListener("change", () => { if (state.playing) { stop(); play(); } });
  $("range").addEventListener("change", (e) => { state.range = e.target.value; schedule(); });
  $("recent").closest("details").addEventListener("toggle", schedule);
  window.addEventListener("resize", schedule);
  const hoverTarget = $("charts");
  hoverTarget.addEventListener("pointermove", onHover);
  hoverTarget.addEventListener("pointerleave", hideHover);
  message("Press Play to start the replay.");
  updateControls();
  schedule();
  forecastStatus();
}

async function forecastStatus() {
  try {
    const s = await (await fetch("/api/forecast/status")).json();
    if (s.available) $("forecast").closest("label").title = "A forecast file is present, but the overlay is not built yet.";
  } catch (_) { /* the toggle just stays disabled */ }
}

function message(text, isError = false) {
  const el = $("message");
  el.textContent = text;
  el.classList.toggle("error", isError);
}

// ---------- the stream ----------

function play() {
  if (state.es || state.finished) return;
  const from = state.lastTs ?? state.info.window.first;
  const es = new EventSource(`/api/stream?speed=${encodeURIComponent($("speed").value)}&from=${encodeURIComponent(from)}`);
  state.es = es;
  state.playing = true;
  es.addEventListener("reading", onReading);
  es.addEventListener("end", () => { stop(); state.finished = true; message("End of the window."); updateControls(); });
  es.onopen = () => message("");
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) { stop(); message("Lost the connection to the replay feed.", true); }
    else message("Reconnecting…");
  };
  updateControls();
}

function stop() {
  if (state.es) { state.es.close(); state.es = null; }
  state.playing = false;
  updateControls();
}

function restart() {
  stop();
  for (const d of state.data.values()) { d.t.length = 0; d.heat.length = 0; d.tout.length = 0; }
  state.lastT = state.lastTs = state.phase = null;
  state.finished = false;
  message("");
  schedule();
  play();
}

function onReading(ev) {
  const p = JSON.parse(ev.data);
  const t = Date.parse(p.timestamp) / 1000;
  if (state.lastT !== null && t <= state.lastT) return;      // a resumed stream repeats the last hour
  for (const r of p.readings) {
    const d = state.data.get(r.building_id);
    if (!d) continue;
    d.t.push(t);
    d.heat.push(r.HtTot / 1000);                              // Wh per hour -> kW
    d.tout.push(r.Tout);
  }
  state.lastT = t;
  state.lastTs = p.timestamp;
  state.phase = p.readings[0]?.phase ?? state.phase;
  schedule();
}

function updateControls() {
  $("play").textContent = state.playing ? "Pause" : "Play";
  $("play").disabled = state.finished;
}

// ---------- drawing, at most once per animation frame ----------

let queued = false;
function schedule() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => { queued = false; render(); });
}

function render() {
  if (!state.info) return;
  renderClock();
  renderTable();
  renderCharts();
  renderRecent();
}

function renderClock() {
  $("clock-time").textContent = state.lastT === null ? "–" : timeFmt.format(at(state.lastT));
  const badge = $("clock-phase");
  badge.textContent = state.phase === "warmup" ? "Warm-up (history)" : state.phase === "replay" ? "Replay" : "Not started";
  const pct = state.lastT === null ? null : Math.round(((state.lastT - state.t0) / (state.t1 - state.t0)) * 100);
  $("clock-progress").textContent = pct === null ? "" : `${pct} % of the window`;
}

// ---------- building table ----------

function buildTable() {
  const body = document.querySelector("#buildings tbody");
  body.replaceChildren();
  for (const b of state.info.buildings) {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.dataset.id = b.building_id;
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = b.building_id;
    tr.append(th);
    for (let i = 0; i < 5; i++) tr.append(Object.assign(document.createElement("td"), { className: "num" }));
    tr.cells[1].textContent = num(b.floor_area);
    const select = () => { state.selected = b.building_id; schedule(); };
    tr.addEventListener("click", select);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); } });
    body.append(tr);
  }
}

function metrics(b) {
  const d = state.data.get(b.building_id);
  const n = d.t.length;
  if (!n) return null;
  let kwh24 = null;
  if (n >= 24) kwh24 = d.heat.slice(n - 24).reduce((a, v) => a + v, 0);   // one reading = one hour, so kW = kWh
  return { now: d.heat[n - 1], kwh24, perM2: kwh24 === null ? null : kwh24 / b.floor_area, tout: d.tout[n - 1] };
}

function renderTable() {
  for (const tr of document.querySelectorAll("#buildings tbody tr")) {
    const b = state.info.buildings.find((x) => String(x.building_id) === tr.dataset.id);
    const m = metrics(b);
    const dash = "–";
    tr.cells[2].textContent = m ? num(m.now, 1) : dash;
    tr.cells[3].textContent = m?.kwh24 != null ? num(m.kwh24) : dash;
    tr.cells[4].textContent = m?.perM2 != null ? num(m.perM2, 3) : dash;
    tr.cells[5].textContent = m ? num(m.tout, 1) : dash;
    if (b.building_id === state.selected) tr.setAttribute("aria-current", "true");
    else tr.removeAttribute("aria-current");
  }
}

// ---------- charts ----------

const M = { left: 48, right: 16, top: 8, bottom: 22 };

function domain() {
  if (state.range === "all") return [state.t0, state.t1];
  const span = Number(state.range) * DAY;
  if (state.lastT === null || state.lastT - span < state.t0) return [state.t0, state.t0 + span];
  return [state.lastT - span, state.lastT];
}

const lowerBound = (a, x) => { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; };

function niceTicks(min, max, count = 4) {
  if (max === min) { max = min + 1; }
  const raw = (max - min) / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((k) => k * pow).find((s) => s >= raw);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v / step) * step);
  return { ticks, lo, hi, step };
}

function xTicks(x0, x1) {
  const out = [];
  const span = x1 - x0;
  if (span > 60 * DAY) {                                           // month starts, in UTC+1
    const d = at(x0 + 3600);
    let y = d.getUTCFullYear(), m = d.getUTCMonth() + 1;
    for (;;) {
      const t = Date.UTC(y, m, 1) / 1000 - 3600;
      if (t > x1) break;
      out.push({ t, label: m % 12 === 0 ? `${monthFmt.format(at(t + 3600))} ${yearFmt.format(at(t + 3600))}` : monthFmt.format(at(t + 3600)) });
      if (++m > 11) { m = 0; y++; }
    }
    return out;
  }
  const step = [1, 2, 7, 14, 30].find((s) => span / (s * DAY) <= 8) ?? 30;
  for (let t = Math.ceil((x0 + 3600) / (step * DAY)) * step * DAY - 3600; t <= x1; t += step * DAY) out.push({ t, label: dayFmt.format(at(t + 3600)) });
  return out;
}

function drawChart(svg, key, { t, v, color, fromZero, area, digits }) {
  const w = svg.clientWidth || 800, h = svg.clientHeight || 200;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const [x0, x1] = domain();
  const px = (tt) => M.left + ((tt - x0) / (x1 - x0)) * (w - M.left - M.right);

  const i0 = lowerBound(t, x0), i1 = lowerBound(t, x1 + 1);
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i < i1; i++) { if (v[i] < lo) lo = v[i]; if (v[i] > hi) hi = v[i]; }
  if (!isFinite(lo)) { lo = 0; hi = 1; }
  if (fromZero) lo = Math.min(0, lo);
  const yt = niceTicks(lo, hi);
  const py = (vv) => h - M.bottom - ((vv - yt.lo) / (yt.hi - yt.lo)) * (h - M.top - M.bottom);

  let s = "";
  for (const tick of yt.ticks) {
    const y = py(tick);
    s += `<line class="grid" x1="${M.left}" x2="${w - M.right}" y1="${y}" y2="${y}"/>`;
    s += `<text x="${M.left - 8}" y="${y + 4}" text-anchor="end">${num(tick, yt.step < 1 ? 1 : 0)}</text>`;
  }
  s += `<line class="axis" x1="${M.left}" x2="${w - M.right}" y1="${h - M.bottom}" y2="${h - M.bottom}"/>`;
  for (const tk of xTicks(x0, x1)) s += `<text x="${px(tk.t)}" y="${h - 5}" text-anchor="middle">${tk.label}</text>`;

  if (i1 > i0) {
    let d = "";
    for (let i = i0; i < i1; i++) d += `${i === i0 ? "M" : "L"}${px(t[i]).toFixed(1)} ${py(v[i]).toFixed(1)}`;
    if (area) s += `<path d="${d}L${px(t[i1 - 1]).toFixed(1)} ${py(yt.lo)}L${px(t[i0]).toFixed(1)} ${py(yt.lo)}Z" fill="${color}" opacity="0.10"/>`;
    s += `<path class="line" d="${d}" stroke="${color}"/>`;
    s += `<circle class="dot" cx="${px(t[i1 - 1])}" cy="${py(v[i1 - 1])}" r="4" fill="${color}"/>`;
  } else {
    s += `<text x="${(w + M.left) / 2}" y="${h / 2}" text-anchor="middle">No data yet</text>`;
  }
  s += `<g class="hover" visibility="hidden"><line class="cross" y1="${M.top}" y2="${h - M.bottom}"/><circle class="dot" r="4" fill="${color}"/></g>`;
  svg.innerHTML = s;                                              // only numbers and fixed text go in here
  state.charts[key] = { svg, px, py, x0, x1, w, h, color, digits };
}

function renderCharts() {
  const b = state.info.buildings.find((x) => x.building_id === state.selected);
  if (!b) return;
  const d = state.data.get(b.building_id);
  const css = getComputedStyle(document.documentElement);
  $("chart-building").textContent = `building ${b.building_id} (${num(b.floor_area)} m²)`;
  drawChart($("chart-heat"), "heat", { t: d.t, v: d.heat, color: css.getPropertyValue("--heat").trim(), fromZero: true, area: true, digits: 1 });
  drawChart($("chart-tout"), "tout", { t: d.t, v: d.tout, color: css.getPropertyValue("--tout").trim(), fromZero: false, area: false, digits: 1 });
}

// ---------- hover: one crosshair and one tooltip for both charts ----------

function onHover(e) {
  const heat = state.charts.heat;
  const b = state.info?.buildings.find((x) => x.building_id === state.selected);
  if (!heat || !b) return;
  const d = state.data.get(b.building_id);
  const box = heat.svg.getBoundingClientRect();
  const x = e.clientX - box.left;
  const tAt = heat.x0 + ((x - M.left) / (heat.w - M.left - M.right)) * (heat.x1 - heat.x0);
  const i0 = lowerBound(d.t, heat.x0), i1 = lowerBound(d.t, heat.x1 + 1);
  if (i1 <= i0 || x < M.left || x > heat.w - M.right) return hideHover();
  let i = Math.min(Math.max(lowerBound(d.t, tAt), i0), i1 - 1);
  if (i > i0 && tAt - d.t[i - 1] < d.t[i] - tAt) i--;             // nearest of the two neighbours

  for (const [key, vals] of [["heat", d.heat], ["tout", d.tout]]) {
    const c = state.charts[key];
    const g = c.svg.querySelector(".hover");
    g.setAttribute("visibility", "visible");
    g.querySelector("line").setAttribute("x1", c.px(d.t[i]));
    g.querySelector("line").setAttribute("x2", c.px(d.t[i]));
    g.querySelector("circle").setAttribute("cx", c.px(d.t[i]));
    g.querySelector("circle").setAttribute("cy", c.py(vals[i]));
  }

  const tip = $("tooltip");
  tip.replaceChildren();
  tip.append(Object.assign(document.createElement("div"), { className: "when", textContent: timeFmt.format(at(d.t[i])) }));
  for (const [name, value, unit, color] of [["Heat", d.heat[i], "kW", heat.color], ["Outdoor", d.tout[i], "°C", state.charts.tout.color]]) {
    const row = document.createElement("div");
    row.className = "row";
    const left = document.createElement("span");
    const key = Object.assign(document.createElement("span"), { className: "key" });
    key.style.background = color;
    left.append(key, " ", Object.assign(document.createElement("span"), { className: "name", textContent: name }));
    row.append(left, Object.assign(document.createElement("span"), { className: "val", textContent: `${num(value, 1)} ${unit}` }));
    tip.append(row);
  }
  tip.hidden = false;
  const wrap = $("charts").getBoundingClientRect();
  const left = e.clientX - wrap.left;
  tip.style.left = `${left > wrap.width / 2 ? left - tip.offsetWidth - 14 : left + 14}px`;
  tip.style.top = `${e.clientY - wrap.top - tip.offsetHeight / 2}px`;
}

function hideHover() {
  $("tooltip").hidden = true;
  for (const c of Object.values(state.charts)) c.svg.querySelector(".hover")?.setAttribute("visibility", "hidden");
}

// ---------- table view of the last 24 hours ----------

function renderRecent() {
  const details = $("recent").closest("details");
  if (!details.open) return;
  const d = state.data.get(state.selected);
  const body = document.querySelector("#recent tbody");
  body.replaceChildren();
  for (let i = d.t.length - 1; i >= Math.max(0, d.t.length - 24); i--) {
    const tr = document.createElement("tr");
    tr.append(Object.assign(document.createElement("th"), { scope: "row", textContent: timeFmt.format(at(d.t[i])) }));
    for (const v of [d.heat[i], d.tout[i]]) tr.append(Object.assign(document.createElement("td"), { className: "num", textContent: num(v, 1) }));
    body.append(tr);
  }
}

init();
