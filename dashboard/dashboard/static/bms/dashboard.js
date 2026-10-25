(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------
  var themeBtn = document.getElementById("themeToggle");
  function applyTheme(mode) {
    document.documentElement.setAttribute("data-theme", mode === "dark" ? "dark" : "light");
    var radios = document.querySelectorAll('input[name="appearance"]');
    radios.forEach(function (r) { r.checked = r.value === (mode === "dark" ? "dark" : "light"); });
  }
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  var savedTheme = null;
  try { savedTheme = localStorage.getItem("hd-theme"); } catch (e) {}
  applyTheme(savedTheme === "dark" ? "dark" : "light");

  function setTheme(mode) {
    applyTheme(mode);
    try { localStorage.setItem("hd-theme", mode); } catch (e) {}
    renderAll();
  }
  themeBtn.addEventListener("click", function () {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  });
  document.querySelectorAll('input[name="appearance"]').forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) setTheme(r.value); });
  });

  // ---------------------------------------------------------------------
  // Units (°C / °F)
  // ---------------------------------------------------------------------
  var unit = "c";
  try { unit = localStorage.getItem("hd-unit") || "c"; } catch (e) {}
  document.querySelectorAll('input[name="unit"]').forEach(function (r) {
    r.checked = r.value === unit;
    r.addEventListener("change", function () {
      if (!r.checked) return;
      unit = r.value;
      try { localStorage.setItem("hd-unit", unit); } catch (e) {}
      renderAll();
    });
  });
  function toUnit(c) { return unit === "f" ? (c * 9) / 5 + 32 : c; }
  function unitLabel() { return unit === "f" ? "°F" : "°C"; }
  function fmtTemp(c, decimals) {
    var d = decimals === undefined ? 1 : decimals;
    return toUnit(c).toFixed(d) + unitLabel();
  }

  // ---------------------------------------------------------------------
  // Nav / section switching
  // ---------------------------------------------------------------------
  var sectionTitles = { weekly: "Smart heating", control: "Control panel", settings: "Settings", about: "About" };
  document.getElementById("mainNav").addEventListener("click", function (e) {
    var btn = e.target.closest(".nav-item");
    if (!btn) return;
    var section = btn.getAttribute("data-section");
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.setAttribute("aria-current", b === btn ? "true" : "false");
    });
    document.querySelectorAll(".view").forEach(function (v) { v.hidden = true; });
    document.getElementById("view-" + section).hidden = false;
    document.getElementById("pageTitle").textContent = sectionTitles[section];
    if (section === "weekly" && DATA) { renderWeekly(); renderWeatherFx(); }
    closeSidebar();
  });
  document.querySelector('.nav-item[data-section="control"]').setAttribute("aria-current", "true");

  // Mobile sidebar toggle
  var sidebarEl = document.getElementById("sidebar");
  var backdropEl = document.getElementById("sidebarBackdrop");
  function openSidebar() { sidebarEl.classList.add("open"); backdropEl.classList.add("open"); }
  function closeSidebar() { sidebarEl.classList.remove("open"); backdropEl.classList.remove("open"); }
  document.getElementById("menuToggle").addEventListener("click", openSidebar);
  backdropEl.addEventListener("click", closeSidebar);

  // ---------------------------------------------------------------------
  // State & data load
  // ---------------------------------------------------------------------
  var DATA = null;
  var rangeDays = 3;
  var currentView = "charts";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Static text tables for the About page: benchmarks, model parameters, open items.
  var STATIC = {};
  fetch("data/about.json").then(function (r) { return r.json(); }).then(function (json) {
    STATIC = json;
    if (DATA) { DATA.benchmarks = STATIC.benchmarks; DATA.model_parameters = STATIC.model_parameters; DATA.open_items = STATIC.open_items; renderAll(); }
  }).catch(function () {});

  var renderQueued = false;
  function onSourceData(d) {
    d.benchmarks = STATIC.benchmarks; d.model_parameters = STATIC.model_parameters; d.open_items = STATIC.open_items;
    DATA = d;
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(function () { renderQueued = false; renderAll(); });
  }
  BmsSource.start({
    onData: onSourceData,
    onStatus: function (s) {
      var el = document.getElementById("subtitle");
      if (s.error) el.textContent = s.error;
      else if (typeof s.twin === "string") document.getElementById("scenarioScope").dataset.busy = s.twin;
    }
  });
  function setLiveWeather(c) {
    var text = typeof c === "number" ? fmtTemp(c, 0) : "—";
    document.getElementById("weatherVal").textContent = text;
    var el = document.getElementById("controlOutdoor");
    if (el) el.textContent = text;
  }

  function fmtDate(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  function fmtDateTime(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) +
      ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Filters (weekly view)
  // ---------------------------------------------------------------------
  document.getElementById("rangeSeg").addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    rangeDays = parseInt(btn.getAttribute("data-days"), 10);
    BmsSource.select({ days: rangeDays });
    Array.prototype.forEach.call(this.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b === btn ? "true" : "false");
    });
    renderWeekly();
  });

  document.getElementById("viewSeg").addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    currentView = btn.getAttribute("data-view");
    Array.prototype.forEach.call(this.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b === btn ? "true" : "false");
    });
    document.getElementById("chartsView").style.display = currentView === "charts" ? "" : "none";
    document.getElementById("tableView").style.display = currentView === "table" ? "" : "none";
  });

  // ---------------------------------------------------------------------
  // Render orchestration
  // ---------------------------------------------------------------------
  function getSlice() {
    return DATA.timeseries;                           // already the last N completed days
  }

  function renderAll() {
    if (!DATA) return;
    renderSubtitle();
    renderWeatherChip();
    renderWeatherFx();
    renderWeekly();
    renderBuildings();
    renderBenchmarks();
    renderParamTable();
    renderForecast();
  }

  // ---------------------------------------------------------------------
  // Heat-usage forecast: the AI model's prediction for every building is shown as columns of the building
  // table (renderBuildings); this writes the line under the table.
  // ---------------------------------------------------------------------
  function renderForecast() {
    var f = DATA.forecast;
    var el = document.getElementById("forecastFeatures");
    if (!el) return;
    var failed = DATA.buildings.filter(function (b) { return b.forecast_error; })[0];
    if (!f) { el.textContent = "Forecasts appear once the replay has started."; return; }
    var m = f.model;
    el.textContent = (m ? "Forecast model " + m.version + ", trained on data before " + m.train_end.slice(0, 10) + ". " : "") +
      "Each forecast is the heat use of that one hour, predicted at " + fmtDateTime(f.origin) + ". " + (f.note || "") +
      (failed ? " No forecast for " + failed.name + ": " + failed.forecast_error : "");
  }

  // ---------------------------------------------------------------------
  // Settings — validation benchmarks + model parameters (from the
  // classroom-twin parameter research, data/params_research.md).
  // Static per load: reuses the .kpi tile and .data-table markup already
  // styled for the Smart heating page, so nothing new to theme.
  // ---------------------------------------------------------------------
  function renderBenchmarks() {
    var el = document.getElementById("benchmarkRow");
    if (!el || !DATA.benchmarks) return;
    el.innerHTML = DATA.benchmarks.map(function (b) {
      return '<div class="kpi">' +
        '<div class="label">' + escapeHtml(b.label) + '</div>' +
        '<div class="value" style="font-size:19px;">' + escapeHtml(b.value) + '</div>' +
        '<div class="sub">' + escapeHtml(b.source) + '</div>' +
        '</div>';
    }).join("");
  }

  function renderParamTable() {
    var tbody = document.querySelector("#paramTable tbody");
    if (!tbody || !DATA.model_parameters) return;
    tbody.innerHTML = DATA.model_parameters.map(function (p) {
      return '<tr>' +
        '<td><span class="b-type-tag">' + escapeHtml(p.group) + '</span></td>' +
        '<td>' + escapeHtml(p.parameter) + '</td>' +
        '<td>' + escapeHtml(p.value) + '</td>' +
        '<td><span class="confidence-pill ' + escapeHtml(p.confidence) + '">' + escapeHtml(p.confidence) + '</span></td>' +
        '<td>' + escapeHtml(p.source) + '</td>' +
        '</tr>';
    }).join("");

    var hintEl = document.getElementById("paramOpenItems");
    if (hintEl && DATA.open_items && DATA.open_items.length) {
      hintEl.innerHTML = "<strong>Open items:</strong> " + DATA.open_items.map(escapeHtml).join(" &middot; ");
    }
  }

  function renderSubtitle() {
    var t = DATA.twin, c = DATA.clock;
    var el = document.getElementById("subtitle");
    if (t) el.textContent = t.days + " completed day(s) · " + fmtDate(t.start + "T00:00") + " – " + fmtDate(DATA.timeseries[DATA.timeseries.length - 1].timestamp) +
      " · replay at " + fmtDateTime(c.position);
    else if (DATA.twin_error) el.textContent = "Simulation unavailable: " + DATA.twin_error;
    else el.textContent = c && c.position ? "Waiting for one completed day of replay…" : "Replay not started. Press Play in the playback console.";
    var side = document.getElementById("sidebarStatus");
    if (side) side.textContent = !c || !c.started ? "Replay not started" : c.finished ? "Replay finished" : c.playing ? "Replay running" : "Replay paused";
    var scope = document.getElementById("scenarioScope");
    if (scope) scope.textContent = DATA.meta.scenario_scope || "";
  }

  function renderWeatherChip() {
    setLiveWeather(DATA.outdoor_c);
  }

  // Decorative weather effect behind the Smart heating page, based on
  // today's outdoor reading: <=0C snow, 0-8C rain, warmer is sunny. There's
  // no precipitation field in the data, so this is a temperature-based
  // stand-in rather than a real forecast condition.
  function renderWeatherFx() {
    var fx = document.getElementById("weatherFx");
    if (!fx) return;
    var temp = DATA.outdoor_c;
    if (typeof temp !== "number") { fx.innerHTML = ""; return; }
    var kind = temp <= 0 ? "snow" : (temp <= 8 ? "rain" : "sunny");
    fx.innerHTML = "";

    function rand(min, max) { return min + Math.random() * (max - min); }

    if (kind === "snow") {
      for (var i = 0; i < 44; i++) {
        var flake = document.createElement("div");
        flake.className = "flake";
        var size = rand(3, 7);
        flake.style.left = rand(0, 100) + "%";
        flake.style.width = size + "px";
        flake.style.height = size + "px";
        flake.style.opacity = rand(0.35, 0.9).toFixed(2);
        var fall = rand(7, 14);
        var sway = rand(3, 6);
        flake.style.animationDuration = fall + "s, " + sway + "s";
        flake.style.animationDelay = "-" + rand(0, fall).toFixed(1) + "s, -" + rand(0, sway).toFixed(1) + "s";
        fx.appendChild(flake);
      }
    } else if (kind === "rain") {
      for (var j = 0; j < 60; j++) {
        var drop = document.createElement("div");
        drop.className = "drop";
        drop.style.left = rand(0, 100) + "%";
        drop.style.height = rand(12, 22) + "px";
        drop.style.opacity = rand(0.4, 0.9).toFixed(2);
        var dur = rand(0.45, 0.9);
        drop.style.animationDuration = dur + "s";
        drop.style.animationDelay = "-" + rand(0, dur).toFixed(2) + "s";
        fx.appendChild(drop);
      }
    } else {
      var glow = document.createElement("div");
      glow.className = "sun-glow";
      fx.appendChild(glow);
      for (var k = 0; k < 14; k++) {
        var sp = document.createElement("div");
        sp.className = "sparkle";
        sp.style.left = rand(5, 95) + "%";
        sp.style.top = rand(5, 70) + "%";
        sp.style.animationDelay = "-" + rand(0, 3).toFixed(1) + "s";
        fx.appendChild(sp);
      }
    }
  }

  function renderWeekly() {
    var rows = getSlice();
    if (!rows.length) {                               // nothing simulated yet: leave the cards empty
      ["kpiRow", "tempChartWrap", "powerChartWrap", "cumChartWrap"].forEach(function (id) { document.getElementById(id).innerHTML = ""; });
      document.querySelector("#dataTable tbody").innerHTML = "";
      return;
    }
    renderKpis(rows);
    renderTempChart(rows);
    renderPowerChart(rows);
    renderCumChart(rows);
    renderTable(rows);
  }

  // ---------------------------------------------------------------------
  // KPI tiles (recomputed per selected range)
  // ---------------------------------------------------------------------
  function renderKpis(rows) {
    var baseTotal = 0, optTotal = 0, basePeak = 0, optPeak = 0;
    var baseViol = 0, optViol = 0;
    var lo = DATA.meta.comfort_band_c[0], hi = DATA.meta.comfort_band_c[1];
    rows.forEach(function (r) {
      baseTotal += r.baseline_energy_kwh;
      optTotal += r.optimized_energy_kwh;
      basePeak = Math.max(basePeak, r.baseline_heating_power_kw);
      optPeak = Math.max(optPeak, r.optimized_heating_power_kw);
      if (r.occupied) {
        if (r.baseline_indoor_temp_c < lo || r.baseline_indoor_temp_c > hi) baseViol++;
        if (r.optimized_indoor_temp_c < lo || r.optimized_indoor_temp_c > hi) optViol++;
      }
    });
    var savingsPct = baseTotal > 0 ? (1 - optTotal / baseTotal) * 100 : 0;
    var peakPct = basePeak > 0 ? (1 - optPeak / basePeak) * 100 : 0;

    var tiles = [
      {
        label: "Total energy use",
        value: fmtNum(optTotal) + " kWh",
        sub: "vs " + fmtNum(baseTotal) + " kWh current heating",
        delta: (savingsPct >= 0 ? "↓ " : "↑ ") + Math.abs(savingsPct).toFixed(1) + "% " + (savingsPct >= 0 ? "savings" : "more"),
        good: savingsPct >= 0
      },
      {
        label: "Peak heating demand",
        value: fmtNum(optPeak) + " kW",
        sub: "vs " + fmtNum(basePeak) + " kW current heating",
        delta: (peakPct >= 0 ? "↓ " : "↑ ") + Math.abs(peakPct).toFixed(1) + "% " + (peakPct >= 0 ? "lower peak" : "higher"),
        good: peakPct >= 0
      },
      {
        label: "Comfort violations",
        value: optViol + " hrs",
        sub: "vs " + baseViol + " hrs current heating",
        delta: baseViol - optViol >= 0 ? "↓ " + (baseViol - optViol) + " fewer" : "↑ " + (optViol - baseViol) + " more",
        good: optViol <= baseViol
      },
      {
        label: "Occupied hours in range",
        value: rows.filter(function (r) { return r.occupied; }).length + " hrs",
        sub: rows.length + " hrs total in range",
        delta: null,
        good: true
      }
    ];

    var html = tiles.map(function (t) {
      return '<div class="kpi">' +
        '<div class="label">' + escapeHtml(t.label) + '</div>' +
        '<div class="value">' + t.value + '</div>' +
        (t.delta ? '<div class="delta ' + (t.good ? 'good' : '') + '">' + escapeHtml(t.delta) + '</div>' : '') +
        '<div class="sub">' + escapeHtml(t.sub) + '</div>' +
        '</div>';
    }).join("");
    document.getElementById("kpiRow").innerHTML = html;
  }

  function fmtNum(n) {
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + "K";
    return n.toFixed(0);
  }

  // ---------------------------------------------------------------------
  // Shared SVG chart helpers
  // ---------------------------------------------------------------------
  var MARGIN = { top: 10, right: 16, bottom: 24, left: 40 };

  function niceTicks(min, max, count) {
    var range = max - min || 1;
    var rough = range / count;
    var mag = Math.pow(10, Math.floor(Math.log10(rough)));
    var norm = rough / mag;
    var step;
    if (norm < 1.5) step = 1 * mag;
    else if (norm < 3) step = 2 * mag;
    else if (norm < 7) step = 5 * mag;
    else step = 10 * mag;
    var ticks = [];
    var t = Math.ceil(min / step) * step;
    for (; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
    return ticks;
  }

  function buildLineChart(opts) {
    var wrap = document.getElementById(opts.wrapId);
    wrap.innerHTML = "";
    var width = opts.width || wrap.clientWidth || 1100;
    var height = opts.height || 220;
    var innerW = width - MARGIN.left - MARGIN.right;
    var innerH = height - MARGIN.top - MARGIN.bottom;

    var rows = opts.rows;
    var n = rows.length;
    if (n === 0) return;

    var allVals = [];
    opts.series.forEach(function (s) {
      rows.forEach(function (r) { allVals.push(r[s.key]); });
    });
    var yMin = Math.min.apply(null, allVals);
    var yMax = Math.max.apply(null, allVals);
    if (opts.yMinFloor !== undefined) yMin = Math.min(yMin, opts.yMinFloor);
    if (opts.yMaxCeil !== undefined) yMax = Math.max(yMax, opts.yMaxCeil);
    var pad = (yMax - yMin) * 0.1 || 1;
    yMin -= pad; yMax += pad;

    function x(i) { return MARGIN.left + (innerW * i) / Math.max(1, n - 1); }
    function y(v) { return MARGIN.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH; }

    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("preserveAspectRatio", "none");

    if (opts.occupancyBand) {
      var i = 0;
      while (i < n) {
        if (rows[i].occupied) {
          var start = i;
          while (i < n && rows[i].occupied) i++;
          var rect = document.createElementNS(svgNS, "rect");
          rect.setAttribute("class", "occ-band");
          rect.setAttribute("x", x(start));
          rect.setAttribute("y", MARGIN.top);
          rect.setAttribute("width", Math.max(0, x(i - 1) - x(start)));
          rect.setAttribute("height", innerH);
          svg.appendChild(rect);
        } else { i++; }
      }
    }

    if (opts.comfortBand) {
      var band = document.createElementNS(svgNS, "rect");
      band.setAttribute("class", "comfort-band");
      band.setAttribute("x", MARGIN.left);
      band.setAttribute("y", y(opts.comfortBand[1]));
      band.setAttribute("width", innerW);
      band.setAttribute("height", Math.max(0, y(opts.comfortBand[0]) - y(opts.comfortBand[1])));
      svg.appendChild(band);
    }

    var yTicks = niceTicks(yMin, yMax, 5);
    yTicks.forEach(function (t) {
      var ly = y(t);
      var line = document.createElementNS(svgNS, "line");
      line.setAttribute("class", "grid-line");
      line.setAttribute("x1", MARGIN.left); line.setAttribute("x2", width - MARGIN.right);
      line.setAttribute("y1", ly); line.setAttribute("y2", ly);
      svg.appendChild(line);
      var label = document.createElementNS(svgNS, "text");
      label.setAttribute("class", "axis-text");
      label.setAttribute("x", MARGIN.left - 6);
      label.setAttribute("y", ly + 3);
      label.setAttribute("text-anchor", "end");
      label.textContent = t;
      svg.appendChild(label);
    });

    var dayBoundaries = [];
    var lastDay = null;
    rows.forEach(function (r, i) {
      var d = new Date(r.timestamp);
      var dayKey = d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
      if (dayKey !== lastDay && d.getHours() === 0) {
        lastDay = dayKey;
        dayBoundaries.push({ i: i, d: d });
      } else if (dayKey !== lastDay) {
        lastDay = dayKey;
      }
    });
    var minLabelSpacing = 56;
    var maxLabels = Math.max(1, Math.floor(innerW / minLabelSpacing));
    var labelStride = Math.max(1, Math.ceil(dayBoundaries.length / maxLabels));
    dayBoundaries.forEach(function (b, bi) {
      var lx = x(b.i);
      var vline = document.createElementNS(svgNS, "line");
      vline.setAttribute("x1", lx); vline.setAttribute("x2", lx);
      vline.setAttribute("y1", MARGIN.top); vline.setAttribute("y2", MARGIN.top + innerH);
      vline.setAttribute("stroke", cssVar("--grid"));
      vline.setAttribute("stroke-width", "1");
      svg.appendChild(vline);
      if (bi % labelStride === 0) {
        var tick = document.createElementNS(svgNS, "text");
        tick.setAttribute("class", "axis-text");
        tick.setAttribute("x", lx);
        tick.setAttribute("y", height - 6);
        tick.setAttribute("text-anchor", "start");
        tick.textContent = b.d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
        svg.appendChild(tick);
      }
    });

    opts.series.forEach(function (s) {
      var d = "";
      rows.forEach(function (r, i) {
        var cmd = i === 0 ? "M" : "L";
        d += cmd + x(i).toFixed(2) + "," + y(r[s.key]).toFixed(2) + " ";
      });
      var path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d.trim());
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", cssVar(s.color));
      path.setAttribute("stroke-width", "2");
      if (s.dashed) path.setAttribute("stroke-dasharray", "4 3");
      path.setAttribute("stroke-linejoin", "round");
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("opacity", s.dashed ? "0.8" : "1");
      svg.appendChild(path);
    });

    if (opts.violationKey && opts.comfortBand) {
      rows.forEach(function (r, i) {
        if (!r.occupied) return;
        var v = r[opts.violationKey];
        if (v < opts.comfortBand[0] || v > opts.comfortBand[1]) {
          var dot = document.createElementNS(svgNS, "circle");
          dot.setAttribute("class", "violation-dot");
          dot.setAttribute("cx", x(i));
          dot.setAttribute("cy", y(v));
          dot.setAttribute("r", "2.5");
          dot.setAttribute("opacity", "0.6");
          svg.appendChild(dot);
        }
      });
    }

    var crosshair = document.createElementNS(svgNS, "line");
    crosshair.setAttribute("class", "crosshair");
    crosshair.setAttribute("y1", MARGIN.top);
    crosshair.setAttribute("y2", MARGIN.top + innerH);
    svg.appendChild(crosshair);

    var hoverDots = opts.series.map(function (s) {
      var g = document.createElementNS(svgNS, "g");
      g.setAttribute("class", "hover-dot");
      var c = document.createElementNS(svgNS, "circle");
      c.setAttribute("r", "4");
      c.setAttribute("fill", cssVar(s.color));
      g.appendChild(c);
      svg.appendChild(g);
      return g;
    });

    var hit = document.createElementNS(svgNS, "rect");
    hit.setAttribute("x", MARGIN.left); hit.setAttribute("y", MARGIN.top);
    hit.setAttribute("width", innerW); hit.setAttribute("height", innerH);
    hit.setAttribute("fill", "transparent");
    svg.appendChild(hit);

    wrap.appendChild(svg);

    var tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    wrap.style.position = "relative";
    wrap.appendChild(tooltip);

    function handleMove(evt) {
      var rect = svg.getBoundingClientRect();
      var px = (evt.clientX - rect.left) * (width / rect.width);
      var i = Math.round(((px - MARGIN.left) / innerW) * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      var cx = x(i);
      crosshair.setAttribute("x1", cx); crosshair.setAttribute("x2", cx);
      crosshair.style.opacity = "1";

      var rowsHtml = '<div class="t-time">' + escapeHtml(fmtDateTime(rows[i].timestamp)) + '</div>';
      opts.series.forEach(function (s, si) {
        var val = rows[i][s.key];
        hoverDots[si].setAttribute("transform", "translate(" + cx + "," + y(val) + ")");
        hoverDots[si].style.opacity = "1";
        rowsHtml += '<div class="t-row"><span class="t-key' + (s.dashed ? ' dash' : '') + '"' +
          (s.dashed ? '' : ' style="background:' + cssVar(s.color) + '"') + '></span>' +
          '<span class="t-val">' + val.toFixed(1) + (opts.unit || '') + '</span> ' +
          '<span class="t-name">' + escapeHtml(s.label) + '</span></div>';
      });
      tooltip.innerHTML = rowsHtml;
      tooltip.style.opacity = "1";

      var tw = tooltip.offsetWidth;
      var leftPx = (cx / width) * rect.width;
      var placeLeft = leftPx + 14;
      if (leftPx + tw + 24 > rect.width) placeLeft = leftPx - tw - 14;
      tooltip.style.left = placeLeft + "px";
      tooltip.style.top = "8px";
    }
    function handleLeave() {
      crosshair.style.opacity = "0";
      hoverDots.forEach(function (g) { g.style.opacity = "0"; });
      tooltip.style.opacity = "0";
    }
    hit.addEventListener("pointermove", handleMove);
    hit.addEventListener("pointerleave", handleLeave);
  }

  function renderTempChart(rows) {
    // Convert to the selected display unit for this chart only.
    var dRows = rows.map(function (r) {
      return {
        timestamp: r.timestamp,
        occupied: r.occupied,
        outdoor_temp_c: toUnit(r.outdoor_temp_c),
        baseline_indoor_temp_c: toUnit(r.baseline_indoor_temp_c),
        optimized_indoor_temp_c: toUnit(r.optimized_indoor_temp_c)
      };
    });
    var band = [toUnit(DATA.meta.comfort_band_c[0]), toUnit(DATA.meta.comfort_band_c[1])];
    buildLineChart({
      wrapId: "tempChartWrap",
      rows: dRows,
      height: 240,
      unit: unitLabel(),
      occupancyBand: true,
      comfortBand: band,
      violationKey: "optimized_indoor_temp_c",
      series: [
        { key: "outdoor_temp_c", color: "--series-outdoor", dashed: true, label: "Outdoor" },
        { key: "baseline_indoor_temp_c", color: "--series-baseline", label: "Current indoor" },
        { key: "optimized_indoor_temp_c", color: "--series-optimized", label: "Smart indoor" }
      ]
    });
  }

  function renderPowerChart(rows) {
    buildLineChart({
      wrapId: "powerChartWrap",
      rows: rows,
      height: 200,
      unit: " kW",
      occupancyBand: true,
      yMinFloor: 0,
      series: [
        { key: "baseline_heating_power_kw", color: "--series-baseline", label: "Current heating" },
        { key: "optimized_heating_power_kw", color: "--series-optimized", label: "Smart heating" }
      ]
    });
  }

  function renderCumChart(rows) {
    var cumBase = 0, cumOpt = 0;
    var cumRows = rows.map(function (r) {
      cumBase += r.baseline_energy_kwh;
      cumOpt += r.optimized_energy_kwh;
      return {
        timestamp: r.timestamp,
        occupied: r.occupied,
        cum_baseline: Math.round(cumBase * 10) / 10,
        cum_optimized: Math.round(cumOpt * 10) / 10
      };
    });
    buildLineChart({
      wrapId: "cumChartWrap",
      rows: cumRows,
      height: 200,
      unit: " kWh",
      occupancyBand: false,
      yMinFloor: 0,
      series: [
        { key: "cum_baseline", color: "--series-baseline", label: "Current heating, cumulative" },
        { key: "cum_optimized", color: "--series-optimized", label: "Smart heating, cumulative" }
      ]
    });
  }

  // ---------------------------------------------------------------------
  // Table view
  // ---------------------------------------------------------------------
  function renderTable(rows) {
    var cols = [
      { key: "timestamp", label: "Time", fmt: fmtDateTime, align: "left" },
      { key: "occupied", label: "Occ.", fmt: function (v) { return v ? "●" : "—"; } },
      { key: "outdoor_temp_c", label: "Outdoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "baseline_indoor_temp_c", label: "Current indoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "optimized_indoor_temp_c", label: "Smart indoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "baseline_heating_power_kw", label: "Current kW" },
      { key: "optimized_heating_power_kw", label: "Smart kW" },
      { key: "baseline_energy_kwh", label: "Current kWh" },
      { key: "optimized_energy_kwh", label: "Smart kWh" }
    ];
    var table = document.getElementById("dataTable");
    var thead = table.querySelector("thead");
    var tbody = table.querySelector("tbody");
    thead.innerHTML = "<tr>" + cols.map(function (c) {
      return '<th style="' + (c.align === "left" ? "text-align:left" : "") + '">' + escapeHtml(c.label) + "</th>";
    }).join("") + "</tr>";

    var frag = document.createDocumentFragment();
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      cols.forEach(function (c) {
        var td = document.createElement("td");
        if (c.align === "left") td.style.textAlign = "left";
        var val = r[c.key];
        td.textContent = c.fmt ? c.fmt(val) : (typeof val === "number" ? val.toFixed(1) : val);
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    tbody.innerHTML = "";
    tbody.appendChild(frag);
    document.getElementById("tableSub").textContent = rows.length + " rows";
  }

  // ---------------------------------------------------------------------
  // Control panel — one row per building, from the replayed feed
  // ---------------------------------------------------------------------
  function nf(v, d) {
    return v === null || v === undefined ? "—" : v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function sum(list, key) {
    var total = 0;
    for (var i = 0; i < list.length; i++) { if (list[i][key] === null) return null; total += list[i][key]; }
    return total;
  }

  var SUMMARY_ICONS = {
    buildings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 21V7l8-4 8 4v14"/><path d="M9 21v-6h6v6"/></svg>',
    heat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5-2 1.6-3 3.5-3 5.5a7 7 0 0 0 7 7Z"/></svg>',
    energy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>',
    outdoor: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 14.5V5a2 2 0 1 0-4 0v9.5a4 4 0 1 0 4 0z"/></svg>'
  };

  function renderSummary() {
    var list = DATA.buildings;
    var kw = sum(list, "heat_kw"), kwh = sum(list, "kwh_24h");
    var area = list.reduce(function (a, b) { return a + b.floor_area_m2; }, 0);
    var tiles = [
      { cls: "auto", icon: "buildings", label: "Buildings", value: String(list.length) },
      { cls: "heating", icon: "heat", label: "Heat now", value: kw === null ? "—" : nf(kw, 0) + " kW" },
      { cls: "manual", icon: "energy", label: "Last 24 h", value: kwh === null ? "—" : nf(kwh, 0) + " kWh" },
      { cls: "manual", icon: "energy", label: "Last 24 h per m²", value: kwh === null ? "—" : nf(kwh / area, 2) + " kWh/m²" },
      { cls: "idle", icon: "outdoor", label: "Outdoor", value: typeof DATA.outdoor_c === "number" ? fmtTemp(DATA.outdoor_c, 1) : "—" }
    ];
    document.getElementById("summaryGrid").innerHTML = tiles.map(function (t) {
      return '<div class="summary-tile ' + t.cls + '" style="cursor:default">' +
        '<span class="st-icon">' + SUMMARY_ICONS[t.icon] + '</span>' +
        '<span class="st-label"><span class="dot"></span>' + escapeHtml(t.label) + '</span>' +
        '<span class="st-value" style="font-size:22px">' + escapeHtml(t.value) + '</span></div>';
    }).join("");
  }

  function renderBuildings() {
    renderSummary();
    var container = document.getElementById("buildingList");
    Array.prototype.slice.call(container.querySelectorAll(".b-row:not(.b-head)")).forEach(function (el) { el.remove(); });
    DATA.buildings.forEach(function (b) {
      var row = document.createElement("div");
      row.className = "b-row";
      row.setAttribute("data-id", b.id);
      row.setAttribute("tabindex", "0");
      row.setAttribute("role", "button");
      row.setAttribute("aria-label", "Open details for " + b.name);
      row.innerHTML =
        '<div class="b-id"><span class="b-name"></span><span class="b-code"></span></div>' +
        '<div class="b-type"><span class="b-type-tag"></span></div>' +
        '<div class="b-temp"></div><div class="b-temp"></div><div class="b-temp"></div><div class="b-temp"></div>' +
        '<div class="b-temp"></div><div class="b-temp"></div><div class="b-temp"></div>';
      row.querySelector(".b-name").textContent = b.name;
      row.querySelector(".b-code").textContent = b.code + " · " + b.type;
      row.querySelector(".b-type-tag").textContent = nf(b.floor_area_m2, 0) + " m² · " + b.year_built;
      var cells = row.querySelectorAll(".b-temp");
      cells[0].textContent = b.heat_kw === null ? "—" : nf(b.heat_kw, 1) + " kW";
      cells[1].textContent = b.kwh_24h === null ? "—" : nf(b.kwh_24h, 0) + " kWh";
      cells[2].textContent = b.kwh_m2_24h === null ? "—" : nf(b.kwh_m2_24h, 3);
      cells[3].textContent = b.outdoor_c === null ? "—" : fmtTemp(b.outdoor_c);
      b.forecast_kwh.forEach(function (v, i) { cells[4 + i].textContent = v === null ? "—" : nf(v, 0) + " kWh"; });
      row.addEventListener("click", function () { openDetail(b.id); });
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(b.id); }
      });
      container.appendChild(row);
    });
    if (activeBuildingId) renderDetail();
  }

  // ---------------------------------------------------------------------
  // Building detail drawer
  // ---------------------------------------------------------------------
  var detailDrawer = document.getElementById("detailDrawer");
  var detailBackdrop = document.getElementById("detailBackdrop");
  var activeBuildingId = null;

  function openDetail(id) {
    activeBuildingId = id;
    renderDetail();
    detailDrawer.classList.add("open");
    detailBackdrop.classList.add("open");
    detailDrawer.setAttribute("aria-hidden", "false");
  }
  function closeDetail() {
    detailDrawer.classList.remove("open");
    detailBackdrop.classList.remove("open");
    detailDrawer.setAttribute("aria-hidden", "true");
    activeBuildingId = null;
  }
  document.getElementById("detailClose").addEventListener("click", closeDetail);
  detailBackdrop.addEventListener("click", closeDetail);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && activeBuildingId) closeDetail();
  });

  function findBuilding(id) {
    return (DATA.buildings || []).filter(function (b) { return b.id === id; })[0];
  }

  function renderDetail() {
    var b = findBuilding(activeBuildingId);
    if (!b) return;
    document.getElementById("detailName").textContent = b.name;
    document.getElementById("detailCode").textContent = b.code + " · " + b.type;
    var statusEl = document.getElementById("detailStatus");
    statusEl.className = "detail-status normal";
    statusEl.textContent = DATA.clock && DATA.clock.position ? "REPLAY " + fmtDateTime(DATA.clock.position).toUpperCase() : "REPLAY NOT STARTED";

    var metrics = [
      { label: "HEAT NOW", value: b.heat_kw === null ? "—" : nf(b.heat_kw, 1) + " kW" },
      { label: "LAST 24 H", value: b.kwh_24h === null ? "—" : nf(b.kwh_24h, 0) + " kWh" },
      { label: "KWH / M²", value: b.kwh_m2_24h === null ? "—" : nf(b.kwh_m2_24h, 3) }
    ];
    document.getElementById("detailMetrics").innerHTML = metrics.map(function (m) {
      return '<div class="detail-metric"><div class="dm-label">' + m.label + '</div>' +
        '<div class="dm-value">' + escapeHtml(m.value) + '</div></div>';
    }).join("");

    var facts = [
      ["Floor area", nf(b.floor_area_m2, 0) + " m²"],
      ["Year built", String(b.year_built)],
      ["Outdoor temperature", b.outdoor_c === null ? "—" : fmtTemp(b.outdoor_c)]
    ];
    document.getElementById("detailTabContent").innerHTML =
      '<div class="detail-section"><div class="detail-section-title">HEAT USE — LAST 24 HOURS (kW)</div>' +
      '<div class="energy-graph" id="energyGraphWrap"></div></div>' +
      '<div class="detail-section"><div class="detail-section-title">BUILDING</div>' +
      facts.map(function (f) {
        return '<div class="room-row"><span class="room-name">' + escapeHtml(f[0]) + '</span>' +
          '<span class="room-right"><span class="room-temp">' + escapeHtml(f[1]) + '</span></span></div>';
      }).join("") + '</div>';
    renderEnergySpark(b);
  }

  function renderEnergySpark(b) {
    var wrap = document.getElementById("energyGraphWrap");
    var series = b.series24.heat_kw;
    if (!wrap) return;
    if (series.length < 2) { wrap.innerHTML = '<p class="lighting-stub">Appears once the replay has started.</p>'; return; }
    var width = wrap.clientWidth || 420, height = 90, pad = 6;
    var min = Math.min.apply(null, series.concat([0])), max = Math.max.apply(null, series);
    var range = (max - min) || 1;
    function x(i) { return pad + ((width - pad * 2) * i) / (series.length - 1); }
    function y(v) { return height - pad - ((v - min) / range) * (height - pad * 2); }
    var d = series.map(function (v, i) { return (i === 0 ? "M" : "L") + x(i).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
    var areaD = d + " L" + x(series.length - 1).toFixed(1) + "," + (height - pad) + " L" + x(0).toFixed(1) + "," + (height - pad) + " Z";
    wrap.innerHTML =
      '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">' +
      '<path d="' + areaD + '" fill="#2ea8e0" opacity="0.12" stroke="none"></path>' +
      '<path d="' + d + '" fill="none" stroke="#2ea8e0" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>' +
      '</svg>';
  }

  window.addEventListener("resize", function () {
    if (!document.getElementById("view-weekly").hidden && DATA) renderWeekly();
    if (activeBuildingId && DATA) renderDetail();
  });
})();
