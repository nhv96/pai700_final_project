// Tests for the BMS data adapter (dashboard/static/bms/data-source.js). Run: node --test tests/js
// The adapter runs in a vm with a fake fetch, EventSource and timers; nothing touches the network.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "../../dashboard/static/bms/data-source.js"), "utf8");
const WINDOW = { first: "2022-09-24T00:00:00+01:00", replay_start: "2022-10-01T00:00:00+01:00", last: "2023-03-31T23:00:00+01:00" };

function clockState(position) {
  return { playing: false, started: position !== null, finished: false, speed: 24, position, phase: "replay", progress: 0.1, window: WINDOW };
}

// One building, 24 hourly rows of 2000 Wh/h (= 2 kW) at 5 C, and a twin run of `days` days: 2 kW all day, occupied in hour 3 only.
function twinBody(start, days) {
  const n = days * 144, hour = (i) => Math.floor(i / 6) % 24;
  const run = (kw) => ({
    summary: { heat_kWh: kw * 24 * days },
    series: {
      time: Array(n).fill("x"), t_air_C: Array(n).fill(kw + 19), radiator_kW: Array(n).fill(kw / 2), coil_kW: Array(n).fill(kw / 2),
      occupants: Array.from({ length: n }, (_, i) => (hour(i) === 3 ? 25 : 0)),
    },
  });
  return { start, days, building: 1, room_floor_area_m2: 60, setpoint_C: 21, comfort_band_C: [20, 26], note: "sim",
           weather: { t_outdoor_C: Array(n).fill(2) }, runs: { legacy: run(2), combined: run(1) } };
}

function setup({ position, fail = {} }) {
  const calls = [];
  const timers = [];
  let listener = null;
  const emitted = [], statuses = [];
  const json = (body, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) });
  const fetch = (url) => {
    calls.push(url);
    for (const key of Object.keys(fail)) if (url.includes(key)) return json({ detail: fail[key] }, false);
    if (url.startsWith("/api/buildings")) return json({ buildings: [{ building_id: 1, floor_area: 1000, year_of_construction: 2000 }], window: WINDOW });
    if (url.startsWith("/api/playback")) return json(clockState(position));
    if (url.startsWith("/api/readings")) {
      const until = Date.parse(new URL(url, "http://x").searchParams.get("until") + ":00Z") - 3600e3;   // data time -> epoch
      return json(Array.from({ length: 24 }, (_, i) => ({ timestamp: new Date(until - (23 - i) * 3600e3).toISOString(), building_id: 1, HtTot: 2000, Tout: 5 })));
    }
    if (url.startsWith("/api/status")) return json({ as_of: position, summary: { alert: 1, watch: 0, ok: 0, no_data: 0 }, note: "n",
      buildings: [{ building_id: 1, status: "alert", reasons: [{ code: "excess_6h", level: "alert", message: "too hot" }] }] });
    if (url.startsWith("/api/forecast/model")) return json({ version: "ai_v1", train_end: "2022-03-01" });
    if (url.startsWith("/api/forecast/series")) return json({ note: "n", series: { 1: [{ wh: 1000 }], 6: [{ wh: 6000 }], 24: [{ wh: 24000 }] } });
    if (url.startsWith("/api/twin/compare")) {
      const q = new URL(url, "http://x").searchParams;
      return json(twinBody(q.get("start"), Number(q.get("days"))));
    }
    return json({ detail: "unknown " + url }, false);
  };
  class EventSource {
    constructor() { listener = null; }
    addEventListener(name, fn) { if (name === "state") listener = fn; }
  }
  const window = {};
  vm.runInNewContext(SRC, { window, fetch, EventSource, URL, Promise, setTimeout: (fn) => timers.push(fn), Math, Date, JSON, Object, Array });
  const flush = async () => {                       // run the pending timers, then let the promises settle
    for (let round = 0; round < 6; round++) {
      while (timers.length) timers.shift()();
      await new Promise((r) => setImmediate(r));
    }
  };
  window.BmsSource.start({ onData: (d) => emitted.push(d), onStatus: (s) => statuses.push(s) });
  return { source: window.BmsSource, calls, emitted, statuses, flush, push: (pos) => listener({ data: JSON.stringify(clockState(pos)) }), last: () => JSON.parse(JSON.stringify(emitted[emitted.length - 1])) };   // plain objects: the vm has its own Array
}

test("before the replay starts: buildings without values, nothing fetched", async () => {
  const t = setup({ position: null });
  await t.flush();
  const d = t.last();
  assert.equal(d.buildings.length, 1);
  assert.equal(d.buildings[0].name, "Building 1");
  assert.equal(d.buildings[0].heat_kw, null);
  assert.deepEqual(d.timeseries, []);
  assert.equal(d.forecast, null);
  assert.ok(!t.calls.some((u) => u.startsWith("/api/readings") || u.startsWith("/api/twin")));
});

test("readings: last 24 hours up to the clock, never later", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  const q = new URL(t.calls.find((u) => u.startsWith("/api/readings")), "http://x").searchParams;
  assert.equal(q.get("until"), "2022-11-08T09:00");
  assert.equal(q.get("from"), "2022-11-07T10:00");
  const b = t.last().buildings[0];
  assert.equal(b.heat_kw, 2);
  assert.equal(b.kwh_24h, 48);
  assert.equal(b.kwh_m2_24h, 0.048);
  assert.equal(b.outdoor_c, 5);
  assert.equal(b.series24.heat_kw.length, 24);
});

test("twin runs on the last completed days before the clock's day", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  const url = new URL(t.calls.find((u) => u.startsWith("/api/twin/compare")), "http://x").searchParams;
  assert.equal(url.get("start"), "2022-11-05");      // 3 days: Nov 5, 6, 7; Nov 8 is not complete
  assert.equal(url.get("days"), "3");
  t.source.select({ days: 5 });
  await t.flush();
  assert.ok(t.calls.some((u) => u.includes("start=2022-11-03&days=5")));
  t.source.select({ days: 50 });                      // capped at 7
  await t.flush();
  assert.ok(t.calls.some((u) => u.includes("days=7")));
});

test("twin: no run until one full day has passed, and never before the data window", async () => {
  const t = setup({ position: "2022-09-24T20:00:00+01:00" });
  await t.flush();
  assert.ok(!t.calls.some((u) => u.startsWith("/api/twin")));
  t.push("2022-09-26T05:00:00+01:00");                 // two completed days: 24 and 25 Sep, so 3 is cut to 2
  await t.flush();
  const call = t.calls.find((u) => u.startsWith("/api/twin/compare"));
  assert.ok(call.includes("start=2022-09-24&days=2"), call);
});

test("twin series become 24 hourly rows per day: kW, kWh, occupancy, band", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  const d = t.last();
  assert.equal(d.timeseries.length, 72);
  const r = d.timeseries[3];
  assert.equal(r.timestamp, "2022-11-05T03:00");
  assert.equal(r.baseline_heating_power_kw, 2);
  assert.equal(r.baseline_energy_kwh, 2);
  assert.equal(r.optimized_heating_power_kw, 1);
  assert.equal(r.occupied, true);
  assert.equal(d.timeseries[4].occupied, false);
  assert.equal(r.outdoor_temp_c, 2);
  assert.deepEqual(d.meta.comfort_band_c, [20, 26]);
  assert.equal(d.twin.days, 3);
  assert.match(d.meta.scenario_scope, /60 m² classroom/);
});

test("forecast: three horizons in kWh for every building, from the clock's hour", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  const d = t.last();
  assert.ok(d.buildings.length >= 1);
  d.buildings.forEach((b) => assert.deepEqual(b.forecast_kwh, [1, 6, 24]));
  assert.equal(d.forecast.model.version, "ai_v1");
  assert.deepEqual(d.forecast.hours, [1, 6, 24]);
  const calls = t.calls.filter((u) => u.startsWith("/api/forecast/series"));
  assert.equal(calls.length, d.buildings.length);
  d.buildings.forEach((b) => assert.ok(
    calls.some((u) => u.includes("from=2022-11-08T09:00&until=2022-11-08T09:00&building=" + b.building_id + "&horizons=1,6,24")), String(b.building_id)));
});

test("forecast failure is reported per building, the rest still works", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00", fail: { "/api/forecast/series": "needs a week of history" } });
  await t.flush();
  const d = t.last();
  assert.equal(d.buildings[0].forecast_error, "needs a week of history");
  assert.deepEqual(d.buildings[0].forecast_kwh, [null, null, null]);
  assert.equal(d.buildings[0].heat_kw, 2);
});

test("twin failure is reported instead of stale or invented numbers", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00", fail: { "/api/twin/compare": "twin down" } });
  await t.flush();
  const d = t.last();
  assert.equal(d.twin_error, "twin down");
  assert.deepEqual(d.timeseries, []);
});

test("a restart of the clock drops the simulated days that are now in the future", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  assert.equal(t.last().timeseries.length, 72);
  t.push("2022-09-24T00:00:00+01:00");
  await t.flush();
  assert.deepEqual(t.last().timeseries, []);
});

test("each building carries its status from /api/status", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00" });
  await t.flush();
  const d = t.last();
  assert.equal(d.buildings[0].status.status, "alert");
  assert.equal(d.buildings[0].status.reasons[0].message, "too hot");
  assert.deepEqual(d.status.summary, { alert: 1, watch: 0, ok: 0, no_data: 0 });
  assert.equal(d.status.error, null);
});

test("a status failure is reported, the rest still works", async () => {
  const t = setup({ position: "2022-11-08T09:00:00+01:00", fail: { "/api/status": "forecast down" } });
  await t.flush();
  const d = t.last();
  assert.equal(d.buildings[0].status, null);
  assert.equal(d.status.error, "forecast down");
  assert.equal(d.buildings[0].heat_kw, 2);
});
