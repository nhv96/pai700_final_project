"use strict";

// Digital-twin card: asks /api/twin/compare for a simulated week (legacy vs combined controller) and draws it.
// Loaded after app.js and relies on its globals ($, num, state, M, niceTicks, xTicks, DAY) and on the twin service's JSON shape.

const TWIN_FIELDS = [
  ["Heat (kWh)", (s) => num(s.heat_kWh, 1)],
  ["  radiator (kWh)", (s) => num(s.radiator_kWh, 1)],
  ["  ventilation coil (kWh)", (s) => num(s.coil_kWh, 1)],
  ["Heat vs legacy", (s) => (s.heat_vs_legacy_pct === 0 ? "reference" : `${s.heat_vs_legacy_pct > 0 ? "+" : ""}${num(s.heat_vs_legacy_pct, 1)} %`)],
  ["Peak room temperature (°C)", (s) => num(s.peak_t_air_C, 1)],
  ["Minutes at or above purge limit", (s) => num(s.minutes_above_purge)],
  ["Lesson minutes below 20 °C", (s) => num(s.occupied_minutes_below_lower_limit)],
];

function twinMessage(text, isError = false) {
  const el = $("twin-message");
  el.textContent = text;
  el.classList.toggle("error", isError);
}

function initTwin() {
  const wait = setInterval(() => {                       // app.js fills state.info once the feed answers
    if (!state.info) return;
    clearInterval(wait);
    const first = state.info.window.first.slice(0, 10), last = state.info.window.last.slice(0, 10);
    const input = $("twin-start");
    input.min = first; input.max = last;
    input.value = "2022-11-07" >= first && "2022-11-07" <= last ? "2022-11-07" : first;
    $("twin-run").addEventListener("click", runTwin);
  }, 200);
}

async function runTwin() {
  const btn = $("twin-run");
  btn.disabled = true;
  twinMessage("Simulating…");
  try {
    const q = new URLSearchParams({ start: $("twin-start").value, days: $("twin-days").value, building: state.selected });
    const r = await fetch(`/api/twin/compare?${q}`);
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail ?? r.status);
    drawTwin(body, await loadBenchmark(body).catch((e) => ({ error: e.message })));
    twinMessage("");
  } catch (e) {
    twinMessage(`Simulation failed: ${e.message}`, true);
  } finally {
    btn.disabled = false;
  }
}

// AI benchmark: the forecast service predicts a whole building, so one hour of it is scaled to the room by
// room m2 / building m2. It is context only: it includes hot water and an average m2, and no controller reads it.
const BENCH_HORIZON = 24;                                // the day-ahead forecast

async function loadBenchmark(d) {
  if (!state.forecast?.available) return { error: "the AI forecast service is not running" };
  const b = state.info.buildings.find((x) => x.building_id === d.building);
  const start = Date.parse(`${d.start}T00:00:00+01:00`) / 1000, end = start + d.days * DAY;
  const q = new URLSearchParams({ from: dataClock(start - BENCH_HORIZON * 3600), until: dataClock(end - (BENCH_HORIZON + 1) * 3600),
                                  building: d.building, horizons: BENCH_HORIZON });
  const r = await fetch(`/api/forecast/series?${q}`);
  const body = await r.json();
  if (!r.ok) return { error: body.detail ?? r.status };
  const pts = body.series[String(BENCH_HORIZON)];
  if (pts.length < d.days * 24) return { error: "the forecast does not cover this period" };
  const scale = d.room_floor_area_m2 / b.floor_area / 1000;   // Wh per hour of the building -> kW of the room
  return { t: pts.map((p) => Date.parse(p.target_time) / 1000), kW: pts.map((p) => p.wh * scale) };
}

function drawTwin(d, bench) {
  $("twin-out").hidden = false;
  const { legacy, combined } = d.runs;
  const head = document.querySelector("#twin-summary thead th");
  head.textContent = `${d.days}-day totals, building ${d.building} weather`;
  const body = document.querySelector("#twin-summary tbody");
  body.replaceChildren();
  for (const [label, fmt] of TWIN_FIELDS) {
    const tr = document.createElement("tr");
    const th = Object.assign(document.createElement("th"), { scope: "row", textContent: label.trim() });
    if (label.startsWith(" ")) th.style.paddingLeft = "24px";
    tr.append(th, ...[legacy, combined].map((r) => Object.assign(document.createElement("td"), { className: "num", textContent: fmt(r.summary) })));
    body.append(tr);
  }
  if (bench?.kW) {
    const tr = document.createElement("tr");
    tr.append(Object.assign(document.createElement("th"), { scope: "row", textContent: `AI benchmark, ${d.room_floor_area_m2} m² share (kWh)` }),
              Object.assign(document.createElement("td"), { className: "num", colSpan: 2, textContent: num(bench.kW.reduce((a, v) => a + v, 0), 1) }));
    body.append(tr);
  }
  const t = legacy.series.time.map((s) => Date.parse(`${s}:00+01:00`) / 1000);
  const css = getComputedStyle(document.documentElement);
  const col = (n) => css.getPropertyValue(n).trim();
  const heat = (r) => r.series.radiator_kW.map((v, i) => v + r.series.coil_kW[i]);
  twinChart($("chart-twin-temp"), t, [
    { v: legacy.series.t_air_C, color: col("--legacy"), label: "legacy" },
    { v: combined.series.t_air_C, color: col("--combined"), label: "combined" },
  ], [
    { y: d.setpoint_C, text: `setpoint ${d.setpoint_C} °C`, color: col("--axis") },
    { y: d.purge_trigger_C, text: `purge starts ${d.purge_trigger_C} °C`, color: col("--limit") },
  ], 1);
  twinChart($("chart-twin-heat"), t, [
    { v: heat(legacy), color: col("--legacy"), label: "legacy" },
    { v: heat(combined), color: col("--combined"), label: "combined" },
    ...(bench?.kW ? [{ v: bench.kW, t: bench.t, color: col("--forecast"), label: "AI benchmark", dashed: true }] : []),
  ], [], 1, true);
  const benchNote = bench?.kW
    ? ` AI benchmark: the ${BENCH_HORIZON} h forecast for the whole building (perfect weather, hot water included) scaled by ${d.room_floor_area_m2} m² / building area. It is a rough reference, not a measurement, and no controller uses it.`
    : bench?.error ? ` AI benchmark not shown: ${bench.error}.` : "";
  $("twin-note").textContent = `${d.note} Sun ratio: ${d.south_facade_ratio}.${benchNote}`;
}

function twinChart(svg, t, lines, refs, digits, fromZero = false) {
  const w = svg.clientWidth || 800, h = svg.clientHeight || 200;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const right = 96;                                       // room for the direct labels
  const x0 = t[0], x1 = t[t.length - 1];
  const px = (tt) => M.left + ((tt - x0) / (x1 - x0)) * (w - M.left - right);
  const all = lines.flatMap((l) => l.v).concat(refs.map((r) => r.y));
  const yt = niceTicks(fromZero ? Math.min(0, ...all) : Math.min(...all), Math.max(...all));
  const py = (v) => h - M.bottom - ((v - yt.lo) / (yt.hi - yt.lo)) * (h - M.top - M.bottom);
  let s = "";
  for (const tick of yt.ticks) {
    s += `<line class="grid" x1="${M.left}" x2="${w - right}" y1="${py(tick)}" y2="${py(tick)}"/>`;
    s += `<text x="${M.left - 8}" y="${py(tick) + 4}" text-anchor="end">${num(tick, yt.step < 1 ? 1 : 0)}</text>`;
  }
  s += `<line class="axis" x1="${M.left}" x2="${w - right}" y1="${h - M.bottom}" y2="${h - M.bottom}"/>`;
  for (const tk of xTicks(x0, x1)) s += `<text x="${px(tk.t)}" y="${h - 5}" text-anchor="middle">${tk.label}</text>`;
  for (const r of refs) {
    s += `<line class="dashed" stroke="${r.color}" x1="${M.left}" x2="${w - right}" y1="${py(r.y)}" y2="${py(r.y)}"/>`;
    const ty = py(r.y) - 4 < M.top + 10 ? py(r.y) + 13 : py(r.y) - 4;   // below the line when it sits at the top edge
    s += `<text x="${M.left + 4}" y="${ty}">${r.text}</text>`;
  }
  for (const l of lines) {
    const lt = l.t ?? t;
    const d = l.v.map((v, i) => `${i ? "L" : "M"}${px(lt[i]).toFixed(1)} ${py(v).toFixed(1)}`).join("");
    s += `<path class="line${l.dashed ? " fc" : ""}" d="${d}" stroke="${l.color}"/>`;
  }
  // direct labels at the right end; nudge apart if the end values are close
  const ends = lines.map((l) => ({ l, y: py(l.v[l.v.length - 1]) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  const maxY = h - M.bottom - 8;                          // keep clear of the x-axis labels
  for (let i = ends.length - 1; i >= 0; i--) {
    ends[i].y = Math.min(ends[i].y, i === ends.length - 1 ? maxY : ends[i + 1].y - 14);
  }
  for (const e of ends) s += `<text class="label" x="${w - right + 6}" y="${e.y + 4}" fill="${e.l.color}" style="fill:${e.l.color}">${e.l.label}</text>`;
  svg.innerHTML = s;                                      // numbers and fixed text only
}

initTwin();
