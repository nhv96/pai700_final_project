// Data source for the BMS display: builds the page's data object from our API and keeps it in step with the
// shared replay clock (/api/playback). Nothing here is invented: a value the API does not supply is absent.
//
//   /api/playback(+/events)  the clock: playing, speed, position (the last hour the replay has reached)
//   /api/buildings           the buildings and the window of the frozen data
//   /api/readings            heat and weather of the last 24 hours, never later than the clock
//   /api/twin/compare        simulated classroom, legacy vs combined controller, for the last N COMPLETED days
//   /api/forecast/*          AI heat forecast of every building, made at the clock's hour
//
// Usage: BmsSource.start({ onData, onStatus }); BmsSource.select({ building, days }).
// onData(data) is called after every refresh; data.clock.position is null until the replay has been started.
(function () {
  "use strict";

  var HOUR = 3600;
  var REFRESH_MS = 400;                 // at most ~2 refreshes per second, however fast the replay runs
  var FORECAST_HOURS = [1, 6, 24];
  var TWIN_MAX_DAYS = 7;
  var COMFORT_FALLBACK = [20, 26];

  var onData = function () {};
  var onStatus = function () {};
  var info = null;                      // /api/buildings
  var clock = null;                     // /api/playback
  var readings = {};                    // building id -> [{t, heat_kw, tout}] for the last 24 hours
  var selection = { building: null, days: 3 };
  var twin = { key: null, body: null, loading: null, error: null };
  var forecast = { key: null, byBuilding: {}, note: null, model: null, modelTried: false };
  var refreshing = false, again = false, timer = null;

  // epoch seconds <-> the data's fixed UTC+1 wall clock ("YYYY-MM-DDTHH:MM")
  function dataClock(t) { return new Date((t + HOUR) * 1000).toISOString().slice(0, 16); }
  function epoch(iso) { return Date.parse(iso) / 1000; }

  function getJson(url) {
    return fetch(url).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) throw new Error(body.detail || ("HTTP " + r.status));
        return body;
      });
    });
  }

  // ---------- start-up ----------

  function start(handlers) {
    onData = handlers.onData || onData;
    onStatus = handlers.onStatus || onStatus;
    Promise.all([getJson("/api/buildings"), getJson("/api/playback")]).then(function (res) {
      info = res[0];
      clock = res[1];
      selection.building = info.buildings.length ? info.buildings[0].building_id : null;
      info.buildings.forEach(function (b) { readings[b.building_id] = []; });
      openEvents();
      schedule();
    }).catch(function (e) {
      onStatus({ error: "Cannot reach the replay feed (" + e.message + "). Is it running?" });
    });
  }

  function openEvents() {
    var es = new EventSource("/api/playback/events");   // the browser reconnects by itself
    es.addEventListener("state", function (ev) {
      var prev = clock;
      clock = JSON.parse(ev.data);
      if (prev && prev.position && clock.position && epoch(clock.position) < epoch(prev.position)) {   // restarted: forget the old run
        Object.keys(readings).forEach(function (k) { readings[k] = []; });
        forecast.key = null; forecast.byBuilding = {};
        twin.key = null; twin.body = null; twin.error = null;
      }
      schedule();
    });
  }

  function select(next) {
    if (next.building !== undefined) selection.building = next.building;
    if (next.days !== undefined) selection.days = Math.min(TWIN_MAX_DAYS, Math.max(1, next.days));
    schedule();
  }

  // ---------- refresh loop ----------

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () { timer = null; refresh(); }, REFRESH_MS);
  }

  function refresh() {
    if (refreshing) { again = true; return; }
    refreshing = true;
    var job = clock && clock.position ? Promise.all([loadReadings(), loadForecast()]) : Promise.resolve();
    job.then(function () {
      if (clock && clock.position) loadTwin();          // slow: runs on its own and emits when it is done
      emit();
    }).catch(function (e) {
      onStatus({ error: "Lost the data feed: " + e.message });
    }).then(function () {
      refreshing = false;
      if (again) { again = false; schedule(); }
    });
  }

  function loadReadings() {
    var pos = epoch(clock.position);
    var q = "from=" + dataClock(pos - 23 * HOUR) + "&until=" + dataClock(pos);
    return getJson("/api/readings?" + q).then(function (rows) {
      Object.keys(readings).forEach(function (k) { readings[k] = []; });
      rows.forEach(function (r) {
        if (readings[r.building_id]) readings[r.building_id].push({ t: epoch(r.timestamp), heat_kw: r.HtTot / 1000, tout: r.Tout });
      });
    });
  }

  // The AI forecast of every building, made at the clock's hour. It only used data up to that hour.
  // A building that fails (e.g. less than a week of history yet) gets an error of its own; the others still show.
  function loadForecast() {
    var key = clock.position;
    if (forecast.key === key) return Promise.resolve();
    var at = dataClock(epoch(clock.position));
    var model = forecast.modelTried ? Promise.resolve() : getJson("/api/forecast/model").then(
      function (m) { forecast.model = m; }, function () {}).then(function () { forecast.modelTried = true; });
    return model.then(function () {
      return Promise.all(info.buildings.map(function (b) {
        var q = "from=" + at + "&until=" + at + "&building=" + b.building_id + "&horizons=" + FORECAST_HOURS.join(",");
        return getJson("/api/forecast/series?" + q).then(function (body) {
          forecast.note = body.note;
          forecast.byBuilding[b.building_id] = {
            kwh: FORECAST_HOURS.map(function (h) {
              var p = (body.series[String(h)] || [])[0];
              return p ? p.wh / 1000 : null;
            })
          };
        }, function (e) {
          forecast.byBuilding[b.building_id] = { error: e.message };
        });
      }));
    }).then(function () { forecast.key = key; });
  }

  // ---------- digital twin: the last N completed days before the clock ----------

  function addDays(day, n) { return new Date(Date.parse(day + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10); }

  function twinRequest() {
    var today = dataClock(epoch(clock.position)).slice(0, 10);        // the day the clock is in: not complete yet
    var firstDay = clock.window.first.slice(0, 10);
    var days = Math.min(selection.days, Math.round((Date.parse(today) - Date.parse(firstDay)) / 86400000));
    if (days < 1 || selection.building === null) return null;
    return { start: addDays(today, -days), days: days, building: selection.building };
  }

  function loadTwin() {
    var req = twinRequest();
    if (!req) return;
    var key = req.building + ":" + req.start + ":" + req.days;
    if (twin.key === key || twin.loading === key) return;
    twin.loading = key;
    onStatus({ twin: "Simulating the classroom…" });
    getJson("/api/twin/compare?start=" + req.start + "&days=" + req.days + "&building=" + req.building).then(function (body) {
      twin.body = body; twin.error = null;
    }).catch(function (e) {
      twin.error = e.message;
    }).then(function () {
      twin.key = key; twin.loading = null;
      onStatus({ twin: "" });
      schedule();                                   // the clock may have moved on while this ran
      emit();
    });
  }

  // 10-minute twin series -> hourly rows in the shape the charts expect (baseline = legacy, optimized = combined)
  function twinRows(body) {
    var legacy = body.runs.legacy.series, combined = body.runs.combined.series;
    var per = 6, hours = Math.floor(legacy.time.length / per);
    var mean = function (a, i) { var s = 0; for (var k = 0; k < per; k++) s += a[i * per + k]; return s / per; };
    var kw = function (s, i) {
      var s2 = 0;
      for (var k = 0; k < per; k++) s2 += s.radiator_kW[i * per + k] + s.coil_kW[i * per + k];
      return s2 / per;
    };
    var t0 = Date.parse(body.start + "T00:00:00Z");
    var rows = [];
    for (var h = 0; h < hours; h++) {
      var occupied = false;
      for (var k = 0; k < per; k++) if (legacy.occupants[h * per + k] > 0) occupied = true;
      var bp = kw(legacy, h), op = kw(combined, h);
      rows.push({
        timestamp: new Date(t0 + h * 3600000).toISOString().slice(0, 16),
        outdoor_temp_c: mean(body.weather.t_outdoor_C, h),
        occupied: occupied,
        baseline_indoor_temp_c: mean(legacy.t_air_C, h),
        baseline_heating_power_kw: bp,
        baseline_energy_kwh: bp,                    // mean kW over one hour = kWh
        optimized_indoor_temp_c: mean(combined.t_air_C, h),
        optimized_heating_power_kw: op,
        optimized_energy_kwh: op
      });
    }
    return rows;
  }

  // ---------- the data object ----------

  function buildData() {
    var buildings = info.buildings.map(function (b) {
      var rows = readings[b.building_id] || [];
      var n = rows.length;
      var kwh24 = n >= 24 ? rows.reduce(function (a, r) { return a + r.heat_kw; }, 0) : null;   // one reading = one hour
      return {
        id: String(b.building_id), building_id: b.building_id,
        code: "B" + b.building_id, name: "Building " + b.building_id, type: "School",
        floor_area_m2: b.floor_area, year_built: b.year_of_construction,
        series24: { t: rows.map(function (r) { return r.t; }), heat_kw: rows.map(function (r) { return r.heat_kw; }) },
        heat_kw: n ? rows[n - 1].heat_kw : null,
        kwh_24h: kwh24, kwh_m2_24h: kwh24 === null ? null : kwh24 / b.floor_area,
        outdoor_c: n ? rows[n - 1].tout : null,
        forecast_kwh: (forecast.byBuilding[b.building_id] || {}).kwh || FORECAST_HOURS.map(function () { return null; }),
        forecast_error: (forecast.byBuilding[b.building_id] || {}).error || null
      };
    });
    var sel = buildings.filter(function (b) { return b.building_id === selection.building; })[0];
    var data = {
      meta: {
        period_start: info.window.first, period_end: info.window.last,
        comfort_band_c: (twin.body && twin.body.comfort_band_C) || COMFORT_FALLBACK
      },
      clock: clock,
      selection: { building: selection.building, days: selection.days },
      buildings: buildings,
      outdoor_c: sel ? sel.outdoor_c : null,
      timeseries: [],
      twin: null,
      forecast: forecast.key === null ? null : { hours: FORECAST_HOURS, origin: forecast.key, note: forecast.note, model: forecast.model }
    };
    if (twin.body) {
      data.timeseries = twinRows(twin.body);
      data.twin = {
        building: twin.body.building, start: twin.body.start, days: twin.body.days, note: twin.body.note,
        room_floor_area_m2: twin.body.room_floor_area_m2, setpoint_c: twin.body.setpoint_C,
        summary: { baseline: twin.body.runs.legacy.summary, optimized: twin.body.runs.combined.summary }
      };
      data.meta.scenario_scope = "Simulated " + twin.body.room_floor_area_m2 + " m² classroom on the weather of building " +
        twin.body.building + ", " + twin.body.days + " completed day(s) from " + twin.body.start +
        ". Current heating = the legacy controls; smart heating = forecast-based heating and supply-air control.";
    }
    data.twin_error = twin.error;
    return data;
  }

  function emit() {
    if (info) onData(buildData());
  }

  window.BmsSource = { start: start, select: select };
})();
